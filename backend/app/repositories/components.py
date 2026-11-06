"""Доступ к таблице `components` и преобразование фрейм ↔ строка БД."""

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.expert.frames import (
    COLUMN_SLOTS,
    PERF_SLOTS,
    Component,
    ComponentFrame,
    ComponentStatus,
)
from app.models import ComponentRow
from app.schemas.catalog import ComponentQuery

_frame_adapter: TypeAdapter[ComponentFrame] = TypeAdapter(ComponentFrame)


def split_frame(frame: Component) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Делит фрейм на колонки таблицы, `specs` и `perf` (пустые индексы в `perf` не пишутся)."""
    data = frame.model_dump(mode="json")
    columns = {name: getattr(frame, name) for name in COLUMN_SLOTS}
    perf = {name: value for name, value in data.items() if name in PERF_SLOTS and value is not None}
    specs = {
        name: value
        for name, value in data.items()
        if name not in COLUMN_SLOTS and name not in PERF_SLOTS
    }
    return columns, specs, perf


def row_to_frame(row: ComponentRow) -> Component:
    """Собирает фрейм категории из строки БД."""
    data = {**row.specs, **row.perf, **{name: getattr(row, name) for name in COLUMN_SLOTS}}
    frame: Component = _frame_adapter.validate_python(data)
    return frame


class ComponentRepository:
    """Запросы к каталогу комплектующих."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, component_id: uuid.UUID) -> ComponentRow | None:
        """Возвращает компонент по id или `None`."""
        return await self.session.get(ComponentRow, component_id)

    async def all(self) -> Sequence[ComponentRow]:
        """Все компоненты каталога (включая снятые с продажи)."""
        result = await self.session.scalars(select(ComponentRow).order_by(ComponentRow.sku))
        return result.all()

    async def get_many(self, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, ComponentRow]:
        """Компоненты по идентификаторам."""
        result = await self.session.scalars(
            select(ComponentRow).where(ComponentRow.id.in_(list(ids)))
        )
        return {row.id: row for row in result}

    async def get_by_skus(self, skus: Iterable[str]) -> dict[str, ComponentRow]:
        """Возвращает компоненты с указанными артикулами, ключ — артикул."""
        result = await self.session.scalars(
            select(ComponentRow).where(ComponentRow.sku.in_(list(skus)))
        )
        return {row.sku: row for row in result}

    def add(self, row: ComponentRow) -> None:
        """Добавляет новый компонент в сессию."""
        self.session.add(row)

    def _filtered(self, query: ComponentQuery) -> Select[ComponentRow]:
        stmt = select(ComponentRow)
        if not query.include_inactive:
            stmt = stmt.where(ComponentRow.status != ComponentStatus.INACTIVE)
        if query.category is not None:
            stmt = stmt.where(ComponentRow.category == query.category)
        if query.brand:
            stmt = stmt.where(func.lower(ComponentRow.brand) == query.brand.lower())
        if query.search:
            pattern = f"%{query.search}%"
            stmt = stmt.where(
                or_(ComponentRow.name.ilike(pattern), ComponentRow.sku.ilike(pattern))
            )
        if query.in_stock is not None:
            stmt = stmt.where(ComponentRow.in_stock.is_(query.in_stock))
        if query.min_price_kop is not None:
            stmt = stmt.where(ComponentRow.price_kop >= query.min_price_kop)
        if query.max_price_kop is not None:
            stmt = stmt.where(ComponentRow.price_kop <= query.max_price_kop)
        if query.status is not None:
            stmt = stmt.where(ComponentRow.status == query.status)
        if query.statuses:
            stmt = stmt.where(ComponentRow.status.in_(query.statuses))
        if query.source is not None:
            stmt = stmt.where(ComponentRow.source == query.source)
        if query.price_checked_before is not None:
            stmt = stmt.where(
                ComponentRow.price_checked_at.is_(None)
                | (ComponentRow.price_checked_at < query.price_checked_before)
            )
        return stmt

    async def list(
        self, query: ComponentQuery, *, limit: int, offset: int
    ) -> tuple[Sequence[ComponentRow], int]:
        """Возвращает страницу компонентов и общее число подходящих."""
        stmt = self._filtered(query)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(
            stmt.order_by(ComponentRow.category, ComponentRow.price_kop, ComponentRow.sku)
            .limit(limit)
            .offset(offset)
        )
        return rows.all(), total or 0
