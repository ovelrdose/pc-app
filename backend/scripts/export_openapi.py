"""Выгружает OpenAPI-схему без запуска сервера: `uv run python -m scripts.export_openapi <путь>`."""

import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def export_openapi(output: Path) -> None:
    """Строит приложение с заглушечными настройками и пишет его OpenAPI-схему в файл."""
    # Схема не зависит от подключения к БД, поэтому настройки — заглушки.
    settings = Settings(
        database_url="postgresql+asyncpg://unused:unused@localhost:5432/unused",
        jwt_secret="unused",  # noqa: S106
        _env_file=None,
    )
    schema = create_app(settings).openapi()
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    export_openapi(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT)
