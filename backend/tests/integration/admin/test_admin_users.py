"""Управление пользователями (superadmin) и параметризованная RBAC-матрица админки."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.models import RefreshTokenRow, UserRole, UserRow
from tests.integration.admin.conftest import auth

pytestmark = pytest.mark.integration

ROLES = ("client", "catalog_admin", "knowledge_engineer", "superadmin")

# (метод, путь, ожидаемый статус для ролей по порядку ROLES)
MATRIX: list[tuple[str, str, tuple[int, int, int, int]]] = [
    ("GET", "/api/v1/admin/components", (403, 200, 403, 200)),
    ("GET", "/api/v1/admin/catalog/export", (403, 200, 403, 200)),
    ("GET", "/api/v1/admin/catalog/issues", (403, 200, 200, 200)),
    ("GET", "/api/v1/admin/rules", (403, 403, 200, 200)),
    ("GET", "/api/v1/admin/rules/REQ-024", (403, 403, 200, 200)),
    ("GET", "/api/v1/admin/kb/vocabulary", (403, 403, 200, 200)),
    ("GET", "/api/v1/admin/kb/snapshots", (403, 403, 200, 200)),
    ("GET", "/api/v1/admin/kb/export", (403, 403, 200, 200)),
    ("POST", "/api/v1/admin/kb/validate", (403, 403, 200, 200)),
    ("GET", "/api/v1/admin/reference", (403, 403, 200, 200)),
    ("GET", "/api/v1/admin/users", (403, 403, 403, 200)),
    # Мутирующие эндпоинты: для чужих ролей — 403 до валидации тела/файла;
    # для своих — безопасный исход (422 за невалидное тело/файл, 404 за отсутствующий код).
    ("POST", "/api/v1/admin/rules", (403, 403, 422, 422)),
    ("POST", "/api/v1/admin/rules/REQ-999/retire", (403, 403, 404, 404)),
    ("PUT", "/api/v1/admin/reference/sockets", (403, 403, 422, 422)),
    ("POST", "/api/v1/admin/components", (403, 422, 403, 422)),
    ("POST", "/api/v1/admin/catalog/import", (403, 422, 403, 422)),
]


@pytest.mark.parametrize(("method", "path", "expected"), MATRIX)
async def test_rbac_matrix(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    method: str,
    path: str,
    expected: tuple[int, int, int, int],
) -> None:
    """Матрица ADR 0010 п.9: роль × эндпоинт → 200 для своих, 403 для чужих."""
    for role, status in zip(ROLES, expected, strict=True):
        response = await client.request(method, path, headers=auth(accounts[role]))
        assert response.status_code == status, f"{role} {method} {path}: {response.status_code}"


async def test_admin_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/admin/components")
    assert response.status_code == 401
    assert response.json()["type"].endswith("/auth-required")


async def test_list_users_and_filters(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["superadmin"])
    response = await client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 4

    by_role = await client.get(
        "/api/v1/admin/users", params={"role": "knowledge_engineer"}, headers=headers
    )
    assert all(item["role"] == "knowledge_engineer" for item in by_role.json()["items"])

    search = await client.get("/api/v1/admin/users", params={"q": "superadmin@"}, headers=headers)
    assert search.json()["total"] == 1


async def test_patch_missing_user_is_404(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["superadmin"])
    response = await client.patch(
        f"/api/v1/admin/users/{uuid.uuid4()}",
        json={"role": "client"},
        headers=headers,
    )
    assert response.status_code == 404


async def test_cannot_change_self(client: httpx.AsyncClient, accounts: dict[str, UserRow]) -> None:
    admin = accounts["superadmin"]
    response = await client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"role": "client"},
        headers=auth(admin),
    )
    assert response.status_code == 409
    assert response.json()["type"].endswith("/self-change-forbidden")

    response = await client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"is_active": False},
        headers=auth(admin),
    )
    assert response.status_code == 409


async def test_promote_demote_and_block_revokes_tokens(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    """Понижение второго суперадмина разрешено; блокировка отзывает все refresh-токены."""
    database = app.state.database
    async with database.session_factory() as session:
        second_id = uuid.uuid4()
        second = UserRow(
            id=second_id,
            email="superadmin2@admins.test",
            password_hash="$argon2id$admins-test",  # noqa: S106 — токен, а не вход по паролю
            role=UserRole.SUPERADMIN,
        )
        token = RefreshTokenRow(
            user_id=second_id,
            token_hash="a" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        session.add(second)
        session.add(token)
        await session.commit()

    admin = accounts["superadmin"]
    # понижение второго суперадмина разрешено — остаётся первый
    demoted = await client.patch(
        f"/api/v1/admin/users/{second_id}",
        json={"role": "knowledge_engineer"},
        headers=auth(admin),
    )
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "knowledge_engineer"

    # блокировка отзывает все refresh-токены
    blocked = await client.patch(
        f"/api/v1/admin/users/{second_id}",
        json={"is_active": False},
        headers=auth(admin),
    )
    assert blocked.status_code == 200
    assert blocked.json()["is_active"] is False
    async with database.session_factory() as session:
        token_row = await session.scalar(
            select(RefreshTokenRow).where(RefreshTokenRow.user_id == second_id)
        )
    assert token_row is not None
    assert token_row.revoked_at is not None


async def test_last_active_superadmin_is_protected(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    """Блокировка или понижение последнего активного суперадмина — 409.

    Через HTTP эту ветку перекрывает проверка «сам себя» (инициатор — тоже суперадмин),
    поэтому сценарий проверяется на уровне сервиса: защита работает в глубину, даже если
    вызов пришёл не через HTTP-зависимость.
    """
    from app.services.users_admin import LastSuperadminError, UsersAdminService

    database = app.state.database
    async with database.session_factory() as session:
        actor = await session.merge(accounts["knowledge_engineer"])
        target = await session.merge(accounts["superadmin"])
        service = UsersAdminService(session)
        with pytest.raises(LastSuperadminError):
            await service.patch_user(target.id, role=UserRole.CLIENT, is_active=None, actor=actor)
        with pytest.raises(LastSuperadminError):
            await service.patch_user(target.id, role=None, is_active=False, actor=actor)
