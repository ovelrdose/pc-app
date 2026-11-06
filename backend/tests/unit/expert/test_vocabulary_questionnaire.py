"""Словарь фактов и анкета визарда."""

from typing import Annotated, Any, Literal

import pytest
from pydantic import ValidationError

from app.expert.frames import Category
from app.expert.questionnaire import (
    AnswerError,
    Questionnaire,
    answers_to_memory,
    check_fact_types,
)
from app.expert.vocabulary import FactRole, FactType, annotation_type, input_paths, lookup
from tests.unit.expert.kb_fixtures import small_tables


def test_vocabulary_lookups() -> None:
    budget = lookup("user.budget")
    assert budget is not None
    assert (budget.type, budget.role) == (FactType.NUMBER, FactRole.INPUT)
    assert lookup("profile.weight.office") is not None
    assert lookup("req.need.case_fan") is not None
    assert lookup("budget.share.cpu_cooler") is not None
    assert lookup("user.nothing") is None
    cooler = lookup("build.cpu_cooler.type")
    assert cooler is not None
    assert cooler.values == ("air", "aio")
    assert lookup("build.gpu.owned") is not None
    assert lookup("build.total.power_w") is not None
    assert lookup("build.gpu.socket") is None
    size = lookup("cand.size_mm")
    assert size is not None
    assert size.type is FactType.NUMBER
    form_factor = lookup("cand.form_factor")  # строка у плат и enum у SSD — значения открыты
    assert form_factor is not None
    assert form_factor.values == ()
    category = lookup("cand.category")
    assert category is not None
    assert category.values == ()
    assert "user.budget" in input_paths()
    assert "profile.main" not in input_paths()


@pytest.mark.parametrize(
    ("annotation", "kind"),
    [
        (int, FactType.NUMBER),
        (bool, FactType.BOOL),
        (list[str], FactType.LIST),
        (Literal[120, 140], FactType.NUMBER),
        (Literal["a"], FactType.STR),
        (Category, FactType.STR),
        (int | None, FactType.NUMBER),
        (str, FactType.STR),
        (Annotated[int, "метаданные"], FactType.NUMBER),
    ],
)
def test_annotation_type(annotation: Any, kind: FactType) -> None:
    assert annotation_type(annotation)[0] is kind


QUESTIONNAIRE: dict[str, Any] = {
    "steps": [
        {
            "id": "main",
            "title": "Главное",
            "questions": [
                {
                    "id": "tasks",
                    "type": "tasks",
                    "fact": "user.weight",
                    "title": "Задачи",
                    "extra_title": "Ещё задачи",
                    "options": [
                        {"value": "office", "label": "Офис"},
                        {"value": "esports", "label": "Игры"},
                        {"value": "programming", "label": "Код"},
                    ],
                },
                {
                    "id": "budget",
                    "type": "number",
                    "fact": "user.budget",
                    "title": "Бюджет",
                    "min": 35000,
                    "max": 500000,
                },
                {
                    "id": "color",
                    "type": "choice",
                    "fact": "user.color",
                    "title": "Цвет",
                    "options": [
                        {"value": "white", "label": "Белый"},
                        {"value": "any", "label": "Любой"},
                    ],
                },
                {
                    "id": "games",
                    "type": "multichoice",
                    "fact": "user.games",
                    "title": "Игры",
                    "options_from": "games",
                },
                {"id": "rgb", "type": "yesno", "fact": "user.rgb", "title": "RGB"},
            ],
        }
    ]
}


TASKS: dict[str, Any] = {"tasks": {"main": "office"}}


def questionnaire() -> Questionnaire:
    return Questionnaire.model_validate(QUESTIONNAIRE)


def test_answers_to_memory() -> None:
    memory = answers_to_memory(
        questionnaire(),
        {
            "tasks": {"main": "esports", "extra": ["office"]},
            "budget": 100000,
            "color": "white",
            "games": ["cs2", "cs2"],
            "rgb": "rather_yes",
        },
        small_tables(),
    )
    user_facts = {k: v for k, v in memory.as_dict().items() if not k.startswith("need.")}
    assert user_facts == {
        "user.weight.office": 0.3,
        "user.weight.esports": 1.0,
        "user.weight.programming": 0.0,
        "user.budget": 100000,
        "user.color": "white",
        "user.games": ("cs2",),
        "user.rgb": True,
    }
    rgb = memory.lookup("user.rgb")
    assert rgb is not None
    assert rgb.cf == 0.6


def test_unknown_and_any_give_no_fact() -> None:
    memory = answers_to_memory(
        questionnaire(),
        {
            "budget": 50000,
            "tasks": {"main": "office"},
            "color": "any",
            "rgb": "unknown",
            "games": [],
        },
        small_tables(),
    )
    assert set(memory.as_dict()) == {
        "user.budget",
        "user.weight.office",
        "user.weight.esports",
        "user.weight.programming",
    }


def test_main_task_wins_over_extra_duplicate() -> None:
    memory = answers_to_memory(
        questionnaire(),
        {"budget": 50000, "tasks": {"main": "office", "extra": ["office", "esports"]}},
        small_tables(),
    )
    assert memory.as_dict()["user.weight.office"] == 1.0
    assert memory.as_dict()["user.weight.esports"] == 0.3


def test_legacy_weights_still_read() -> None:
    """Снимки, опубликованные со слайдерами, продолжают открываться."""
    legacy = {
        "steps": [
            {
                "id": "s",
                "title": "s",
                "questions": [
                    {
                        "id": "purposes",
                        "type": "weights",
                        "fact": "user.weight",
                        "title": "Задачи",
                        "options": [{"value": "esports", "label": "Игры"}],
                    },
                    {
                        "id": "budget",
                        "type": "number",
                        "fact": "user.budget",
                        "title": "Бюджет",
                        "min": 35000,
                        "max": 500000,
                    },
                ],
            }
        ]
    }
    old = Questionnaire.model_validate(legacy)
    memory = answers_to_memory(old, {"budget": 50000, "purposes": {"esports": 70}}, small_tables())
    assert memory.as_dict()["user.weight.esports"] == 0.7
    assert check_fact_types(old) == ["purposes: слайдеры весов устарели — используйте вопрос tasks"]
    for answer, fragment in (
        ({"esports": 150}, "от 0 до 100"),
        ({"mining": 50}, "неизвестные варианты"),
        ([50], "веса"),
        ({"esports": "много"}, "числом"),
    ):
        with pytest.raises(AnswerError, match=fragment):
            answers_to_memory(old, {"budget": 50000, "purposes": answer}, small_tables())


@pytest.mark.parametrize(
    ("answers", "fragment"),
    [
        ({"tasks": {"main": "office"}}, "Бюджет: ответ обязателен"),
        ({"budget": 50000}, "Задачи: ответ обязателен"),
        ({**TASKS, "budget": 10}, "допустимо от 35000"),
        ({**TASKS, "budget": "много"}, "ожидается число"),
        ({"budget": 50000, "tasks": ["office"]}, "основная и дополнительные"),
        ({"budget": 50000, "tasks": {"extra": ["office"]}}, "выберите основную"),
        ({"budget": 50000, "tasks": {"main": "mining"}}, "недопустимый вариант"),
        ({"budget": 50000, "tasks": {"main": "office", "extra": "esports"}}, "список"),
        ({"budget": 50000, "tasks": {"main": "office", "extra": ["mining"]}}, "неизвестные"),
        ({"budget": 50000, "tasks": {"main": "office", "weights": 1}}, "неизвестные поля"),
        ({**TASKS, "budget": 50000, "color": "red"}, "недопустимый вариант"),
        ({**TASKS, "budget": 50000, "games": ["tetris"]}, "неизвестные варианты"),
        ({**TASKS, "budget": 50000, "games": "cs2"}, "список"),
        ({**TASKS, "budget": 50000, "rgb": "maybe"}, "да/скорее"),
        ({"budget": 50000, "nope": 1}, "неизвестные вопросы"),
    ],
)
def test_answer_errors(answers: dict[str, Any], fragment: str) -> None:
    with pytest.raises(AnswerError, match=fragment):
        answers_to_memory(questionnaire(), answers, small_tables())


@pytest.mark.parametrize(
    ("question", "fragment"),
    [
        ({"id": "x", "type": "choice", "fact": "user.color", "title": "x"}, "нужны варианты"),
        (
            {
                "id": "x",
                "type": "tasks",
                "fact": "user.weight",
                "title": "x",
                "options": [{"value": "office", "label": "Офис"}],
            },
            "extra_title",
        ),
        (
            {
                "id": "x",
                "type": "tasks",
                "fact": "user.weight",
                "title": "x",
                "extra_title": "y",
                "main_weight": 0.3,
                "options": [{"value": "office", "label": "Офис"}],
            },
            "меньше main_weight",
        ),
        ({"id": "x", "type": "multichoice", "fact": "user.games", "title": "x"}, "options_from"),
        ({"id": "x", "type": "number", "fact": "user.budget", "title": "x"}, "min и max"),
        ({"id": "x", "type": "yesno", "fact": "profile.main", "title": "x"}, "не входной факт"),
    ],
)
def test_questionnaire_schema_errors(question: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        Questionnaire.model_validate(
            {"steps": [{"id": "s", "title": "s", "questions": [question]}]}
        )


def test_check_fact_types_detects_mismatch() -> None:
    data = {
        "steps": [
            {
                "id": "s",
                "title": "s",
                "questions": [{"id": "x", "type": "yesno", "fact": "user.budget", "title": "x"}],
            }
        ]
    }
    assert check_fact_types(Questionnaire.model_validate(data)) == [
        "x: тип вопроса не совпадает с типом user.budget"
    ]


MONITOR: dict[str, Any] = {
    "id": "monitor",
    "type": "choice",
    "title": "Монитор",
    "allow_unknown": True,
    "options": [
        {
            "value": "fhd_60",
            "label": "Full HD, 60 Гц",
            "facts": {"user.resolution": "1080p", "user.refresh_hz": 60},
        },
        {
            "value": "qhd_144",
            "label": "2K, 144 Гц",
            "facts": {"user.resolution": "1440p", "user.refresh_hz": 144},
        },
    ],
}


def test_choice_option_sets_several_facts() -> None:
    data = {"steps": [{"id": "s", "title": "s", "questions": [MONITOR]}]}
    monitor = Questionnaire.model_validate(data)
    memory = answers_to_memory(monitor, {"monitor": "qhd_144"}, small_tables())
    assert memory.as_dict() == {"user.resolution": "1440p", "user.refresh_hz": 144}
    assert answers_to_memory(monitor, {"monitor": "unknown"}, small_tables()).as_dict() == {}
    assert check_fact_types(monitor) == []
    with pytest.raises(AnswerError, match="недопустимый вариант"):
        answers_to_memory(monitor, {"monitor": "uhd_60"}, small_tables())


@pytest.mark.parametrize(
    ("facts", "fragment"),
    [
        ({"profile.main": "office"}, "не входной факт"),
        ({"user.resolution": "720p"}, "не может быть"),
        ({"user.budget": "много"}, "тип user.budget"),
    ],
)
def test_option_facts_are_checked(facts: dict[str, Any], fragment: str) -> None:
    question = {**MONITOR, "options": [{"value": "x", "label": "x", "facts": facts}]}
    with pytest.raises(ValidationError, match=fragment):
        Questionnaire.model_validate(
            {"steps": [{"id": "s", "title": "s", "questions": [question]}]}
        )


def test_choice_without_fact_needs_facts_in_every_option() -> None:
    question = {**MONITOR, "options": [*MONITOR["options"], {"value": "any", "label": "Любой"}]}
    with pytest.raises(ValidationError, match="нужен fact"):
        Questionnaire.model_validate(
            {"steps": [{"id": "s", "title": "s", "questions": [question]}]}
        )
