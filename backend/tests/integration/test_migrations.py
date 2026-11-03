"""Миграции откатываются и накатываются повторно без ошибок."""

import asyncio

import pytest
from alembic import command
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration


async def _tables(url: str) -> set[str]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    await engine.dispose()
    return set(names)


def test_downgrade_to_base_and_upgrade_again(migrated_database_url: str) -> None:
    config = alembic_config(migrated_database_url)
    command.downgrade(config, "base")
    assert asyncio.run(_tables(migrated_database_url)) == {"alembic_version"}
    command.upgrade(config, "head")
    assert {"components", "meta"} <= asyncio.run(_tables(migrated_database_url))
