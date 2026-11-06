"""Админка каталога (ADR 0010 п.1, п.7, п.8): CRUD компонентов, импорт CSV, экспорт, журнал.

Статус компонента пересчитывается `compute_status` по справочникам последнего опубликованного
снимка БЗ (SnapshotCache; снимка нет — `known=None`, архитектура §17). Удаления нет: компонент
снимается с продажи статусом `inactive`.
"""

import io
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.expert.frames import (
    Category,
    ComponentFrame,
    ComponentStatus,
    KnownSlotValues,
    compute_status,
)
from app.models import (
    CatalogImportRow,
    CatalogImportStatus,
    ComponentRow,
    ComponentSource,
    UserRow,
)
from app.repositories.catalog_imports import CatalogImportRepository
from app.repositories.components import ComponentRepository, row_to_frame, split_frame
from app.repositories.meta import MetaRepository
from app.schemas.catalog import ComponentOut, ComponentPage, ComponentQuery
from app.services.catalog_csv import dump_catalog_csv, parse_catalog_csv
from app.services.catalog_loader import load_catalog
from app.services.snapshot_cache import KnowledgeNotPublishedError, SnapshotCache

logger = structlog.get_logger(__name__)


class CatalogImportError(DomainError):
    """Файл импорта отклонён: не UTF-8, неверный заголовок или все строки отклонены."""

    status = 422
    code = "catalog-import-invalid"
    title = "Файл импорта не подходит"


class CatalogImportTooLargeError(DomainError):
    """Файл импорта больше лимита настроек (`catalog_import_max_bytes`)."""

    status = 413
    code = "catalog-import-too-large"
    title = "Файл импорта слишком большой"


class ComponentStatusPatchError(DomainError):
    """Руками можно только снять компонент с продажи или вернуть его к продаже."""

    status = 422
    code = "component-status-invalid"
    title = "Недопустимый статус"


@dataclass(frozen=True, slots=True)
class CatalogImportReport:
    """Отчёт импорта каталога: что изменилось, какие строки отклонены, запись журнала."""

    import_id: uuid.UUID
    status: CatalogImportStatus
    dry_run: bool
    created: int
    updated: int
    unchanged: int
    catalog_revision: int
    status_counts: dict[str, int]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


class CatalogAdminService:
    """Сценарии администратора каталога."""

    def __init__(self, session: AsyncSession, cache: SnapshotCache) -> None:
        self.session = session
        self.cache = cache
        self.components = ComponentRepository(session)

    async def _known_slots(self) -> KnownSlotValues | None:
        """Значения слотов последнего опубликованного снимка БЗ; снимка нет — `None` (§17)."""
        try:
            _snapshot_id, snapshot = await self.cache.knowledge(self.session)
        except KnowledgeNotPublishedError:
            return None
        return snapshot.known_slot_values

    async def list_components(
        self, query: ComponentQuery, *, limit: int, offset: int
    ) -> ComponentPage:
        """Страница каталога по фильтрам админки (включая снятые с продажи)."""
        rows, total = await self.components.list(query, limit=limit, offset=offset)
        return ComponentPage(
            items=[ComponentOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_component(self, component_id: uuid.UUID) -> ComponentOut:
        """Карточка компонента; `NotFoundError`, если его нет."""
        row = await self.components.get(component_id)
        if row is None:
            raise NotFoundError("Компонент не найден", component_id=str(component_id))
        return ComponentOut.model_validate(row)

    async def create_component(self, frame: ComponentFrame, *, author: UserRow) -> ComponentOut:
        """Создаёт компонент из JSON фрейма категории; `source=manual`, статус по §17."""
        if await self.components.get_by_skus([frame.sku]):
            raise ConflictError(f"Компонент с артикулом {frame.sku} уже есть")
        known = await self._known_slots()
        status = compute_status(frame, known=known)
        columns, specs, perf = split_frame(frame)
        row = ComponentRow(
            **columns,
            specs=specs,
            perf=perf,
            source=ComponentSource.MANUAL,
            status=status.status,
            status_issues=list(status.issues),
        )
        self.components.add(row)
        await self.session.flush()
        await MetaRepository(self.session).bump_catalog_revision()
        logger.info("component_created", sku=frame.sku, author_id=str(author.id))
        return ComponentOut.model_validate(row)

    async def replace_component(
        self, component_id: uuid.UUID, frame: ComponentFrame, *, author: UserRow
    ) -> ComponentOut:
        """Полностью заменяет компонент фреймом; источник — `manual`, статус пересчитывается.

        Сведения о проверке цены (`price_checked_at`, `price_note`) фрейм не описывает —
        сохраняются прежние. Снятый с продажи компонент остаётся `inactive` (§17).
        """
        row = await self._row_or_404(component_id)
        owner = (await self.components.get_by_skus([frame.sku])).get(frame.sku)
        if owner is not None and owner.id != component_id:
            raise ConflictError(f"Артикул {frame.sku} занят другим компонентом")
        known = await self._known_slots()
        status = compute_status(
            frame, known=known, discontinued=row.status is ComponentStatus.INACTIVE
        )
        columns, specs, perf = split_frame(frame)
        for key, value in {**columns, "specs": specs, "perf": perf}.items():
            setattr(row, key, value)
        row.source = ComponentSource.MANUAL
        row.status = status.status
        row.status_issues = list(status.issues)
        await self.session.flush()
        await MetaRepository(self.session).bump_catalog_revision()
        logger.info("component_replaced", sku=frame.sku, author_id=str(author.id))
        return ComponentOut.model_validate(row)

    async def patch_component(
        self,
        component_id: uuid.UUID,
        *,
        in_stock: bool | None,
        status: ComponentStatus | None,
        author: UserRow,
    ) -> ComponentOut:
        """Служебные поля: наличие и статус (снять с продажи / вернуть к продаже)."""
        row = await self._row_or_404(component_id)
        changed = False
        if in_stock is not None and row.in_stock != in_stock:
            row.in_stock = in_stock
            changed = True
        if status is not None and status is not row.status:
            if status not in (ComponentStatus.ACTIVE, ComponentStatus.INACTIVE):
                raise ComponentStatusPatchError(
                    "Статус вручную можно только снять с продажи (inactive) "
                    "или вернуть к продаже (active)"
                )
            row.status = status
            row.status_issues = [] if status is ComponentStatus.ACTIVE else row.status_issues
            changed = True
        if changed:
            await self.session.flush()
            await MetaRepository(self.session).bump_catalog_revision()
            logger.info(
                "component_patched",
                sku=row.sku,
                in_stock=row.in_stock,
                status=row.status.value,
                author_id=str(author.id),
            )
        return ComponentOut.model_validate(row)

    async def import_csv(
        self,
        *,
        filename: str,
        content: bytes,
        category: Category,
        dry_run: bool,
        max_bytes: int,
        author: UserRow,
    ) -> CatalogImportReport:
        """Импортирует CSV одной категории (ADR 0010 п.1): разбор, dry-run или применение.

        Каждый вызов пишет строку в журнал `catalog_imports`, включая dry-run. Файл больше
        лимита, не в UTF-8 или с неверным заголовком отклоняются: в журнале `failed`, клиенту
        — problem+json; отзыв токенов не требуется, поэтому отзыв фиксируется до raise.
        """
        if len(content) > max_bytes:
            await self._journal_failed(filename, dry_run, author, f"файл больше {max_bytes} байт")
            raise CatalogImportTooLargeError(f"Файл больше лимита {max_bytes} байт")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            await self._journal_failed(filename, dry_run, author, "файл не в кодировке UTF-8")
            raise CatalogImportError("Файл должен быть в кодировке UTF-8") from exc
        parsed = parse_catalog_csv(text, category)
        if parsed.fatal:
            detail = "; ".join(str(error) for error in parsed.errors)
            await self._journal_failed(filename, dry_run, author, detail)
            raise CatalogImportError(f"Файл отклонён: {detail}")

        known = await self._known_slots()
        load = await load_catalog(
            self.session,
            [record for record in parsed.records],
            source=ComponentSource.IMPORT,
            known=known,
            dry_run=dry_run,
        )
        errors = tuple(str(error) for error in parsed.errors)
        warnings = [
            f"{status.value}: {count}"
            for status, count in load.status_counts.items()
            if count and status is not ComponentStatus.ACTIVE
        ]
        journal = await self._journal(
            filename=filename,
            dry_run=dry_run,
            status=CatalogImportStatus.COMPLETED,
            report={
                "category": category.value,
                "created": load.created,
                "updated": load.updated,
                "unchanged": load.unchanged,
                "status_counts": {s.value: c for s, c in load.status_counts.items() if c},
                "errors": list(errors),
                "warnings": warnings,
                "catalog_revision": load.catalog_revision,
            },
            author=author,
        )
        logger.info(
            "catalog_imported",
            filename=filename,
            dry_run=dry_run,
            created=load.created,
            updated=load.updated,
            author_id=str(author.id),
        )
        return CatalogImportReport(
            import_id=journal.id,
            status=CatalogImportStatus.COMPLETED,
            dry_run=dry_run,
            created=load.created,
            updated=load.updated,
            unchanged=load.unchanged,
            catalog_revision=load.catalog_revision,
            status_counts={s.value: c for s, c in load.status_counts.items() if c},
            errors=errors,
            warnings=tuple(warnings),
        )

    async def export_zip(self) -> bytes:
        """Zip со всеми категориями: `<category>.csv` в формате §12 (колонки `csv_columns`)."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for category in Category:
                rows, _total = await self.components.list(
                    ComponentQuery(category=category, include_inactive=True),
                    limit=10_000,
                    offset=0,
                )
                lines = [(row_to_frame(row), row.price_checked_at, row.price_note) for row in rows]
                archive.writestr(f"{category.value}.csv", dump_catalog_csv(lines, category))
        return buffer.getvalue()

    async def _row_or_404(self, component_id: uuid.UUID) -> ComponentRow:
        row = await self.components.get(component_id)
        if row is None:
            raise NotFoundError("Компонент не найден", component_id=str(component_id))
        return row

    async def _journal(
        self,
        *,
        filename: str,
        dry_run: bool,
        status: CatalogImportStatus,
        report: dict[str, Any],
        author: UserRow,
    ) -> CatalogImportRow:
        row = CatalogImportRow(
            filename=filename,
            dry_run=dry_run,
            status=status,
            report=report,
            created_by=author.id,
        )
        CatalogImportRepository(self.session).add(row)
        await self.session.flush()  # id журнала нужен в ответе сразу
        return row

    async def _journal_failed(
        self, filename: str, dry_run: bool, author: UserRow, reason: str
    ) -> None:
        """Пишет `failed`-запись и фиксирует её до raise (транзакция запроса откатится)."""
        await self._journal(
            filename=filename,
            dry_run=dry_run,
            status=CatalogImportStatus.FAILED,
            report={"errors": [reason]},
            author=author,
        )
        await self.session.commit()
