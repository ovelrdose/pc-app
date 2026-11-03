"""Проверки живости и готовности без реальной БД."""

import httpx
from fastapi import FastAPI

from app.api.deps import get_database


class _FakeDatabase:
    def __init__(self, *, healthy: bool) -> None:
        self.healthy = healthy

    async def ping(self) -> None:
        if not self.healthy:
            raise ConnectionError("db down")


async def test_healthz_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_ok_when_db_available(app: FastAPI, client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_database] = lambda: _FakeDatabase(healthy=True)
    response = await client.get("/api/v1/readyz")
    assert response.status_code == 200


async def test_readyz_problem_json_when_db_down(app: FastAPI, client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_database] = lambda: _FakeDatabase(healthy=False)
    response = await client.get("/api/v1/readyz")
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"].endswith("/service-unavailable")
    assert body["instance"] == "/api/v1/readyz"
