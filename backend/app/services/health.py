"""Проверка готовности приложения к обслуживанию запросов."""

import structlog

from app.core.db import Database
from app.core.errors import DomainError

logger = structlog.get_logger(__name__)


class ServiceUnavailableError(DomainError):
    """Зависимость приложения (например, БД) недоступна."""

    status = 503
    code = "service-unavailable"
    title = "Сервис временно недоступен"


async def check_readiness(database: Database) -> None:
    """Проверяет доступность БД; при сбое бросает `ServiceUnavailableError`."""
    try:
        await database.ping()
    except Exception as exc:
        logger.warning("readiness_db_failed", error_type=type(exc).__name__)
        raise ServiceUnavailableError("База данных недоступна") from exc
