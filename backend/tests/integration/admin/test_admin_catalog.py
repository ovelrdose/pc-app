"""Админка каталога: CRUD компонентов, импорт CSV с журналом, экспорт, список проблем."""

import io
import uuid
import zipfile

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.expert.frames import Category, ComponentStatus
from app.models import CatalogImportRow, CatalogImportStatus, UserRow
from app.services.catalog_csv import parse_catalog_csv
from tests.factories import slots
from tests.integration.admin.conftest import auth

pytestmark = pytest.mark.integration

FAN_CSV = (
    "sku,brand,model,release_year,color,rgb,size_mm,quantity,pwm,noise_db,airflow_cfm,"
    "price_rub,price_checked_at,price_note\n"
    "FAN-TEST-ADMIN-1,Arctic,P12 PWM,2020,black,false,120,1,true,22.5,56.3,"
    "1500,2026-11-05,тест импорта\n"
)

# Строка 3 без цены — отклоняется; строки 2 и 4 валидны и должны загрузиться.
FAN_CSV_PARTIAL = (
    "sku,brand,model,release_year,color,rgb,size_mm,quantity,pwm,noise_db,airflow_cfm,"
    "price_rub,price_checked_at,price_note\n"
    "FAN-TEST-PARTIAL-1,Arctic,P12 PWM,2020,black,false,120,1,true,22.5,56.3,"
    "1500,2026-11-05,первая\n"
    "FAN-TEST-PARTIAL-BAD,Arctic,P12 PWM,2020,black,false,120,1,true,22.5,56.3,"
    ",2026-11-05,без цены\n"
    "FAN-TEST-PARTIAL-2,Noctua,NF-A12,2021,black,false,120,1,true,18.1,60.1,"
    "2400,2026-11-05,вторая\n"
)


def _upload(csv_text: str) -> dict[str, tuple[str, str, str]]:
    return {"upload": ("fans.csv", csv_text, "text/csv")}


async def test_list_components_with_filters(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["catalog_admin"])
    response = await client.get(
        "/api/v1/admin/components",
        params={"category": "cpu", "status": "active", "limit": 5},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    assert all(item["category"] == "cpu" for item in body["items"])
    assert all(item["status"] == "active" for item in body["items"])

    stale = await client.get(
        "/api/v1/admin/components", params={"price_stale_days": 3650}, headers=headers
    )
    assert stale.status_code == 200
    # stale-фильтр работает: всё, что проверялось позже порога, отфильтровано
    assert all(
        item["price_checked_at"] is None or item["price_checked_at"] < "2017-01-01"
        for item in stale.json()["items"]
    )


async def test_create_get_replace_patch_component(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["catalog_admin"])
    frame = {"category": "cpu", **slots(Category.CPU, sku="CPU-TEST-ADMIN-1")}
    response = await client.post("/api/v1/admin/components", json=frame, headers=headers)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["status"] == "active"
    assert created["source"] == "manual"
    component_id = created["id"]

    # дубликат артикула — 409
    again = await client.post("/api/v1/admin/components", json=frame, headers=headers)
    assert again.status_code == 409

    card = await client.get(f"/api/v1/admin/components/{component_id}", headers=headers)
    assert card.status_code == 200
    assert card.json()["sku"] == "CPU-TEST-ADMIN-1"

    # полная замена: цена выросла
    replaced_frame = {
        "category": "cpu",
        **slots(Category.CPU, sku="CPU-TEST-ADMIN-1", price_kop=2_500_000),
    }
    replaced = await client.put(
        f"/api/v1/admin/components/{component_id}", json=replaced_frame, headers=headers
    )
    assert replaced.status_code == 200
    assert replaced.json()["price_kop"] == 2_500_000
    assert replaced.json()["source"] == "manual"

    # служебные поля
    patched = await client.patch(
        f"/api/v1/admin/components/{component_id}",
        json={"in_stock": False},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["in_stock"] is False

    retired = await client.patch(
        f"/api/v1/admin/components/{component_id}",
        json={"status": "inactive"},
        headers=headers,
    )
    assert retired.status_code == 200
    assert retired.json()["status"] == "inactive"

    # возврат к продаже: статус active, причины неактивности очищены
    restored = await client.patch(
        f"/api/v1/admin/components/{component_id}",
        json={"status": "active"},
        headers=headers,
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["status_issues"] == []

    # снова снять с продажи, чтобы не мешать фильтрам активных в других тестах
    await client.patch(
        f"/api/v1/admin/components/{component_id}",
        json={"status": "inactive"},
        headers=headers,
    )

    # руками можно только active/inactive
    bad = await client.patch(
        f"/api/v1/admin/components/{component_id}",
        json={"status": "needs_kb"},
        headers=headers,
    )
    assert bad.status_code == 422

    missing = await client.get(f"/api/v1/admin/components/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404


async def test_import_csv_dry_run_then_apply(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    headers = auth(accounts["catalog_admin"])

    dry = await client.post(
        "/api/v1/admin/catalog/import",
        params={"category": "case_fan", "dry_run": "true"},
        files=_upload(FAN_CSV),
        headers=headers,
    )
    assert dry.status_code == 201, dry.text
    body = dry.json()
    assert body["dry_run"] is True
    assert body["created"] == 1
    # dry-run не меняет БД
    found = await client.get(
        "/api/v1/admin/components", params={"q": "FAN-TEST-ADMIN-1"}, headers=headers
    )
    assert found.json()["total"] == 0

    applied = await client.post(
        "/api/v1/admin/catalog/import",
        params={"category": "case_fan", "dry_run": "false"},
        files=_upload(FAN_CSV),
        headers=headers,
    )
    assert applied.status_code == 201, applied.text
    body = applied.json()
    assert body["dry_run"] is False
    assert body["created"] == 1
    found = await client.get(
        "/api/v1/admin/components", params={"q": "FAN-TEST-ADMIN-1"}, headers=headers
    )
    assert found.json()["total"] == 1
    assert found.json()["items"][0]["source"] == "import"

    # повторный импорт того же файла — без изменений
    again = await client.post(
        "/api/v1/admin/catalog/import",
        params={"category": "case_fan"},
        files=_upload(FAN_CSV),
        headers=headers,
    )
    assert again.json()["unchanged"] == 1

    # каждый вызов пишет журнал, включая dry-run
    async with app.state.database.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(CatalogImportRow))
        dry_runs = await session.scalar(
            select(func.count())
            .select_from(CatalogImportRow)
            .where(CatalogImportRow.dry_run.is_(True))
        )
    assert count == 3
    assert dry_runs == 1


async def test_import_csv_fatal_error_is_journalized(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    headers = auth(accounts["catalog_admin"])
    broken = FAN_CSV.replace("sku,brand", "sku,unknown_column,brand")
    response = await client.post(
        "/api/v1/admin/catalog/import",
        params={"category": "case_fan"},
        files=_upload(broken),
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("/catalog-import-invalid")

    async with app.state.database.session_factory() as session:
        row = await session.scalar(
            select(CatalogImportRow).where(CatalogImportRow.status == CatalogImportStatus.FAILED)
        )
    assert row is not None
    assert row.report["errors"]


async def test_import_csv_partial_rows_apply_valid_and_reject_broken(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    """Частично битый файл: валидные строки загружаются, битая отклоняется с номером строки."""
    headers = auth(accounts["catalog_admin"])
    response = await client.post(
        "/api/v1/admin/catalog/import",
        params={"category": "case_fan"},
        files=_upload(FAN_CSV_PARTIAL),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] == 2
    assert body["errors"], "отклонённая строка должна быть перечислена в отчёте"
    assert any("строка 3" in error for error in body["errors"]), body["errors"]
    assert any("price_rub" in error for error in body["errors"]), body["errors"]

    found = await client.get(
        "/api/v1/admin/components", params={"q": "FAN-TEST-PARTIAL"}, headers=headers
    )
    skus = {item["sku"] for item in found.json()["items"]}
    assert skus == {"FAN-TEST-PARTIAL-1", "FAN-TEST-PARTIAL-2"}

    # отчёт журнала хранит и ошибки, и счётчики (имя файла у импортов общее — ищем по отчёту)
    async with app.state.database.session_factory() as session:
        rows = (
            await session.scalars(
                select(CatalogImportRow).where(
                    CatalogImportRow.status == CatalogImportStatus.COMPLETED
                )
            )
        ).all()
    journal = next(row for row in rows if row.report["created"] == 2)
    assert journal.filename == "fans.csv"
    assert journal.report["errors"]


async def test_import_csv_too_large_is_rejected_and_journalized(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    """Файл больше лимита отклоняется целиком (413), в журнале остаётся запись об отказе."""
    headers = auth(accounts["catalog_admin"])
    big = FAN_CSV + ("x," * 40 + "\n") * 60_000  # ~3,5 МБ
    assert len(big.encode("utf-8")) > 2 * 1024 * 1024
    response = await client.post(
        "/api/v1/admin/catalog/import",
        params={"category": "case_fan"},
        files=_upload(big),
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json()["type"].endswith("/catalog-import-too-large")

    async with app.state.database.session_factory() as session:
        rows = (
            await session.scalars(
                select(CatalogImportRow).where(
                    CatalogImportRow.status == CatalogImportStatus.FAILED
                )
            )
        ).all()
    assert any(any("больше" in error for error in row.report["errors"]) for row in rows), (
        "в журнале должна быть запись об отказе по лимиту размера"
    )


async def test_export_catalog_zip(client: httpx.AsyncClient, accounts: dict[str, UserRow]) -> None:
    headers = auth(accounts["catalog_admin"])
    response = await client.get("/api/v1/admin/catalog/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert names == {f"{category.value}.csv" for category in Category}
    # экспортированный CSV снова парсится без ошибок
    parsed = parse_catalog_csv(archive.read("cpu.csv").decode("utf-8"), Category.CPU)
    assert not parsed.errors
    assert parsed.records
    assert list(parsed.records[0].frame.model_dump())  # фрейм собирается обратно


async def test_catalog_issues_lists_incomplete_and_needs_kb(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers_admin = auth(accounts["catalog_admin"])
    headers_ke = auth(accounts["knowledge_engineer"])
    # компонент со слотом, которого нет в справочниках снимка
    frame = {"category": "cpu", **slots(Category.CPU, sku="CPU-TEST-NEEDSKB-1", socket="AM6")}
    response = await client.post("/api/v1/admin/components", json=frame, headers=headers_admin)
    assert response.status_code == 201
    assert response.json()["status"] == "needs_kb"

    for headers in (headers_admin, headers_ke):
        issues = await client.get(
            "/api/v1/admin/catalog/issues", params={"category": "cpu"}, headers=headers
        )
        assert issues.status_code == 200
        items = issues.json()["items"]
        assert items
        assert all(
            item["status"] in (ComponentStatus.INCOMPLETE, ComponentStatus.NEEDS_KB)
            for item in items
        )
        target = next(item for item in items if item["sku"] == "CPU-TEST-NEEDSKB-1")
        assert "AM6" in target["status_issues"][0]
