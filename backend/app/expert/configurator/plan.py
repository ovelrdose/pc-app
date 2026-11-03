"""План подбора: бюджет, доли, порядок и состав категорий из фактов профилирования.

Конфигуратор не содержит знаний о клиентах: всё, что зависит от клиента, он читает из фактов,
выведенных правилами (архитектура §7, ADR 0003):

| Факт | Смысл | Если нет |
|---|---|---|
| `user.budget` | бюджет, ₽ | ошибка |
| `budget.share.<категория>` | доля бюджета | `DEFAULT_SHARES` |
| `budget.first_category` | категория, которую подбирать первой | `DEFAULT_ORDER` |
| `req.need.<категория>` | нужна ли категория | `DEFAULT_NEEDED` |
| — | необязательные категории | `OPTIONAL_WITH` |
| `profile.weight.<сценарий>` | вес сценария 0…1 | офис = 1 |
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from app.expert.certainty import is_established
from app.expert.facts import FactView
from app.expert.frames import Category

MANDATORY_CF = 0.5
"""Требования `req.*` с таким CF и выше обязательны (фильтруют), ниже — желательны (баллы)."""


class Scenario(StrEnum):
    """Сценарии использования (архитектура §1)."""

    OFFICE = "office"
    ESPORTS = "esports"
    AAA_GAMING = "aaa_gaming"
    RENDER_3D = "render_3d"
    VIDEO_EDITING = "video_editing"
    PHOTO_CAD = "photo_cad"
    PROGRAMMING = "programming"
    STREAMING = "streaming"


DEFAULT_ORDER: tuple[Category, ...] = (
    Category.CPU,
    Category.MOTHERBOARD,
    Category.RAM,
    Category.GPU,
    Category.CPU_COOLER,
    Category.CASE,
    Category.PSU,
    Category.SSD,
    Category.HDD,
    Category.CASE_FAN,
)

DEFAULT_SHARES: Mapping[Category, float] = MappingProxyType(
    {
        Category.GPU: 0.40,
        Category.CPU: 0.18,
        Category.MOTHERBOARD: 0.10,
        Category.RAM: 0.09,
        Category.SSD: 0.07,
        Category.PSU: 0.07,
        Category.CASE: 0.05,
        Category.CPU_COOLER: 0.03,
        Category.HDD: 0.04,
        Category.CASE_FAN: 0.01,
    }
)

DEFAULT_NEEDED: Mapping[Category, bool] = MappingProxyType(
    {category: category not in (Category.HDD, Category.CASE_FAN) for category in Category}
)

OPTIONAL_WITH: Mapping[Category, Category] = MappingProxyType({Category.CASE_FAN: Category.CASE})
"""Необязательная категория → категория, при которой она есть в плане (вики §4.4).

Корпусные вентиляторы подбираются всегда, когда подбирается корпус, но могут не понадобиться:
поиск может обойтись без них. Нужны ли они, решают compat-правила (CMP-024: в корпусе должно
быть хотя бы два вентилятора — своих или докупленных). Доля бюджета у необязательной категории 0.
"""


class PlanError(ValueError):
    """Факты профилирования не позволяют построить план (например, нет бюджета)."""


@dataclass(frozen=True, slots=True)
class Constraints:
    """Ограничения поиска от клиента: имеющиеся, зафиксированные и исключённые детали."""

    owned: frozenset[str] = frozenset()
    locked: Mapping[Category, str] = field(default_factory=lambda: MappingProxyType({}))
    excluded_skus: frozenset[str] = frozenset()
    excluded_brands: frozenset[str] = frozenset()
    share_overrides: Mapping[Category, float] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class SearchPlan:
    """Что и в каком порядке подбирать, сколько можно потратить."""

    budget_kop: int
    order: tuple[Category, ...]
    shares: Mapping[Category, float]
    weights: Mapping[Scenario, float]
    optional: frozenset[Category] = frozenset()

    def target_kop(self, category: Category) -> int:
        """Сколько бюджета выделено на категорию."""
        return round(self.budget_kop * self.shares.get(category, 0.0))


def _number(view: FactView, path: str) -> float | None:
    fact = view.lookup(path)
    if fact is None or not is_established(fact.cf):
        return None
    value = fact.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PlanError(f"факт {path} должен быть числом, получено «{value}»")
    return float(value)


def _flag(view: FactView, path: str) -> bool | None:
    fact = view.lookup(path)
    if fact is None or not is_established(fact.cf):
        return None
    if not isinstance(fact.value, bool):
        raise PlanError(f"факт {path} должен быть да/нет, получено «{fact.value}»")
    return fact.value


def build_plan(view: FactView, constraints: Constraints) -> SearchPlan:
    """Строит план подбора из фактов профилирования и ограничений клиента."""
    budget = _number(view, "user.budget")
    if budget is None or budget <= 0:
        raise PlanError("не задан бюджет (user.budget)")

    needed: set[Category] = set(constraints.locked)
    for category in DEFAULT_ORDER:
        flag = _flag(view, f"req.need.{category.value}")
        if flag if flag is not None else DEFAULT_NEEDED[category]:
            needed.add(category)
    optional = frozenset(
        category
        for category, host in OPTIONAL_WITH.items()
        if category not in needed and host in needed
    )
    needed |= optional

    first = view.lookup("budget.first_category")
    order = [c for c in DEFAULT_ORDER if c in needed]
    if first is not None and is_established(first.cf):
        try:
            category = Category(str(first.value))
        except ValueError as exc:
            raise PlanError(
                f"budget.first_category: неизвестная категория «{first.value}»"
            ) from exc
        if category in order:
            order.remove(category)
            order.insert(0, category)

    raw_shares: dict[Category, float] = {}
    for category in order:
        if category in optional:
            continue
        share = constraints.share_overrides.get(category)
        if share is None:
            share = _number(view, f"budget.share.{category.value}")
        raw_shares[category] = max(share if share is not None else DEFAULT_SHARES[category], 0.0)
    total = sum(raw_shares.values()) or 1.0
    shares = {category: share / total for category, share in raw_shares.items()}

    weights: dict[Scenario, float] = {}
    for scenario in Scenario:
        weight = _number(view, f"profile.weight.{scenario.value}")
        if weight is not None and weight > 0:
            weights[scenario] = min(weight, 1.0)
    if not weights:
        weights[Scenario.OFFICE] = 1.0

    return SearchPlan(
        budget_kop=round(budget * 100),
        order=tuple(order),
        shares=MappingProxyType(shares),
        weights=MappingProxyType(weights),
        optional=optional,
    )
