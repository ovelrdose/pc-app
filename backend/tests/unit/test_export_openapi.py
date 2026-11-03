"""Выгрузка OpenAPI-схемы для генерации клиента фронтенда."""

import json
from pathlib import Path

from scripts.export_openapi import export_openapi


def test_export_openapi_writes_schema(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"
    export_openapi(output)
    schema = json.loads(output.read_text(encoding="utf-8"))
    assert "/api/v1/healthz" in schema["paths"]
