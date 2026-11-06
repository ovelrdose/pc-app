"""Первичное наполнение БД из `knowledge/`: `uv run python -m scripts.seed [--dry-run]`.

Загружает каталог, импортирует правила, справочники и анкету в рабочую копию БЗ и публикует
снимок (статические проверки + golden cases). Повторный запуск безопасен.
Загрузка «всё или ничего»: при любой ошибке в файлах база не меняется.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.core.db import Database
from app.core.logging import configure_logging
from app.expert.frames import KnownSlotValues
from app.models import ComponentSource
from app.services.catalog_csv import CatalogDirResult, read_catalog_dir
from app.services.catalog_loader import LoadReport, load_catalog
from app.services.knowledge_files import KnowledgeFileError, load_tables
from app.services.knowledge_store import (
    KnowledgeValidationError,
    PublishReport,
    import_files,
    publish,
)
from app.services.snapshot_cache import SnapshotCache

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

logger = structlog.get_logger("seed")


def report_errors(result: CatalogDirResult) -> None:
    """Пишет в лог ошибки разбора по файлам."""
    for file_name, errors in result.errors.items():
        for error in errors:
            logger.error("catalog_row_rejected", file=file_name, error=str(error))
    for file_name in result.missing_files:
        logger.warning("catalog_file_missing", file=file_name)


async def seed_catalog(
    database: Database, result: CatalogDirResult, known: KnownSlotValues | None = None
) -> LoadReport:
    """Загружает прочитанный каталог в БД одной транзакцией; `known` — для статуса needs_kb."""
    async with database.session_factory() as session:
        report = await load_catalog(
            session, result.records, source=ComponentSource.MANUAL, known=known
        )
        await session.commit()
    return report


async def seed_knowledge(
    database: Database, knowledge_dir: Path, *, golden: bool = True
) -> PublishReport:
    """Импортирует базу знаний из файлов и публикует снимок (с golden cases, если нужно).

    Эталонные кейсы `import_files` заливает в рабочую копию (`reference_tables['golden']`),
    публикация читает их оттуда (ADR 0010 п.2); `--skip-golden` публикует без прогона кейсов.
    """
    async with database.session_factory() as session:
        imported = await import_files(session, knowledge_dir)
        logger.info(
            "kb_imported",
            created=imported.created,
            updated=imported.updated,
            unchanged=imported.unchanged,
            tables=list(imported.tables_changed),
            retired=list(imported.retired),
        )
        catalog = (await SnapshotCache().catalog(session)).snapshot if golden else None
        report = await publish(session, comment="seed из knowledge/", catalog=catalog)
        await session.commit()
    return report


async def main(argv: list[str] | None = None) -> int:
    """Точка входа: 0 — успех, 1 — ошибки в файлах знаний."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="только проверить файлы")
    parser.add_argument("--knowledge-dir", type=Path, default=KNOWLEDGE_DIR)
    parser.add_argument(
        "--skip-golden", action="store_true", help="публиковать без прогона эталонных кейсов"
    )
    args = parser.parse_args(argv)
    configure_logging()

    try:
        known = load_tables(args.knowledge_dir / "tables").known_slot_values()
    except KnowledgeFileError as exc:
        logger.error("seed_aborted", reason=str(exc))
        return 1
    result = read_catalog_dir(args.knowledge_dir / "catalog")
    report_errors(result)
    if not result.ok:
        logger.error("seed_aborted", reason="ошибки в файлах каталога, база не изменена")
        return 1
    logger.info("catalog_parsed", records=len(result.records))
    if args.dry_run:
        return 0

    database = Database(get_settings())
    try:
        report = await seed_catalog(database, result, known)
        published = await seed_knowledge(database, args.knowledge_dir, golden=not args.skip_golden)
    except KnowledgeValidationError as exc:
        logger.error("kb_publish_failed", reason=str(exc), details=exc.extra)
        return 1
    finally:
        await database.dispose()
    logger.info(
        "kb_published" if published.created else "kb_up_to_date",
        snapshot_id=published.snapshot_id,
        version=published.version,
        rules=published.rules,
        golden_cases=published.golden_cases,
    )
    logger.info(
        "seed_done",
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
        catalog_revision=report.catalog_revision,
        statuses={status.value: count for status, count in report.status_counts.items() if count},
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
