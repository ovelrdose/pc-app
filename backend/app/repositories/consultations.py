"""Доступ к консультациям и сборкам."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BuildItemRow, BuildRow, ConsultationRow


class ConsultationRepository:
    """Запросы к консультациям, сборкам и их деталям."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def consultation(self, consultation_id: uuid.UUID) -> ConsultationRow | None:
        """Консультация по id."""
        return await self.session.get(ConsultationRow, consultation_id)

    async def build(self, build_id: uuid.UUID) -> BuildRow | None:
        """Сборка по id."""
        return await self.session.get(BuildRow, build_id)

    async def saved_builds(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[BuildRow], int]:
        """Сохранённые сборки пользователя (включая перенесённые с гостевой сессии)."""
        condition = (ConsultationRow.user_id == user_id) & (BuildRow.is_saved.is_(True))
        total = await self.session.scalar(
            select(func.count())
            .select_from(BuildRow)
            .join(ConsultationRow, BuildRow.consultation_id == ConsultationRow.id)
            .where(condition)
        )
        result = await self.session.scalars(
            select(BuildRow)
            .join(ConsultationRow, BuildRow.consultation_id == ConsultationRow.id)
            .where(condition)
            .order_by(BuildRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.all(), int(total or 0)

    async def items(self, build_id: uuid.UUID) -> Sequence[BuildItemRow]:
        """Детали сборки."""
        result = await self.session.scalars(
            select(BuildItemRow).where(BuildItemRow.build_id == build_id)
        )
        return result.all()

    async def builds_of(self, consultation_id: uuid.UUID) -> Sequence[BuildRow]:
        """Сборки консультации в порядке создания."""
        result = await self.session.scalars(
            select(BuildRow)
            .where(BuildRow.consultation_id == consultation_id)
            .order_by(BuildRow.created_at, BuildRow.tier)
        )
        return result.all()

    def add(self, row: ConsultationRow | BuildRow | BuildItemRow) -> None:
        """Добавляет строку в сессию."""
        self.session.add(row)
