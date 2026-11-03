"""Совместимость (compat) и проверка готовой сборки (validate).

Compat-правило проверяется, как только в сборке есть все детали, о которых оно говорит
(forward checking, вики §4.4). Если какой-то категории в плане нет (например, сборка без
видеокарты), правило проверяется по тем деталям, что есть; ссылки на отсутствующую деталь
делают условие ложным.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.expert.certainty import is_established
from app.expert.configurator.build import Build
from app.expert.dsl.compiler import (
    CompiledMessageAction,
    CompiledRule,
    CompiledRuleSet,
    fact_resolver,
)
from app.expert.dsl.expr import ExprEvalError
from app.expert.dsl.schema import RuleKind
from app.expert.facts import Fact, FactView, OverlayView
from app.expert.frames import Category
from app.expert.trace import Phase, RuleFailure, Trace

_CATEGORY_VALUES = {category.value: category for category in Category}


def rule_categories(rule: CompiledRule) -> frozenset[Category]:
    """Категории, детали которых читает правило (`build.<категория>.*`)."""
    categories: set[Category] = set()
    for path in rule.reads:
        if path.startswith("perf."):
            # Прогноз производительности появляется, когда в сборке есть процессор и графика.
            categories |= {Category.CPU, Category.GPU}
            continue
        parts = path.split(".")
        if parts[0] == "build" and len(parts) > 2 and parts[1] in _CATEGORY_VALUES:
            categories.add(_CATEGORY_VALUES[parts[1]])
    return frozenset(categories)


@dataclass(frozen=True, slots=True)
class Violation:
    """Нарушенное правило совместимости."""

    rule_code: str
    message: str


def _message(rule: CompiledRule, view: FactView) -> str:
    action = next((a for a in rule.actions if isinstance(a, CompiledMessageAction)), None)
    if action is None or action.message is None:
        return rule.rule.name
    return action.message.render(fact_resolver(view))


def trigger_index(
    rules: Iterable[CompiledRule], order: Iterable[Category]
) -> tuple[dict[Category, tuple[CompiledRule, ...]], dict[Category, tuple[CompiledRule, ...]]]:
    """Раскладывает правила по категории-«триггеру» и по всем упомянутым категориям плана.

    Триггер — последняя (по порядку плана) из категорий, детали которых читает правило:
    к этому моменту в сборке есть всё, о чём правило говорит.
    """
    sequence = tuple(order)
    position = {category: index for index, category in enumerate(sequence)}
    triggers: dict[Category, list[CompiledRule]] = {}
    involving: dict[Category, list[CompiledRule]] = {}
    for rule in rules:
        relevant = rule_categories(rule) & set(sequence)
        if not relevant:
            continue
        trigger = max(relevant, key=position.__getitem__)
        triggers.setdefault(trigger, []).append(rule)
        for category in relevant:
            involving.setdefault(category, []).append(rule)
    return (
        {c: tuple(rules) for c, rules in triggers.items()},
        {c: tuple(rules) for c, rules in involving.items()},
    )


class CompatChecker:
    """Compat-правила, разложенные по категории-«триггеру» для заданного порядка подбора."""

    def __init__(
        self,
        rule_set: CompiledRuleSet,
        order: Iterable[Category],
        memory: FactView,
        trace: Trace,
    ) -> None:
        self.memory = memory
        self.trace = trace
        triggers, involving = trigger_index(rule_set.of_kind(RuleKind.COMPAT), order)
        self.triggers: Mapping[Category, tuple[CompiledRule, ...]] = MappingProxyType(triggers)
        self.involving: Mapping[Category, tuple[CompiledRule, ...]] = MappingProxyType(involving)
        self.rejections: dict[str, int] = {}

    def _first_violation(self, build: Build, rules: Iterable[CompiledRule]) -> Violation | None:
        view = OverlayView(self.memory, build.facts)
        for rule in rules:
            try:
                match = rule.condition.evaluate(view)
            except ExprEvalError as exc:
                self.trace.add(RuleFailure(0, Phase.SEARCH, rule.code, str(exc)))
                continue
            if match is not None and is_established(match.cf):
                self.rejections[rule.code] = self.rejections.get(rule.code, 0) + 1
                return Violation(rule.code, _message(rule, view))
        return None

    def on_added(self, build: Build, category: Category) -> Violation | None:
        """Проверка после добавления детали `category` (только правила с этим триггером)."""
        return self._first_violation(build, self.triggers.get(category, ()))

    def on_replaced(self, build: Build, category: Category) -> Violation | None:
        """Проверка готовой сборки после замены детали `category`."""
        return self._first_violation(build, self.involving.get(category, ()))

    def violations_for(self, build: Build, category: Category) -> list[Violation]:
        """Все нарушения правил, в которых участвует деталь `category` (для «почему не»)."""
        found: list[Violation] = []
        for rule in self.involving.get(category, ()):
            violation = self._first_violation(build, (rule,))
            if violation is not None:
                found.append(violation)
        return found

    def violations(self, build: Build) -> list[Violation]:
        """Все нарушения в готовой сборке (для контроля результата)."""
        found: list[Violation] = []
        seen: set[str] = set()
        for rules in self.triggers.values():
            for rule in rules:
                if rule.code in seen:
                    continue
                seen.add(rule.code)
                violation = self._first_violation(build, (rule,))
                if violation is not None:
                    found.append(violation)
        return found


@dataclass(frozen=True, slots=True)
class Issue:
    """Результат validate-правила: ошибка, предупреждение или совет."""

    rule_code: str
    action: str
    message: str
    category: str | None = None
    target: str | None = None


def validate_build(
    build: Build,
    memory: FactView,
    rule_set: CompiledRuleSet,
    trace: Trace,
    perf_facts: Mapping[str, Fact] | None = None,
) -> tuple[Issue, ...]:
    """Применяет validate-правила к готовой сборке (с фактами прогноза `perf.*`, если есть)."""
    view = OverlayView(memory, {**build.facts, **(perf_facts or {})})
    issues: list[Issue] = []
    rules = sorted(rule_set.of_kind(RuleKind.VALIDATE), key=lambda r: (-r.rule.priority, r.code))
    for rule in rules:
        try:
            match = rule.condition.evaluate(view)
        except ExprEvalError as exc:
            trace.add(RuleFailure(0, Phase.VALIDATION, rule.code, str(exc)))
            continue
        if match is None or not is_established(match.cf):
            continue
        resolve = fact_resolver(view)
        for action in rule.actions:
            if isinstance(action, CompiledMessageAction):
                message = action.message.render(resolve) if action.message else rule.rule.name
                issues.append(
                    Issue(rule.code, action.action, message, action.category, action.target)
                )
    return tuple(issues)
