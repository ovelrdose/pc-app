"""Загрузка каталога в БД: добавление, обновление, ревизия, снятые с продажи."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.expert.frames import FRAMES_BY_CATEGORY, Category, ComponentStatus
from app.models import ComponentRow, ComponentSource
from app.repositories.components import row_to_frame
from app.services.catalog_csv import CatalogRecord
from app.services.catalog_loader import load_catalog
from tests.factories import slots

pytestmark = pytest.mark.integration


def record(category: Category, **overrides: object) -> CatalogRecord:
    frame = FRAMES_BY_CATEGORY[category].model_validate(slots(category, **overrides))
    return CatalogRecord(frame=frame, price_checked_at=None, price_note="ориентир")


async def load(session: AsyncSession, records: list[CatalogRecord]):  # type: ignore[no-untyped-def]
    report = await load_catalog(session, records, source=ComponentSource.MANUAL)
    await session.commit()
    return report


async def test_first_load_creates_rows_and_bumps_revision(session: AsyncSession) -> None:
    report = await load(session, [record(category) for category in Category])
    assert (report.created, report.updated, report.unchanged) == (len(Category), 0, 0)
    assert report.catalog_revision == 1
    assert report.status_counts[ComponentStatus.ACTIVE] == len(Category)

    row = await session.scalar(select(ComponentRow).where(ComponentRow.sku == "GPU-TEST-4060"))
    assert row is not None
    assert row.perf == {"perf_raster": 100.0, "perf_rt": 100.0}
    assert row.specs["length_mm"] == 250
    assert row_to_frame(row) == record(Category.GPU).frame


async def test_reload_without_changes_keeps_revision(session: AsyncSession) -> None:
    await load(session, [record(Category.CPU)])
    report = await load(session, [record(Category.CPU)])
    assert (report.created, report.updated, report.unchanged) == (0, 0, 1)
    assert report.catalog_revision == 1


async def test_changed_price_updates_row_and_bumps_revision(session: AsyncSession) -> None:
    await load(session, [record(Category.CPU)])
    report = await load(session, [record(Category.CPU, price_kop=1_799_000)])
    assert (report.updated, report.catalog_revision) == (1, 2)
    row = await session.scalar(select(ComponentRow))
    assert row is not None
    assert row.price_kop == 1_799_000


async def test_incomplete_status_is_stored_with_reasons(session: AsyncSession) -> None:
    await load(session, [record(Category.CPU, perf_multi=None)])
    row = await session.scalar(select(ComponentRow))
    assert row is not None
    assert row.status is ComponentStatus.INCOMPLETE
    assert row.status_issues == ["perf_multi не заполнен"]


async def test_discontinued_component_stays_inactive(session: AsyncSession) -> None:
    await load(session, [record(Category.CPU)])
    row = await session.scalar(select(ComponentRow))
    assert row is not None
    row.status = ComponentStatus.INACTIVE
    await session.commit()

    await load(session, [record(Category.CPU, price_kop=1_700_000)])
    await session.refresh(row)
    assert row.status is ComponentStatus.INACTIVE
    assert row.price_kop == 1_700_000
