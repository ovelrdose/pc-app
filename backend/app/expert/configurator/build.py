"""Сборка (фрейм «Сборка»): выбранные детали, цена и факты `build.*` для правил."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from app.expert.facts import COMPUTED, Fact, frame_facts
from app.expert.frames import CPU, GPU, Category, Component

OTHER_POWER_W = 75
"""Потребление «прочего» (плата, память, накопители, вентиляторы) в оценке мощности."""


CATEGORY_INDEX: Mapping[Category, int] = MappingProxyType(
    {category: index for index, category in enumerate(Category)}
)


@dataclass(frozen=True, slots=True)
class BuildItem:
    """Деталь сборки. Имеющаяся у клиента (`owned`) стоит 0 ₽ и всегда зафиксирована."""

    frame: Component
    owned: bool = False
    locked: bool = False
    facts: Mapping[str, Fact] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        # Факты детали считаются один раз: деталь неизменяема, а в поиске её добавляют
        # в тысячи частичных сборок.
        object.__setattr__(self, "facts", MappingProxyType(_item_facts(self)))

    @property
    def category(self) -> Category:
        """Категория детали."""
        return self.frame.category

    @property
    def price_kop(self) -> int:
        """Цена в расчёте бюджета."""
        return 0 if self.owned else self.frame.price_kop


@dataclass(frozen=True, slots=True)
class Build:
    """Неизменяемая (возможно, частичная) сборка: не больше одной детали на категорию."""

    items: tuple[BuildItem, ...] = ()
    _facts: Mapping[str, Fact] = field(
        default_factory=lambda: MappingProxyType({}), compare=False, repr=False
    )
    skus: tuple[str, ...] = field(default=(), compare=False)
    """Артикулы по порядку категорий (ключ для сравнения сборок)."""

    def with_item(self, item: BuildItem) -> "Build":
        """Новая сборка с добавленной деталью (факты собираются из готовых фактов деталей)."""
        if self.get(item.category) is not None:
            raise ValueError(f"категория {item.category.value} уже есть в сборке")
        items = (*self.items, item)
        ordered = sorted(items, key=lambda i: CATEGORY_INDEX[i.category])
        facts = {**self._facts, **item.facts, **_totals(items)}
        return Build(items, MappingProxyType(facts), tuple(i.frame.sku for i in ordered))

    @classmethod
    def of(cls, items: Iterable[BuildItem]) -> "Build":
        """Сборка из набора деталей."""
        build = cls()
        for item in items:
            build = build.with_item(item)
        return build

    def get(self, category: Category) -> BuildItem | None:
        """Деталь категории или `None`."""
        return next((item for item in self.items if item.category is category), None)

    def frame(self, category: Category) -> Component | None:
        """Фрейм детали категории или `None`."""
        item = self.get(category)
        return item.frame if item else None

    @property
    def categories(self) -> frozenset[Category]:
        """Категории, которые уже есть в сборке."""
        return frozenset(item.category for item in self.items)

    @property
    def price_kop(self) -> int:
        """Цена сборки без имеющихся у клиента деталей."""
        return sum(item.price_kop for item in self.items)

    @property
    def est_power_w(self) -> int:
        """Демон «если нужно»: оценка потребления = TDP + TBP + 75 Вт на прочее."""
        return _estimate_power(self.items)

    @property
    def facts(self) -> Mapping[str, Fact]:
        """Факты `build.<категория>.<слот>` и `build.total.*` для правил."""
        return self._facts


def _estimate_power(items: tuple[BuildItem, ...]) -> int:
    power = OTHER_POWER_W
    for item in items:
        if isinstance(item.frame, CPU):
            power += item.frame.tdp_w
        elif isinstance(item.frame, GPU):
            power += item.frame.tbp_w
    return power


def _totals(items: tuple[BuildItem, ...]) -> dict[str, Fact]:
    values = (
        ("build.total.price_rub", sum(item.price_kop for item in items) // 100),
        ("build.total.power_w", _estimate_power(items)),
        ("build.total.parts", len(items)),
    )
    return {path: Fact(path, value, 1.0, (COMPUTED,)) for path, value in values}


def _item_facts(item: BuildItem) -> dict[str, Fact]:
    prefix = f"build.{item.category.value}"
    facts = frame_facts(prefix, item.frame)
    for name, value in (("owned", item.owned), ("locked", item.locked)):
        path = f"{prefix}.{name}"
        facts[path] = Fact(path, value, 1.0, (COMPUTED,))
    return facts
