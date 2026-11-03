"""Этап 4: полезность сборки `U = Σ w_s · perf_s + Σ prefer` (архитектура §7.3).

`perf_s` даёт модель производительности. До этапа 5 используется `IndexPerformanceModel` —
упрощённая модель на индексах `perf_*` (эталон = 100) с поправками на объём ОЗУ и SSD.
Она скрыта за протоколом `PerformanceModel`, поэтому замена на модель FPS не затронет поиск.
Штрафы за дисбаланс (BAL) — это score-правила с отрицательным весом.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from app.expert.certainty import conclusion, is_established
from app.expert.configurator.build import Build
from app.expert.configurator.checks import trigger_index
from app.expert.configurator.plan import Scenario, SearchPlan
from app.expert.dsl.compiler import CompiledMessageAction, CompiledRuleSet, fact_resolver
from app.expert.dsl.expr import ExprEvalError
from app.expert.dsl.schema import RuleKind
from app.expert.facts import Fact, FactView, OverlayView
from app.expert.frames import CPU, GPU, RAM, SSD, Category
from app.expert.trace import Phase, RuleFailure, Trace

IGPU_RASTER = 12.0
"""Индекс растеризации встроенной графики (эталон RTX 4060 = 100)."""

# Вклад индексов в сценарии: (одноядерный CPU, многоядерный CPU, растеризация, трассировка).
SCENARIO_MIX: Mapping[Scenario, tuple[float, float, float, float]] = MappingProxyType(
    {
        Scenario.OFFICE: (0.6, 0.4, 0.0, 0.0),
        Scenario.PROGRAMMING: (0.5, 0.5, 0.0, 0.0),
        Scenario.ESPORTS: (0.5, 0.0, 0.5, 0.0),
        Scenario.AAA_GAMING: (0.2, 0.0, 0.7, 0.1),
        Scenario.RENDER_3D: (0.0, 0.5, 0.2, 0.3),
        Scenario.VIDEO_EDITING: (0.15, 0.6, 0.25, 0.0),
        Scenario.PHOTO_CAD: (0.5, 0.3, 0.2, 0.0),
        Scenario.STREAMING: (0.2, 0.3, 0.5, 0.0),
    }
)


class PerformanceModel(Protocol):
    """Оценка производительности сборки по сценариям (эталонная сборка ≈ 100)."""

    def scenario_scores(self, build: Build) -> Mapping[Scenario, float]:
        """Производительность в каждом сценарии; для частичной сборки — по имеющимся деталям."""
        ...

    def perf_facts(self, build: Build) -> Mapping[str, Fact]:
        """Факты прогноза `perf.*` для правил (пусто, если модель их не считает)."""
        ...


def build_view(memory: FactView, build: Build, model: PerformanceModel | None) -> OverlayView:
    """Рабочая память + факты сборки + факты прогноза производительности."""
    facts = build.facts if model is None else {**build.facts, **model.perf_facts(build)}
    return OverlayView(memory, facts)


def _ram_factor(build: Build) -> float:
    ram = build.frame(Category.RAM)
    if not isinstance(ram, RAM):
        return 1.0
    factor = (
        0.85
        if ram.capacity_gb <= 8
        else 0.97
        if ram.capacity_gb <= 16
        else 1.02
        if ram.capacity_gb <= 32
        else 1.05
    )
    return factor - (0.05 if ram.modules == 1 else 0.0)


def storage_factor(build: Build) -> float:
    """Поправка на объём SSD (0.96–1.02)."""
    ssd = build.frame(Category.SSD)
    if not isinstance(ssd, SSD):
        return 1.0
    if ssd.capacity_gb < 500:
        return 0.96
    if ssd.capacity_gb < 1000:
        return 0.98
    return 1.0 if ssd.capacity_gb < 2000 else 1.02


class IndexPerformanceModel:
    """Модель полезности на индексах производительности (без прогноза FPS и фактов `perf.*`).

    Используется, когда о клиенте неизвестно ничего, кроме весов сценариев (например, в тестах
    конфигуратора). В консультации её заменяет `performance.FpsPerformanceModel`.
    """

    def perf_facts(self, build: Build) -> Mapping[str, Fact]:
        """Прогноза FPS нет — фактов `perf.*` тоже."""
        return {}

    def scenario_scores(self, build: Build) -> Mapping[Scenario, float]:
        """Взвешенная смесь индексов CPU/GPU с поправками на ОЗУ и SSD."""
        cpu, gpu = build.frame(Category.CPU), build.frame(Category.GPU)
        single = (cpu.perf_single or 0.0) if isinstance(cpu, CPU) else 0.0
        multi = (cpu.perf_multi or 0.0) if isinstance(cpu, CPU) else 0.0
        if isinstance(gpu, GPU):
            raster, rt = gpu.perf_raster or 0.0, gpu.perf_rt or 0.0
        else:
            has_igpu = isinstance(cpu, CPU) and cpu.igpu
            raster, rt = (IGPU_RASTER if has_igpu else 0.0), 0.0
        factor = _ram_factor(build) * storage_factor(build)
        return {
            scenario: (a * single + b * multi + c * raster + d * rt) * factor
            for scenario, (a, b, c, d) in SCENARIO_MIX.items()
        }


@dataclass(frozen=True, slots=True)
class Preference:
    """Вклад score-правила в полезность."""

    rule_code: str
    delta: float
    message: str


@dataclass(frozen=True, slots=True)
class Utility:
    """Полезность и её разбивка: вклад сценариев и баллы правил."""

    total: float
    performance: Mapping[Scenario, float]
    preferences: tuple[Preference, ...] = ()


def performance_utility(build: Build, plan: SearchPlan, model: PerformanceModel) -> float:
    """Полезность только по производительности (для частичных сборок в поиске)."""
    scores = model.scenario_scores(build)
    total_weight = sum(plan.weights.values())
    return sum(w * scores[s] for s, w in plan.weights.items()) / total_weight


def evaluate_utility(
    build: Build,
    plan: SearchPlan,
    model: PerformanceModel,
    memory: FactView,
    rule_set: CompiledRuleSet,
    trace: Trace,
) -> Utility:
    """Полная полезность готовой сборки: производительность + баллы score-правил."""
    scores = model.scenario_scores(build)
    total_weight = sum(plan.weights.values())
    contributions = {s: w * scores[s] / total_weight for s, w in plan.weights.items()}
    view = build_view(memory, build, model)
    preferences: list[Preference] = []
    for rule in rule_set.of_kind(RuleKind.SCORE):
        try:
            match = rule.condition.evaluate(view)
        except ExprEvalError as exc:
            trace.add(RuleFailure(0, Phase.SCORING, rule.code, str(exc)))
            continue
        if match is None or not is_established(match.cf):
            continue
        cf = conclusion(rule.rule.cf, match.cf)
        for action in rule.actions:
            if isinstance(action, CompiledMessageAction) and action.weight is not None:
                text = action.message.render(fact_resolver(view)) if action.message else ""
                preferences.append(
                    Preference(rule.code, action.weight * cf, text or rule.rule.name)
                )
    total = sum(contributions.values()) + sum(p.delta for p in preferences)
    return Utility(total, MappingProxyType(contributions), tuple(preferences))


class ScoreIndex:
    """Score-правила, разложенные по категории-«триггеру»: баллы частичной сборки в поиске.

    Правило начисляет баллы, как только в сборке появились все упомянутые им детали. Так поиск
    видит штрафы за дисбаланс уже на частичных сборках, а не только на готовых.
    """

    def __init__(
        self,
        rule_set: CompiledRuleSet,
        order: Iterable[Category],
        memory: FactView,
        model: PerformanceModel | None = None,
    ) -> None:
        self.memory = memory
        self.model = model
        self.triggers, _ = trigger_index(rule_set.of_kind(RuleKind.SCORE), order)

    def on_added(self, build: Build, category: Category) -> float:
        """Сумма баллов правил, ставших применимыми после добавления детали `category`."""
        rules = self.triggers.get(category, ())
        if not rules:
            return 0.0
        view = build_view(self.memory, build, self.model)
        total = 0.0
        for rule in rules:
            try:
                match = rule.condition.evaluate(view)
            except ExprEvalError:
                continue  # ошибка попадёт в трассу при полной оценке сборки
            if match is None or not is_established(match.cf):
                continue
            cf = conclusion(rule.rule.cf, match.cf)
            total += sum(
                action.weight * cf
                for action in rule.actions
                if isinstance(action, CompiledMessageAction) and action.weight is not None
            )
        return total
