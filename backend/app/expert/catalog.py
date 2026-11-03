"""Неизменяемый снимок каталога для ядра (архитектура §4.2)."""

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.expert.frames import Category, Component, ComponentStatus


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """Позиция каталога: фрейм и статус."""

    frame: Component
    status: ComponentStatus = ComponentStatus.ACTIVE

    @property
    def sku(self) -> str:
        """Артикул."""
        return self.frame.sku


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """Каталог на момент подбора; ключуется ревизией каталога."""

    revision: int
    entries: tuple[CatalogEntry, ...]
    _by_sku: dict[str, CatalogEntry] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def build(cls, revision: int, entries: Iterable[CatalogEntry]) -> "CatalogSnapshot":
        """Создаёт снимок; позиции упорядочиваются по категории, цене и артикулу."""
        ordered = tuple(
            sorted(entries, key=lambda e: (e.frame.category.value, e.frame.price_kop, e.sku))
        )
        by_sku = {entry.sku: entry for entry in ordered}
        if len(by_sku) != len(ordered):
            raise ValueError("артикулы в снимке каталога повторяются")
        return cls(revision, ordered, by_sku)

    def get(self, sku: str) -> CatalogEntry | None:
        """Позиция по артикулу."""
        return self._by_sku.get(sku)

    def of_category(self, category: Category) -> tuple[CatalogEntry, ...]:
        """Позиции категории (по возрастанию цены)."""
        return tuple(e for e in self.entries if e.frame.category is category)
