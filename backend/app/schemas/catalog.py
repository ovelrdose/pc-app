"""DTO публичного каталога и схем фреймов."""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.expert.frames import Category, ComponentStatus
from app.models.component import ComponentSource


class ComponentOut(BaseModel):
    """Позиция каталога. `specs` и `perf` описаны схемой фрейма категории (`GET /frames`)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    category: Category
    brand: str
    model: str
    name: str
    price_kop: int
    price_checked_at: date | None
    price_note: str | None
    in_stock: bool
    source: ComponentSource
    status: ComponentStatus
    status_issues: list[str]
    specs: dict[str, Any]
    perf: dict[str, Any]


class ComponentPage(BaseModel):
    """Страница списка компонентов."""

    items: list[ComponentOut]
    total: int
    limit: int
    offset: int


class FrameOut(BaseModel):
    """Фрейм категории: название и JSON Schema слотов (типы, единицы, ограничения)."""

    category: Category
    title: str
    json_schema: dict[str, Any] = Field(description="JSON Schema фрейма; `unit` — единицы слота")


@dataclass(frozen=True, slots=True)
class ComponentQuery:
    """Фильтры каталога (публичного и админского)."""

    category: Category | None = None
    brand: str | None = None
    search: str | None = None
    in_stock: bool | None = None
    min_price_kop: int | None = None
    max_price_kop: int | None = None
    include_inactive: bool = False
    status: ComponentStatus | None = None
    """Точный статус (админка)."""
    statuses: tuple[ComponentStatus, ...] = ()
    """Несколько статусов сразу (например, «требуют внимания»)."""
    source: ComponentSource | None = None
    """Источник позиции: ручное создание или импорт CSV (админка)."""
    price_checked_before: date | None = None
    """Цена не проверялась раньше этой даты (или не проверялась вовсе)."""
