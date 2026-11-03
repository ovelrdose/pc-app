"""Доступ к таблицам базы знаний: правила, справочники, опубликованные снимки."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KbSnapshotRow, ReferenceTableRow, RuleRevisionRow, RuleRow


class KnowledgeRepository:
    """Запросы к рабочей копии и снимкам базы знаний."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rules(self) -> Sequence[RuleRow]:
        """Все правила рабочей копии (по коду)."""
        result = await self.session.scalars(select(RuleRow).order_by(RuleRow.code))
        return result.all()

    async def tables(self) -> dict[str, Any]:
        """Справочники и анкета: имя → данные."""
        rows = await self.session.scalars(select(ReferenceTableRow))
        return {row.name: row.data for row in rows}

    async def upsert_table(self, name: str, data: Any) -> bool:  # noqa: ANN401 — JSON справочника
        """Записывает справочник; `True`, если он изменился."""
        row = await self.session.get(ReferenceTableRow, name)
        if row is None:
            self.session.add(ReferenceTableRow(name=name, data=data))
            return True
        if row.data == data:
            return False
        row.data = data
        return True

    def add_rule(self, row: RuleRow) -> None:
        """Добавляет правило (историю пишет `add_revision` после записи правила)."""
        self.session.add(row)

    def add_revision(self, row: RuleRow, change_type: str) -> None:
        """Пишет текущее состояние правила в историю."""
        self.session.add(
            RuleRevisionRow(
                rule=row,
                revision=row.revision,
                body=row.body,
                change_type=change_type,
                author_id=row.updated_by,
            )
        )

    async def latest_snapshot(self) -> KbSnapshotRow | None:
        """Последний опубликованный снимок."""
        return await self.session.scalar(
            select(KbSnapshotRow).order_by(KbSnapshotRow.version.desc()).limit(1)
        )

    async def latest_snapshot_id(self) -> int | None:
        """Идентификатор последнего опубликованного снимка."""
        return await self.session.scalar(
            select(KbSnapshotRow.id).order_by(KbSnapshotRow.version.desc()).limit(1)
        )

    async def snapshot(self, snapshot_id: int) -> KbSnapshotRow | None:
        """Снимок по идентификатору."""
        return await self.session.get(KbSnapshotRow, snapshot_id)

    async def snapshots(self) -> Sequence[KbSnapshotRow]:
        """Все снимки, новые первыми."""
        result = await self.session.scalars(
            select(KbSnapshotRow).order_by(KbSnapshotRow.version.desc())
        )
        return result.all()

    async def next_version(self) -> int:
        """Номер следующей версии снимка."""
        current = await self.session.scalar(select(func.max(KbSnapshotRow.version)))
        return (current or 0) + 1

    def add_snapshot(self, row: KbSnapshotRow) -> None:
        """Добавляет снимок."""
        self.session.add(row)
