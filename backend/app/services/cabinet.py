"""Личный кабинет: сохранённые сборки пользователя."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRow
from app.repositories.consultations import ConsultationRepository
from app.schemas.auth import MeBuildsOut, SavedBuildOut
from app.services.consultations import summary
from app.services.snapshot_cache import SnapshotCache


class CabinetService:
    """Сценарии личного кабинета."""

    def __init__(self, session: AsyncSession, cache: SnapshotCache) -> None:
        self.session = session
        self.cache = cache
        self.repo = ConsultationRepository(session)

    async def saved_builds(self, user: UserRow, *, limit: int, offset: int) -> MeBuildsOut:
        """Сохранённые сборки аккаунта: новые первыми, с краткими карточками деталей."""
        rows, total = await self.repo.saved_builds(user.id, limit=limit, offset=offset)
        catalog = await self.cache.catalog(self.session)
        builds = []
        for row in rows:
            card = summary(row, await self.repo.items(row.id), catalog)
            builds.append(SavedBuildOut(consultation_id=row.consultation_id, build=card))
        return MeBuildsOut(builds=builds, total=total)
