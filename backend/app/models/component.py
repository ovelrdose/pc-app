"""ORM-модель комплектующего: общие слоты — колонками, остальные — в JSONB."""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Enum, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.expert.frames import Category, ComponentStatus


class ComponentSource(StrEnum):
    """Откуда пришла позиция каталога."""

    MANUAL = "manual"
    IMPORT = "import"


def pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda cls: [item.value for item in cls])


class ComponentRow(Base):
    """Позиция каталога."""

    __tablename__ = "components"
    __table_args__ = (
        CheckConstraint("price_kop > 0", name="price_positive"),
        Index("ix_components_category_status_price", "category", "status", "price_kop"),
        Index("ix_components_specs_gin", "specs", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    category: Mapped[Category] = mapped_column(pg_enum(Category, "component_category"))
    brand: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(200))
    price_kop: Mapped[int] = mapped_column(BigInteger)
    price_checked_at: Mapped[date | None]
    price_note: Mapped[str | None] = mapped_column(String(200))
    in_stock: Mapped[bool] = mapped_column(server_default=text("true"))
    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    perf: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    source: Mapped[ComponentSource] = mapped_column(pg_enum(ComponentSource, "component_source"))
    status: Mapped[ComponentStatus] = mapped_column(pg_enum(ComponentStatus, "component_status"))
    status_issues: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
