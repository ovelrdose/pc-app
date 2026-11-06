"""Доступ к журналу импорта каталога `catalog_imports`."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogImportRow


class CatalogImportRepository:
    """Записи журнала импорта каталога."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, row: CatalogImportRow) -> None:
        """Добавляет запись журнала в сессию."""
        self.session.add(row)
