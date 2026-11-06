"""Кэш снимков: double-checked locking — конкурентные запросы собирают снимок ровно один раз."""

import asyncio
from collections.abc import Sequence

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Database
from app.expert.knowledge import KnowledgeSnapshot
from app.models import ComponentRow
from app.repositories.components import ComponentRepository
from app.services.catalog_csv import read_catalog_dir
from app.services.knowledge_files import load_tables
from app.services.knowledge_store import import_files, publish
from app.services.snapshot_cache import CatalogData, SnapshotCache, snapshot_from_row
from scripts.seed import KNOWLEDGE_DIR, seed_catalog

pytestmark = pytest.mark.integration


async def _seed_minimal(database: Database) -> None:
    """Каталог и одна опубликованная версия БЗ без прогона эталонных кейсов."""
    known = load_tables(KNOWLEDGE_DIR / "tables").known_slot_values()
    await seed_catalog(database, read_catalog_dir(KNOWLEDGE_DIR / "catalog"), known)
    async with database.session_factory() as session:
        await import_files(session, KNOWLEDGE_DIR)
        await publish(session, golden=[], catalog=None)
        await session.commit()


async def test_catalog_built_once_under_concurrency(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N параллельных запросов при пустом кэше: каталог собирается один раз (проверка в локе)."""
    await _seed_minimal(database)
    cache = SnapshotCache()
    calls = 0
    original_all = ComponentRepository.all

    async def counting_all(self: ComponentRepository) -> Sequence[ComponentRow]:
        nonlocal calls
        calls += 1
        return await original_all(self)

    monkeypatch.setattr(ComponentRepository, "all", counting_all)
    sessions = [database.session_factory() for _ in range(8)]
    try:
        results = await asyncio.gather(*(cache.catalog(session) for session in sessions))
    finally:
        for session in sessions:
            await session.close()
    assert calls == 1
    assert all(isinstance(result, CatalogData) for result in results)
    assert all(result is results[0] for result in results)


async def test_knowledge_built_once_under_concurrency(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N параллельных запросов при пустом кэше: снимок БЗ собирается и компилируется один раз."""
    await _seed_minimal(database)
    cache = SnapshotCache()
    builds = 0

    def counting_from_row(
        version: str,
        rules: list[dict[str, object]],
        tables: dict[str, object],
        questionnaire: object,
    ) -> KnowledgeSnapshot:
        nonlocal builds
        builds += 1
        return snapshot_from_row(version, rules, tables, questionnaire)

    monkeypatch.setattr("app.services.snapshot_cache.snapshot_from_row", counting_from_row)
    sessions: list[AsyncSession] = [database.session_factory() for _ in range(6)]
    try:
        results = await asyncio.gather(
            *(cache.knowledge(session, snapshot_id=1) for session in sessions)
        )
    finally:
        for session in sessions:
            await session.close()
    assert builds == 1
    assert all(snapshot is results[0][1] for _, snapshot in results)
