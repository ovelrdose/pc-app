"""Админка базы знаний: валидация, публикация, снимки, экспорт (round-trip), правила,
справочники, регенерация — ADR 0010 п.2–7."""

import io
import zipfile
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI

from app.expert.golden import cases_to_json
from app.models import RuleRow, UserRow
from app.repositories.knowledge import KnowledgeRepository
from app.services.knowledge_files import load_golden
from app.services.knowledge_store import GOLDEN, import_files
from scripts.seed import KNOWLEDGE_DIR
from tests.integration.admin.conftest import auth

pytestmark = pytest.mark.integration


async def _snapshots(client: httpx.AsyncClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = await client.get("/api/v1/admin/kb/snapshots", headers=headers)
    assert response.status_code == 200
    return cast(list[dict[str, Any]], response.json())


async def test_validate_clean_draft_matches_latest(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.post("/api/v1/admin/kb/validate", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["errors"] == []
    assert body["rules_total"] >= 500
    assert body["golden"]["failed"] == 0
    assert body["golden"]["passed"] >= 16
    assert body["matches_latest"] is True


async def test_publish_blocked_by_broken_draft(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    database = app.state.database
    async with database.session_factory() as session:
        row = await session.get(RuleRow, "REQ-024")
        assert row is not None
        original = row.body
        row.body = {**row.body, "when": {"fact": "user.nope", "op": "exists"}}
        await session.commit()
    try:
        before = len(await _snapshots(client, headers))
        response = await client.post(
            "/api/v1/admin/kb/publish?comment=битый черновик", headers=headers
        )
        assert response.status_code == 409
        problem = response.json()
        assert problem["type"].endswith("/kb-invalid")
        assert problem["findings"]
        assert len(await _snapshots(client, headers)) == before

        # stateless-валидация показывает те же ошибки, но не падает
        report = await client.post("/api/v1/admin/kb/validate", headers=headers)
        assert report.status_code == 200
        assert report.json()["errors"]
    finally:
        async with database.session_factory() as session:
            row = await session.get(RuleRow, "REQ-024")
            assert row is not None
            row.body = original
            await session.commit()


async def test_publish_blocked_by_broken_golden(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    database = app.state.database
    cases = load_golden(KNOWLEDGE_DIR / "golden")
    async with database.session_factory() as session:
        repo = KnowledgeRepository(session)
        await repo.upsert_table(
            GOLDEN,
            [{"id": "G-XXX", "title": "битый", "answers": {}, "expect": {"feasible": "нет"}}],
        )
        await session.commit()
    try:
        before = len(await _snapshots(client, headers))
        response = await client.post("/api/v1/admin/kb/publish", headers=headers)
        assert response.status_code == 409
        assert response.json()["type"].endswith("/kb-invalid")
        assert len(await _snapshots(client, headers)) == before
    finally:
        async with database.session_factory() as session:
            repo = KnowledgeRepository(session)
            await repo.upsert_table(GOLDEN, cases_to_json(cases))
            await session.commit()


async def test_publish_idempotent_when_nothing_changed(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.post("/api/v1/admin/kb/publish?comment=ещё раз", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] is False
    assert body["rules"] >= 500


async def test_republish_creates_new_version(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    database = app.state.database
    # ускоряем прогон: оставляем один эталонный кейс (в снимок golden не входит)
    cases = load_golden(KNOWLEDGE_DIR / "golden")
    async with database.session_factory() as session:
        repo = KnowledgeRepository(session)
        await repo.upsert_table(GOLDEN, cases_to_json(cases[:1]))
        await session.commit()
    try:
        snapshots = await _snapshots(client, headers)
        assert len(snapshots) == 1
        response = await client.post(
            f"/api/v1/admin/kb/snapshots/{snapshots[0]['id']}/republish", headers=headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] is True
        assert body["version"] == snapshots[0]["version"] + 1
        updated = await _snapshots(client, headers)
        assert len(updated) == 2
        assert updated[0]["checksum"] == snapshots[0]["checksum"]
    finally:
        async with database.session_factory() as session:
            repo = KnowledgeRepository(session)
            await repo.upsert_table(GOLDEN, cases_to_json(cases))
            await session.commit()


async def test_export_kb_round_trip(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    """Экспорт → замена knowledge/ → повторный seed: created=0, updated=0, снимок не создаётся."""
    headers = auth(accounts["knowledge_engineer"])
    # выравниваем снимок с черновиком (в файле тестов выше черновик не менялся)
    response = await client.post("/api/v1/admin/kb/publish?comment=round-trip", headers=headers)
    assert response.status_code == 200
    response = await client.get("/api/v1/admin/kb/export", headers=headers)
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert "questionnaire.yaml" in names
    assert "golden/cases.yaml" in names
    assert "tables/sockets.yaml" in names
    assert "tables/form_factors.yaml" in names
    assert any(name.startswith("rules/manual/") for name in names)
    assert any(name.startswith("rules/generated/") for name in names)

    knowledge = tmp_path / "knowledge"
    archive.extractall(knowledge)
    database = app.state.database
    async with database.session_factory() as session:
        report = await import_files(session, knowledge)
        await session.commit()
    assert report.created == 0
    assert report.updated == 0
    assert report.unchanged == 531

    response = await client.post("/api/v1/admin/kb/publish", headers=headers)
    assert response.json()["created"] is False


async def test_republish_missing_snapshot_is_404(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.post("/api/v1/admin/kb/snapshots/999999/republish", headers=headers)
    assert response.status_code == 404


async def test_publish_with_warnings_succeeds(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
) -> None:
    """Предупреждения §6.2 (например «избыточно») показываются в отчёте, но не блокируют
    публикацию — блокируют только ошибки и упавшие эталонные кейсы."""
    headers = auth(accounts["knowledge_engineer"])
    base = {
        "name": "Тестовое правило: предупреждения не блокируют публикацию",
        "kind": "inference",
        "group": "requirements",
        "priority": 100,
        "cf": 0.6,
        "then": [{"action": "assert", "fact": "req.wifi", "value": True}],
        "explain": "Тест этапа 9: пара правил с избыточностью для проверки предупреждений.",
    }
    payloads = [
        {**base, "code": "REQ-901", "when": {"fact": "user.wifi", "op": "eq", "value": True}},
        {
            **base,
            "code": "REQ-902",
            "when": {
                "all": [
                    {"fact": "user.wifi", "op": "eq", "value": True},
                    {"fact": "user.budget", "op": "gt", "value": 0},
                ]
            },
        },
    ]
    for payload in payloads:
        response = await client.post("/api/v1/admin/rules", json=payload, headers=headers)
        assert response.status_code == 201, response.text
    try:
        report = await client.post("/api/v1/admin/kb/validate", headers=headers)
        assert report.status_code == 200, report.text
        body = report.json()
        assert body["errors"] == []
        assert any(
            "REQ-902" in warning and "избыточно" in warning for warning in body["warnings"]
        ), body["warnings"]

        response = await client.post(
            "/api/v1/admin/kb/publish?comment=с предупреждениями", headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["created"] is True
    finally:
        for code in ("REQ-901", "REQ-902"):
            retired = await client.post(f"/api/v1/admin/rules/{code}/retire", headers=headers)
            assert retired.status_code == 200
        # черновик без тестовых правил снова публикуется новым снимком —
        # после этого «создано=0» для неизменного черновика восстанавливается
        restored = await client.post("/api/v1/admin/kb/publish", headers=headers)
        assert restored.status_code == 200
        assert restored.json()["created"] is True


async def test_vocabulary_lists_all_specs(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.get("/api/v1/admin/kb/vocabulary", headers=headers)
    assert response.status_code == 200
    specs = {item["path"]: item for item in response.json()}
    assert specs["user.budget"]["role"] == "input"
    assert specs["user.budget"]["type"] == "number"
    assert specs["user.resolution"]["values"] == ["1080p", "1440p", "2160p"]
    assert specs["build.cpu.socket"]["role"] == "catalog"
    assert specs["cand.price_kop"]["type"] == "number"
    assert "budget.share.gpu" in specs


async def test_kb_status_is_lightweight_and_tracks_draft(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /admin/kb/status: 200, схема, matches_latest True/False; без компиляции и кейсов."""
    headers = auth(accounts["knowledge_engineer"])
    forbidden = await client.get("/api/v1/admin/kb/status", headers=auth(accounts["catalog_admin"]))
    assert forbidden.status_code == 403

    touched = {"check_case": 0, "compile": 0}

    def counting_check_case(*args: Any, **kwargs: Any) -> list[str]:
        touched["check_case"] += 1
        return []

    def counting_compile(*args: Any, **kwargs: Any) -> Any:
        touched["compile"] += 1
        raise AssertionError("статус не должен компилировать черновик")

    monkeypatch.setattr("app.services.knowledge_store.check_case", counting_check_case)
    monkeypatch.setattr("app.services.knowledge_store.snapshot_from_row", counting_compile)

    response = await client.get("/api/v1/admin/kb/status", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"checksum", "matches_latest", "rules_total"}
    assert len(body["checksum"]) == 64
    assert body["matches_latest"] is True
    assert body["rules_total"] >= 500
    assert touched == {"check_case": 0, "compile": 0}

    # правим черновик: статус отвечает сразу и показывает расхождение со снимком
    database = app.state.database
    async with database.session_factory() as session:
        donor = await session.get(RuleRow, "REQ-024")
        assert donor is not None
        session.add(
            RuleRow(
                code="REQ-990",
                kind=donor.kind,
                group=donor.group,
                name="Тест лёгкого статуса",
                priority=donor.priority,
                cf=donor.cf,
                enabled=True,
                origin=donor.origin,
                body={**donor.body, "code": "REQ-990"},
                explain=donor.explain,
                revision=1,
            )
        )
        await session.commit()
    try:
        changed = await client.get("/api/v1/admin/kb/status", headers=headers)
        assert changed.status_code == 200
        body_changed = changed.json()
        assert body_changed["matches_latest"] is False
        assert body_changed["rules_total"] == body["rules_total"] + 1
        assert body_changed["checksum"] != body["checksum"]
        assert touched == {"check_case": 0, "compile": 0}
    finally:
        async with database.session_factory() as session:
            row = await session.get(RuleRow, "REQ-990")
            assert row is not None
            await session.delete(row)
            await session.commit()
