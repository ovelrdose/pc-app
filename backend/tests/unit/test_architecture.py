"""Архитектурные инварианты: ядро `app/expert` не зависит от инфраструктуры."""

import ast
from pathlib import Path

import pytest

EXPERT_DIR = Path(__file__).resolve().parents[2] / "app" / "expert"
FORBIDDEN_PREFIXES = ("fastapi", "starlette", "sqlalchemy", "httpx", "asyncpg", "app.")
ALLOWED_APP_PREFIX = "app.expert"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
    return modules


@pytest.mark.parametrize("path", sorted(EXPERT_DIR.rglob("*.py")), ids=str)
def test_expert_has_no_infrastructure_imports(path: Path) -> None:
    for module in _imported_modules(path):
        if module.startswith(ALLOWED_APP_PREFIX):
            continue
        assert not module.startswith(FORBIDDEN_PREFIXES), f"{path.name} импортирует {module}"
