"""Установка и снятие auth-cookie: refresh-токен и гостевая сессия.

Оба токена — HttpOnly (недоступны JavaScript), SameSite=Lax (не уходят
cross-site POST, CSRF-риск низкий), Secure — в prod.
"""

from datetime import UTC, datetime

from fastapi import Response

from app.api.deps import GUEST_COOKIE, REFRESH_COOKIE
from app.core.config import Settings
from app.services.auth import IssuedTokens

# Гостевая сессия на сервере не протухает (до слияния с аккаунтом или удаления строки);
# браузерному cookie ставим длинный, но конечный срок.
GUEST_COOKIE_MAX_AGE_DAYS = 400

REFRESH_COOKIE_PATH = "/api/v1/auth"
"""Refresh-токен нужен только эндпоинтам /auth — сужаем путь cookie."""
GUEST_COOKIE_PATH = "/api/v1"


def _secure(settings: Settings) -> bool:
    return (
        settings.cookie_secure
        if settings.cookie_secure is not None
        else (settings.environment == "prod")
    )


def set_refresh_cookie(response: Response, settings: Settings, tokens: IssuedTokens) -> None:
    """Отправляет refresh-токен HttpOnly-cookie."""
    max_age = int((tokens.refresh_expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=_secure(settings),
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    """Удаляет cookie с refresh-токеном."""
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def set_guest_cookie(response: Response, settings: Settings, token: str) -> None:
    """Отправляет токен гостевой сессии HttpOnly-cookie."""
    response.set_cookie(
        GUEST_COOKIE,
        token,
        max_age=GUEST_COOKIE_MAX_AGE_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=_secure(settings),
        path=GUEST_COOKIE_PATH,
    )


def clear_guest_cookie(response: Response) -> None:
    """Удаляет cookie гостевой сессии (после слияния с аккаунтом)."""
    response.delete_cookie(GUEST_COOKIE, path=GUEST_COOKIE_PATH)
