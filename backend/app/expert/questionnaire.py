"""Анкета визарда: схема `knowledge/questionnaire.yaml` и перевод ответов в факты `user.*`.

Уверенность ответов (архитектура §5.4): «да/нет» — 1.0, «скорее да/нет» — 0.6, «не знаю» —
факт не записывается. Задачи («основная» и «дополнительные») переводятся в веса по всем вариантам:
основная — `main_weight`, дополнительные — `extra_weight`, остальные — 0, чтобы правила могли
сравнивать их между собой. Вариант выбора может задавать сразу несколько фактов (`facts`): так
вопрос «Какой у вас монитор?» записывает и разрешение, и частоту. После всех ответов считаются
требования по играм клиента — факты `need.*` (`expert/game_needs.py`).
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.expert.facts import WorkingMemory
from app.expert.game_needs import record_game_needs
from app.expert.tables import KnowledgeTables
from app.expert.vocabulary import FactRole, FactType, lookup

UNKNOWN = "unknown"
YESNO_ANSWERS: Mapping[str, tuple[bool, float]] = {
    "yes": (True, 1.0),
    "rather_yes": (True, 0.6),
    "rather_no": (False, 0.6),
    "no": (False, 1.0),
}


class AnswerError(ValueError):
    """Ответ не подходит к вопросу; сообщение — для пользователя."""


class QuestionType(StrEnum):
    """Вид вопроса."""

    TASKS = "tasks"
    WEIGHTS = "weights"
    """Устаревшие слайдеры весов: остаются, чтобы читались ранее опубликованные снимки БЗ."""
    NUMBER = "number"
    CHOICE = "choice"
    MULTICHOICE = "multichoice"
    YESNO = "yesno"


WEIGHTED = (QuestionType.TASKS, QuestionType.WEIGHTS)
"""Вопросы, дающие факт `<fact>.<вариант>` по каждому варианту."""


class Option(BaseModel):
    """Вариант ответа."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str | int
    label: str = Field(min_length=1, max_length=100)
    facts: dict[str, str | int] | None = None
    """Факты, которые записывает этот вариант (вместо `fact` вопроса)."""

    @model_validator(mode="after")
    def _facts(self) -> Self:
        for path, value in (self.facts or {}).items():
            spec = lookup(path)
            if spec is None or spec.role is not FactRole.INPUT:
                raise ValueError(f"вариант {self.value}: {path} — не входной факт словаря")
            if spec.values and value not in spec.values:
                raise ValueError(f"вариант {self.value}: {path} не может быть «{value}»")
            want = FactType.NUMBER if isinstance(value, int) else FactType.STR
            if spec.type is not want:
                raise ValueError(f"вариант {self.value}: тип {path} не совпадает со значением")
        return self


class Question(BaseModel):
    """Вопрос анкеты."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    type: QuestionType
    fact: str | None = None
    title: str = Field(min_length=1, max_length=200)
    options: list[Option] = Field(default_factory=list)
    options_from: Literal["games", "applications"] | None = None
    allow_unknown: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    extra_title: str | None = Field(default=None, max_length=200)
    main_weight: float = Field(default=1.0, gt=0, le=1)
    extra_weight: float = Field(default=0.3, gt=0, le=1)

    @property
    def path(self) -> str:
        """Факт вопроса; у выбора с фактами в вариантах его нет."""
        if self.fact is None:
            raise AnswerError(f"{self.title}: у вопроса нет общего факта")
        return self.fact

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.type in (*WEIGHTED, QuestionType.CHOICE) and not self.options:
            raise ValueError(f"{self.id}: нужны варианты ответа")
        if self.type is QuestionType.TASKS:
            if not self.extra_title:
                raise ValueError(f"{self.id}: нужен extra_title — вопрос о дополнительных задачах")
            if self.extra_weight >= self.main_weight:
                raise ValueError(f"{self.id}: extra_weight должен быть меньше main_weight")
        if self.type is QuestionType.MULTICHOICE and not (self.options or self.options_from):
            raise ValueError(f"{self.id}: нужны варианты или options_from")
        if self.type is QuestionType.NUMBER and (self.min is None or self.max is None):
            raise ValueError(f"{self.id}: для числа нужны min и max")
        if self.fact is None:
            if self.type is not QuestionType.CHOICE or not all(o.facts for o in self.options):
                raise ValueError(f"{self.id}: нужен fact или facts у каждого варианта")
            return self
        paths = (
            [f"{self.fact}.{o.value}" for o in self.options]
            if self.type in WEIGHTED
            else [self.fact]
        )
        for path in paths:
            spec = lookup(path)
            if spec is None or spec.role is not FactRole.INPUT:
                raise ValueError(f"{self.id}: {path} — не входной факт словаря")
        return self


class Step(BaseModel):
    """Шаг визарда."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    questions: list[Question] = Field(min_length=1)


class Questionnaire(BaseModel):
    """Анкета целиком."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    steps: list[Step] = Field(min_length=1)

    @property
    def questions(self) -> list[Question]:
        """Все вопросы по порядку."""
        return [question for step in self.steps for question in step.questions]


def _option_values(question: Question, tables: KnowledgeTables) -> list[str | int]:
    if question.options_from == "games":
        return [game.id for game in tables.games]
    if question.options_from == "applications":
        return [app.id for app in tables.applications]
    return [option.value for option in question.options]


def _record(
    memory: WorkingMemory, question: Question, answer: object, tables: KnowledgeTables
) -> None:
    match question.type:
        case QuestionType.TASKS:
            for value, weight in _task_weights(question, answer).items():
                memory.set_fact(f"{question.path}.{value}", weight)
        case QuestionType.WEIGHTS:
            if not isinstance(answer, Mapping):
                raise AnswerError(f"{question.title}: ожидаются веса по вариантам")
            values = {str(o.value) for o in question.options}
            unknown = set(answer) - values
            if unknown:
                raise AnswerError(f"{question.title}: неизвестные варианты {sorted(unknown)}")
            for option in question.options:
                percent = answer.get(option.value, 0)
                if isinstance(percent, bool) or not isinstance(percent, int | float):
                    raise AnswerError(f"{question.title}: вес должен быть числом 0–100")
                if not 0 <= percent <= 100:
                    raise AnswerError(f"{question.title}: вес должен быть от 0 до 100")
                memory.set_fact(f"{question.path}.{option.value}", round(percent / 100, 3))
        case QuestionType.NUMBER:
            if isinstance(answer, bool) or not isinstance(answer, int | float):
                raise AnswerError(f"{question.title}: ожидается число")
            low, high = question.min or 0, question.max or 0
            if not low <= answer <= high:
                raise AnswerError(f"{question.title}: допустимо от {low:g} до {high:g}")
            memory.set_fact(question.path, answer)
        case QuestionType.CHOICE:
            if answer not in _option_values(question, tables):
                raise AnswerError(f"{question.title}: недопустимый вариант «{answer}»")
            chosen = next((o for o in question.options if o.value == answer), None)
            if chosen is not None and chosen.facts:
                for path, value in chosen.facts.items():
                    memory.set_fact(path, value)
            elif answer != "any":
                memory.set_fact(question.path, answer)
        case QuestionType.MULTICHOICE:
            if not isinstance(answer, list) or not all(isinstance(a, str) for a in answer):
                raise AnswerError(f"{question.title}: ожидается список")
            allowed = _option_values(question, tables)
            bad = [a for a in answer if a not in allowed]
            if bad:
                raise AnswerError(f"{question.title}: неизвестные варианты {bad}")
            if answer:
                memory.set_fact(question.path, sorted(set(answer)))
        case QuestionType.YESNO:
            if answer not in YESNO_ANSWERS:
                raise AnswerError(f"{question.title}: ожидается да/скорее да/скорее нет/нет")
            value, cf = YESNO_ANSWERS[str(answer)]
            memory.set_fact(question.path, value, cf)


def _task_weights(question: Question, answer: object) -> dict[str | int, float]:
    if not isinstance(answer, Mapping):
        raise AnswerError(f"{question.title}: ожидаются основная и дополнительные задачи")
    unknown_keys = set(answer) - {"main", "extra"}
    if unknown_keys:
        raise AnswerError(f"{question.title}: неизвестные поля {sorted(unknown_keys)}")
    values = [option.value for option in question.options]
    main = answer.get("main")
    if main is None:
        raise AnswerError(f"{question.title}: выберите основную задачу")
    if main not in values:
        raise AnswerError(f"{question.title}: недопустимый вариант «{main}»")
    extra = answer.get("extra", [])
    if not isinstance(extra, list):
        raise AnswerError(f"{question.extra_title}: ожидается список")
    bad = [e for e in extra if e not in values]
    if bad:
        raise AnswerError(f"{question.extra_title}: неизвестные варианты {bad}")
    weights: dict[str | int, float] = {value: 0.0 for value in values}
    for value in extra:
        weights[value] = question.extra_weight
    weights[main] = question.main_weight
    return weights


def answers_to_memory(
    questionnaire: Questionnaire, answers: Mapping[str, object], tables: KnowledgeTables
) -> WorkingMemory:
    """Переводит ответы `{id вопроса: ответ}` в рабочую память с фактами `user.*` и `need.*`.

    Пропущенный вопрос и ответ «unknown» факта не дают. Бюджет и основная задача обязательны.
    """
    known = {question.id: question for question in questionnaire.questions}
    extra = sorted(set(answers) - known.keys())
    if extra:
        raise AnswerError(f"неизвестные вопросы: {', '.join(extra)}")
    memory = WorkingMemory()
    for question in questionnaire.questions:
        answer = answers.get(question.id, UNKNOWN)
        if answer == UNKNOWN or answer is None:
            if question.type in (QuestionType.NUMBER, QuestionType.TASKS):
                raise AnswerError(f"{question.title}: ответ обязателен")
            continue
        _record(memory, question, answer, tables)
    record_game_needs(tables, memory)
    return memory


def check_fact_types(questionnaire: Questionnaire) -> list[str]:
    """Проблемы анкеты для валидатора: типы вопросов против словаря, устаревшие виды вопросов."""
    expected = {
        QuestionType.TASKS: FactType.NUMBER,
        QuestionType.WEIGHTS: FactType.NUMBER,
        QuestionType.NUMBER: FactType.NUMBER,
        QuestionType.MULTICHOICE: FactType.LIST,
        QuestionType.YESNO: FactType.BOOL,
    }
    problems: list[str] = []
    for question in questionnaire.questions:
        if question.type is QuestionType.WEIGHTS:
            problems.append(f"{question.id}: слайдеры весов устарели — используйте вопрос tasks")
        if question.fact is None:
            continue  # факты вариантов проверены схемой
        path = (
            f"{question.fact}.{question.options[0].value}"
            if question.type in WEIGHTED
            else question.fact
        )
        spec = lookup(path)
        want = expected.get(question.type)
        if spec is not None and want is not None and spec.type is not want:
            problems.append(f"{question.id}: тип вопроса не совпадает с типом {path}")
    return problems
