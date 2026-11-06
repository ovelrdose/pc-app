"""Схема правила базы знаний (архитектура §5.3): условия, действия, общие поля.

Здесь проверяется то, что видно по одному правилу: формат кода, допустимые действия для вида,
CF правил совместимости, пространства имён фактов. Проверки всей базы (противоречия, циклы,
недостижимые правила) — в `expert/validation` (этап 4).
"""

from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.expert.facts import NAMESPACES, Scalar

CODE_PATTERN = r"^(?:[A-Z]{3}-\d{3}|GEN-[A-Z0-9]+(?:-[A-Z0-9]+)+)$"
PATH_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$"

MANUAL_PREFIXES: frozenset[str] = frozenset(
    {"PRF", "REQ", "BUD", "FLT", "CMP", "BAL", "SCR", "VAL", "GOL"}
)
"""Префиксы ручных правил (архитектура §6.5); `GEN-*` создаёт только генератор."""

# Куда правилу вида inference разрешено писать (архитектура §5.2).
INFERENCE_WRITABLE: frozenset[str] = frozenset({"profile", "req", "budget"})

type LiteralValue = Scalar | list[Scalar]


class DslModel(BaseModel):
    """Общая конфигурация моделей DSL: неизменяемые, без лишних полей."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class RuleKind(StrEnum):
    """Вид правила: на каком этапе и как оно применяется."""

    INFERENCE = "inference"
    FILTER = "filter"
    COMPAT = "compat"
    SCORE = "score"
    VALIDATE = "validate"
    GOAL = "goal"


class RuleOrigin(StrEnum):
    """Происхождение правила."""

    MANUAL = "manual"
    GENERATED = "generated"


class Op(StrEnum):
    """Операторы сравнения в листе условия."""

    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    BETWEEN = "between"
    EXISTS = "exists"


FactPath = Annotated[str, Field(pattern=PATH_PATTERN, max_length=120)]


def _check_namespace(path: str) -> str:
    namespace = path.split(".", 1)[0]
    if namespace not in NAMESPACES:
        raise ValueError(f"неизвестное пространство имён «{namespace}» в пути {path}")
    return path


# --- Условия -----------------------------------------------------------------------------------


class FactCondition(DslModel):
    """Лист: `{fact, op, value}` или `{fact, op, ref}` (сравнение двух фактов)."""

    fact: FactPath
    op: Op
    value: LiteralValue | None = None
    ref: FactPath | None = None

    @model_validator(mode="after")
    def _operands(self) -> Self:
        _check_namespace(self.fact)
        if self.ref is not None:
            _check_namespace(self.ref)
        if self.op is Op.EXISTS:
            if self.value is not None or self.ref is not None:
                raise ValueError("у оператора exists не бывает value и ref")
            return self
        if (self.value is None) == (self.ref is None):
            raise ValueError(f"оператору {self.op.value} нужно ровно одно из value или ref")
        if self.ref is not None and self.op is Op.BETWEEN:
            raise ValueError("between сравнивает только со списком [от, до] в value")
        if self.op in (Op.IN, Op.NOT_IN) and self.ref is None and not isinstance(self.value, list):
            raise ValueError(f"оператору {self.op.value} нужен список в value")
        if self.op is Op.BETWEEN and not (isinstance(self.value, list) and len(self.value) == 2):
            raise ValueError("оператору between нужен список [от, до]")
        return self


class ExprCondition(DslModel):
    """Лист: формула `{expr: "..."}`; проверяется интерпретатором при компиляции."""

    expr: str = Field(min_length=1, max_length=500)


class GoalRef(DslModel):
    """Цель обратного вывода: `predicate(args)`; аргументы могут быть переменными `$x`."""

    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    args: dict[str, Scalar] = Field(default_factory=dict)


class GoalCondition(DslModel):
    """Лист-подцель (только в правилах вида goal)."""

    goal: GoalRef


class AllCondition(DslModel):
    """«Все из» (И)."""

    all: list["Condition"] = Field(min_length=1)


class AnyCondition(DslModel):
    """«Любое из» (ИЛИ)."""

    any: list["Condition"] = Field(min_length=1)


class NotCondition(DslModel):
    """«Не»."""

    not_: "Condition" = Field(alias="not")


Condition = (
    AllCondition | AnyCondition | NotCondition | FactCondition | ExprCondition | GoalCondition
)


# --- Действия ----------------------------------------------------------------------------------


class AssertAction(DslModel):
    """Добавить или усилить факт: значение-литерал (`value`) или формула (`expr`)."""

    action: Literal["assert"]
    fact: FactPath
    value: LiteralValue | None = None
    expr: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.value is None) == (self.expr is None):
            raise ValueError("у assert должно быть ровно одно из value или expr")
        return self


class RetractAction(DslModel):
    """Снять факт."""

    action: Literal["retract"]
    fact: FactPath


class RejectAction(DslModel):
    """Отсечь кандидата (filter) или сочетание (compat)."""

    action: Literal["reject"]
    message: str = Field(min_length=1, max_length=500)


class PreferAction(DslModel):
    """Добавить к полезности `weight × cf` (score); вес может быть отрицательным."""

    action: Literal["prefer"]
    weight: float = Field(ge=-100, le=100)
    message: str | None = Field(default=None, max_length=500)


class WarnAction(DslModel):
    """Предупреждение по готовой сборке (validate)."""

    action: Literal["warn"]
    message: str = Field(min_length=1, max_length=500)


class ErrorAction(DslModel):
    """Блокирующая ошибка по готовой сборке (validate)."""

    action: Literal["error"]
    message: str = Field(min_length=1, max_length=500)


class SuggestAction(DslModel):
    """Предложить правку: заменить компонент категории на более подходящий класс (validate)."""

    action: Literal["suggest"]
    category: str = Field(pattern=r"^[a-z_]+$")
    target: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)


Action = Annotated[
    AssertAction
    | RetractAction
    | RejectAction
    | PreferAction
    | WarnAction
    | ErrorAction
    | SuggestAction,
    Field(discriminator="action"),
]

ALLOWED_ACTIONS: dict[RuleKind, frozenset[str]] = {
    RuleKind.INFERENCE: frozenset({"assert", "retract"}),
    RuleKind.FILTER: frozenset({"reject"}),
    RuleKind.COMPAT: frozenset({"reject"}),
    RuleKind.SCORE: frozenset({"prefer"}),
    RuleKind.VALIDATE: frozenset({"warn", "error", "suggest"}),
    RuleKind.GOAL: frozenset(),
}


# --- Правило -----------------------------------------------------------------------------------


class Rule(DslModel):
    """Правило базы знаний в том виде, как оно хранится в YAML и в БД."""

    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    kind: RuleKind
    group: str = Field(pattern=r"^[a-z_]+$")
    priority: int = Field(ge=0, le=1000)
    cf: float = Field(ge=-1, le=1)
    enabled: bool = True
    origin: RuleOrigin = RuleOrigin.MANUAL
    source: str | None = Field(default=None, max_length=200)
    goal: GoalRef | None = None
    when: Condition
    then: list[Action] = Field(default_factory=list)
    explain: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        problems = [*self._kind_problems(), *self._action_problems()]
        if self.origin is RuleOrigin.GENERATED and not self.source:
            problems.append("у сгенерированного правила должен быть source")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _kind_problems(self) -> list[str]:
        problems: list[str] = []
        if self.cf == 0:
            problems.append("cf не может быть равен 0")
        if self.kind is RuleKind.COMPAT and self.cf != 1.0:
            problems.append("у правил совместимости cf всегда 1.0")
        if self.kind is RuleKind.GOAL:
            if self.goal is None:
                problems.append("у правила вида goal должна быть цель (goal)")
            if self.then:
                problems.append("у правила вида goal нет действий (then)")
        else:
            if self.goal is not None:
                problems.append("цель (goal) бывает только у правил вида goal")
            if not self.then:
                problems.append("нужно хотя бы одно действие (then)")
            if _has_goal_leaf(self.when):
                problems.append("подцели бывают только в правилах вида goal")
        return problems

    def _action_problems(self) -> list[str]:
        problems: list[str] = []
        allowed = ALLOWED_ACTIONS[self.kind]
        for action in self.then:
            if action.action not in allowed:
                names = ", ".join(sorted(allowed)) or "нет"
                problems.append(
                    f"действие {action.action} недопустимо для вида {self.kind.value} "
                    f"(допустимы: {names})"
                )
            if isinstance(action, AssertAction | RetractAction):
                namespace = action.fact.split(".", 1)[0]
                if namespace not in INFERENCE_WRITABLE:
                    problems.append(
                        f"правило вида inference не может писать в {namespace}.* ({action.fact})"
                    )
        return problems


def _has_goal_leaf(condition: Condition) -> bool:
    match condition:
        case GoalCondition():
            return True
        case AllCondition(all=items) | AnyCondition(any=items):
            return any(_has_goal_leaf(item) for item in items)
        case NotCondition(not_=inner):
            return _has_goal_leaf(inner)
    return False


def parse_rules(data: list[dict[str, Any]]) -> list[Rule]:
    """Разбирает список правил (из YAML или БД); ошибки — `pydantic.ValidationError`."""
    return [Rule.model_validate(item) for item in data]


AllCondition.model_rebuild()
AnyCondition.model_rebuild()
NotCondition.model_rebuild()
Rule.model_rebuild()
