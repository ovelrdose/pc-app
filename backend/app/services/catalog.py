"""Публичный каталог: список, карточка компонента, схемы фреймов."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.expert.frames import FRAMES_BY_CATEGORY
from app.repositories.components import ComponentRepository
from app.schemas.catalog import ComponentOut, ComponentPage, ComponentQuery, FrameOut


class CatalogService:
    """Чтение каталога для клиентов."""

    def __init__(self, session: AsyncSession) -> None:
        self.components = ComponentRepository(session)

    async def list_components(
        self, query: ComponentQuery, *, limit: int, offset: int
    ) -> ComponentPage:
        """Страница каталога по фильтрам; снятые с продажи не показываются."""
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


def list_frames() -> list[FrameOut]:
    """Схемы фреймов всех категорий: по ним строятся формы админки и CSV-шаблоны."""
    return [
        FrameOut(
            category=category,
            title=str(frame.model_config.get("title", category.value)),
            json_schema=frame.model_json_schema(),
        )
        for category, frame in FRAMES_BY_CATEGORY.items()
    ]
