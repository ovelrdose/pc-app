"""Схемы аутентификации: регистрация, вход, токены, текущий пользователь, кабинет."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole
from app.schemas.consultations import BuildSummary

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class RegisterIn(BaseModel):
    """Регистрация нового клиента."""

    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class LoginIn(BaseModel):
    """Вход по email и паролю."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class UserOut(BaseModel):
    """Публичные данные пользователя."""

    id: uuid.UUID
    email: str
    role: UserRole
    created_at: datetime


class TokenOut(BaseModel):
    """Успешный вход или регистрация: access-токен и профиль.

    Refresh-токен приходит отдельной HttpOnly-cookie, в теле его нет.
    """

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 — стандартное имя поля OAuth
    expires_in: int = Field(description="срок жизни access-токена, секунды")
    user: UserOut


class RefreshOut(BaseModel):
    """Новая пара токенов по refresh (сам refresh — снова в cookie)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 — стандартное имя поля OAuth
    expires_in: int


class GuestSessionOut(BaseModel):
    """Результат выдачи гостевой сессии (токен — HttpOnly-cookie)."""

    status: Literal["created", "existing"]


class SavedBuildOut(BaseModel):
    """Сохранённая сборка в личном кабинете."""

    consultation_id: uuid.UUID
    build: BuildSummary


class MeBuildsOut(BaseModel):
    """Сохранённые сборки пользователя с пагинацией."""

    builds: list[SavedBuildOut]
    total: int
