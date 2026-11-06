"""Админка: управление пользователями и ролями (superadmin, ADR 0010 п.9)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.api.v1.admin.deps import SuperadminOwner, actor
from app.models import UserRole
from app.schemas.admin import UserAdminOut, UserAdminPage, UserPatchIn
from app.services.users_admin import UsersAdminService

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("", summary="Пользователи: список с фильтрами (superadmin)")
async def list_users(
    session: SessionDep,
    owner: SuperadminOwner,
    role: UserRole | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Поиск по email")] = None,
    is_active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserAdminPage:
    rows, total = await UsersAdminService(session).list_users(
        role=role, search=q, is_active=is_active, limit=limit, offset=offset
    )
    return UserAdminPage(
        items=[UserAdminOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{user_id}", summary="Сменить роль или заблокировать (отзывает токены)")
async def patch_user(
    session: SessionDep,
    owner: SuperadminOwner,
    user_id: uuid.UUID,
    patch: UserPatchIn,
) -> UserAdminOut:
    row = await UsersAdminService(session).patch_user(
        user_id,
        role=patch.role,
        is_active=patch.is_active,
        actor=actor(owner),
    )
    return UserAdminOut.model_validate(row)
