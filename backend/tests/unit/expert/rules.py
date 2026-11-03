"""Конструктор правил для тестов ядра."""

from typing import Any

from app.expert.dsl.schema import Rule


def rule(
    code: str,
    when: dict[str, Any],
    then: list[dict[str, Any]] | None = None,
    **fields: Any,
) -> Rule:
    """Правило вида inference с разумными умолчаниями; поля можно переопределить."""
    data: dict[str, Any] = {
        "code": code,
        "name": f"Правило {code}",
        "kind": "inference",
        "group": "test",
        "priority": 100,
        "cf": 1.0,
        "when": when,
        "then": then if then is not None else [],
        "explain": f"Объяснение {code}",
        **fields,
    }
    return Rule.model_validate(data)


def fact(path: str, op: str, value: Any = None, *, ref: str | None = None) -> dict[str, Any]:
    """Лист условия."""
    leaf: dict[str, Any] = {"fact": path, "op": op}
    if value is not None:
        leaf["value"] = value
    if ref is not None:
        leaf["ref"] = ref
    return leaf


def assert_(path: str, value: Any = None, *, expr: str | None = None) -> dict[str, Any]:
    """Действие assert."""
    action: dict[str, Any] = {"action": "assert", "fact": path}
    if expr is not None:
        action["expr"] = expr
    else:
        action["value"] = value
    return action
