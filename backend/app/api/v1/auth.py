"""Аутентификация: регистрация, вход, обновление и отзыв токенов, текущий пользователь."""

from fastapi import APIRouter, Request, Response, status

from app.api.cookies import clear_guest_cookie, clear_refresh_cookie, set_refresh_cookie
from app.api.deps import GUEST_COOKIE, REFRESH_COOKIE, CurrentUserDep, SessionDep, SettingsDep
from app.models import UserRow
from app.schemas.auth import LoginIn, RefreshOut, RegisterIn, TokenOut, UserOut
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: UserRow) -> UserOut:
    """Публичная карточка пользователя."""
    return UserOut(id=user.id, email=user.email, role=user.role, created_at=user.created_at)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация: создаёт аккаунт и сразу входит",
)
async def register(
    data: RegisterIn,
    response: Response,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenOut:
    auth = AuthService(session, settings)
    guest_session_id = await auth.existing_guest_session_id(request.cookies.get(GUEST_COOKIE))
    user, tokens = await auth.register(data.email, data.password, guest_session_id=guest_session_id)
    set_refresh_cookie(response, settings, tokens)
    if guest_session_id is not None:
        clear_guest_cookie(response)  # сборки гостя перенесены на аккаунт
    return TokenOut(
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
        user=_user_out(user),
    )


@router.post("/login", summary="Вход по email и паролю")
async def login(
    data: LoginIn,
    response: Response,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenOut:
    auth = AuthService(session, settings)
    guest_session_id = await auth.existing_guest_session_id(request.cookies.get(GUEST_COOKIE))
    user, tokens = await auth.login(data.email, data.password, guest_session_id=guest_session_id)
    set_refresh_cookie(response, settings, tokens)
    if guest_session_id is not None:
        clear_guest_cookie(response)  # сборки гостя перенесены на аккаунт
    return TokenOut(
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
        user=_user_out(user),
    )


@router.post("/refresh", summary="Обновить пару токенов по refresh-cookie")
async def refresh(
    request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> RefreshOut:
    auth = AuthService(session, settings)
    _user, tokens = await auth.refresh(request.cookies.get(REFRESH_COOKIE))
    set_refresh_cookie(response, settings, tokens)
    return RefreshOut(access_token=tokens.access_token, expires_in=tokens.access_expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выйти: отозвать токены")
async def logout(
    request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> None:
    await AuthService(session, settings).logout(request.cookies.get(REFRESH_COOKIE))
    clear_refresh_cookie(response)


@router.get("/me", summary="Текущий пользователь")
async def me(user: CurrentUserDep) -> UserOut:
    return _user_out(user)
