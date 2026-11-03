"""Компиляция правил: условия → дерево вычисления, формулы → разобранные выражения, индексы.

Компилируется один раз при загрузке снимка базы знаний (вики §3.6): условия и формулы
разбираются, для каждого правила считается специфичность (число листьев условия), строится
индекс «факт → правила» для прямого вывода.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol

from app.expert.certainty import conjunction, disjunction, is_established, negation
from app.expert.dsl.expr import (
    Expression,
    ExprEvalError,
    ExprSyntaxError,
    MissingFactError,
    Template,
    compile_expr,
    compile_template,
)
from app.expert.dsl.schema import (
    AllCondition,
    AnyCondition,
    AssertAction,
    Condition,
    ErrorAction,
    ExprCondition,
    FactCondition,
    GoalCondition,
    GoalRef,
    NotCondition,
    Op,
    PreferAction,
    RejectAction,
    RetractAction,
    Rule,
    RuleKind,
    SuggestAction,
    WarnAction,
)
from app.expert.facts import Fact, FactView, Value, normalize_value

# --- Условия -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Match:
    """Условие выполнено: CF посылки и факты, на которых оно сработало."""

    cf: float
    facts: tuple[Fact, ...] = ()


def _merge_facts(matches: Iterable[Match]) -> tuple[Fact, ...]:
    seen: dict[str, Fact] = {}
    for match in matches:
        for fact in match.facts:
            seen.setdefault(fact.path, fact)
    return tuple(seen.values())


def _established(view: FactView, path: str) -> Fact | None:
    fact = view.lookup(path)
    return fact if fact is not None and is_established(fact.cf) else None


def fact_resolver(view: FactView, used: list[Fact] | None = None) -> Callable[[str], Value]:
    """Функция чтения фактов для выражений: только установленные факты (cf ≥ порога)."""

    def resolve(path: str) -> Value:
        fact = _established(view, path)
        if fact is None:
            raise MissingFactError(path)
        if used is not None:
            used.append(fact)
        return fact.value

    return resolve


def _ordered(op: Op, left: Value, right: Value) -> bool:
    numbers = all(isinstance(v, int | float) and not isinstance(v, bool) for v in (left, right))
    strings = isinstance(left, str) and isinstance(right, str)
    if not (numbers or strings):
        raise ExprEvalError(f"нельзя сравнить «{left}» и «{right}» оператором {op.value}")
    a, b = left, right
    match op:
        case Op.LT:
            return a < b  # type: ignore[operator]
        case Op.LE:
            return a <= b  # type: ignore[operator]
        case Op.GT:
            return a > b  # type: ignore[operator]
        case _:
            return a >= b  # type: ignore[operator]


def apply_op(op: Op, left: Value, right: Value) -> bool:
    """Применяет оператор листа условия к значению факта и операнду."""
    match op:
        case Op.EQ:
            return left == right
        case Op.NE:
            return left != right
        case Op.IN | Op.NOT_IN:
            if not isinstance(right, tuple):
                raise ExprEvalError(f"{op.value}: справа ожидается список")
            return (left in right) == (op is Op.IN)
        case Op.CONTAINS:
            if isinstance(left, tuple) or (isinstance(left, str) and isinstance(right, str)):
                return right in left
            raise ExprEvalError(f"contains: значение факта «{left}» не список и не строка")
        case Op.BETWEEN:
            if not (isinstance(right, tuple) and len(right) == 2):
                raise ExprEvalError("between: нужен список [от, до]")
            return _ordered(Op.GE, left, right[0]) and _ordered(Op.LE, left, right[1])
        case _:
            return _ordered(op, left, right)


class CompiledCondition(Protocol):
    """Узел скомпилированного условия."""

    @property
    def paths(self) -> frozenset[str]:
        """Пути фактов, которые читает узел."""
        ...

    @property
    def leaves(self) -> int:
        """Число листьев (для специфичности)."""
        ...

    def evaluate(self, view: FactView) -> Match | None:
        """`Match`, если условие выполнено, иначе `None`; `ExprEvalError` при ошибке типов."""
        ...


@dataclass(frozen=True, slots=True)
class _FactLeaf:
    fact: str
    op: Op
    value: Value | None
    ref: str | None

    @property
    def paths(self) -> frozenset[str]:
        return frozenset(p for p in (self.fact, self.ref) if p is not None)

    @property
    def leaves(self) -> int:
        return 1

    def evaluate(self, view: FactView) -> Match | None:
        left = _established(view, self.fact)
        if self.op is Op.EXISTS:
            return Match(left.cf, (left,)) if left is not None else None
        if left is None:
            return None
        if self.ref is None:
            assert self.value is not None  # noqa: S101 — гарантирует схема
            return Match(left.cf, (left,)) if apply_op(self.op, left.value, self.value) else None
        right = _established(view, self.ref)
        if right is None or not apply_op(self.op, left.value, right.value):
            return None
        return Match(min(left.cf, right.cf), (left, right))


@dataclass(frozen=True, slots=True)
class _ExprLeaf:
    expression: Expression

    @property
    def paths(self) -> frozenset[str]:
        return self.expression.paths

    @property
    def leaves(self) -> int:
        return 1

    def evaluate(self, view: FactView) -> Match | None:
        used: list[Fact] = []
        try:
            result = self.expression.evaluate(fact_resolver(view, used))
        except MissingFactError:
            return None
        if not isinstance(result, bool):
            raise ExprEvalError(f"условие «{self.expression.source}» должно давать да/нет")
        if not result:
            return None
        facts = _merge_facts([Match(1.0, tuple(used))])
        return Match(min((f.cf for f in facts), default=1.0), facts)


@dataclass(frozen=True, slots=True)
class _GoalLeaf:
    goal: GoalRef

    @property
    def paths(self) -> frozenset[str]:
        return frozenset()

    @property
    def leaves(self) -> int:
        return 1

    def evaluate(self, view: FactView) -> Match | None:
        raise ExprEvalError("подцели вычисляются только обратным выводом")


@dataclass(frozen=True, slots=True)
class _AllNode:
    items: tuple[CompiledCondition, ...]

    @property
    def paths(self) -> frozenset[str]:
        return frozenset().union(*(item.paths for item in self.items))

    @property
    def leaves(self) -> int:
        return sum(item.leaves for item in self.items)

    def evaluate(self, view: FactView) -> Match | None:
        matches: list[Match] = []
        for item in self.items:
            match = item.evaluate(view)
            if match is None:
                return None
            matches.append(match)
        return Match(conjunction(m.cf for m in matches), _merge_facts(matches))


@dataclass(frozen=True, slots=True)
class _AnyNode:
    items: tuple[CompiledCondition, ...]

    @property
    def paths(self) -> frozenset[str]:
        return frozenset().union(*(item.paths for item in self.items))

    @property
    def leaves(self) -> int:
        return sum(item.leaves for item in self.items)

    def evaluate(self, view: FactView) -> Match | None:
        matches = [m for m in (item.evaluate(view) for item in self.items) if m is not None]
        if not matches:
            return None
        best = max(matches, key=lambda m: m.cf)
        return Match(disjunction(m.cf for m in matches), best.facts)


@dataclass(frozen=True, slots=True)
class _NotNode:
    inner: CompiledCondition

    @property
    def paths(self) -> frozenset[str]:
        return self.inner.paths

    @property
    def leaves(self) -> int:
        return self.inner.leaves

    def evaluate(self, view: FactView) -> Match | None:
        match = self.inner.evaluate(view)
        if match is None:
            return Match(1.0)
        cf = negation(match.cf)
        return Match(cf, match.facts) if is_established(cf) else None


def compile_condition(condition: Condition) -> CompiledCondition:
    """Строит дерево вычисления условия; ошибки формул — `ExprSyntaxError`."""
    match condition:
        case AllCondition(all=items):
            return _AllNode(tuple(compile_condition(item) for item in items))
        case AnyCondition(any=items):
            return _AnyNode(tuple(compile_condition(item) for item in items))
        case NotCondition(not_=inner):
            return _NotNode(compile_condition(inner))
        case FactCondition(fact=fact, op=op, value=value, ref=ref):
            literal = normalize_value(value) if value is not None else None
            return _FactLeaf(fact, op, literal, ref)
        case ExprCondition(expr=source):
            return _ExprLeaf(compile_expr(source))
        case GoalCondition(goal=goal):
            return _GoalLeaf(goal)
    raise TypeError(f"неизвестный вид условия: {type(condition).__name__}")  # pragma: no cover


# --- Действия ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompiledAssert:
    """assert: путь и либо значение, либо формула."""

    fact: str
    value: Value | None
    expression: Expression | None


@dataclass(frozen=True, slots=True)
class CompiledRetract:
    """retract: путь снимаемого факта."""

    fact: str


@dataclass(frozen=True, slots=True)
class CompiledMessageAction:
    """reject / prefer / warn / error / suggest: вид действия, шаблон сообщения, параметры."""

    action: str
    message: Template | None
    weight: float | None = None
    category: str | None = None
    target: str | None = None


type CompiledAction = CompiledAssert | CompiledRetract | CompiledMessageAction


def _compile_action(
    action: AssertAction
    | RetractAction
    | RejectAction
    | PreferAction
    | WarnAction
    | ErrorAction
    | SuggestAction,
) -> CompiledAction:
    match action:
        case AssertAction(fact=fact, value=value, expr=expr):
            literal = normalize_value(value) if value is not None else None
            return CompiledAssert(fact, literal, compile_expr(expr) if expr else None)
        case RetractAction(fact=fact):
            return CompiledRetract(fact)
        case PreferAction(weight=weight, message=message):
            template = compile_template(message) if message else None
            return CompiledMessageAction("prefer", template, weight=weight)
        case SuggestAction(category=category, target=target, message=message):
            return CompiledMessageAction(
                "suggest", compile_template(message), category=category, target=target
            )
        case (
            RejectAction(message=message)
            | WarnAction(message=message)
            | ErrorAction(message=message)
        ):
            return CompiledMessageAction(action.action, compile_template(message))
    raise TypeError(f"неизвестное действие: {action!r}")  # pragma: no cover


# --- Правило и набор правил --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompiledRule:
    """Правило, готовое к вычислению."""

    rule: Rule
    condition: CompiledCondition
    actions: tuple[CompiledAction, ...]
    explain: Template

    @property
    def code(self) -> str:
        """Код правила."""
        return self.rule.code

    @property
    def specificity(self) -> int:
        """Специфичность: число листьев условия."""
        return self.condition.leaves

    @property
    def reads(self) -> frozenset[str]:
        """Пути фактов, которые читает условие."""
        return self.condition.paths

    @property
    def writes(self) -> frozenset[str]:
        """Пути фактов, которые правило записывает или снимает."""
        return frozenset(
            a.fact for a in self.actions if isinstance(a, CompiledAssert | CompiledRetract)
        )


@dataclass(frozen=True, slots=True)
class RuleCompileError:
    """Ошибка компиляции одного правила."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class KnowledgeCompileError(ValueError):
    """Набор правил не компилируется; `errors` — все найденные ошибки."""

    def __init__(self, errors: list[RuleCompileError]) -> None:
        super().__init__("; ".join(str(error) for error in errors))
        self.errors = tuple(errors)


@dataclass(frozen=True, slots=True)
class CompiledRuleSet:
    """Скомпилированные включённые правила с индексами по виду и по читаемым фактам."""

    rules: tuple[CompiledRule, ...]
    by_kind: dict[RuleKind, tuple[CompiledRule, ...]] = field(default_factory=dict)
    index: dict[str, tuple[CompiledRule, ...]] = field(default_factory=dict)

    def of_kind(self, kind: RuleKind) -> tuple[CompiledRule, ...]:
        """Правила указанного вида (в порядке кодов)."""
        return self.by_kind.get(kind, ())

    def dependents(self, path: str) -> tuple[CompiledRule, ...]:
        """Inference-правила, условия которых читают `path`."""
        return self.index.get(path, ())


def compile_rule(rule: Rule) -> CompiledRule:
    """Компилирует одно правило; `ExprSyntaxError` при ошибке в формуле или шаблоне."""
    return CompiledRule(
        rule=rule,
        condition=compile_condition(rule.when),
        actions=tuple(_compile_action(action) for action in rule.then),
        explain=compile_template(rule.explain),
    )


def compile_rules(rules: Iterable[Rule]) -> CompiledRuleSet:
    """Компилирует включённые правила; собирает все ошибки и бросает `KnowledgeCompileError`."""
    compiled: list[CompiledRule] = []
    errors: list[RuleCompileError] = []
    seen: set[str] = set()
    for rule in rules:
        if rule.code in seen:
            errors.append(RuleCompileError(rule.code, "код правила повторяется"))
            continue
        seen.add(rule.code)
        if not rule.enabled:
            continue
        try:
            compiled.append(compile_rule(rule))
        except ExprSyntaxError as exc:
            errors.append(RuleCompileError(rule.code, str(exc)))
    if errors:
        raise KnowledgeCompileError(errors)

    compiled.sort(key=lambda r: r.code)
    by_kind: dict[RuleKind, list[CompiledRule]] = {}
    index: dict[str, list[CompiledRule]] = {}
    for item in compiled:
        by_kind.setdefault(item.rule.kind, []).append(item)
        if item.rule.kind is RuleKind.INFERENCE:
            for path in item.reads:
                index.setdefault(path, []).append(item)
    return CompiledRuleSet(
        rules=tuple(compiled),
        by_kind={kind: tuple(items) for kind, items in by_kind.items()},
        index={path: tuple(items) for path, items in index.items()},
    )
