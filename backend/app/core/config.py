"""Конфигурация приложения из переменных окружения и файла `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения. Значения читаются из окружения и `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False

    database_url: PostgresDsn
    db_echo: bool = False

    jwt_secret: SecretStr
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    cookie_secure: bool | None = None
    """Secure-флаг auth-cookie: по умолчанию включён только в prod."""

    cors_origins: list[str] = ["http://localhost:5173"]

    catalog_import_max_bytes: int = 2 * 1024 * 1024
    """Лимит multipart-импорта каталога (ADR 0010 п. «Альтернативы»: CSV ≤ 2 МБ)."""

    knowledge_dir: Path = Path(__file__).resolve().parents[3] / "knowledge"
    """Файлы знаний: seed, golden cases для проверки перед публикацией."""


@lru_cache
def get_settings() -> Settings:
    """Возвращает закэшированный экземпляр настроек."""
    return Settings()
