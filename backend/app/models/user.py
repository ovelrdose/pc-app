"""ORM-модели аккаунтов: пользователи с ролями, refresh-токены и гостевые сессии."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.component import pg_enum


class UserRole(StrEnum):
    """Роль пользователя. Расширяет права: от клиента до суперадмина."""

    CLIENT = "client"
    CATALOG_ADMIN = "catalog_admin"
    KNOWLEDGE_ENGINEER = "knowledge_engineer"
    SUPERADMIN = "superadmin"


class UserRow(Base):
    """Пользователь системы: вход по email и паролю, роль для RBAC."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), server_default=text("'client'::user_role")
    )
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RefreshTokenRow(Base):
    """Refresh-токен: непрозрачная строка, в БД — только её хеш.

    Ротация: новый токен ссылается на заменённый (`replaced_by_id`), отзыв —
    через `revoked_at`. Повторное использование отозванного токена отзывает
    всю цепочку.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped[UserRow] = relationship(lazy="raise")


class GuestSessionRow(Base):
    """Гостевая сессия: анонимный идентификатор клиента без регистрации.

    После регистрации или входа сессия связывается с аккаунтом
    (`merged_user_id`), консультации гостя переносятся на пользователя.
    """

    __tablename__ = "guest_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    merged_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    merged_user: Mapped[UserRow | None] = relationship(lazy="raise")
