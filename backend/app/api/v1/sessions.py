"""Гостевые сессии для клиентов без аккаунта."""

from fastapi import APIRouter, Request, Response, status

from app.api.cookies import set_guest_cookie
from app.api.deps import GUEST_COOKIE, SessionDep, SettingsDep
from app.schemas.auth import GuestSessionOut
from app.services.auth import AuthService

router = APIRouter(tags=["sessions"])


@router.post(
    "/sessions/guest",
    status_code=status.HTTP_201_CREATED,
    summary="Выдать или продлить гостевую сессию (токен — HttpOnly-cookie)",
)
async def create_guest_session(
    request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> GuestSessionOut:
    auth = AuthService(session, settings)
    row = await auth.guest_session(request.cookies.get(GUEST_COOKIE))
    raw_token = auth.guest_cookie_value(row.id)
    if raw_token is None:
        return GuestSessionOut(status="existing")
    set_guest_cookie(response, settings, raw_token)
    return GuestSessionOut(status="created")
