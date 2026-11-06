"""Доступ к пользователям, refresh-токенам и гостевым сессиям."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConsultationRow, GuestSessionRow, RefreshTokenRow, UserRole, UserRow


class UserRepository:
    """Запросы к аккаунтам, токенам и гостевым сессиям."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def user(self, user_id: uuid.UUID) -> UserRow | None:
        """Пользователь по id."""
        return await self.session.get(UserRow, user_id)

    async def user_by_email(self, email: str) -> UserRow | None:
        """Пользователь по email (email хранится в нижнем регистре)."""
        return await self.session.scalar(select(UserRow).where(UserRow.email == email))

    async def add_user(self, row: UserRow) -> None:
        """Добавляет пользователя в сессию."""
        self.session.add(row)

    async def add_token(self, row: RefreshTokenRow) -> None:
        """Добавляет refresh-токен в сессию."""
        self.session.add(row)

    async def token_by_hash(self, token_hash: str) -> RefreshTokenRow | None:
        """Refresh-токен по хешу (вместе с пользователем)."""
        return await self.session.scalar(
            select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)
        )

    async def revoke_token(self, token_id: uuid.UUID, *, revoked_at: datetime) -> None:
        """Отзывает один refresh-токен."""
        await self._revoke_where(RefreshTokenRow.id == token_id, revoked_at=revoked_at)

    async def revoke_user_tokens(self, user_id: uuid.UUID, *, revoked_at: datetime) -> None:
        """Отзывает все действующие refresh-токены пользователя (компрометация)."""
        await self._revoke_where(
            (RefreshTokenRow.user_id == user_id) & (RefreshTokenRow.revoked_at.is_(None)),
            revoked_at=revoked_at,
        )

    async def _revoke_where(self, condition: ColumnElement[bool], *, revoked_at: datetime) -> None:
        await self.session.execute(
            update(RefreshTokenRow)
            .where(condition & RefreshTokenRow.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )

    async def add_guest_session(self, row: GuestSessionRow) -> None:
        """Добавляет гостевую сессию в сессию БД."""
        self.session.add(row)

    async def guest_by_hash(self, token_hash: str) -> GuestSessionRow | None:
        """Гостевая сессия по хешу токена."""
        return await self.session.scalar(
            select(GuestSessionRow).where(GuestSessionRow.token_hash == token_hash)
        )

    async def touch_guest_session(self, session_id: uuid.UUID, *, seen_at: datetime) -> None:
        """Обновляет время последней активности гостевой сессии."""
        await self.session.execute(
            update(GuestSessionRow)
            .where(GuestSessionRow.id == session_id)
            .values(last_seen_at=seen_at)
        )

    async def merge_guest(self, guest_session_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Переносит консультации гостевой сессии на аккаунт; возвращает число перенесённых."""
        moved = await self.session.scalar(
            select(func.count())
            .select_from(ConsultationRow)
            .where(ConsultationRow.guest_session_id == guest_session_id)
        )
        await self.session.execute(
            update(ConsultationRow)
            .where(ConsultationRow.guest_session_id == guest_session_id)
            .values(user_id=user_id)
        )
        await self.session.execute(
            update(GuestSessionRow)
            .where(GuestSessionRow.id == guest_session_id)
            .values(merged_user_id=user_id)
        )
        return int(moved or 0)

    async def list_users(
        self,
        *,
        role: UserRole | None,
        search: str | None,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[UserRow], int]:
        """Страница пользователей по фильтрам админки (поиск — по email)."""
        stmt = select(UserRow)
        if role is not None:
            stmt = stmt.where(UserRow.role == role)
        if search:
            stmt = stmt.where(UserRow.email.ilike(f"%{search}%"))
        if is_active is not None:
            stmt = stmt.where(UserRow.is_active.is_(is_active))
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        result = await self.session.scalars(
            stmt.order_by(UserRow.created_at, UserRow.email).limit(limit).offset(offset)
        )
        return result.all(), total or 0

    async def count_active_superadmins(self, *, exclude_id: uuid.UUID | None = None) -> int:
        """Число активных суперадминов (можно исключить одного — для проверки «последнего»)."""
        stmt = (
            select(func.count())
            .select_from(UserRow)
            .where((UserRow.role == UserRole.SUPERADMIN) & UserRow.is_active.is_(True))
        )
        if exclude_id is not None:
            stmt = stmt.where(UserRow.id != exclude_id)
        return int(await self.session.scalar(stmt) or 0)
