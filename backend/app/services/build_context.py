"""Контекст сохранённой сборки: снимок БЗ, каталог, профиль клиента, план и фильтрация.

Ядро детерминировано (вики §3.7), поэтому профиль клиента не хранится целиком: он заново
выводится из ответов на том же снимке базы знаний, с которым посчитана сборка.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, NotFoundError
from app.expert.configurator.build import Build, BuildItem
from app.expert.configurator.checks import validate_build
from app.expert.configurator.filtering import FilterResult, filter_candidates
from app.expert.configurator.pipeline import EvaluatedBuild, Tier, resolve_constraints
from app.expert.configurator.plan import Constraints, SearchPlan, build_plan
from app.expert.configurator.utility import evaluate_utility
from app.expert.consultation import performance_model
from app.expert.facts import Value, WorkingMemory
from app.expert.frames import Category
from app.expert.inference.forward import run_forward
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.performance import (
    DEFAULT_GAMES,
    FpsPerformanceModel,
    benchmarks,
    estimate_app,
    estimate_game,
)
from app.expert.questionnaire import AnswerError, answers_to_memory
from app.expert.tables import RESOLUTIONS, Preset, Resolution
from app.expert.trace import Trace
from app.expert.waivers import waive
from app.models import BuildItemRow, BuildRow, ConsultationRow
from app.repositories.consultations import ConsultationRepository
from app.schemas.consultations import (
    AppOut,
    BenchmarkOut,
    BuildItemOut,
    FpsOut,
    PerformanceOut,
)
from app.services.snapshot_cache import CatalogData, SnapshotCache

DISCLAIMER = (
    "Оценка на основе референсных тестов: реальный результат зависит от драйверов, "
    "настроек и сцены (±15%)."
)


class InvalidAnswersError(DomainError):
    """Ответы визарда не подходят к анкете."""

    status = 422
    code = "invalid-answers"
    title = "Некорректные ответы"


# --- Ограничения ↔ JSON ---------------------------------------------------------------------


def constraints_to_json(constraints: Constraints) -> dict[str, Any]:
    """Ограничения поиска в JSON для хранения в сборке."""
    return {
        "owned": sorted(constraints.owned),
        "locked": {c.value: sku for c, sku in sorted(constraints.locked.items())},
        "excluded_skus": sorted(constraints.excluded_skus),
        "excluded_brands": sorted(constraints.excluded_brands),
        "share_overrides": {c.value: v for c, v in sorted(constraints.share_overrides.items())},
    }


def constraints_from_json(data: Mapping[str, Any]) -> Constraints:
    """Ограничения поиска из JSON сборки."""
    return Constraints(
        owned=frozenset(data.get("owned", [])),
        locked=MappingProxyType({Category(c): s for c, s in data.get("locked", {}).items()}),
        excluded_skus=frozenset(data.get("excluded_skus", [])),
        excluded_brands=frozenset(data.get("excluded_brands", [])),
        share_overrides=MappingProxyType(
            {Category(c): float(v) for c, v in data.get("share_overrides", {}).items()}
        ),
    )


# --- Профиль и прогноз ----------------------------------------------------------------------


def profile_memory(knowledge: KnowledgeSnapshot, answers: Mapping[str, Any]) -> WorkingMemory:
    """Ответы → факты → прямой вывод (без поиска)."""
    try:
        memory = answers_to_memory(knowledge.questionnaire, answers, knowledge.tables)
    except AnswerError as exc:
        raise InvalidAnswersError(str(exc)) from exc
    run_forward(knowledge.compiled, memory)
    return memory


def jsonable(value: Value | None) -> Any:  # noqa: ANN401 — значение факта в JSON
    """Значение факта для JSON (кортежи → списки)."""
    return list(value) if isinstance(value, tuple) else value


def client_games(memory: WorkingMemory, model: FpsPerformanceModel) -> list[str]:
    """Игры для прогноза: выбранные клиентом или типовой набор главного сценария."""
    chosen = memory.lookup("user.games")
    if chosen is not None and isinstance(chosen.value, tuple) and chosen.value:
        return [str(g) for g in chosen.value]
    return list(DEFAULT_GAMES[model.primary])


def client_resolution(memory: WorkingMemory) -> Resolution:
    """Разрешение клиента или 1080p."""
    fact = memory.lookup("user.resolution")
    return next((r for r in RESOLUTIONS if fact is not None and fact.value == r), "1080p")


def performance_out(
    build: Build, knowledge: KnowledgeSnapshot, memory: WorkingMemory, model: FpsPerformanceModel
) -> PerformanceOut:
    """Прогноз для карточки: игры клиента на его разрешении, его программы, бенчмарки, баланс."""
    games = {g.id: g for g in knowledge.tables.games}
    apps = {a.id: a for a in knowledge.tables.applications}
    resolution = client_resolution(memory)
    fps: list[FpsOut] = []
    for game_id in client_games(memory, model):
        game = games.get(game_id)
        if game is None:
            continue
        for preset in Preset:
            e = estimate_game(build, game, resolution, preset)
            fps.append(
                FpsOut(
                    game=game.id,
                    title=game.title,
                    resolution=resolution,
                    preset=preset.value,
                    fps=e.fps,
                    low=round(e.low, 1),
                    high=round(e.high, 1),
                    limited_by=e.limited_by.value,
                    bottleneck_ratio=round(min(e.bottleneck_ratio, 99.0), 3),
                    vram_ok=e.vram_ok,
                )
            )
    chosen_apps = memory.lookup("user.apps")
    app_ids = (
        [str(a) for a in chosen_apps.value]
        if chosen_apps and isinstance(chosen_apps.value, tuple)
        else []
    )
    app_out = []
    for app_id in app_ids:
        app = apps.get(app_id)
        if app is None:
            continue
        a = estimate_app(build, app)
        app_out.append(
            AppOut(
                app=app.id,
                title=app.title,
                task=app.task,
                minutes=a.minutes,
                reference_minutes=app.ref_minutes,
                basic_ok=a.basic_ok,
                pro_ok=a.pro_ok,
            )
        )
    balance = {
        path.removeprefix("perf."): jsonable(f.value) for path, f in model.perf_facts(build).items()
    }
    return PerformanceOut(
        games=fps,
        apps=app_out,
        benchmarks=[
            BenchmarkOut(name=b.name, value=b.value, estimated=b.estimated)
            for b in benchmarks(build)
        ],
        balance=balance,
        disclaimer=DISCLAIMER,
    )


# --- Контекст сохранённой сборки ------------------------------------------------------------------


@dataclass(slots=True)
class BuildContext:
    """Всё, что нужно для объяснений, гипотез и правок по сохранённой сборке."""

    row: BuildRow
    items: Sequence[BuildItemRow]
    consultation: ConsultationRow
    knowledge: KnowledgeSnapshot
    catalog: CatalogData
    memory: WorkingMemory
    constraints: Constraints
    model: FpsPerformanceModel
    build: Build
    _evaluated: EvaluatedBuild | None = field(default=None, repr=False)
    _plan: tuple[SearchPlan, FilterResult] | None = field(default=None, repr=False)

    @property
    def tier(self) -> Tier:
        """Вариант сборки."""
        return Tier(self.row.tier)

    def evaluated(self) -> EvaluatedBuild:
        """Сборка с пересчитанной полезностью и замечаниями (на текущем каталоге)."""
        if self._evaluated is None:
            plan, _ = self.plan_and_filtering()
            rules = self.knowledge.compiled
            utility = evaluate_utility(self.build, plan, self.model, self.memory, rules, Trace())
            perf = self.model.perf_facts(self.build)
            issues = validate_build(self.build, self.memory, rules, Trace(), perf)
            self._evaluated = EvaluatedBuild(self.build, utility, issues)
        return self._evaluated

    def plan_and_filtering(self) -> tuple[SearchPlan, FilterResult]:
        """План подбора и результат фильтрации для этой консультации."""
        if self._plan is None:
            snapshot = self.catalog.snapshot
            resolved = resolve_constraints(snapshot, self.constraints)
            plan = build_plan(self.memory, resolved)
            filtering = filter_candidates(
                snapshot, plan, self.memory, self.knowledge.compiled, resolved, Trace()
            )
            self._plan = (plan, filtering)
        return self._plan

    def item_out(self, item: BuildItem) -> BuildItemOut:
        """Деталь сборки для ответа (цена — на момент расчёта, если деталь из этой сборки)."""
        stored = {row.category: row for row in self.items}.get(item.category)
        same = stored is not None and self.catalog.ids.get(item.frame.sku) == stored.component_id
        price = stored.price_kop_at_build if stored is not None and same else item.price_kop
        return BuildItemOut(
            category=item.category,
            component_id=self.catalog.ids[item.frame.sku],
            sku=item.frame.sku,
            name=item.frame.name,
            brand=item.frame.brand,
            price_kop=price,
            locked=item.locked,
            owned=item.owned,
        )


async def load_context(
    session: AsyncSession, cache: SnapshotCache, build_id: uuid.UUID
) -> BuildContext:
    """Восстанавливает контекст сборки; `NotFoundError`, если её нет."""
    repo = ConsultationRepository(session)
    row = await repo.build(build_id)
    if row is None:
        raise NotFoundError("Сборка не найдена", build_id=str(build_id))
    consultation = await repo.consultation(row.consultation_id)
    if consultation is None:  # pragma: no cover — внешний ключ не даст
        raise NotFoundError("Консультация не найдена")
    items = await repo.items(build_id)
    _, knowledge = await cache.knowledge(session, row.snapshot_id)
    catalog = await cache.catalog(session)
    memory = profile_memory(knowledge, consultation.answers)
    waive(memory, consultation.waived)
    constraints = constraints_from_json(row.constraints)
    model = performance_model(knowledge, memory)
    build_items = []
    for item in items:
        sku = catalog.skus[item.component_id]
        entry = catalog.snapshot.get(sku)
        if entry is None:  # pragma: no cover — каталог содержит и снятые с продажи товары
            raise NotFoundError(f"товар {sku} исчез из каталога")
        build_items.append(BuildItem(entry.frame, owned=item.owned, locked=item.locked))
    return BuildContext(
        row,
        items,
        consultation,
        knowledge,
        catalog,
        memory,
        constraints,
        model,
        Build.of(build_items),
    )
