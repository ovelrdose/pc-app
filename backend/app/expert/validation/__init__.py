"""Статические проверки базы знаний (архитектура §6.2). Ошибки блокируют публикацию.

Проверки: уникальность кодов, компиляция формул, существование путей фактов и типы операндов,
циклы между inference-правилами, противоречия, недостижимые правила, неизвестные предикаты
целей; предупреждения — избыточность, неиспользуемые выводы, правила без «предмета в руках».
"""

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from app.expert.dsl.compiler import KnowledgeCompileError, compile_rules
from app.expert.dsl.expr import ExprSyntaxError, compile_expr, compile_template
from app.expert.dsl.schema import (
    AllCondition,
    AnyCondition,
    AssertAction,
    Condition,
    ExprCondition,
    FactCondition,
    GoalCondition,
    NotCondition,
    Op,
    RetractAction,
    Rule,
    RuleKind,
)
from app.expert.vocabulary import FactRole, FactSpec, FactType, lookup

BUILTIN_PREDICATES: frozenset[str] = frozenset({"fps_at_least", "vram_enough", "bench_at_least"})
"""Предикаты, которые вычисляет модель производительности (этап 5)."""

CONFIGURATOR_READS_PREFIXES: tuple[str, ...] = (
    "budget.share.",
    "budget.first_category",
    "req.need.",
    "profile.weight.",
)
"""Факты, которые читает конфигуратор (ADR 0003), — их вывод не считается «неиспользуемым»."""

_ORDERED_OPS = {Op.LT, Op.LE, Op.GT, Op.GE, Op.BETWEEN}


class Severity(StrEnum):
    """Серьёзность замечания."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Finding:
    """Замечание валидатора."""

    severity: Severity
    check: str
    rule_code: str | None
    message: str

    def __str__(self) -> str:
        where = f"{self.rule_code}: " if self.rule_code else ""
        return f"[{self.check}] {where}{self.message}"


@dataclass(slots=True)
class ValidationReport:
    """Итог проверки базы знаний."""

    findings: list[Finding] = field(default_factory=list)
    rules_total: int = 0

    @property
    def errors(self) -> list[Finding]:
        """Блокирующие ошибки."""
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        """Предупреждения."""
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        """Ошибок нет."""
        return not self.errors

    def add(self, severity: Severity, check: str, rule: str | None, message: str) -> None:
        """Добавляет замечание."""
        self.findings.append(Finding(severity, check, rule, message))


# --- Обход условий ------------------------------------------------------------------------------


def iter_leaves(condition: Condition) -> Iterator[FactCondition | ExprCondition | GoalCondition]:
    """Все листья дерева условия."""
    match condition:
        case AllCondition(all=items) | AnyCondition(any=items):
            for item in items:
                yield from iter_leaves(item)
        case NotCondition(not_=inner):
            yield from iter_leaves(inner)
        case _:
            yield condition


def _expr_paths(source: str) -> frozenset[str]:
    try:
        return compile_expr(source).paths
    except ExprSyntaxError:
        return frozenset()  # о синтаксисе сообщает проверка компиляции


def _template_paths(template: str) -> frozenset[str]:
    try:
        return compile_template(template).paths
    except ExprSyntaxError:
        return frozenset()


def rule_reads(rule: Rule) -> set[str]:
    """Пути фактов, которые читает условие правила."""
    paths: set[str] = set()
    for leaf in iter_leaves(rule.when):
        if isinstance(leaf, FactCondition):
            paths.add(leaf.fact)
            if leaf.ref:
                paths.add(leaf.ref)
        elif isinstance(leaf, ExprCondition):
            paths |= _expr_paths(leaf.expr)
    return paths


def rule_writes(rule: Rule) -> set[str]:
    """Пути фактов, которые правило утверждает или снимает."""
    return {a.fact for a in rule.then if isinstance(a, AssertAction | RetractAction)}


def _template_reads(rule: Rule) -> set[str]:
    paths = set(_template_paths(rule.explain))
    for action in rule.then:
        message = getattr(action, "message", None)
        if message:
            paths |= _template_paths(message)
    for action in rule.then:
        if isinstance(action, AssertAction) and action.expr:
            paths |= _expr_paths(action.expr)
    return paths


# --- Типы ---------------------------------------------------------------------------------------


def _value_type(value: object) -> FactType:
    if isinstance(value, bool):
        return FactType.BOOL
    if isinstance(value, int | float):
        return FactType.NUMBER
    if isinstance(value, list):
        return FactType.LIST
    return FactType.STR


def _check_value(spec: FactSpec, value: object, what: str) -> str | None:
    kind = _value_type(value)
    if kind is not spec.type:
        return f"{what}: {spec.path} — {spec.type.value}, а значение «{value}» — {kind.value}"
    if spec.values and value not in spec.values:
        allowed = ", ".join(str(v) for v in spec.values)
        return f"{what}: «{value}» не входит в допустимые значения {spec.path} ({allowed})"
    return None


def _check_fact_leaf(leaf: FactCondition) -> list[str]:
    spec = lookup(leaf.fact)
    if spec is None:
        return []  # о неизвестном пути сообщает проверка путей
    problems: list[str] = []
    if leaf.op in _ORDERED_OPS and spec.type is not FactType.NUMBER:
        problems.append(f"оператор {leaf.op.value} применён к нечисловому факту {leaf.fact}")
    if leaf.op is Op.CONTAINS and spec.type not in (FactType.LIST, FactType.STR):
        problems.append(f"contains применён к {leaf.fact}, который не список и не строка")
    if leaf.ref is not None:
        other = lookup(leaf.ref)
        if other is not None and leaf.op is not Op.CONTAINS and other.type is not spec.type:
            problems.append(
                f"сравниваются факты разных типов: {leaf.fact} ({spec.type.value}) и "
                f"{leaf.ref} ({other.type.value})"
            )
        return problems
    value = leaf.value
    if value is None or leaf.op is Op.EXISTS:
        return problems
    if leaf.op in (Op.IN, Op.NOT_IN, Op.BETWEEN):
        items = value if isinstance(value, list) else [value]
        problems += [p for item in items if (p := _check_value(spec, item, "значение"))]
    elif leaf.op is Op.CONTAINS:
        if spec.type is FactType.LIST and spec.values and value not in spec.values:
            problems.append(f"«{value}» не может содержаться в {leaf.fact}")
    elif spec.type is not FactType.LIST and (p := _check_value(spec, value, "значение")):
        problems.append(p)
    return problems


# --- Проверки -----------------------------------------------------------------------------------


def _check_compilation(rules: list[Rule], report: ValidationReport) -> None:
    try:
        compile_rules(rules)
    except KnowledgeCompileError as exc:
        for error in exc.errors:
            report.add(Severity.ERROR, "compile", error.code, error.message)


def _check_paths_and_types(rules: list[Rule], report: ValidationReport) -> None:
    for rule in rules:
        for path in sorted(rule_reads(rule) | rule_writes(rule) | _template_reads(rule)):
            if lookup(path) is None:
                report.add(Severity.ERROR, "paths", rule.code, f"неизвестный факт {path}")
        for leaf in iter_leaves(rule.when):
            if isinstance(leaf, FactCondition):
                for problem in _check_fact_leaf(leaf):
                    report.add(Severity.ERROR, "types", rule.code, problem)
        for action in rule.then:
            if isinstance(action, AssertAction):
                spec = lookup(action.fact)
                if spec is None:
                    continue
                if spec.role is not FactRole.DERIVED:
                    report.add(Severity.ERROR, "paths", rule.code, f"{action.fact} нельзя выводить")
                if action.value is not None and (p := _check_value(spec, action.value, "assert")):
                    report.add(Severity.ERROR, "types", rule.code, p)


def _check_subjects(rules: list[Rule], report: ValidationReport) -> None:
    needs: dict[RuleKind, tuple[str, ...]] = {
        RuleKind.FILTER: ("cand.",),
        RuleKind.COMPAT: ("build.",),
        RuleKind.SCORE: ("build.", "perf."),
    }
    for rule in rules:
        prefixes = needs.get(rule.kind)
        if prefixes and not any(p.startswith(prefixes) for p in rule_reads(rule)):
            subject = " / ".join(f"{prefix}*" for prefix in prefixes)
            report.add(
                Severity.WARNING,
                "subject",
                rule.code,
                f"правило вида {rule.kind.value} не читает {subject} — применяется ко всему подряд",
            )


def _inference(rules: Iterable[Rule]) -> list[Rule]:
    return [r for r in rules if r.kind is RuleKind.INFERENCE and r.enabled]


def _check_cycles(rules: list[Rule], report: ValidationReport) -> None:
    inference = _inference(rules)
    readers: dict[str, list[str]] = {}
    for rule in inference:
        for path in rule_reads(rule):
            readers.setdefault(path, []).append(rule.code)
    graph = {
        rule.code: sorted({r for p in rule_writes(rule) for r in readers.get(p, [])})
        for rule in inference
    }
    reported: set[frozenset[str]] = set()
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(code: str) -> None:
        state[code] = 1
        stack.append(code)
        for nxt in graph[code]:
            if state.get(nxt) == 1:
                cycle = stack[stack.index(nxt) :]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    chain = " → ".join([*cycle, nxt])
                    report.add(Severity.ERROR, "cycle", nxt, f"цикл выводов: {chain}")
            elif nxt not in state:
                visit(nxt)
        stack.pop()
        state[code] = 2

    for code in sorted(graph):
        if code not in state:
            visit(code)


def _condition_key(condition: Condition) -> str:
    return json.dumps(condition.model_dump(mode="json", by_alias=True), sort_keys=True)


def _check_contradictions(rules: list[Rule], report: ValidationReport) -> None:
    seen: dict[tuple[str, str], tuple[str, object]] = {}
    for rule in _inference(rules):
        key_when = _condition_key(rule.when)
        for action in rule.then:
            if not isinstance(action, AssertAction) or action.value is None:
                continue
            key = (key_when, action.fact)
            previous = seen.get(key)
            if previous is not None and previous[1] != action.value:
                report.add(
                    Severity.ERROR,
                    "contradiction",
                    rule.code,
                    f"при тех же условиях, что {previous[0]}, утверждает {action.fact} = "
                    f"{action.value}, а не {previous[1]}",
                )
            seen.setdefault(key, (rule.code, action.value))


def _check_reachability(rules: list[Rule], report: ValidationReport) -> None:
    derived = {p for r in _inference(rules) for p in rule_writes(r)}
    for rule in rules:
        for path in sorted(rule_reads(rule)):
            spec = lookup(path)
            if spec is not None and spec.role is FactRole.DERIVED and path not in derived:
                report.add(
                    Severity.ERROR,
                    "unreachable",
                    rule.code,
                    f"читает {path}, но ни одно правило его не выводит",
                )


def _leaf_keys(rule: Rule) -> frozenset[str] | None:
    condition = rule.when
    items = condition.all if isinstance(condition, AllCondition) else [condition]
    if any(isinstance(item, AnyCondition | NotCondition | AllCondition) for item in items):
        return None
    return frozenset(_condition_key(item) for item in items)


def _check_redundancy(rules: list[Rule], report: ValidationReport) -> None:
    keyed = [
        (rule, keys, json.dumps([a.model_dump(mode="json") for a in rule.then], sort_keys=True))
        for rule in rules
        if rule.kind is not RuleKind.GOAL and (keys := _leaf_keys(rule)) is not None
    ]
    for general, general_keys, general_then in keyed:
        for specific, specific_keys, specific_then in keyed:
            if (
                general.code != specific.code
                and general_then == specific_then
                and general.kind is specific.kind
                and general_keys < specific_keys
            ):
                report.add(
                    Severity.WARNING,
                    "redundancy",
                    specific.code,
                    f"избыточно: {general.code} делает то же при более общем условии",
                )


def _check_unused(rules: list[Rule], report: ValidationReport) -> None:
    read = {p for r in rules for p in rule_reads(r) | _template_reads(r)}
    for rule in _inference(rules):
        for path in sorted(rule_writes(rule)):
            if path in read or path.startswith(CONFIGURATOR_READS_PREFIXES):
                continue
            report.add(
                Severity.WARNING,
                "unused",
                rule.code,
                f"выводит {path}, но ни одно правило и ни один этап подбора его не читает",
            )


def _check_goals(rules: list[Rule], report: ValidationReport) -> None:
    heads = {r.goal.predicate for r in rules if r.kind is RuleKind.GOAL and r.goal}
    known = heads | BUILTIN_PREDICATES
    for rule in rules:
        for leaf in iter_leaves(rule.when):
            if isinstance(leaf, GoalCondition) and leaf.goal.predicate not in known:
                report.add(
                    Severity.ERROR,
                    "goal",
                    rule.code,
                    f"неизвестный предикат подцели {leaf.goal.predicate}",
                )


def _check_codes(rules: list[Rule], report: ValidationReport) -> None:
    seen: set[str] = set()
    for rule in rules:
        if rule.code in seen:
            report.add(Severity.ERROR, "unique", rule.code, "код правила повторяется")
        seen.add(rule.code)


def validate_knowledge(rules: list[Rule]) -> ValidationReport:
    """Проверяет набор правил целиком."""
    report = ValidationReport(rules_total=len(rules))
    _check_codes(rules, report)
    if report.errors:
        return report  # дальнейшие проверки на повторяющихся кодах бессмысленны
    _check_compilation(rules, report)
    _check_paths_and_types(rules, report)
    _check_goals(rules, report)
    _check_cycles(rules, report)
    _check_contradictions(rules, report)
    _check_reachability(rules, report)
    _check_subjects(rules, report)
    _check_redundancy(rules, report)
    _check_unused(rules, report)
    return report
