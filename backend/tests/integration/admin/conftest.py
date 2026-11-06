"""Фикстуры админ-интеграционных тестов: засеянная БД и аккаунты по ролям."""

from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.db import Database
from app.core.security import create_access_token
from app.main import create_app
from app.models import UserRole, UserRow
from app.services.snapshot_cache import SnapshotCache
from tests.integration.conftest import seeded_settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def app(seeded: Database) -> FastAPI:
    application = create_app(seeded_settings(seeded))
    application.state.database = seeded
    application.state.cache = SnapshotCache()
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Отдельный клиент на тест: изолированные cookie."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as fresh:
        yield fresh


@pytest.fixture(scope="module")
async def accounts(seeded: Database) -> dict[str, UserRow]:
    """По аккаунту на каждую роль (пароль не нужен: авторизация — access-токеном)."""
    users: dict[str, UserRow] = {}
    async with seeded.session_factory() as session:
        for role in UserRole:
            row = UserRow(
                email=f"{role.value}@admins.test",
                password_hash="$argon2id$admins-test",  # noqa: S106 — токен, а не вход по паролю
                role=role,
            )
            session.add(row)
            users[role.value] = row
        await session.commit()
        return users


def auth(user: UserRow) -> dict[str, str]:
    """Заголовок Authorization с access-токеном для аккаунта.

    Секрет берём из настроек приложения (как зависимость `SettingsDep`): токен должен
    проходить проверку в `get_owner_context`.
    """
    secret = get_settings().jwt_secret.get_secret_value()
    token = create_access_token(
        user_id=user.id,
        role=user.role.value,
        secret=secret,
        ttl=timedelta(minutes=15),
    )
    return {"Authorization": f"Bearer {token}"}
