"""Служебные значения: ревизия каталога и т.п."""

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import BigInteger, Text

from app.models import MetaRow

CATALOG_REVISION_KEY = "catalog_revision"


class MetaRepository:
    """Чтение и атомарное изменение служебных значений."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_catalog_revision(self) -> int:
        """Текущая ревизия каталога (0, если каталог ещё не загружался)."""
        value = await self.session.scalar(
            select(MetaRow.value).where(MetaRow.key == CATALOG_REVISION_KEY)
        )
        return int(value) if value is not None else 0

    async def bump_catalog_revision(self) -> int:
        """Атомарно увеличивает ревизию каталога на 1 и возвращает новое значение."""
        insert_stmt = insert(MetaRow).values(key=CATALOG_REVISION_KEY, value="1")
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[MetaRow.key],
            set_={"value": cast(cast(MetaRow.value, BigInteger) + 1, Text)},
        ).returning(MetaRow.value)
        value = await self.session.scalar(stmt)
        return int(value or 0)
