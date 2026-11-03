"""Публичный API каталога на реальной БД."""

import uuid

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.expert.frames import FRAMES_BY_CATEGORY, Category, ComponentStatus
from app.models import ComponentRow, ComponentSource
from app.services.catalog_csv import CatalogRecord
from app.services.catalog_loader import load_catalog
from tests.factories import slots

pytestmark = pytest.mark.integration


@pytest.fixture
async def catalog(session: AsyncSession) -> None:
    records = [
        CatalogRecord(
            frame=FRAMES_BY_CATEGORY[category].model_validate(slots(category)),
            price_checked_at=None,
            price_note=None,
        )
        for category in Category
    ]
    extra_cpu = slots(Category.CPU, sku="CPU-INTEL-I5", brand="Intel", model="Core i5-14400F")
    records.append(
        CatalogRecord(
            frame=FRAMES_BY_CATEGORY[Category.CPU].model_validate(
                {**extra_cpu, "price_kop": 1_500_000, "in_stock": False, "socket": "LGA1700"}
            ),
            price_checked_at=None,
            price_note=None,
        )
    )
    await load_catalog(session, records, source=ComponentSource.MANUAL)
    await session.commit()


@pytest.mark.usefixtures("catalog")
async def test_list_filters_by_category_and_sorts_by_price(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/components", params={"category": "cpu"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["sku"] for item in body["items"]] == ["CPU-INTEL-I5", "CPU-AMD-R5-7600"]
    assert body["items"][1]["specs"]["socket"] == "AM5"
    assert body["items"][1]["perf"] == {"perf_single": 100.0, "perf_multi": 100.0}


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize(
    ("params", "expected_total"),
    [
        ({}, len(Category) + 1),
        ({"in_stock": "true", "category": "cpu"}, 1),
        ({"brand": "intel"}, 1),
        ({"q": "ryzen"}, 1),
        ({"min_price_kop": 1_500_000, "max_price_kop": 1_900_000}, 3),
    ],
)
async def test_list_filters(
    client: httpx.AsyncClient, params: dict[str, str | int], expected_total: int
) -> None:
    response = await client.get("/api/v1/components", params=params)
    assert response.json()["total"] == expected_total


@pytest.mark.usefixtures("catalog")
async def test_pagination(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/components", params={"limit": 3, "offset": 9})).json()
    assert (body["total"], len(body["items"]), body["offset"]) == (len(Category) + 1, 2, 9)


@pytest.mark.usefixtures("catalog")
async def test_inactive_components_are_hidden(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await session.execute(
        update(ComponentRow)
        .where(ComponentRow.sku == "CPU-INTEL-I5")
        .values(status=ComponentStatus.INACTIVE)
    )
    await session.commit()
    body = (await client.get("/api/v1/components", params={"category": "cpu"})).json()
    assert body["total"] == 1


@pytest.mark.usefixtures("catalog")
async def test_get_component_and_not_found(client: httpx.AsyncClient) -> None:
    first = (await client.get("/api/v1/components", params={"limit": 1})).json()["items"][0]
    response = await client.get(f"/api/v1/components/{first['id']}")
    assert response.status_code == 200
    assert response.json()["sku"] == first["sku"]

    missing = await client.get(f"/api/v1/components/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.headers["content-type"] == "application/problem+json"
    assert missing.json()["detail"] == "Компонент не найден"


async def test_invalid_query_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/components", params={"category": "monitor"})
    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-error")


async def test_frames_endpoint(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/frames")).json()
    assert len(body) == len(Category)
    cpu = next(frame for frame in body if frame["category"] == "cpu")
    assert cpu["title"] == "Процессор"
    assert cpu["json_schema"]["properties"]["tdp_w"]["unit"] == "Вт"
