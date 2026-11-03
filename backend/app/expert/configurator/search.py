"""Этап 3: поиск сборок лучом (архитектура §7.2, вики §4.4).

Категории добавляются по порядку плана. Кандидаты берутся из ценового коридора
`доля × бюджет × [0.6; 1.5]` плюс несколько самых дешёвых; если для частичной сборки ни один
не подошёл, пробуются все кандидаты категории (коридор — предпочтение, а не запрет).
После каждой детали проверяются compat-правила, ветки дороже бюджета отсекаются.
На каждом шаге остаётся `beam_width` лучших частичных сборок по цели поиска.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.expert.catalog import CatalogEntry
from app.expert.configurator.build import Build, BuildItem
from app.expert.configurator.checks import CompatChecker
from app.expert.configurator.plan import Constraints, SearchPlan
from app.expert.configurator.utility import PerformanceModel, ScoreIndex, performance_utility
from app.expert.frames import CPU, Category
from app.expert.trace import CombinationRejected, Phase, Trace


class Objective(StrEnum):
    """Цель поиска: какие частичные сборки оставлять в луче."""

    ECONOMY = "economy"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


@dataclass(frozen=True, slots=True)
class SearchSettings:
    """Параметры поиска."""

    beam_width: int = 30
    retry_width_factor: int = 4
    corridor: tuple[float, float] = (0.6, 1.5)
    cheapest_always: int = 3
    traced_rejections_per_rule: int = 3
    max_upgrade_steps: int = 20
    upgrade_top: int = 5


type Scorer = Callable[[Build], float]


@dataclass(slots=True)
class SearchContext:
    """Всё, что нужно поиску: план, кандидаты, проверки, модель полезности."""

    plan: SearchPlan
    candidates: Mapping[Category, tuple[CatalogEntry, ...]]
    constraints: Constraints
    checker: CompatChecker
    model: PerformanceModel
    settings: SearchSettings
    trace: Trace
    budget_kop: int
    scores: ScoreIndex | None = None
    traced: dict[str, int] = field(default_factory=dict)
    items: dict[str, BuildItem] = field(default_factory=dict)
    bonus: dict[tuple[str, ...], float] = field(default_factory=dict)

    def item(self, entry: CatalogEntry) -> BuildItem:
        """Деталь сборки с флагами «имеется» и «зафиксирована» (кэшируется по артикулу)."""
        item = self.items.get(entry.sku)
        if item is None:
            item = BuildItem(
                entry.frame,
                owned=entry.sku in self.constraints.owned,
                locked=self.constraints.locked.get(entry.frame.category) == entry.sku,
            )
            self.items[entry.sku] = item
        return item

    def utility(self, build: Build) -> float:
        """Полезность частичной сборки: производительность + баллы уже применимых score-правил."""
        return performance_utility(build, self.plan, self.model) + self.bonus.get(build.skus, 0.0)

    def min_price(self, category: Category) -> int:
        """Минимальная цена детали категории в расчёте бюджета (необязательная — 0)."""
        if category in self.plan.optional:
            return 0
        prices = [self.item(entry).price_kop for entry in self.candidates.get(category, ())]
        return min(prices, default=0)

    def record(self, build: Build, rule_code: str, message: str) -> None:
        """Пишет отброшенное сочетание в трассу (первые случаи на правило)."""
        count = self.traced.get(rule_code, 0)
        if count < self.settings.traced_rejections_per_rule:
            self.traced[rule_code] = count + 1
            self.trace.add(CombinationRejected(Phase.SEARCH, build.skus, rule_code, message))


def _rank_key(objective: Objective, context: SearchContext) -> Callable[[Build], tuple[float, ...]]:
    def key(build: Build) -> tuple[float, ...]:
        utility = context.utility(build)
        price = build.price_kop
        match objective:
            case Objective.ECONOMY:
                return (price, -utility)
            case Objective.PERFORMANCE:
                return (-utility, price)
            case _:
                ratio = utility / (price / max(context.budget_kop, 1) + 0.25)
                return (-ratio, price)

    return key


def _options(context: SearchContext, category: Category, build: Build) -> list[CatalogEntry | None]:
    entries = context.candidates.get(category, ())
    if category in context.constraints.locked:
        return list(entries)
    target = context.plan.target_kop(category)
    low, high = (target * bound for bound in context.settings.corridor)
    in_corridor = [e for e in entries if low <= e.frame.price_kop <= high]
    cheapest = list(entries[: context.settings.cheapest_always])
    unique = {entry.sku: entry for entry in [*cheapest, *in_corridor]}
    options: list[CatalogEntry | None] = list(unique.values())
    cpu = build.frame(Category.CPU)
    if category is Category.CPU_COOLER and isinstance(cpu, CPU) and cpu.cooler_included:
        options.append(None)  # можно обойтись боксовым кулером
    if category in context.plan.optional:
        options.append(None)  # необязательная категория: нужна ли деталь, решат compat-правила
    return options


def _extend(
    context: SearchContext,
    build: Build,
    category: Category,
    options: Sequence[CatalogEntry | None],
    remaining_min: int,
) -> list[Build]:
    extended: list[Build] = []
    for entry in options:
        new = build if entry is None else build.with_item(context.item(entry))
        if new.price_kop + remaining_min > context.budget_kop:
            continue
        violation = context.checker.on_added(new, category)
        if violation is not None:
            context.record(new, violation.rule_code, violation.message)
            continue
        if context.scores is not None and new is not build:
            parent = context.bonus.get(build.skus, 0.0)
            context.bonus[new.skus] = parent + context.scores.on_added(new, category)
        extended.append(new)
    return extended


def beam_search(context: SearchContext, objective: Objective) -> list[Build]:
    """Возвращает до `beam_width` полных сборок для цели поиска (лучшие первыми).

    Если луч зашёл в тупик (ни одну частичную сборку нельзя продолжить), поиск повторяется
    с лучом в `retry_width_factor` раз шире: лучшие по цели ветки бывают похожи друг на друга
    и упираются в одно ограничение, например все с высокой памятью для компактного корпуса.
    """
    width = context.settings.beam_width
    builds = _beam_pass(context, objective, width)
    if not builds and context.settings.retry_width_factor > 1:
        builds = _beam_pass(context, objective, width * context.settings.retry_width_factor)
    return builds[:width]


def _beam_pass(context: SearchContext, objective: Objective, width: int) -> list[Build]:
    order = context.plan.order
    rank = _rank_key(objective, context)
    min_prices = {category: context.min_price(category) for category in order}
    beam: list[Build] = [Build()]
    for index, category in enumerate(order):
        remaining_min = sum(min_prices[c] for c in order[index + 1 :])
        next_beam: dict[tuple[str, ...], Build] = {}
        for build in beam:
            extended = _extend(
                context, build, category, _options(context, category, build), remaining_min
            )
            if not extended:
                all_entries: list[CatalogEntry | None] = list(context.candidates.get(category, ()))
                if category in context.plan.optional:
                    all_entries.append(None)
                extended = _extend(context, build, category, all_entries, remaining_min)
            for new in extended:
                next_beam.setdefault(new.skus, new)
        beam = sorted(next_beam.values(), key=lambda b: (*rank(b), b.skus))[:width]
        if not beam:
            return []
    return beam


def _replace(build: Build, item: BuildItem) -> Build:
    items = [item if i.category is item.category else i for i in build.items]
    return Build.of(items)


def upgrade_pass(context: SearchContext, build: Build, score: Scorer) -> Build:
    """Тратит остаток бюджета жадно: апгрейд с наибольшим приростом полезности на рубль."""
    current, current_score = build, score(build)
    for _ in range(context.settings.max_upgrade_steps):
        best: tuple[float, Build, float] | None = None
        for item in current.items:
            if item.locked or item.owned:
                continue
            for entry in context.candidates.get(item.category, ()):
                delta_price = entry.frame.price_kop - item.price_kop
                if delta_price <= 0 or current.price_kop + delta_price > context.budget_kop:
                    continue
                candidate = _replace(current, context.item(entry))
                if context.checker.on_replaced(candidate, item.category) is not None:
                    continue
                candidate_score = score(candidate)
                gain = candidate_score - current_score
                if gain <= 1e-9:
                    continue
                ratio = gain / delta_price
                if best is None or ratio > best[0]:
                    best = (ratio, candidate, candidate_score)
        if best is None:
            break
        _, current, current_score = best
    return current
