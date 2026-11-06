"""Аутентификация: регистрация, вход, refresh-токены, гостевые сессии, перенос сборок."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, DomainError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_guest_token,
    new_refresh_token,
    normalize_email,
    verify_password,
)
from app.models import GuestSessionRow, RefreshTokenRow, UserRole, UserRow
from app.repositories.users import UserRepository

logger = structlog.get_logger(__name__)


class AuthError(DomainError):
    """Ошибка аутентификации: неверные данные, истёкший или отозванный токен."""

    status = 401
    code = "unauthorized"
    title = "Ошибка входа"


class EmailTakenError(ConflictError):
    """Email уже зарегистрирован."""

    code = "email-taken"
    title = "Email занят"


class AccountBlockedError(DomainError):
    """Аккаунт заблокирован администратором."""

    status = 403
    code = "account-blocked"
    title = "Аккаунт заблокирован"


@dataclass(frozen=True)
class IssuedTokens:
    """Свежая пара токенов: access (JWT) отдаётся клиенту, refresh — в cookie."""

    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    """Сценарии входа, регистрации и работы с гостевыми сессиями."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = UserRepository(session)
        self._fresh_guest_tokens: dict[uuid.UUID, str] = {}

    async def register(
        self, email: str, password: str, *, guest_session_id: uuid.UUID | None = None
    ) -> tuple[UserRow, IssuedTokens]:
        """Регистрирует клиента и сразу входит; гостевые консультации переносятся на аккаунт."""
        normalized = normalize_email(email)
        if await self.repo.user_by_email(normalized) is not None:
            raise EmailTakenError(f"Пользователь с email {normalized} уже зарегистрирован")
        user = UserRow(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=hash_password(password),
            role=UserRole.CLIENT,
        )
        await self.repo.add_user(user)
        await self.session.flush()
        tokens, _new_token_row = await self._issue_tokens(user)
        await self._merge_guest(guest_session_id, user)
        logger.info("user_registered", user_id=str(user.id))
        return user, tokens

    async def login(
        self, email: str, password: str, *, guest_session_id: uuid.UUID | None = None
    ) -> tuple[UserRow, IssuedTokens]:
        """Вход по email и паролю; гостевые консультации переносятся на аккаунт."""
        user = await self.repo.user_by_email(normalize_email(email))
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Неверный email или пароль")
        if not user.is_active:
            raise AccountBlockedError("Аккаунт заблокирован")
        tokens, _new_token_row = await self._issue_tokens(user)
        await self._merge_guest(guest_session_id, user)
        logger.info("user_logged_in", user_id=str(user.id))
        return user, tokens

    async def refresh(self, refresh_token: str | None) -> tuple[UserRow, IssuedTokens]:
        """Ротация refresh-токена: старый отзывается, выдаётся новая пара.

        Повторное использование отозванного токена означает кражу — отзываются
        все токены пользователя.
        """
        if not refresh_token:
            raise AuthError("Refresh-токен не предъявлен")
        row = await self.repo.token_by_hash(hash_token(refresh_token))
        if row is None:
            raise AuthError("Refresh-токен недействителен")
        now = datetime.now(UTC)
        if row.revoked_at is not None:
            await self.repo.revoke_user_tokens(row.user_id, revoked_at=now)
            # Транзакция на запрос откатывается при исключении (ADR 0006), а отзыв
            # цепочки должен пережить отказ — фиксируем его до raise вручную.
            await self.session.commit()
            logger.warning("refresh_token_reuse_detected", user_id=str(row.user_id))
            raise AuthError("Refresh-токен отозван, выполните вход заново")
        if row.expires_at <= now:
            await self.repo.revoke_token(row.id, revoked_at=now)
            raise AuthError("Refresh-токен истёк, выполните вход заново")
        user = await self.repo.user(row.user_id)
        if user is None or not user.is_active:  # pragma: no cover — CASCADE не даст
            raise AuthError("Пользователь недоступен")
        tokens, new_row = await self._issue_tokens(user)
        await self.repo.revoke_token(row.id, revoked_at=now)
        row.replaced_by_id = new_row.id
        return user, tokens

    async def logout(self, refresh_token: str | None) -> None:
        """Отзывает refresh-токен; идемпотентен (неизвестный токен — молчание)."""
        if not refresh_token:
            return
        row = await self.repo.token_by_hash(hash_token(refresh_token))
        if row is not None and row.revoked_at is None:
            await self.repo.revoke_token(row.id, revoked_at=datetime.now(UTC))
            logger.info("user_logged_out", user_id=str(row.user_id))

    async def guest_session(self, guest_token: str | None) -> GuestSessionRow:
        """Гостевая сессия по cookie: действующую продлевает, иначе создаёт новую.

        Слитая с аккаунтом (merged) сессия не продлевается — клиенту выдаётся новая.
        Токен только что созданной сессии забирают `guest_cookie_value` для cookie.
        """
        if guest_token:
            row = await self.repo.guest_by_hash(hash_token(guest_token))
            if row is not None and row.merged_user_id is None:
                await self.repo.touch_guest_session(row.id, seen_at=datetime.now(UTC))
                return row
        token, token_hash = new_guest_token()
        row = GuestSessionRow(id=uuid.uuid4(), token_hash=token_hash)
        await self.repo.add_guest_session(row)
        await self.session.flush()
        self._fresh_guest_tokens[row.id] = token
        logger.info("guest_session_created", guest_session_id=str(row.id))
        return row

    def guest_cookie_value(self, session_id: uuid.UUID) -> str | None:
        """Сырой токен только что созданной гостевой сессии (для установки cookie)."""
        return self._fresh_guest_tokens.pop(session_id, None)

    async def existing_guest_session_id(self, guest_token: str | None) -> uuid.UUID | None:
        """Id действующей гостевой сессии по токену из cookie (без создания новой)."""
        if not guest_token:
            return None
        row = await self.repo.guest_by_hash(hash_token(guest_token))
        if row is None or row.merged_user_id is not None:
            return None
        return row.id

    async def user(self, user_id: uuid.UUID) -> UserRow | None:
        """Пользователь по id (для GET /auth/me)."""
        return await self.repo.user(user_id)

    async def _issue_tokens(self, user: UserRow) -> tuple[IssuedTokens, RefreshTokenRow]:
        access_ttl = timedelta(minutes=self.settings.access_token_ttl_minutes)
        access = create_access_token(
            user_id=user.id,
            role=user.role.value,
            secret=self.settings.jwt_secret.get_secret_value(),
            ttl=access_ttl,
        )
        raw_refresh, refresh_hash = new_refresh_token()
        refresh_expires = datetime.now(UTC) + timedelta(days=self.settings.refresh_token_ttl_days)
        row = RefreshTokenRow(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=refresh_expires,
        )
        await self.repo.add_token(row)
        await self.session.flush()
        return (
            IssuedTokens(
                access_token=access,
                access_expires_in=int(access_ttl.total_seconds()),
                refresh_token=raw_refresh,
                refresh_expires_at=refresh_expires,
            ),
            row,
        )

    async def _merge_guest(self, guest_session_id: uuid.UUID | None, user: UserRow) -> None:
        if guest_session_id is None:
            return
        moved = await self.repo.merge_guest(guest_session_id, user.id)
        if moved:
            logger.info("guest_data_merged", user_id=str(user.id), moved_consultations=moved)
