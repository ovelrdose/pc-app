"""Перевод исключений в RFC 9457 problem+json."""

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import ConflictError, NotFoundError


class _Payload(BaseModel):
    count: int


def _add_routes(app: FastAPI) -> None:
    @app.get("/boom/not-found")
    async def not_found() -> None:
        raise NotFoundError("Компонент не найден", component_id="42")

    @app.get("/boom/conflict")
    async def conflict() -> None:
        raise ConflictError()

    @app.post("/boom/validate")
    async def validate(payload: _Payload) -> _Payload:
        return payload


async def test_domain_error_with_extra(app: FastAPI, client: httpx.AsyncClient) -> None:
    _add_routes(app)
    response = await client.get("/boom/not-found")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["title"] == "Объект не найден"
    assert body["detail"] == "Компонент не найден"
    assert body["component_id"] == "42"


async def test_domain_error_without_detail(app: FastAPI, client: httpx.AsyncClient) -> None:
    _add_routes(app)
    body = (await client.get("/boom/conflict")).json()
    assert body["status"] == 409
    assert "detail" not in body


async def test_validation_error(app: FastAPI, client: httpx.AsyncClient) -> None:
    _add_routes(app)
    response = await client.post("/boom/validate", json={"count": "много"})
    assert response.status_code == 422
    body = response.json()
    assert body["type"].endswith("/validation-error")
    assert body["errors"][0]["loc"] == ["body", "count"]


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
