"""Пароли и токены: Argon2id для паролей, JWT для access-токенов.

Модуль не зависит от FastAPI и БД: чистые функции для сервиса авторизации.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, VerifyMismatchError

ALGORITHM = "HS256"

_hasher = PasswordHasher(
    type=Type.ID,  # Argon2id
    memory_cost=65536,  # 64 МиБ
    time_cost=3,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


class TokenError(Exception):
    """Access-токен отсутствует, истёк или подписан недействительной подписью."""


@dataclass(frozen=True)
class AccessTokenPayload:
    """Содержимое access-токена."""

    user_id: uuid.UUID
    role: str
    expires_at: datetime


def normalize_email(email: str) -> str:
    """Приводит email к каноническому виду: без краевых пробелов, в нижнем регистре."""
    return email.strip().lower()


def hash_password(password: str) -> str:
    """Хеширует пароль по Argon2id (RFC 9106, первый вариант параметров)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль против хеша; любая ошибка проверки — это несовпадение."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    secret: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> str:
    """Подписывает JWT с claims sub (id пользователя), role, iat, exp, typ=access."""
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": issued_at,
        "exp": issued_at + ttl,
        "typ": "access",
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> AccessTokenPayload:
    """Проверяет подпись и срок действия access-токена; бросает TokenError при любой ошибке."""
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        if payload.get("typ") != "access":  # pragma: no cover — защита от подмены типа
            raise TokenError("Неверный тип токена")
        return AccessTokenPayload(
            user_id=uuid.UUID(payload["sub"]),
            role=str(payload["role"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise TokenError("Токен недействителен") from exc


def new_refresh_token() -> tuple[str, str]:
    """Генерирует пару (токен, sha256-хеш) для refresh-токена.

    В БД и в логи попадает только хеш; сам токен знает только клиент.
    """
    token = uuid.uuid4().hex + uuid.uuid4().hex
    return token, hash_token(token)


def new_guest_token() -> tuple[str, str]:
    """Генерирует пару (токен, sha256-хеш) для гостевой сессии."""
    return new_refresh_token()


def hash_token(token: str) -> str:
    """SHA-256 для непрозрачных токенов: фиксированная длина, односторонне."""
    return hashlib.sha256(token.encode()).hexdigest()
