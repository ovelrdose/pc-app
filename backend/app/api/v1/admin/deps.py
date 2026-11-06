"""Зависимости админских роутеров: роли по матрице доступа ADR 0010 п.9."""

from typing import Annotated

from fastapi import Depends

from app.api.deps import require_roles
from app.models import UserRole, UserRow
from app.services.ownership import OwnerContext

CatalogAdminOwner = Annotated[
    OwnerContext, Depends(require_roles(UserRole.CATALOG_ADMIN, UserRole.SUPERADMIN))
]
"""Каталог: компоненты, импорт и экспорт CSV."""

CatalogIssuesOwner = Annotated[
    OwnerContext,
    Depends(
        require_roles(UserRole.CATALOG_ADMIN, UserRole.KNOWLEDGE_ENGINEER, UserRole.SUPERADMIN)
    ),
]
"""Позиции, требующие внимания: каталог и инженер знаний читают список."""

KnowledgeOwner = Annotated[
    OwnerContext, Depends(require_roles(UserRole.KNOWLEDGE_ENGINEER, UserRole.SUPERADMIN))
]
"""База знаний: правила, справочники, валидация, публикация, снимки."""

SuperadminOwner = Annotated[OwnerContext, Depends(require_roles(UserRole.SUPERADMIN))]
"""Пользователи и роли."""


def actor(owner: OwnerContext) -> UserRow:
    """Аккаунт админа: `require_roles` гарантирует, что пользователь аутентифицирован."""
    assert owner.user is not None  # noqa: S101 — гарантируется зависимостью require_roles
    return owner.user
