"""Критерий этапа 1: seed загружает реальный каталог без ошибок валидации."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.db import Database
from app.expert.frames import ComponentStatus
from app.models import ComponentRow
from app.services.catalog_csv import read_catalog_dir
from scripts.seed import KNOWLEDGE_DIR, seed_catalog

pytestmark = pytest.mark.integration


async def test_seed_real_catalog_is_idempotent(database: Database) -> None:
    result = read_catalog_dir(Path(KNOWLEDGE_DIR) / "catalog")
    assert result.ok

    first = await seed_catalog(database, result)
    assert first.created == len(result.records)
    assert first.status_counts[ComponentStatus.ACTIVE] == len(result.records)

    second = await seed_catalog(database, result)
    assert (second.created, second.updated, second.unchanged) == (0, 0, len(result.records))
    assert second.catalog_revision == first.catalog_revision

    async with database.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ComponentRow))
    assert count == len(result.records)
