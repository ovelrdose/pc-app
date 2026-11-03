"""Конвейер подбора: фильтрация → поиск → оценка → проверка → три варианта (архитектура §7)."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.build import Build
from app.expert.configurator.checks import CompatChecker, Issue, validate_build
from app.expert.configurator.filtering import FilterResult, filter_candidates
from app.expert.configurator.plan import Constraints, SearchPlan, build_plan
from app.expert.configurator.search import (
    Objective,
    SearchContext,
    SearchSettings,
    beam_search,
    upgrade_pass,
)
from app.expert.configurator.utility import (
    IndexPerformanceModel,
    PerformanceModel,
    ScoreIndex,
    Utility,
    evaluate_utility,
)
from app.expert.dsl.compiler import CompiledRuleSet
from app.expert.dsl.expr import format_number
from app.expert.facts import FactView
from app.expert.frames import Category
from app.expert.trace import BuildIssue, Phase, Trace

OPTIMUM_UTILITY_SHARE = 0.9
"""Оптимум выбирается среди сборок с полезностью не ниже 90% от максимальной."""

UNLIMITED_BUDGET_KOP = 10**12


class Tier(StrEnum):
    """Вариант сборки."""

    ECONOMY = "economy"
    OPTIMUM = "optimum"
    MAXIMUM = "maximum"


class ConfigurationError(ValueError):
    """Подбор невозможен из-за входных данных (неизвестная имеющаяся деталь и т.п.)."""


@dataclass(frozen=True, slots=True)
class EvaluatedBuild:
    """Готовая сборка с полезностью и замечаниями проверки (без ошибок)."""

    build: Build
    utility: Utility
    issues: tuple[Issue, ...]

    @property
    def warnings(self) -> tuple[Issue, ...]:
        """Предупреждения."""
        return tuple(i for i in self.issues if i.action == "warn")

    @property
    def suggestions(self) -> tuple[Issue, ...]:
        """Советы."""
        return tuple(i for i in self.issues if i.action == "suggest")


@dataclass(frozen=True, slots=True)
class Infeasibility:
    """Почему не удалось подобрать ни одной сборки."""

    reason: str
    empty_categories: tuple[Category, ...] = ()
    min_budget_rub: int | None = None
    blocking_rules: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConfigResult:
    """Итог подбора."""

    plan: SearchPlan
    tiers: Mapping[Tier, EvaluatedBuild]
    filtering: FilterResult
    infeasibility: Infeasibility | None
    trace: Trace = field(compare=False)

    def distinct(self) -> list[tuple[tuple[Tier, ...], EvaluatedBuild]]:
        """Различающиеся варианты: совпавшие объединяются (вики §4.7)."""
        groups: dict[tuple[str, ...], tuple[list[Tier], EvaluatedBuild]] = {}
        for tier in Tier:
            evaluated = self.tiers.get(tier)
            if evaluated is not None:
                groups.setdefault(evaluated.build.skus, ([], evaluated))[0].append(tier)
        return [(tuple(tiers), evaluated) for tiers, evaluated in groups.values()]


def resolve_constraints(catalog: CatalogSnapshot, constraints: Constraints) -> Constraints:
    """Проверяет фиксации и переносит имеющиеся детали в зафиксированные."""
    locked = dict(constraints.locked)
    for sku in sorted(constraints.owned):
        entry = catalog.get(sku)
        if entry is None:
            raise ConfigurationError(f"имеющаяся деталь {sku} не найдена в каталоге")
        locked[entry.frame.category] = sku
    for category, sku in locked.items():
        entry = catalog.get(sku)
        if entry is None or entry.frame.category is not category:
            raise ConfigurationError(f"зафиксированная деталь {sku} не подходит к {category.value}")
    return replace(constraints, locked=MappingProxyType(locked))


def select_tiers(pool: list[EvaluatedBuild]) -> dict[Tier, EvaluatedBuild]:
    """Эконом — самая дешёвая, максимум — самая полезная, оптимум — «колено» U/цена."""
    if not pool:
        return {}
    economy = min(pool, key=lambda e: (e.build.price_kop, -e.utility.total, e.build.skus))
    maximum = min(pool, key=lambda e: (-e.utility.total, e.build.price_kop, e.build.skus))
    threshold = OPTIMUM_UTILITY_SHARE * maximum.utility.total
    near_best = [e for e in pool if e.utility.total >= threshold] or [maximum]
    optimum = min(
        near_best,
        key=lambda e: (
            -e.utility.total / max(e.build.price_kop, 1),
            -e.utility.total,
            e.build.skus,
        ),
    )
    return {Tier.ECONOMY: economy, Tier.OPTIMUM: optimum, Tier.MAXIMUM: maximum}


def _diagnose(
    context: SearchContext, filtering: FilterResult, rejected_by: Mapping[str, str]
) -> Infeasibility:
    plan = context.plan
    empty = tuple(
        c for c in plan.order if c not in plan.optional and not filtering.candidates.get(c)
    )
    if empty:
        names = ", ".join(c.value for c in empty)
        return Infeasibility(f"не осталось подходящих товаров в категориях: {names}", empty)
    if rejected_by:
        # Сборки в бюджете нашлись, но все отброшены ошибками проверки — дело не в бюджете.
        details = "; ".join(f"{message} ({code})" for code, message in sorted(rejected_by.items()))
        return Infeasibility(
            f"все найденные сборки не прошли проверку: {details}",
            blocking_rules=tuple(sorted(rejected_by)),
        )
    blocking = tuple(
        code for code, _ in sorted(context.checker.rejections.items(), key=lambda kv: -kv[1])[:3]
    )
    unlimited = replace(context, budget_kop=UNLIMITED_BUDGET_KOP, traced={})
    cheapest = beam_search(unlimited, Objective.ECONOMY)
    if cheapest:
        price_rub = -(-min(b.price_kop for b in cheapest) // 100)
        return Infeasibility(
            f"совместимая сборка стоит от {format_number(price_rub)} ₽ — это больше бюджета",
            min_budget_rub=price_rub,
            blocking_rules=blocking,
        )
    return Infeasibility("не нашлось ни одного совместимого сочетания", blocking_rules=blocking)


def cheapest_price_kop(
    memory: FactView,
    rule_set: CompiledRuleSet,
    catalog: CatalogSnapshot,
    constraints: Constraints | None = None,
) -> int | None:
    """Цена самой дешёвой совместимой сборки без учёта бюджета (`None` — сборки нет).

    Быстрый расчёт для разбора невыполнимых требований: только фильтрация и проход «дешевле».
    """
    trace = Trace()
    resolved = resolve_constraints(catalog, constraints or Constraints())
    plan = build_plan(memory, resolved)
    filtering = filter_candidates(catalog, plan, memory, rule_set, resolved, trace)
    if any(not filtering.candidates.get(c) for c in plan.order if c not in plan.optional):
        return None
    context = SearchContext(
        plan=plan,
        candidates=filtering.candidates,
        constraints=resolved,
        checker=CompatChecker(rule_set, plan.order, memory, trace),
        model=IndexPerformanceModel(),
        settings=SearchSettings(beam_width=10),
        trace=trace,
        budget_kop=UNLIMITED_BUDGET_KOP,
    )
    builds = beam_search(context, Objective.ECONOMY)
    return min((b.price_kop for b in builds), default=None)


def configure(
    memory: FactView,
    rule_set: CompiledRuleSet,
    catalog: CatalogSnapshot,
    constraints: Constraints | None = None,
    *,
    model: PerformanceModel | None = None,
    settings: SearchSettings | None = None,
    trace: Trace | None = None,
) -> ConfigResult:
    """Подбирает три варианта сборки по фактам профилирования (этапы 2–5 конвейера)."""
    trace = trace if trace is not None else Trace()
    constraints = resolve_constraints(catalog, constraints or Constraints())
    plan = build_plan(memory, constraints)
    filtering = filter_candidates(catalog, plan, memory, rule_set, constraints, trace)
    perf_model = model or IndexPerformanceModel()
    context = SearchContext(
        plan=plan,
        candidates=filtering.candidates,
        constraints=constraints,
        checker=CompatChecker(rule_set, plan.order, memory, trace),
        scores=ScoreIndex(rule_set, plan.order, memory, perf_model),
        model=perf_model,
        settings=settings or SearchSettings(),
        trace=trace,
        budget_kop=plan.budget_kop,
    )

    def full_utility(build: Build) -> Utility:
        return evaluate_utility(build, plan, context.model, memory, rule_set, trace)

    found: dict[tuple[str, ...], Build] = {}
    for objective in Objective:
        for rank, build in enumerate(beam_search(context, objective)):
            found.setdefault(build.skus, build)
            if objective is Objective.PERFORMANCE and rank < context.settings.upgrade_top:
                upgraded = upgrade_pass(context, build, lambda b: full_utility(b).total)
                found.setdefault(upgraded.skus, upgraded)

    pool: list[EvaluatedBuild] = []
    rejected_by: dict[str, str] = {}
    for skus in sorted(found):
        build = found[skus]
        issues = validate_build(build, memory, rule_set, trace, context.model.perf_facts(build))
        errors = [issue for issue in issues if issue.action == "error"]
        if errors:
            for error in errors:
                rejected_by.setdefault(error.rule_code, error.message)
                trace.add(
                    BuildIssue(Phase.VALIDATION, skus, error.rule_code, "error", error.message)
                )
            continue
        pool.append(EvaluatedBuild(build, full_utility(build), issues))

    tiers = select_tiers(pool)
    for tier, evaluated in tiers.items():
        for issue in evaluated.issues:
            trace.add(
                BuildIssue(
                    Phase.VALIDATION,
                    evaluated.build.skus,
                    issue.rule_code,
                    issue.action,
                    f"[{tier.value}] {issue.message}",
                )
            )
        for preference in evaluated.utility.preferences:
            trace.add(
                BuildIssue(
                    Phase.SCORING,
                    evaluated.build.skus,
                    preference.rule_code,
                    "prefer",
                    f"[{tier.value}] {preference.message}",
                    preference.delta,
                )
            )
    infeasibility = None if tiers else _diagnose(context, filtering, rejected_by)
    return ConfigResult(plan, MappingProxyType(tiers), filtering, infeasibility, trace)
