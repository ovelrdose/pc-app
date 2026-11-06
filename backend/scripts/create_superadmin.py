"""Создание первого суперадмина: `uv run python -m scripts.create_superadmin <email>`.

Пароль запрашивается интерактивно (или читается из переменной окружения
SUPERADMIN_PASSWORD для автоматизации). Повторный запуск для того же email —
ошибка, аккаунт уже есть.
"""

import argparse
import asyncio
import getpass
import os
import sys

import structlog

from app.core.config import get_settings
from app.core.db import Database
from app.core.logging import configure_logging
from app.core.security import hash_password, normalize_email
from app.models import UserRole, UserRow
from app.repositories.users import UserRepository

logger = structlog.get_logger("create_superadmin")

PASSWORD_MIN_LENGTH = 8


async def create_superadmin(database: Database, email: str, password: str) -> str:
    """Создаёт суперадмина; возвращает 'created' или 'exists'."""
    async with database.session_factory() as session:
        repo = UserRepository(session)
        if await repo.user_by_email(email) is not None:
            return "exists"
        user = UserRow(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.SUPERADMIN,
        )
        await repo.add_user(user)
        await session.commit()
        logger.info("superadmin_created", email=email, user_id=str(user.id))
        return "created"


async def run(email: str, password: str) -> str:
    """Создаёт суперадмина и закрывает пул в том же event loop."""
    settings = get_settings()
    database = Database(settings)
    try:
        return await create_superadmin(database, email, password)
    finally:
        await database.dispose()


def main(argv: list[str] | None = None) -> int:
    """Точка входа: 0 — создан, 1 — ошибка."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="email суперадмина")
    args = parser.parse_args(argv)
    configure_logging()

    password = os.environ.get("SUPERADMIN_PASSWORD") or getpass.getpass("Пароль: ")
    if len(password) < PASSWORD_MIN_LENGTH:
        logger.error("password_too_short", min_length=PASSWORD_MIN_LENGTH)
        return 1

    email = normalize_email(args.email)
    result = asyncio.run(run(email, password))
    if result == "exists":
        logger.error("email_taken", email=email)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
