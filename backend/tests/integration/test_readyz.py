"""Готовность приложения с реальной базой pcapp_test."""

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.integration


async def test_readyz_with_real_db(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        response = await client.get("/api/v1/readyz")
    assert response.status_code == 200
