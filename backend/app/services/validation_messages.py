"""Перевод ошибок валидации Pydantic в понятные русские сообщения."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

_TEMPLATES: dict[str, str] = {
    "missing": "не заполнено",
    "int_parsing": "ожидается целое число",
    "int_from_float": "ожидается целое число",
    "float_parsing": "ожидается число",
    "bool_parsing": "ожидается true или false",
    "date_parsing": "ожидается дата в формате ГГГГ-ММ-ДД",
    "date_from_datetime_parsing": "ожидается дата в формате ГГГГ-ММ-ДД",
    "greater_than": "должно быть больше {gt}",
    "greater_than_equal": "должно быть не меньше {ge}",
    "less_than": "должно быть меньше {lt}",
    "less_than_equal": "должно быть не больше {le}",
    "string_pattern_mismatch": "недопустимые символы",
    "string_too_short": "не может быть пустым",
    "string_too_long": "слишком длинное значение (не больше {max_length} символов)",
    "too_short": "нужно хотя бы {min_length} значение",
    "enum": "допустимые значения: {expected}",
    "literal_error": "допустимые значения: {expected}",
    "extra_forbidden": "неизвестное поле",
}


def _slot_title(model: type[BaseModel], name: str) -> str:
    field = model.model_fields.get(name)
    title = field.title if field and field.title else None
    return f"«{title}» ({name})" if title else name


def _message(error: ErrorDetails) -> str:
    ctx: Mapping[str, Any] = error.get("ctx") or {}
    if error["type"] == "value_error" and "error" in ctx:
        return str(ctx["error"])
    template = _TEMPLATES.get(error["type"])
    if template is None:
        return error["msg"]
    try:
        return template.format(**ctx).replace(" or ", " или ")
    except KeyError:
        return error["msg"]


def describe_validation_error(exc: ValidationError, model: type[BaseModel]) -> list[str]:
    """Возвращает сообщения вида «"Длина" (length_mm) = "abc": ожидается целое число»."""
    messages: list[str] = []
    for error in exc.errors():
        loc = [part for part in error["loc"] if isinstance(part, str)]
        message = _message(error)
        if not loc:
            messages.append(message)
            continue
        subject = _slot_title(model, loc[0])
        value = error.get("input")
        if error["type"] != "missing" and isinstance(value, str | int | float):
            subject += f" = «{value}»"
        messages.append(f"{subject}: {message}")
    return messages
