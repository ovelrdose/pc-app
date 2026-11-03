"""Общие зависимости FastAPI."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Database
from app.services.snapshot_cache import SnapshotCache


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
