"""Сборки: карточка, объяснения, «почему не», замены, гипотезы, правки, сравнение."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, NotFoundError
from app.expert.configurator.modify import Edit, EditError, apply_edit
from app.expert.configurator.pipeline import ConfigurationError
from app.expert.configurator.plan import PlanError
from app.expert.explanation.why_not import WhyNot, WhyNotVerdict, why_not
from app.expert.frames import Category
from app.expert.hypotheses import check_hypothesis
from app.expert.inference.backward import ProofNode
from app.expert.trace import Trace
from app.repositories.consultations import ConsultationRepository
from app.schemas.consultations import (
    AlternativeOut,
    BuildDetail,
    BuildPatch,
    BuildSummary,
    CompareOut,
    CompareRowOut,
    EffectOut,
    ExplanationOut,
    HypothesisOut,
    HypothesisRequest,
    IssueOut,
    ItemChangeOut,
    ModificationOut,
    ModificationRequest,
    NeedInputOut,
    PerformanceOut,
    PreferenceOut,
    ProofNodeOut,
    ReasoningStepOut,
    ReasonOut,
    WhyNotOut,
)
from app.services.build_context import BuildContext, jsonable, load_context
from app.services.consultations import persist_build, summary
from app.services.snapshot_cache import SnapshotCache

MAX_ALTERNATIVES = 10
COMPATIBLE = (WhyNotVerdict.BETTER, WhyNotVerdict.WORSE, WhyNotVerdict.OVER_BUDGET)
"""Вердикты совместимых замен (дорогие тоже показываются — с пометкой о бюджете)."""
FIRING = "rule_fired"
"""Тип записи трассы «сработало правило»."""


class EditRejectedError(DomainError):
    """Правку нельзя применить."""

    status = 422
    code = "edit-rejected"
    title = "Правку нельзя применить"


def proof_out(node: ProofNode) -> ProofNodeOut:
    """Дерево доказательства для ответа."""
    return ProofNodeOut(
        kind=node.kind,
        label=node.label,
        status=node.status,
        cf=node.cf,
        rule_code=node.rule_code,
        detail=node.detail,
        value=jsonable(node.value),
        children=[proof_out(child) for child in node.children],
    )


def why_not_out(answer: WhyNot, component_id: uuid.UUID) -> WhyNotOut:
    """Ответ «почему не» для API."""
    return WhyNotOut(
        component_id=component_id,
        sku=answer.sku,
        verdict=answer.verdict,
        reasons=[ReasonOut(rule_code=r.rule_code, message=r.message) for r in answer.reasons],
        can_replace=answer.can_replace,
        price_delta_kop=answer.price_delta_kop,
        utility_delta_pct=answer.utility_delta_pct,
        fps_delta_pct=answer.fps_delta_pct,
    )


class BuildService:
    """Операции над сохранёнными сборками."""

    def __init__(self, session: AsyncSession, cache: SnapshotCache) -> None:
        self.session = session
        self.cache = cache
        self.repo = ConsultationRepository(session)

    async def _context(self, build_id: uuid.UUID) -> BuildContext:
        return await load_context(self.session, self.cache, build_id)

    def _detail(self, ctx: BuildContext) -> BuildDetail:
        base = summary(ctx.row, ctx.items, ctx.catalog)
        warnings = ctx.row.warnings
        return BuildDetail(
            **base.model_dump(),
            consultation_id=ctx.row.consultation_id,
            kb_version=ctx.knowledge.version,
            catalog_revision=ctx.row.catalog_revision,
            performance=PerformanceOut.model_validate(ctx.row.performance),
            issues=[IssueOut.model_validate(w) for w in warnings if w["action"] != "prefer"],
            preferences=[
                PreferenceOut(rule_code=w["rule_code"], delta=w["delta"], message=w["message"])
                for w in warnings
                if w["action"] == "prefer"
            ],
        )

    async def detail(self, build_id: uuid.UUID) -> BuildDetail:
        """Карточка сборки: состав, цены на момент расчёта, прогноз, замечания."""
        return self._detail(await self._context(build_id))

    async def patch(self, build_id: uuid.UUID, data: BuildPatch) -> BuildDetail:
        """Сохранить или переименовать сборку."""
        ctx = await self._context(build_id)
        if data.title is not None:
            ctx.row.title = data.title.strip() or None
        if data.is_saved is not None:
            ctx.row.is_saved = data.is_saved
        await self.session.flush()
        return self._detail(ctx)

    async def explanation(self, build_id: uuid.UUID) -> ExplanationOut:
        """Рассуждение профилирования, вклад сценариев в полезность, баллы и замечания."""
        ctx = await self._context(build_id)
        steps = []
        for entry in ctx.row.trace:
            if entry.get("type") != FIRING:
                continue
            steps.append(
                ReasoningStepOut(
                    step=entry["step"],
                    rule_code=entry["rule_code"],
                    rule_name=entry["rule_name"],
                    explanation=entry["explanation"],
                    rule_cf=entry["rule_cf"],
                    premise_cf=entry["premise_cf"],
                    matched=entry["matched"],
                    effects=[
                        EffectOut(
                            path=e["path"],
                            outcome=e["outcome"],
                            value=e["contributed_value"],
                            cf=e["contributed_cf"],
                        )
                        for e in entry["effects"]
                    ],
                )
            )
        evaluated = ctx.evaluated()
        detail = self._detail(ctx)
        return ExplanationOut(
            reasoning=steps,
            utility=round(evaluated.utility.total, 2),
            scenario_contributions={
                s.value: round(v, 2) for s, v in evaluated.utility.performance.items()
            },
            preferences=detail.preferences,
            issues=detail.issues,
        )

    async def why_not(self, build_id: uuid.UUID, component_id: uuid.UUID) -> WhyNotOut:
        """«Почему не этот товар?»."""
        ctx = await self._context(build_id)
        sku = ctx.catalog.skus.get(component_id)
        if sku is None:
            raise NotFoundError("Товар не найден", component_id=str(component_id))
        plan, filtering = ctx.plan_and_filtering()
        answer = why_not(
            sku,
            ctx.evaluated(),
            plan,
            filtering,
            ctx.catalog.snapshot,
            ctx.memory,
            ctx.knowledge.compiled,
            ctx.model,
        )
        return why_not_out(answer, component_id)

    async def alternatives(self, build_id: uuid.UUID, category: Category) -> list[AlternativeOut]:
        """Совместимые замены детали категории с разницей в цене, полезности и FPS."""
        ctx = await self._context(build_id)
        plan, filtering = ctx.plan_and_filtering()
        evaluated = ctx.evaluated()
        current = ctx.build.get(category)
        result: list[AlternativeOut] = []
        for entry in filtering.candidates.get(category, ()):
            if current is not None and entry.sku == current.frame.sku:
                continue
            answer = why_not(
                entry.sku,
                evaluated,
                plan,
                filtering,
                ctx.catalog.snapshot,
                ctx.memory,
                ctx.knowledge.compiled,
                ctx.model,
            )
            if answer.verdict not in COMPATIBLE:
                continue
            out = why_not_out(answer, ctx.catalog.ids[entry.sku])
            result.append(
                AlternativeOut(
                    **out.model_dump(), name=entry.frame.name, price_kop=entry.frame.price_kop
                )
            )
        within_budget = (WhyNotVerdict.BETTER, WhyNotVerdict.WORSE)
        result.sort(
            key=lambda a: (
                a.verdict not in within_budget,
                -(a.utility_delta_pct or 0.0),
                a.price_kop,
            )
        )
        return result[:MAX_ALTERNATIVES]

    async def hypothesis(self, build_id: uuid.UUID, request: HypothesisRequest) -> HypothesisOut:
        """«Потянет ли?»: обратный вывод по goal-правилам; при нехватке данных — вопросы."""
        ctx = await self._context(build_id)
        checked = check_hypothesis(
            ctx.knowledge,
            ctx.memory,
            ctx.build,
            request.predicate,
            request.args,
            request.bindings,
            ctx.model,
        )
        return HypothesisOut(
            status=checked.root.status,
            tree=proof_out(checked.root),
            questions=[
                NeedInputOut(variable=q.variable, question=q.question, options=list(q.options))
                for q in checked.questions
            ],
        )

    async def modify(self, build_id: uuid.UUID, request: ModificationRequest) -> ModificationOut:
        """Правка: новые ограничения → новый подбор → новая сборка с родителем и разницей."""
        ctx = await self._context(build_id)
        sku = None
        if request.component_id is not None:
            sku = ctx.catalog.skus.get(request.component_id)
            if sku is None:
                raise NotFoundError("Товар не найден", component_id=str(request.component_id))
        edit = Edit(
            kind=request.kind,
            category=request.category,
            sku=sku,
            brand=request.brand,
            to_category=request.to_category,
        )
        try:
            outcome = apply_edit(
                ctx.memory,
                ctx.knowledge.compiled,
                ctx.catalog.snapshot,
                ctx.constraints,
                ctx.build,
                ctx.tier,
                edit,
                model=ctx.model,
            )
        except (EditError, ConfigurationError, PlanError) as exc:
            raise EditRejectedError(str(exc)) from exc
        if outcome.build is None or outcome.diff is None:
            reason = outcome.result.infeasibility.reason if outcome.result.infeasibility else ""
            raise EditRejectedError(f"После правки подобрать сборку не удалось: {reason}")
        trace = Trace()
        row = persist_build(
            self.repo,
            consultation=ctx.consultation,
            evaluated=outcome.build,
            tier=ctx.tier,
            snapshot_id=ctx.row.snapshot_id,
            catalog=ctx.catalog,
            knowledge=ctx.knowledge,
            memory=ctx.memory,
            model=ctx.model,
            constraints=outcome.constraints,
            trace=trace,
            parent_id=ctx.row.id,
        )
        await self.session.flush()
        await self.session.refresh(row)
        new = await self._context(row.id)
        before_items = {i.category: ctx.item_out(i) for i in ctx.build.items}
        after_items = {i.category: new.item_out(i) for i in new.build.items}
        changes = [
            ItemChangeOut(
                category=change.category,
                before=before_items.get(change.category),
                after=after_items.get(change.category),
                delta_kop=change.delta_kop,
            )
            for change in outcome.diff.changes
        ]
        fps = "perf.fps_avg"
        before_fps = ctx.model.perf_facts(ctx.build).get(fps)
        after_fps = new.model.perf_facts(new.build).get(fps)
        return ModificationOut(
            build=self._detail(new),
            changes=changes,
            price_delta_kop=outcome.diff.price_delta_kop,
            fps_avg_before=float(before_fps.value) if before_fps else None,  # type: ignore[arg-type]
            fps_avg_after=float(after_fps.value) if after_fps else None,  # type: ignore[arg-type]
        )

    async def compare(self, build_ids: list[uuid.UUID]) -> CompareOut:
        """Сравнение 2–3 сборок: состав по категориям, цена, FPS, баланс."""
        contexts = [await self._context(build_id) for build_id in build_ids]
        summaries: list[BuildSummary] = [summary(c.row, c.items, c.catalog) for c in contexts]
        categories = [c for c in Category if any(ctx.build.get(c) for ctx in contexts)]
        rows = [
            CompareRowOut(
                category=category,
                items=[
                    next((i for i in s.items if i.category is category), None) for s in summaries
                ],
            )
            for category in categories
        ]
        performances = [PerformanceOut.model_validate(c.row.performance) for c in contexts]
        return CompareOut(
            builds=summaries,
            rows=rows,
            games=[p.games for p in performances],
            balance=[p.balance for p in performances],
        )

    async def pdf_context(self, build_id: uuid.UUID) -> dict[str, Any]:
        """Данные для PDF-спецификации."""
        ctx = await self._context(build_id)
        detail = self._detail(ctx)
        reasoning = [entry["explanation"] for entry in ctx.row.trace if entry.get("type") == FIRING]
        return {"build": detail, "reasoning": reasoning}
