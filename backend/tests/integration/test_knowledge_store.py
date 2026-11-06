"""База знаний в БД: импорт, ревизии, публикация, проверки, кэш снимков."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.core.db import Database
from app.models import RuleRevisionRow, RuleRow
from app.repositories.meta import MetaRepository
from app.services import knowledge_store
from app.services.catalog_csv import read_catalog_dir
from app.services.knowledge_files import load_golden, load_tables
from app.services.knowledge_store import KnowledgeValidationError, import_files, publish
from app.services.snapshot_cache import KnowledgeNotPublishedError, SnapshotCache
from scripts.seed import KNOWLEDGE_DIR, seed_catalog

pytestmark = pytest.mark.integration


async def seed_catalog_only(database: Database) -> None:
    known = load_tables(KNOWLEDGE_DIR / "tables").known_slot_values()
    await seed_catalog(database, read_catalog_dir(KNOWLEDGE_DIR / "catalog"), known)


async def test_import_is_idempotent_and_tracks_revisions(database: Database) -> None:
    async with database.session_factory() as session:
        first = await import_files(session, KNOWLEDGE_DIR)
        await session.commit()
    assert first.created >= 500
    assert "questionnaire" in first.tables_changed
    async with database.session_factory() as session:
        again = await import_files(session, KNOWLEDGE_DIR)
        await session.commit()
        assert (again.created, again.updated, again.tables_changed) == (0, 0, ())
        rule = await session.get(RuleRow, "REQ-024")
        assert rule is not None
        rule.body = {**rule.body, "cf": 0.55}  # кто-то поправил правило в рабочей копии
        await session.commit()
    async with database.session_factory() as session:
        restored = await import_files(session, KNOWLEDGE_DIR)
        await session.commit()
        assert restored.updated == 1
        rule = await session.get(RuleRow, "REQ-024")
        assert rule is not None
        assert rule.revision == 2
        history = await session.scalar(
            select(func.count()).where(RuleRevisionRow.rule_code == "REQ-024")
        )
        assert history == 2


async def test_import_retires_rules_from_registry(database: Database) -> None:
    async with database.session_factory() as session:
        await import_files(session, KNOWLEDGE_DIR)
        await session.commit()
        # правило, выведенное позже, но ещё живое в рабочей копии (как после прежнего seed)
        donor = await session.get(RuleRow, "REQ-024")
        assert donor is not None
        session.add(
            RuleRow(
                code="REQ-012",
                kind=donor.kind,
                group=donor.group,
                name="12 ГБ видеопамяти для AAA в 2K",
                priority=donor.priority,
                cf=donor.cf,
                enabled=True,
                origin=donor.origin,
                body={**donor.body, "code": "REQ-012"},
                explain=donor.explain,
                revision=1,
            )
        )
        await session.commit()
    async with database.session_factory() as session:
        report = await import_files(session, KNOWLEDGE_DIR)
        await session.commit()
        assert report.retired == ("REQ-012",)
        rule = await session.get(RuleRow, "REQ-012")
        assert rule is not None
        assert (rule.enabled, rule.revision, rule.body["enabled"]) == (False, 2, False)
        history = await session.scalar(
            select(func.count()).where(
                RuleRevisionRow.rule_code == "REQ-012", RuleRevisionRow.change_type == "retire"
            )
        )
        assert history == 1
    async with database.session_factory() as session:
        again = await import_files(session, KNOWLEDGE_DIR)
        await session.commit()
        assert again.retired == ()
    await seed_catalog_only(database)
    async with database.session_factory() as session:
        published = await publish(session)
        await session.commit()
        assert published.rules == 531  # выведенное правило в снимок не попало


async def test_publish_creates_snapshot_once(database: Database) -> None:
    await seed_catalog_only(database)
    async with database.session_factory() as session:
        await import_files(session, KNOWLEDGE_DIR)
        first = await publish(session, comment="первая")
        await session.commit()
        second = await publish(session)
        await session.commit()
    assert (first.created, first.version) == (True, 1)
    assert first.rules >= 500
    assert (second.created, second.snapshot_id) == (False, first.snapshot_id)


async def test_checks_run_in_thread_with_connection_released(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """validate/publish гоняют проверки в worker-потоке; к его старту соединение уже в пуле."""
    await seed_catalog_only(database)
    async with database.session_factory() as session:
        await import_files(session, KNOWLEDGE_DIR)
        await publish(session, golden=[], catalog=None)  # эталоны не нужны: тест про потоки
        await session.commit()
    observed: list[bool] = []
    real_to_thread = asyncio.to_thread

    async def spy_to_thread(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        observed.append(session.in_transaction())
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(knowledge_store, "to_thread", spy_to_thread)
    async with database.session_factory() as session:
        report = await knowledge_store.validate_draft(session)
        assert report.errors == ()
        assert observed == [False]  # транзакция чтения закрыта до старта прогона
        published = await knowledge_store.publish(session, golden=[], catalog=None)
        assert published.created is False  # черновик совпадает с опубликованным снимком
        assert observed == [False, False]


async def test_publish_blocked_by_validation_errors(database: Database) -> None:
    async with database.session_factory() as session:
        await import_files(session, KNOWLEDGE_DIR)
        rule = await session.get(RuleRow, "REQ-024")
        assert rule is not None
        rule.body = {**rule.body, "when": {"fact": "user.nope", "op": "exists"}}
        await session.flush()
        with pytest.raises(KnowledgeValidationError) as info:
            await publish(session)
    findings = info.value.extra["findings"]
    assert isinstance(findings, list)
    assert any("user.nope" in str(finding) for finding in findings)


async def test_publish_with_golden_cases(database: Database) -> None:
    await seed_catalog_only(database)
    async with database.session_factory() as session:
        await import_files(session, KNOWLEDGE_DIR)
        catalog = await SnapshotCache().catalog(session)
        report = await publish(
            session, golden=load_golden(KNOWLEDGE_DIR / "golden"), catalog=catalog.snapshot
        )
        await session.commit()
    assert report.created
    assert report.golden_cases >= 16


async def test_cache_reloads_on_changes(database: Database) -> None:
    await seed_catalog_only(database)
    cache = SnapshotCache()
    async with database.session_factory() as session:
        with pytest.raises(KnowledgeNotPublishedError):
            await cache.knowledge(session)
        await import_files(session, KNOWLEDGE_DIR)
        await publish(session)
        await session.commit()
        snapshot_id, first = await cache.knowledge(session)
        assert (await cache.knowledge(session))[1] is first
        catalog = await cache.catalog(session)
        assert await cache.catalog(session) is catalog
        await MetaRepository(session).bump_catalog_revision()
        await session.commit()
        reloaded = await cache.catalog(session)
        assert reloaded is not catalog
        assert reloaded.revision == catalog.revision + 1
        assert snapshot_id == 1


async def test_api_without_published_kb(app: FastAPI, database: Database) -> None:
    app.state.database = database
    app.state.cache = SnapshotCache()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/questionnaire")
    assert response.status_code == 503
    assert response.json()["type"].endswith("/kb-not-published")
