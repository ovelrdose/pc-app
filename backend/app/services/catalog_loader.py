"""Загрузка проверенных позиций каталога в БД (seed, позже — импорт из админки)."""

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.expert.frames import ComponentStatus, KnownSlotValues, compute_status
from app.models import ComponentRow, ComponentSource
from app.repositories.components import ComponentRepository, split_frame
from app.repositories.meta import MetaRepository
from app.services.catalog_csv import CatalogRecord

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LoadReport:
    """Итог загрузки: сколько позиций добавлено, обновлено и не изменилось."""

    created: int
    updated: int
    unchanged: int
    catalog_revision: int
    status_counts: dict[ComponentStatus, int]


def _row_values(
    record: CatalogRecord, *, known: KnownSlotValues | None, discontinued: bool
) -> dict[str, Any]:
    columns, specs, perf = split_frame(record.frame)
    status = compute_status(record.frame, known=known, discontinued=discontinued)
    return {
        **columns,
        "specs": specs,
        "perf": perf,
        "price_checked_at": record.price_checked_at,
        "price_note": record.price_note,
        "status": status.status,
        "status_issues": list(status.issues),
    }


async def load_catalog(
    session: AsyncSession,
    records: list[CatalogRecord],
    *,
    source: ComponentSource,
    known: KnownSlotValues | None = None,
    dry_run: bool = False,
) -> LoadReport:
    """Добавляет новые позиции и обновляет изменившиеся по артикулу; ревизия растёт при изменениях.

    Позиции, которых нет в `records`, не трогаются. Снятые с продажи (`inactive`) остаются такими.
    `dry_run=True` только считает, что изменилось бы, не записывая. Транзакцию фиксирует
    вызывающий код.
    """
    repo = ComponentRepository(session)
    existing = await repo.get_by_skus(record.frame.sku for record in records)
    created = updated = unchanged = 0
    status_counts = dict.fromkeys(ComponentStatus, 0)

    for record in records:
        row = existing.get(record.frame.sku)
        discontinued = row is not None and row.status is ComponentStatus.INACTIVE
        values = _row_values(record, known=known, discontinued=discontinued)
        status_counts[values["status"]] += 1
        if row is None:
            if not dry_run:
                repo.add(ComponentRow(**values, source=source))
            created += 1
            continue
        changed = {key: value for key, value in values.items() if getattr(row, key) != value}
        if not changed:
            unchanged += 1
            continue
        if not dry_run:
            for key, value in changed.items():
                setattr(row, key, value)
        updated += 1

    if dry_run:
        revision = await MetaRepository(session).get_catalog_revision()
    else:
        meta = MetaRepository(session)
        if created or updated:
            await session.flush()
            revision = await meta.bump_catalog_revision()
        else:
            revision = await meta.get_catalog_revision()
    logger.info(
        "catalog_loaded",
        dry_run=dry_run,
        created=created,
        updated=updated,
        unchanged=unchanged,
        catalog_revision=revision,
    )
    return LoadReport(created, updated, unchanged, revision, status_counts)
