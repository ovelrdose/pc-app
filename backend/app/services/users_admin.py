"""Управление пользователями для суперадмина (ADR 0010 п.9): роли, блокировка, токены."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import UserRole, UserRow
from app.repositories.users import UserRepository

logger = structlog.get_logger(__name__)


class SelfChangeError(ConflictError):
    """Суперадмин не может изменить собственную роль или заблокировать себя."""

    code = "self-change-forbidden"
    title = "Нельзя изменить самого себя"


class LastSuperadminError(ConflictError):
    """Блокировка или понижение последнего активного суперадмина запрещены."""

    code = "last-superadmin"
    title = "Последний активный суперадмин"


class UsersAdminService:
    """Сценарии управления аккаунтами: список, смена роли, блокировка с отзывом токенов."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def list_users(
        self,
        *,
        role: UserRole | None,
        search: str | None,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[UserRow], int]:
        """Страница пользователей по фильтрам."""
        return await self.repo.list_users(
            role=role, search=search, is_active=is_active, limit=limit, offset=offset
        )

    async def patch_user(
        self,
        target_id: uuid.UUID,
        *,
        role: UserRole | None,
        is_active: bool | None,
        actor: UserRow,
    ) -> UserRow:
        """Меняет роль и/или активность; отзывает все refresh-токены при блокировке.

        Запрещено: менять самого себя; блокировать или понижать последнего активного
        суперадмина (ADR 0010 п.9).
        """
        target = await self.repo.user(target_id)
        if target is None:
            raise NotFoundError("Пользователь не найден", user_id=str(target_id))
        if target.id == actor.id:
            raise SelfChangeError("Нельзя менять роль или блокировать собственный аккаунт")
        demoting = role is not None and role is not UserRole.SUPERADMIN
        if (
            (is_active is False or demoting)
            and target.role is UserRole.SUPERADMIN
            and target.is_active
        ):
            others = await self.repo.count_active_superadmins(exclude_id=target.id)
            if others == 0:
                raise LastSuperadminError(
                    "Нельзя заблокировать или понизить последнего активного суперадмина"
                )
        if role is not None:
            target.role = role
        blocked = is_active is False and target.is_active
        if is_active is not None:
            target.is_active = is_active
        if blocked:
            await self.repo.revoke_user_tokens(target.id, revoked_at=datetime.now(UTC))
        await self.session.flush()
        logger.info(
            "user_patched",
            target_id=str(target.id),
            role=target.role.value,
            is_active=target.is_active,
            tokens_revoked=blocked,
            actor_id=str(actor.id),
        )
        return target
