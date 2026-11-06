"""Сериализация golden cases в JSON рабочей копии и обратно (ADR 0010 п.2)."""

import pytest

from app.expert.golden import cases_from_json, cases_to_json

CASE = {
    "id": "G-900",
    "title": "Кейс для теста сериализации",
    "answers": {"tasks": {"main": "office"}, "budget_rub": 60000},
    "expect": {"feasible": True, "fired": ["PRF-001"]},
}


def test_cases_json_round_trip() -> None:
    cases = cases_from_json([CASE])
    assert len(cases) == 1
    assert cases[0].id == "G-900"
    assert cases[0].expect.fired == ["PRF-001"]
    # повторная сериализация стабильна (можно сравнивать JSON в БД)
    again = cases_to_json(cases_from_json(cases_to_json(cases)))
    assert again == cases_to_json(cases)


def test_cases_from_json_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="список"):
        cases_from_json({"id": "G-900"})
    with pytest.raises(ValueError, match="схему"):
        cases_from_json([{"id": "не-код", "title": "x", "answers": {}, "expect": {}}])
    with pytest.raises(ValueError, match="схему"):
        cases_from_json([{**CASE, "expect": {"feasible": "не-булево"}}])
