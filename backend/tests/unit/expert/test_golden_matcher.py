"""Сопоставление значений с ожиданиями golden cases."""

import pytest
from pydantic import ValidationError

from app.expert.golden import GoldenCase, match


@pytest.mark.parametrize(
    ("actual", "matcher", "ok"),
    [
        (12, 12, True),
        (12, {"ge": 12}, True),
        (8, {"ge": 12}, False),
        ("ATX", {"in": ["ATX"]}, True),
        (("a", "b"), {"contains": "b"}, True),
        ("x", {"ne": "y"}, True),
        (None, 1, False),
        (None, {"ge": 1}, False),
        (5, {"gt": 1, "lt": 10}, True),
        (("a",), ["a"], True),
    ],
)
def test_match(actual: object, matcher: object, ok: bool) -> None:
    assert match(actual, matcher) is ok  # type: ignore[arg-type]


def test_unknown_matcher_op() -> None:
    with pytest.raises(ValueError, match="неизвестные операторы"):
        match(1, {"approx": 1})


def test_min_budget_only_for_infeasible() -> None:
    with pytest.raises(ValidationError, match="min_budget_rub"):
        GoldenCase.model_validate(
            {"id": "G-999", "title": "x", "answers": {}, "expect": {"min_budget_rub": {"ge": 1}}}
        )
