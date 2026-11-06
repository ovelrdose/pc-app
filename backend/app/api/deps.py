"""Общие зависимости FastAPI."""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import Database
from app.core.errors import AuthRequiredError, PermissionDeniedError
from app.core.security import TokenError, decode_access_token, hash_token
from app.models import UserRole, UserRow
from app.repositories.users import UserRepository
from app.services.ownership import OwnerContext
from app.services.snapshot_cache import SnapshotCache

REFRESH_COOKIE = "refresh_token"
"""HttpOnly-cookie с refresh-токеном."""
GUEST_COOKIE = "guest_session"
"""HttpOnly-cookie с токеном гостевой сессии."""
_BEARER_PREFIX = "Bearer "


def get_database(request: Request) -> Database:
    """Возвращает объект БД, созданный при старте приложения."""
    database: Database = request.app.state.database
    return database


DatabaseDep = Annotated[Database, Depends(get_database)]


async def get_session(database: DatabaseDep) -> AsyncIterator[AsyncSession]:
    """Выдаёт async-сессию SQLAlchemy на время запроса."""
    async for session in database.session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_cache(request: Request) -> SnapshotCache:
    """Кэш снимков БЗ и каталога, созданный при старте приложения."""
    cache: SnapshotCache = request.app.state.cache
    return cache


CacheDep = Annotated[SnapshotCache, Depends(get_cache)]


def get_settings_dep() -> Settings:
    """Настройки приложения (закэшированы)."""
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_owner_context(
    request: Request, session: SessionDep, settings: SettingsDep
) -> OwnerContext:
    """Определяет владельца запроса: аккаунт по Bearer-токену либо гостевая сессия по cookie.

    Просроченный или подделанный токен — 401 (клиент обновляет токен и повторяет
    запрос); без токена и без действующей гостевой сессии — 401.
    """
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith(_BEARER_PREFIX):
        token = authorization.removeprefix(_BEARER_PREFIX).strip()
        try:
            payload = decode_access_token(token, secret=settings.jwt_secret.get_secret_value())
        except TokenError as exc:
            raise AuthRequiredError("Токен доступа недействителен или истёк") from exc
        user = await UserRepository(session).user(payload.user_id)
        if user is None:
            raise AuthRequiredError("Пользователь не найден")
        if not user.is_active:
            raise PermissionDeniedError("Аккаунт заблокирован")
        return OwnerContext(user=user)
    guest_token = request.cookies.get(GUEST_COOKIE)
    if guest_token:
        guest = await UserRepository(session).guest_by_hash(hash_token(guest_token))
        if guest is not None and guest.merged_user_id is None:
            return OwnerContext(guest=guest)
    raise AuthRequiredError()


OwnerDep = Annotated[OwnerContext, Depends(get_owner_context)]


async def get_current_user(owner: OwnerDep) -> UserRow:
    """Текущий аккаунт: запрос доступен только вошедшему пользователю."""
    if owner.user is None:
        raise AuthRequiredError("Этот запрос доступен только аккаунту")
    return owner.user


CurrentUserDep = Annotated[UserRow, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[OwnerContext], Coroutine[Any, Any, OwnerContext]]:
    """Зависимость для будущих админских эндпоинтов: только указанные роли."""

    async def checker(owner: OwnerDep) -> OwnerContext:
        if owner.user is None or owner.user.role not in roles:
            raise PermissionDeniedError("Недостаточно прав для операции")
        return owner

    return checker
