"""Аутентификация: регистрация, вход, токены, гостевые сессии, перенос сборок, владение."""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import TypedDict, cast

import httpx
import pytest
from fastapi import FastAPI

from app.core.db import Database
from app.core.security import create_access_token
from app.main import create_app
from app.services.snapshot_cache import SnapshotCache
from tests.integration.conftest import seeded_settings

pytestmark = pytest.mark.integration

PASSWORD = "сложный-пароль-123"  # noqa: S105 — осознанный тестовый пароль
JWT_SECRET = "test-secret"  # noqa: S105 — как в фикстурах conftest


class UserBody(TypedDict):
    id: str
    email: str
    role: str
    created_at: str


class TokenBody(TypedDict):
    access_token: str
    token_type: str
    expires_in: int
    user: UserBody


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


async def stranger(app: FastAPI) -> httpx.AsyncClient:
    """Свежий клиент без cookie — «другой посетитель»."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def register(client: httpx.AsyncClient, email: str) -> TokenBody:
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return cast(TokenBody, response.json())


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_register_login_me_and_password_security(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    body = await register(client, "ivan@example.com")
    assert body["token_type"] == "bearer"  # noqa: S105 — стандартное имя поля OAuth
    assert body["expires_in"] == 15 * 60
    assert body["user"]["role"] == "client"
    assert "password" not in body
    assert "password_hash" not in body

    refresh = client.cookies.get("refresh_token")
    assert refresh is not None
    assert len(refresh) == 64

    me = await client.get("/api/v1/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "ivan@example.com"

    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "ivan@example.com", "password": "не-тот-пароль"}
    )
    assert wrong.status_code == 401

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": "Ivan@Example.com", "password": PASSWORD}
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["email"] == "ivan@example.com"  # email нормализован

    async with await stranger(app) as anonymous:
        me = await anonymous.get("/api/v1/auth/me")
        assert me.status_code == 401


async def test_password_hash_is_argon2id(app: FastAPI) -> None:
    from sqlalchemy import select

    from app.models import UserRow

    async with app.state.database.session_factory() as session:
        user = await session.scalar(select(UserRow).where(UserRow.email == "ivan@example.com"))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")


async def test_access_token_security(client: httpx.AsyncClient) -> None:
    """Истёкший и подделанный access-токены отклоняются."""
    expired = create_access_token(
        user_id=uuid.uuid4(),
        role="client",
        secret=JWT_SECRET,
        ttl=timedelta(minutes=-1),
    )
    response = await client.get("/api/v1/auth/me", headers=bearer(expired))
    assert response.status_code == 401

    body = await register(client, "maria@example.com")
    good = body["access_token"]
    head, _, tail = good.partition(".")
    tampered = f"{head}.AAAA.{tail}"
    response = await client.get("/api/v1/auth/me", headers=bearer(tampered))
    assert response.status_code == 401


async def test_guest_lifecycle_and_merge(app: FastAPI, client: httpx.AsyncClient) -> None:
    """Гостевая сессия → консультация → регистрация → сборки перенесены в аккаунт."""
    guest = await client.post("/api/v1/sessions/guest")
    assert guest.status_code == 201
    assert guest.json() == {"status": "created"}
    assert "guest_session" in client.cookies
    again = await client.post("/api/v1/sessions/guest")
    assert again.json() == {"status": "existing"}  # действующая сессия продлевается

    created = await client.post(
        "/api/v1/consultations",
        json={"answers": {"tasks": {"main": "office"}, "budget": 60000}},
    )
    assert created.status_code == 201, created.text
    consultation_id = created.json()["id"]
    run = await client.post(f"/api/v1/consultations/{consultation_id}/builds")
    assert run.status_code == 201, run.text
    builds = run.json()["builds"]
    saved = await client.patch(f"/api/v1/builds/{builds[0]['id']}", json={"is_saved": True})
    assert saved.status_code == 200

    registered = await register(client, "guest-becomes-user@example.com")
    # Гостевая cookie слилась с аккаунтом: удалена, взамен поставлен refresh-токен
    assert client.cookies.get("guest_session") is None
    assert client.cookies.get("refresh_token") is not None

    mine = await client.get("/api/v1/me/builds", headers=bearer(registered["access_token"]))
    assert mine.status_code == 200
    body = mine.json()
    assert body["total"] == 1
    assert body["builds"][0]["consultation_id"] == consultation_id
    assert body["builds"][0]["build"]["id"] == builds[0]["id"]

    # Владение теперь через аккаунт: без авторизации — 401, чужой гость — 404
    async with await stranger(app) as anonymous:
        response = await anonymous.get(f"/api/v1/consultations/{consultation_id}")
        assert response.status_code == 401
    async with await stranger(app) as other_guest:
        await other_guest.post("/api/v1/sessions/guest")
        response = await other_guest.get(f"/api/v1/consultations/{consultation_id}")
        assert response.status_code == 404  # чужая консультация не раскрывается


async def test_refresh_rotation_and_reuse_detection(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    await register(client, "rotation@example.com")
    old_refresh = client.cookies["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    new_refresh = client.cookies["refresh_token"]
    assert new_refresh != old_refresh

    # Повторное использование отозванного токена = кража: вся цепочка отзывается
    async with await stranger(app) as thief:
        thief.cookies.set("refresh_token", old_refresh)
        replay = await thief.post("/api/v1/auth/refresh")
        assert replay.status_code == 401
    stolen = await client.post("/api/v1/auth/refresh")  # новый токен тоже отозван
    assert stolen.status_code == 401

    relogin = await client.post(
        "/api/v1/auth/login",
        json={"email": "rotation@example.com", "password": PASSWORD},
    )
    assert relogin.status_code == 200
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200


async def test_logout_revokes_refresh(client: httpx.AsyncClient) -> None:
    await register(client, "logout@example.com")
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_auth_endpoints_set_http_only_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/sessions/guest")
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/api/v1" in set_cookie

    logged = await client.post(
        "/api/v1/auth/login",
        json={"email": "ivan@example.com", "password": PASSWORD},
    )
    assert logged.status_code == 200
    refresh_cookie = logged.headers["set-cookie"]
    assert "HttpOnly" in refresh_cookie
    assert "Path=/api/v1/auth" in refresh_cookie
