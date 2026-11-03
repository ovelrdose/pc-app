"""Коэффициенты уверенности MYCIN (архитектура §5.4, вики §3.4)."""

import pytest

from app.expert.certainty import (
    clamp,
    combine,
    combine_all,
    conclusion,
    conjunction,
    disjunction,
    is_established,
    negation,
)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (0.24, 0.5, 0.62),  # пример из вики §3.4
        (0.6, 0.6, 0.84),
        (-0.4, -0.5, -0.7),
        (0.8, -0.4, 0.6667),
        (-0.8, 0.4, -0.6667),
        (1.0, -1.0, 0.0),
        (1.0, 0.3, 1.0),
    ],
)
def test_combine(a: float, b: float, expected: float) -> None:
    assert combine(a, b) == pytest.approx(expected, abs=1e-4)
    assert combine(b, a) == pytest.approx(expected, abs=1e-4)


def test_combine_all() -> None:
    assert combine_all([]) == 0.0
    assert combine_all([0.5]) == 0.5
    assert combine_all([0.5, 0.5, 0.5]) == pytest.approx(0.875)


def test_premise_and_conclusion() -> None:
    assert conjunction([0.9, 0.3, 0.7]) == 0.3
    assert disjunction([0.9, 0.3]) == 0.9
    assert negation(0.3) == pytest.approx(0.7)
    assert conclusion(0.8, 0.3) == pytest.approx(0.24)  # пример REQ-024 из вики


def test_threshold() -> None:
    assert is_established(0.2)
    assert is_established(0.19999999999)
    assert not is_established(0.19)
    assert not is_established(-0.5)


def test_clamp() -> None:
    assert clamp(1.5) == 1.0
    assert clamp(-3) == -1.0
