"""Обратный вывод: доказательство цели по goal-правилам (архитектура §5.6, вики §3.5).

Цель — `predicate(args)`. Ищутся goal-правила с таким предикатом, аргументы унифицируются
(переменные `$x` связываются из вопроса клиента или его фактов), условие правила доказывается
по частям: факты — по рабочей памяти и сборке, встроенные предикаты — моделью
производительности, подцели — рекурсивно. Если для переменной нет значения, но его можно
спросить, узел получает статус «неизвестно» и в доказательство добавляется вопрос клиенту.
Результат — дерево с узлами «доказано / опровергнуто / неизвестно».
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from app.expert.certainty import is_established
from app.expert.dsl.compiler import CompiledRuleSet, compile_condition, fact_resolver
from app.expert.dsl.expr import (
    ExprEvalError,
    MissingFactError,
    compile_expr,
    compile_template,
    format_value,
)
from app.expert.dsl.schema import (
    AllCondition,
    AnyCondition,
    Condition,
    ExprCondition,
    FactCondition,
    GoalCondition,
    GoalRef,
    NotCondition,
    Op,
    Rule,
    RuleKind,
)
from app.expert.facts import FactView, Scalar, Value, normalize_value
from app.expert.frames import FRAMES_BY_CATEGORY
from app.expert.vocabulary import lookup

MAX_DEPTH = 8

OP_TEXT: Mapping[Op, str] = {
    Op.EQ: "=",
    Op.NE: "≠",
    Op.LT: "<",
    Op.LE: "≤",
    Op.GT: ">",
    Op.GE: "≥",
    Op.IN: "∈",
    Op.NOT_IN: "∉",
    Op.CONTAINS: "содержит",
    Op.BETWEEN: "в диапазоне",
    Op.EXISTS: "есть",
}


class ProofStatus(StrEnum):
    """Исход узла доказательства."""

    PROVED = "proved"
    FAILED = "failed"
    UNKNOWN = "unknown"


class NodeKind(StrEnum):
    """Вид узла дерева доказательства."""

    GOAL = "goal"
    RULE = "rule"
    ALL = "all"
    ANY = "any"
    NOT = "not"
    FACT = "fact"
    EXPR = "expr"
    BUILTIN = "builtin"


@dataclass(frozen=True, slots=True)
class NeedInput:
    """Вопрос клиенту: значения не хватает, чтобы продолжить доказательство."""

    variable: str
    fact: str
    question: str
    options: tuple[Scalar, ...] = ()


@dataclass(frozen=True, slots=True)
class ProofNode:
    """Узел дерева доказательства."""

    kind: NodeKind
    label: str
    status: ProofStatus
    cf: float = 0.0
    rule_code: str | None = None
    detail: str | None = None
    value: Value | None = None
    children: tuple["ProofNode", ...] = ()
    need_input: tuple[NeedInput, ...] = ()

    @property
    def proved(self) -> bool:
        """Узел доказан."""
        return self.status is ProofStatus.PROVED

    def questions(self) -> list[NeedInput]:
        """Все вопросы клиенту в поддереве (без повторов)."""
        seen: dict[str, NeedInput] = {}
        for item in self.need_input:
            seen.setdefault(item.variable, item)
        for child in self.children:
            for item in child.questions():
                seen.setdefault(item.variable, item)
        return list(seen.values())


@dataclass(frozen=True, slots=True)
class Askable:
    """Переменная, значение которой можно взять из факта или спросить у клиента."""

    fact: str
    question: str
    options: tuple[Scalar, ...] = ()


type Builtin = Callable[[Mapping[str, Scalar]], ProofNode]
"""Встроенный предикат: аргументы → узел доказательства."""


def combine_children(
    children: list[ProofNode], *, any_of: bool = False
) -> tuple[ProofStatus, float]:
    """Статус и CF «все из» / «любое из» по дочерним узлам."""
    proved = [c for c in children if c.proved]
    if any_of:
        if proved:
            return ProofStatus.PROVED, max(c.cf for c in proved)
        unknown = any(c.status is ProofStatus.UNKNOWN for c in children)
        return (ProofStatus.UNKNOWN if unknown else ProofStatus.FAILED), 0.0
    if any(c.status is ProofStatus.FAILED for c in children):
        return ProofStatus.FAILED, 0.0
    if any(c.status is ProofStatus.UNKNOWN for c in children):
        return ProofStatus.UNKNOWN, 0.0
    return ProofStatus.PROVED, min((c.cf for c in children), default=1.0)


@dataclass(slots=True)
class BackwardChainer:
    """Доказывает цели по goal-правилам набора."""

    rule_set: CompiledRuleSet
    view: FactView
    builtins: Mapping[str, Builtin] = field(default_factory=dict)
    askable: Mapping[str, Askable] = field(default_factory=dict)
    max_depth: int = MAX_DEPTH
    _stack: list[tuple[str, tuple[tuple[str, Scalar], ...]]] = field(default_factory=list)

    def prove(
        self,
        predicate: str,
        args: Mapping[str, Scalar] | None = None,
        bindings: Mapping[str, Scalar] | None = None,
    ) -> ProofNode:
        """Доказывает `predicate(args)`; `bindings` — значения переменных `$x` от клиента."""
        return self._prove_goal(
            GoalRef(predicate=predicate, args=dict(args or {})), dict(bindings or {}), 0
        )

    # --- цели ---------------------------------------------------------------------------------

    def _rules_for(self, goal: GoalRef) -> list[tuple[Rule, dict[str, Scalar]]]:
        matches: list[tuple[Rule, dict[str, Scalar]]] = []
        for compiled in self.rule_set.of_kind(RuleKind.GOAL):
            head = compiled.rule.goal
            if head is None or head.predicate != goal.predicate:
                continue
            bound: dict[str, Scalar] = {}
            ok = True
            for name, head_value in head.args.items():
                query_value = goal.args.get(name)
                if isinstance(head_value, str) and head_value.startswith("$"):
                    if query_value is not None:
                        bound[head_value[1:]] = query_value
                elif query_value is not None and query_value != head_value:
                    ok = False
            if ok:
                matches.append((compiled.rule, bound))
        return matches

    def _prove_goal(self, goal: GoalRef, bindings: dict[str, Scalar], depth: int) -> ProofNode:
        label = self._goal_label(goal)
        builtin = self.builtins.get(goal.predicate)
        if builtin is not None:
            return builtin(goal.args)
        key = (goal.predicate, tuple(sorted(goal.args.items())))
        if depth > self.max_depth or key in self._stack:
            return ProofNode(
                NodeKind.GOAL, label, ProofStatus.FAILED, detail="цикл или слишком глубокая цель"
            )
        rules = self._rules_for(goal)
        if not rules:
            return ProofNode(
                NodeKind.GOAL, label, ProofStatus.FAILED, detail="нет правил для этой цели"
            )
        self._stack.append(key)
        try:
            children = [
                self._prove_rule(rule, {**bindings, **bound}, depth) for rule, bound in rules
            ]
        finally:
            self._stack.pop()
        status, cf = combine_children(children, any_of=True)
        return ProofNode(NodeKind.GOAL, label, status, cf, children=tuple(children))

    def _prove_rule(self, rule: Rule, bindings: dict[str, Scalar], depth: int) -> ProofNode:
        body = self._prove_condition(rule.when, bindings, depth)
        cf = round(rule.cf * body.cf, 6) if body.proved else 0.0
        explanation = compile_expr_template(rule.explain, self.view)
        return ProofNode(
            NodeKind.RULE,
            rule.name,
            body.status,
            cf,
            rule_code=rule.code,
            detail=explanation,
            children=(body,),
        )

    # --- условия ------------------------------------------------------------------------------

    def _prove_condition(
        self, condition: Condition, bindings: dict[str, Scalar], depth: int
    ) -> ProofNode:
        match condition:
            case AllCondition(all=items):
                children = [self._prove_condition(i, bindings, depth) for i in items]
                status, cf = combine_children(children)
                return ProofNode(NodeKind.ALL, "все условия", status, cf, children=tuple(children))
            case AnyCondition(any=items):
                children = [self._prove_condition(i, bindings, depth) for i in items]
                status, cf = combine_children(children, any_of=True)
                return ProofNode(
                    NodeKind.ANY, "любое из условий", status, cf, children=tuple(children)
                )
            case NotCondition(not_=inner):
                child = self._prove_condition(inner, bindings, depth)
                inverted = {
                    ProofStatus.PROVED: ProofStatus.FAILED,
                    ProofStatus.FAILED: ProofStatus.PROVED,
                }.get(child.status, ProofStatus.UNKNOWN)
                cf = 1.0 if inverted is ProofStatus.PROVED else 0.0
                return ProofNode(NodeKind.NOT, "не выполняется", inverted, cf, children=(child,))
            case GoalCondition(goal=goal):
                resolved, questions = self._resolve_args(goal.args, bindings)
                if questions:
                    return ProofNode(
                        NodeKind.GOAL,
                        self._goal_label(goal),
                        ProofStatus.UNKNOWN,
                        detail="не хватает данных",
                        need_input=tuple(questions),
                    )
                return self._prove_goal(
                    GoalRef(predicate=goal.predicate, args=resolved), bindings, depth + 1
                )
            case FactCondition():
                return self._prove_fact(condition)
            case ExprCondition(expr=source):
                return self._prove_expr(source)
        raise TypeError(f"неизвестное условие {condition!r}")  # pragma: no cover

    def _resolve_args(
        self, args: Mapping[str, Scalar], bindings: Mapping[str, Scalar]
    ) -> tuple[dict[str, Scalar], list[NeedInput]]:
        resolved: dict[str, Scalar] = {}
        questions: list[NeedInput] = []
        for name, value in args.items():
            if not (isinstance(value, str) and value.startswith("$")):
                resolved[name] = value
                continue
            variable = value[1:]
            if variable in bindings:
                resolved[name] = bindings[variable]
                continue
            askable = self.askable.get(variable)
            fact = self.view.lookup(askable.fact) if askable else None
            if fact is not None and is_established(fact.cf) and not isinstance(fact.value, tuple):
                resolved[name] = fact.value
            elif askable is not None:
                questions.append(
                    NeedInput(variable, askable.fact, askable.question, askable.options)
                )
            else:
                questions.append(
                    NeedInput(variable, f"${variable}", f"Укажите значение «{variable}»")
                )
        return resolved, questions

    def _prove_fact(self, leaf: FactCondition) -> ProofNode:
        operand = (
            fact_title(leaf.ref)
            if leaf.ref
            else format_value(normalize_value(leaf.value))
            if leaf.value is not None
            else ""
        )
        expected = f"{fact_title(leaf.fact)} {OP_TEXT[leaf.op]} {operand}".strip()
        fact = self.view.lookup(leaf.fact)
        actual = fact.value if fact is not None and is_established(fact.cf) else None
        try:
            match = compile_condition(leaf).evaluate(self.view)
        except ExprEvalError as exc:
            return ProofNode(
                NodeKind.FACT, expected, ProofStatus.FAILED, detail=str(exc), value=actual
            )
        if match is not None and is_established(match.cf):
            detail = f"есть: {format_value(actual)}" if actual is not None else None
            return ProofNode(
                NodeKind.FACT, expected, ProofStatus.PROVED, match.cf, detail=detail, value=actual
            )
        if actual is None and not leaf.fact.startswith(("build.", "cand.", "perf.")):
            return ProofNode(NodeKind.FACT, expected, ProofStatus.UNKNOWN, detail="нет данных")
        detail = (
            f"на самом деле: {format_value(actual)}" if actual is not None else "в сборке этого нет"
        )
        return ProofNode(NodeKind.FACT, expected, ProofStatus.FAILED, detail=detail, value=actual)

    def _prove_expr(self, source: str) -> ProofNode:
        expression = compile_expr(source)
        try:
            result = expression.evaluate(fact_resolver(self.view))
        except MissingFactError as exc:
            return ProofNode(
                NodeKind.EXPR, source, ProofStatus.FAILED, detail=f"нет значения {exc.path}"
            )
        except ExprEvalError as exc:
            return ProofNode(NodeKind.EXPR, source, ProofStatus.FAILED, detail=str(exc))
        status = ProofStatus.PROVED if result is True else ProofStatus.FAILED
        return ProofNode(
            NodeKind.EXPR, source, status, 1.0 if result is True else 0.0, value=result
        )

    def _goal_label(self, goal: GoalRef) -> str:
        args = ", ".join(f"{k}={format_value(v)}" for k, v in goal.args.items())
        return f"{goal.predicate}({args})"


def compile_expr_template(template: str, view: FactView) -> str:
    """Текст объяснения с подставленными значениями."""
    return compile_template(template).render(fact_resolver(view))


def fact_title(path: str) -> str:
    """Понятное название факта: «Оперативная память — Объём комплекта» вместо пути."""
    spec = lookup(path)
    if spec is None:
        return path
    parts = path.split(".")
    if parts[0] == "build" and len(parts) == 3 and parts[1] in _FRAME_TITLES:
        return f"{_FRAME_TITLES[parts[1]]} — {spec.title.lower()}"
    return spec.title


_FRAME_TITLES: Mapping[str, str] = {
    category.value: str(frame.model_config.get("title", category.value))
    for category, frame in FRAMES_BY_CATEGORY.items()
}
