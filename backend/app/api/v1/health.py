"""Проверки живости и готовности."""

from fastapi import APIRouter

from app.api.deps import DatabaseDep
from app.schemas.health import HealthStatus
from app.services.health import check_readiness

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Процесс жив")
async def healthz() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/readyz", summary="Приложение готово: БД доступна")
async def readyz(database: DatabaseDep) -> HealthStatus:
    await check_readiness(database)
    return HealthStatus(status="ok")
