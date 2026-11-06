"""ORM-модели базы знаний: рабочая копия правил и справочников, история, опубликованные снимки."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class RuleRow(Base):
    """Рабочая копия правила (черновик до публикации)."""

    __tablename__ = "rules"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    group: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    priority: Mapped[int]
    cf: Mapped[float]
    enabled: Mapped[bool] = mapped_column(server_default=text("true"))
    origin: Mapped[str] = mapped_column(String(16))
    source: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    explain: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_by: Mapped[uuid.UUID | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class RuleRevisionRow(Base):
    """История правки правила."""

    __tablename__ = "rule_revisions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    rule_code: Mapped[str] = mapped_column(ForeignKey("rules.code", ondelete="CASCADE"), index=True)
    # Связь нужна, чтобы при одной фиксации правило записывалось раньше истории.
    rule: Mapped[RuleRow] = relationship(lazy="raise")
    revision: Mapped[int]
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    change_type: Mapped[str] = mapped_column(String(16))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReferenceTableRow(Base):
    """Справочник (sockets, chipsets, form_factors, games, applications) или анкета."""

    __tablename__ = "reference_tables"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class KbSnapshotRow(Base):
    """Опубликованный неизменяемый снимок базы знаний."""

    __tablename__ = "kb_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    tables: Mapped[dict[str, Any]] = mapped_column(JSONB)
    questionnaire: Mapped[dict[str, Any]] = mapped_column(JSONB)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(String(500))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime] = mapped_column(server_default=func.now())
