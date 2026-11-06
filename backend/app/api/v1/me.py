"""Личный кабинет: сохранённые сборки текущего аккаунта."""

from fastapi import APIRouter, Query

from app.api.deps import CacheDep, CurrentUserDep, SessionDep
from app.schemas.auth import MeBuildsOut
from app.services.cabinet import CabinetService

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/builds", summary="Сохранённые сборки аккаунта")
async def my_builds(
    user: CurrentUserDep,
    session: SessionDep,
    cache: CacheDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MeBuildsOut:
    return await CabinetService(session, cache).saved_builds(user, limit=limit, offset=offset)
