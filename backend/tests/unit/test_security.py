"""Пароли и JWT: хеширование Argon2id, подпись и проверка access-токенов."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_guest_token,
    new_refresh_token,
    normalize_email,
    verify_password,
)

SECRET = "unit-test-secret"  # noqa: S105 — тестовый секрет, не боевой


def test_password_hash_and_verify() -> None:
    password_hash = hash_password("сложный пароль 123")
    assert password_hash.startswith("$argon2id$")
    assert verify_password("сложный пароль 123", password_hash)
    assert not verify_password("другой пароль", password_hash)


def test_normalize_email() -> None:
    assert normalize_email("  Ivan@Example.COM ") == "ivan@example.com"


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(
        user_id=user_id, role="client", secret=SECRET, ttl=timedelta(minutes=15)
    )
    payload = decode_access_token(token, secret=SECRET)
    assert payload.user_id == user_id
    assert payload.role == "client"
    assert payload.expires_at > datetime.now(UTC)


def test_access_token_expired() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(
        user_id=user_id,
        role="client",
        secret=SECRET,
        ttl=timedelta(minutes=-1),
        now=datetime.now(UTC) - timedelta(minutes=2),
    )
    with pytest.raises(TokenError):
        decode_access_token(token, secret=SECRET)


def test_access_token_wrong_secret() -> None:
    token = create_access_token(
        user_id=uuid.uuid4(), role="client", secret=SECRET, ttl=timedelta(minutes=15)
    )
    with pytest.raises(TokenError):
        decode_access_token(token, secret="другой-секрет")  # noqa: S106 — тестовый секрет


def test_access_token_tampered() -> None:
    token = create_access_token(
        user_id=uuid.uuid4(), role="client", secret=SECRET, ttl=timedelta(minutes=15)
    )
    head, _, tail = token.partition(".")
    tampered = f"{head}.AAAA.{tail}"
    with pytest.raises(TokenError):
        decode_access_token(tampered, secret=SECRET)


def test_access_token_wrong_type() -> None:
    import jwt

    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "client", "typ": "refresh"},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        decode_access_token(token, secret=SECRET)


def test_opaque_tokens_are_unique_and_hashed() -> None:
    token_a, hash_a = new_refresh_token()
    token_b, hash_b = new_refresh_token()
    guest, guest_hash = new_guest_token()
    assert token_a != token_b
    assert token_b != guest
    assert len(token_a) == 64
    assert token_a != hash_a
    assert hash_a != hash_b
    assert guest_hash == hash_token(guest)
