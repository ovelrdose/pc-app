"""ORM-модель журнала импорта каталога из админки (ADR 0010 п.1)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.component import pg_enum


class CatalogImportStatus(StrEnum):
    """Итог импорта: файл применён или отклонён целиком."""

    COMPLETED = "completed"
    FAILED = "failed"


class CatalogImportRow(Base):
    """Одна запись журнала импорта каталога (включая dry-run): отчёт лежит в `report`."""

    __tablename__ = "catalog_imports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(200))
    status: Mapped[CatalogImportStatus] = mapped_column(
        pg_enum(CatalogImportStatus, "catalog_import_status")
    )
    dry_run: Mapped[bool] = mapped_column(server_default=text("false"))
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
