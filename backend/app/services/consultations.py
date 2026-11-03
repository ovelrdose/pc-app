"""Консультации: анкета, ответы клиента, подбор трёх вариантов, разбор невыполнимого запроса."""

import uuid
from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.expert.configurator.build import CATEGORY_INDEX, Build
from app.expert.configurator.pipeline import ConfigurationError, EvaluatedBuild, Tier
from app.expert.configurator.plan import Constraints, PlanError
from app.expert.consultation import consult, performance_model
from app.expert.dsl.schema import GoalCondition, RuleKind
from app.expert.explanation.infeasible import explain_infeasible
from app.expert.facts import WorkingMemory, facts_from_mapping
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.performance import FpsPerformanceModel
from app.expert.questionnaire import AnswerError, QuestionType
from app.expert.trace import Trace
from app.expert.validation import iter_leaves
from app.expert.waivers import WAIVABLE, waiver_title
from app.models import BuildItemRow, BuildRow, ConsultationRow
from app.repositories.consultations import ConsultationRepository
from app.schemas.consultations import (
    BestEffortOut,
    BlockingOut,
    BuildItemOut,
    BuildSummary,
    CompromiseOut,
    ConcessionOut,
    ConsultationCreate,
    ConsultationOut,
    GoalOut,
    InfeasibleBrief,
    InfeasibleOut,
    OptionOut,
    OwnedComponentOut,
    QuestionnaireOut,
    QuestionOut,
    RelaxationOut,
    StepOut,
    WaivedOut,
)
from app.services.build_context import (
    InvalidAnswersError,
    constraints_to_json,
    jsonable,
    performance_out,
    profile_memory,
)
from app.services.snapshot_cache import CatalogData, SnapshotCache

logger = structlog.get_logger(__name__)

PROFILE_PREFIXES = ("profile.", "req.", "budget.first_category")


class ConsultationStateError(ConflictError):
    """Операция не подходит к состоянию консультации."""

    code = "consultation-state"


class ConsultationInputError(DomainError):
    """Подбор невозможен из-за входных данных (неизвестная имеющаяся деталь и т.п.)."""

    status = 422
    code = "invalid-consultation"
    title = "Некорректные данные консультации"


def summary(row: BuildRow, items: Sequence[BuildItemRow], catalog: CatalogData) -> BuildSummary:
    """Краткая карточка сохранённой сборки."""
    out: list[BuildItemOut] = []
    for item in sorted(items, key=lambda i: CATEGORY_INDEX[i.category]):
        entry = catalog.snapshot.get(catalog.skus[item.component_id])
        assert entry is not None  # noqa: S101 — каталог хранит и снятые с продажи товары
        out.append(
            BuildItemOut(
                category=item.category,
                component_id=item.component_id,
                sku=entry.sku,
                name=entry.frame.name,
                brand=entry.frame.brand,
                price_kop=item.price_kop_at_build,
                locked=item.locked,
                owned=item.owned,
            )
        )
    return BuildSummary(
        id=row.id,
        tier=Tier(row.tier),
        parent_build_id=row.parent_build_id,
        total_price_kop=row.total_price_kop,
        utility=round(row.utility, 2),
        items=out,
        title=row.title,
        is_saved=row.is_saved,
        created_at=row.created_at,
    )


def build_items_out(build: Build, catalog: CatalogData) -> list[BuildItemOut]:
    """Детали несохранённой сборки (цены — текущие)."""
    return [
        BuildItemOut(
            category=item.category,
            component_id=catalog.ids[item.frame.sku],
            sku=item.frame.sku,
            name=item.frame.name,
            brand=item.frame.brand,
            price_kop=item.price_kop,
            locked=item.locked,
            owned=item.owned,
        )
        for item in build.items
    ]


def persist_build(
    repo: ConsultationRepository,
    *,
    consultation: ConsultationRow,
    evaluated: EvaluatedBuild,
    tier: Tier,
    snapshot_id: int,
    catalog: CatalogData,
    knowledge: KnowledgeSnapshot,
    memory: WorkingMemory,
    model: FpsPerformanceModel,
    constraints: Constraints,
    trace: Trace,
    parent_id: uuid.UUID | None = None,
) -> BuildRow:
    """Сохраняет сборку с ценами на момент расчёта, прогнозом, трассой и замечаниями."""
    build = evaluated.build
    row = BuildRow(
        id=uuid.uuid4(),
        consultation=consultation,
        parent_build_id=parent_id,
        tier=tier.value,
        snapshot_id=snapshot_id,
        catalog_revision=catalog.revision,
        total_price_kop=build.price_kop,
        utility=evaluated.utility.total,
        performance=performance_out(build, knowledge, memory, model).model_dump(mode="json"),
        trace=trace.to_jsonable(),
        warnings=[
            {
                "rule_code": i.rule_code,
                "action": i.action,
                "message": i.message,
                "category": i.category,
                "target": i.target,
            }
            for i in evaluated.issues
        ]
        + [
            {
                "rule_code": p.rule_code,
                "action": "prefer",
                "message": p.message,
                "delta": round(p.delta, 3),
            }
            for p in evaluated.utility.preferences
        ],
        constraints=constraints_to_json(constraints),
        is_saved=False,
    )
    repo.add(row)
    for item in build.items:
        repo.add(
            BuildItemRow(
                build=row,
                category=item.category,
                component_id=catalog.ids[item.frame.sku],
                price_kop_at_build=item.price_kop,
                locked=item.locked,
                owned=item.owned,
            )
        )
    return row


class ConsultationService:
    """Сценарий клиента: анкета → ответы → три варианта."""

    def __init__(self, session: AsyncSession, cache: SnapshotCache) -> None:
        self.session = session
        self.cache = cache
        self.repo = ConsultationRepository(session)

    async def questionnaire(self) -> QuestionnaireOut:
        """Анкета опубликованной базы знаний с подставленными вариантами игр и программ."""
        _, knowledge = await self.cache.knowledge(self.session)
        sources = {
            "games": [OptionOut(value=g.id, label=g.title) for g in knowledge.tables.games],
            "applications": [
                OptionOut(value=a.id, label=a.title) for a in knowledge.tables.applications
            ],
        }
        steps = []
        for step in knowledge.questionnaire.steps:
            questions = [
                QuestionOut(
                    id=q.id,
                    type=q.type.value,
                    title=q.title,
                    options=sources[q.options_from]
                    if q.options_from
                    else [OptionOut(value=o.value, label=o.label) for o in q.options],
                    allow_unknown=q.allow_unknown or q.type is QuestionType.YESNO,
                    min=q.min,
                    max=q.max,
                    step=q.step,
                    extra_title=q.extra_title,
                )
                for q in step.questions
            ]
            steps.append(StepOut(id=step.id, title=step.title, questions=questions))
        return QuestionnaireOut(kb_version=knowledge.version, steps=steps)

    async def goals(self) -> list[GoalOut]:
        """Гипотезы, которые можно проверить: игры × пресеты, программы × уровни, общие цели."""
        _, knowledge = await self.cache.knowledge(self.session)
        goals: list[GoalOut] = []
        for compiled in knowledge.compiled.of_kind(RuleKind.GOAL):
            rule = compiled.rule
            if rule.goal is None:  # pragma: no cover — схема не пропустит
                continue
            needs = sorted(
                {
                    value[1:]
                    for leaf in iter_leaves(rule.when)
                    if isinstance(leaf, GoalCondition)
                    for value in leaf.goal.args.values()
                    if isinstance(value, str) and value.startswith("$")
                }
            )
            goals.append(
                GoalOut(
                    predicate=rule.goal.predicate,
                    args={k: str(v) for k, v in rule.goal.args.items()},
                    title=rule.name,
                    needs=needs,
                )
            )
        return goals

    async def create(self, data: ConsultationCreate) -> ConsultationOut:
        """Проверяет ответы и сохраняет консультацию (подбор — отдельным запросом)."""
        snapshot_id, knowledge = await self.cache.knowledge(self.session)
        catalog = await self.cache.catalog(self.session)
        profile_memory(knowledge, data.answers)  # проверка ответов
        unknown = [path for path in data.waived_requirements if path not in WAIVABLE]
        if unknown:
            raise ConsultationInputError(
                f"От требований {', '.join(unknown)} отказаться нельзя: "
                f"допустимы {', '.join(WAIVABLE)}"
            )
        owned = []
        for component_id in data.owned_component_ids:
            sku = catalog.skus.get(component_id)
            if sku is None:
                raise ConsultationInputError(f"Деталь {component_id} не найдена в каталоге")
            owned.append(sku)
        row = ConsultationRow(
            id=uuid.uuid4(),
            answers=data.answers,
            owned=owned,
            waived=sorted(set(data.waived_requirements), key=list(WAIVABLE).index),
            status="created",
            snapshot_id=snapshot_id,
        )
        self.repo.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return await self._out(row, knowledge, catalog, [])

    async def run(self, consultation_id: uuid.UUID) -> ConsultationOut:
        """Запускает вывод и подбор; сохраняет по сборке на вариант."""
        row = await self._get(consultation_id)
        if row.status != "created":
            raise ConsultationStateError("Подбор по этой консультации уже выполнен")
        snapshot_id, knowledge = await self.cache.knowledge(self.session, row.snapshot_id)
        catalog = await self.cache.catalog(self.session)
        constraints = Constraints(owned=frozenset(row.owned))
        try:
            result = consult(
                knowledge, catalog.snapshot, row.answers, constraints, waived=row.waived
            )
        except AnswerError as exc:  # pragma: no cover — ответы проверены при создании
            raise InvalidAnswersError(str(exc)) from exc
        except (ConfigurationError, PlanError) as exc:
            raise ConsultationInputError(str(exc)) from exc
        memory = result.memory
        model = performance_model(knowledge, memory)
        row.catalog_revision = catalog.revision
        row.derived_facts = {f.path: jsonable(f.value) for f in memory}
        builds: list[BuildRow] = []
        for tier, evaluated in result.result.tiers.items():
            builds.append(
                persist_build(
                    self.repo,
                    consultation=row,
                    evaluated=evaluated,
                    tier=tier,
                    snapshot_id=snapshot_id,
                    catalog=catalog,
                    knowledge=knowledge,
                    memory=memory,
                    model=model,
                    constraints=constraints,
                    trace=result.trace,
                )
            )
        row.status = "completed" if builds else "infeasible"
        await self.session.flush()
        logger.info("consultation_completed", consultation_id=str(row.id), status=row.status)
        out = await self._out(row, knowledge, catalog, builds)
        if result.result.infeasibility is not None:
            info = result.result.infeasibility
            out.infeasibility = InfeasibleBrief(
                reason=info.reason,
                min_budget_rub=info.min_budget_rub,
                empty_categories=list(info.empty_categories),
            )
        return out

    async def get(self, consultation_id: uuid.UUID) -> ConsultationOut:
        """Консультация и её сборки."""
        row = await self._get(consultation_id)
        _, knowledge = await self.cache.knowledge(self.session, row.snapshot_id)
        catalog = await self.cache.catalog(self.session)
        return await self._out(row, knowledge, catalog, await self.repo.builds_of(row.id))

    async def infeasible(self, consultation_id: uuid.UUID) -> InfeasibleOut:
        """Подробный разбор невыполнимого запроса: что мешает, как ослабить, что можно собрать."""
        row = await self._get(consultation_id)
        _, knowledge = await self.cache.knowledge(self.session, row.snapshot_id)
        catalog = await self.cache.catalog(self.session)
        report = explain_infeasible(
            knowledge,
            catalog.snapshot,
            row.answers,
            Constraints(owned=frozenset(row.owned)),
            waived=row.waived,
        )
        best = report.best_effort
        compromise = report.compromise
        return InfeasibleOut(
            budget_rub=report.budget_rub,
            min_budget_rub=report.min_budget_rub,
            blocking=[
                BlockingOut(
                    fact=b.fact,
                    title=b.title,
                    value=jsonable(b.value),  # type: ignore[arg-type]
                    rules=list(b.rules),
                    min_budget_without_rub=b.min_budget_without_rub,
                )
                for b in report.blocking
            ],
            relaxations=[
                RelaxationOut(
                    title=r.title, answers=dict(r.answers), min_budget_rub=r.min_budget_rub
                )
                for r in report.relaxations
            ],
            compromise=CompromiseOut(
                concessions=[
                    ConcessionOut(title=c.title, answers=dict(c.answers), waived=list(c.waived))
                    for c in compromise.concessions
                ],
                answers=dict(compromise.answers),
                waived=list(compromise.waived),
                total_price_kop=compromise.build.build.price_kop,
                items=build_items_out(compromise.build.build, catalog),
            )
            if compromise is not None
            else None,
            best_effort=BestEffortOut(
                total_price_kop=best.build.price_kop,
                items=build_items_out(best.build, catalog),
                unmet=list(report.unmet),
            )
            if best is not None
            else None,
        )

    async def _get(self, consultation_id: uuid.UUID) -> ConsultationRow:
        row = await self.repo.consultation(consultation_id)
        if row is None:
            raise NotFoundError("Консультация не найдена", consultation_id=str(consultation_id))
        return row

    async def _out(
        self,
        row: ConsultationRow,
        knowledge: KnowledgeSnapshot,
        catalog: CatalogData,
        builds: Sequence[BuildRow],
    ) -> ConsultationOut:
        profile: dict[str, Any] = {
            path: value
            for path, value in row.derived_facts.items()
            if path.startswith(PROFILE_PREFIXES)
        }
        memory = facts_from_mapping(
            {path: value for path, value in row.derived_facts.items() if path.startswith("need.")}
        )
        order = list(Tier)
        ordered = sorted(builds, key=lambda b: (b.created_at, order.index(Tier(b.tier))))
        summaries = [summary(b, await self.repo.items(b.id), catalog) for b in ordered]
        owned = []
        for sku in row.owned:
            entry = catalog.snapshot.get(sku)
            if entry is None:  # pragma: no cover — каталог содержит и снятые с продажи товары
                continue
            owned.append(
                OwnedComponentOut(
                    component_id=catalog.ids[sku],
                    category=entry.frame.category,
                    sku=sku,
                    name=entry.frame.name,
                    brand=entry.frame.brand,
                    price_kop=entry.frame.price_kop,
                )
            )
        return ConsultationOut(
            id=row.id,
            status=row.status,
            answers=row.answers,
            owned=owned,
            waived=[WaivedOut(fact=path, title=waiver_title(path, memory)) for path in row.waived],
            profile=profile,
            kb_version=knowledge.version,
            catalog_revision=row.catalog_revision,
            builds=summaries,
            infeasibility=None,
            created_at=row.created_at,
        )
