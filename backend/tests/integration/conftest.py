"""Фикстуры интеграционных тестов: только база `pcapp_test`, схема пересоздаётся миграциями."""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.core.db import Database
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DB_PREFIX = "pcapp_test"


def _test_database_url() -> str | None:
    env_file = BACKEND_DIR / ".env"
    return os.environ.get("TEST_DATABASE_URL") or dotenv_values(env_file).get("TEST_DATABASE_URL")


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


async def _reset_schema(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = _test_database_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL не задан")
    if not url.rsplit("/", 1)[-1].startswith(TEST_DB_PREFIX):
        pytest.fail("Интеграционные тесты запускаются только на базе pcapp_test")
    return url


@pytest.fixture(scope="session")
def migrated_database_url(test_database_url: str) -> str:
    """Пустая схема `pcapp_test` + все миграции; один раз на сессию тестов."""
    asyncio.run(_reset_schema(test_database_url))
    command.upgrade(alembic_config(test_database_url), "head")
    return test_database_url


@pytest.fixture
def settings(migrated_database_url: str) -> Settings:
    return Settings(
        environment="test",
        database_url=migrated_database_url,
        jwt_secret="test-secret",  # noqa: S106
        _env_file=None,
    )


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    database = Database(settings)
    await truncate_all(database)
    yield database
    await database.dispose()


@pytest.fixture
async def session(database: Database) -> AsyncIterator[AsyncSession]:
    async with database.session_factory() as session:
        yield session


@pytest.fixture
async def client(app: FastAPI, database: Database) -> AsyncIterator[httpx.AsyncClient]:
    app.state.database = database
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def truncate_all(database: Database) -> None:
    async with database.engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE build_items, builds, consultations, refresh_tokens, guest_sessions, "
                "users, catalog_imports, rule_revisions, rules, "
                "reference_tables, kb_snapshots, components, meta RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture(scope="module")
async def seeded(migrated_database_url: str) -> AsyncIterator[Database]:
    """База pcapp_test с реальным каталогом и опубликованной базой знаний (на модуль тестов)."""
    from app.services.catalog_csv import read_catalog_dir
    from app.services.knowledge_files import load_tables
    from scripts.seed import KNOWLEDGE_DIR, seed_catalog, seed_knowledge

    settings = Settings(
        environment="test",
        database_url=migrated_database_url,
        jwt_secret="test-secret",  # noqa: S106
        _env_file=None,
    )
    database = Database(settings)
    await truncate_all(database)
    known = load_tables(KNOWLEDGE_DIR / "tables").known_slot_values()
    await seed_catalog(database, read_catalog_dir(KNOWLEDGE_DIR / "catalog"), known)
    await seed_knowledge(database, KNOWLEDGE_DIR, golden=False)
    yield database
    await database.dispose()


@pytest.fixture(scope="module")
async def api(seeded: Database) -> AsyncIterator[httpx.AsyncClient]:
    """Клиент API поверх засеянной базы (общий для тестов модуля)."""
    from app.services.snapshot_cache import SnapshotCache

    app = create_app(seeded_settings(seeded))
    app.state.database = seeded
    app.state.cache = SnapshotCache()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def seeded_settings(database: Database) -> Settings:
    return Settings(
        environment="test",
        database_url=str(database.engine.url.render_as_string(hide_password=False)),
        jwt_secret="test-secret",  # noqa: S106
        _env_file=None,
    )
