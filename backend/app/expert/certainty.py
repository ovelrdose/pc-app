"""Коэффициенты уверенности в стиле MYCIN (архитектура §5.4)."""

from collections.abc import Iterable

CF_THRESHOLD = 0.2
"""Факт считается установленным при `cf ≥ CF_THRESHOLD`."""

_EPSILON = 1e-9


def clamp(cf: float) -> float:
    """Ограничивает CF диапазоном [-1; 1] и убирает шум округления."""
    return round(max(-1.0, min(1.0, cf)), 9)


def is_established(cf: float) -> bool:
    """Факт с этим CF виден условиям правил."""
    return cf >= CF_THRESHOLD - _EPSILON


def combine(a: float, b: float) -> float:
    """Комбинирует два независимых свидетельства об одном факте."""
    if a >= 0 and b >= 0:
        result = a + b * (1 - a)
    elif a < 0 and b < 0:
        result = a + b * (1 + a)
    else:
        denominator = 1 - min(abs(a), abs(b))
        result = 0.0 if denominator <= _EPSILON else (a + b) / denominator
    return clamp(result)


def combine_all(values: Iterable[float]) -> float:
    """Комбинирует несколько свидетельств; без свидетельств CF равен 0."""
    result: float | None = None
    for value in values:
        result = value if result is None else combine(result, value)
    return clamp(result) if result is not None else 0.0


def conjunction(values: Iterable[float]) -> float:
    """CF посылки «все из»: минимум."""
    return min(values)


def disjunction(values: Iterable[float]) -> float:
    """CF посылки «любое из»: максимум."""
    return max(values)


def negation(cf: float) -> float:
    """CF посылки «не»."""
    return clamp(1 - cf)


def conclusion(rule_cf: float, premise_cf: float) -> float:
    """CF вывода правила."""
    return clamp(rule_cf * premise_cf)
