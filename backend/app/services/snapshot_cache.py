"""Кэш снимков в памяти процесса (архитектура §4.2): база знаний по id, каталог по ревизии."""

import asyncio
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.expert.catalog import CatalogEntry, CatalogSnapshot
from app.expert.dsl.schema import Rule
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.questionnaire import Questionnaire
from app.expert.tables import KnowledgeTables
from app.repositories.components import ComponentRepository, row_to_frame
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.meta import MetaRepository

logger = structlog.get_logger(__name__)

KNOWLEDGE_CACHE_SIZE = 4


class KnowledgeNotPublishedError(DomainError):
    """Нет ни одного опубликованного снимка базы знаний."""

    status = 503
    code = "kb-not-published"
    title = "База знаний не опубликована"


@dataclass(frozen=True, slots=True)
class CatalogData:
    """Снимок каталога и соответствие артикулов идентификаторам строк БД."""

    revision: int
    snapshot: CatalogSnapshot
    ids: dict[str, uuid.UUID]
    skus: dict[uuid.UUID, str]


def snapshot_from_row(
    version: str, rules: list[dict[str, object]], tables: dict[str, object], questionnaire: object
) -> KnowledgeSnapshot:
    """Собирает и компилирует снимок базы знаний из JSON, сохранённого в БД."""
    return KnowledgeSnapshot.build(
        version,
        [Rule.model_validate(item) for item in rules],
        KnowledgeTables.model_validate(tables),
        Questionnaire.model_validate(questionnaire),
    )


@dataclass(slots=True)
class SnapshotCache:
    """Держит скомпилированные снимки БЗ и каталог; перечитывает их при изменениях."""

    _knowledge: OrderedDict[int, KnowledgeSnapshot] = field(default_factory=OrderedDict)
    _catalog: CatalogData | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def knowledge(
        self, session: AsyncSession, snapshot_id: int | None = None
    ) -> tuple[int, KnowledgeSnapshot]:
        """Снимок БЗ по id (по умолчанию — последний опубликованный)."""
        repo = KnowledgeRepository(session)
        if snapshot_id is None:
            snapshot_id = await repo.latest_snapshot_id()
            if snapshot_id is None:
                raise KnowledgeNotPublishedError(
                    "Опубликуйте базу знаний: uv run python -m scripts.seed"
                )
        cached = self._knowledge.get(snapshot_id)
        if cached is not None:
            self._knowledge.move_to_end(snapshot_id)
            return snapshot_id, cached
        async with self._lock:
            # повторная проверка под локом: пока ждали, снимок мог собрать другой запрос
            cached = self._knowledge.get(snapshot_id)
            if cached is not None:
                self._knowledge.move_to_end(snapshot_id)
                return snapshot_id, cached
            row = await repo.snapshot(snapshot_id)
            if row is None:
                raise KnowledgeNotPublishedError(f"снимок базы знаний {snapshot_id} не найден")
            snapshot = snapshot_from_row(
                f"v{row.version}", row.rules, row.tables, row.questionnaire
            )
            self._knowledge[snapshot_id] = snapshot
            while len(self._knowledge) > KNOWLEDGE_CACHE_SIZE:
                self._knowledge.popitem(last=False)
            logger.info("kb_snapshot_loaded", snapshot_id=snapshot_id, rules=len(snapshot.rules))
            return snapshot_id, snapshot

    async def catalog(self, session: AsyncSession) -> CatalogData:
        """Каталог текущей ревизии; перечитывается, если ревизия выросла."""
        data = self._catalog
        if data is not None:
            revision = await MetaRepository(session).get_catalog_revision()
            if data.revision == revision:
                return data
        async with self._lock:
            # повторная проверка под локом; ревизию читаем заново, чтобы свежий снимок
            # не подменить устаревшим номером ревизии, прочитанным до ожидания лока
            revision = await MetaRepository(session).get_catalog_revision()
            if self._catalog is not None and self._catalog.revision == revision:
                return self._catalog
            rows = await ComponentRepository(session).all()
            entries = [CatalogEntry(row_to_frame(row), row.status) for row in rows]
            data = CatalogData(
                revision,
                CatalogSnapshot.build(revision, entries),
                {row.sku: row.id for row in rows},
                {row.id: row.sku for row in rows},
            )
            self._catalog = data
            logger.info("catalog_loaded", revision=revision, components=len(rows))
            return data
