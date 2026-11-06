"""ORM-модели консультаций и сборок."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.expert.frames import Category
from app.models.component import pg_enum


class ConsultationRow(Base):
    """Консультация: ответы клиента и выведенные факты."""

    __tablename__ = "consultations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("guest_sessions.id", ondelete="SET NULL"), index=True
    )
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB)
    owned: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    # требования, от которых клиент отказался ради бюджета (компромиссная сборка, вики §4.10)
    waived: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    derived_facts: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16))
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("kb_snapshots.id"))
    catalog_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BuildRow(Base):
    """Сборка: вариант подбора или результат правки (с родителем)."""

    __tablename__ = "builds"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    consultation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    parent_build_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("builds.id", ondelete="SET NULL")
    )
    tier: Mapped[str] = mapped_column(String(16))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("kb_snapshots.id"))
    catalog_revision: Mapped[int] = mapped_column(Integer)
    total_price_kop: Mapped[int] = mapped_column(BigInteger)
    utility: Mapped[float]
    performance: Mapped[dict[str, Any]] = mapped_column(JSONB)
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB)
    title: Mapped[str | None] = mapped_column(String(200))
    is_saved: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Связи нужны, чтобы при одной фиксации строки вставлялись в порядке внешних ключей.
    consultation: Mapped[ConsultationRow] = relationship(lazy="raise")


class BuildItemRow(Base):
    """Деталь сборки с ценой на момент расчёта."""

    __tablename__ = "build_items"

    build_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("builds.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[Category] = mapped_column(
        pg_enum(Category, "component_category"), primary_key=True
    )
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("components.id"))
    quantity: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    price_kop_at_build: Mapped[int] = mapped_column(BigInteger)
    locked: Mapped[bool] = mapped_column(server_default=text("false"))
    owned: Mapped[bool] = mapped_column(server_default=text("false"))

    build: Mapped[BuildRow] = relationship(lazy="raise")
