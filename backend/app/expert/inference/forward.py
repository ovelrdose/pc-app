"""Прямой вывод: цикл «распознавание — действие» (архитектура §5.5, вики §3.1)."""

from collections.abc import Iterable
from dataclasses import dataclass

from app.expert.certainty import conclusion, is_established
from app.expert.dsl.compiler import (
    CompiledAssert,
    CompiledRetract,
    CompiledRule,
    CompiledRuleSet,
    fact_resolver,
)
from app.expert.dsl.expr import ExprEvalError
from app.expert.dsl.schema import RuleKind
from app.expert.facts import FactChange, FactSource, Value, WorkingMemory
from app.expert.inference.agenda import Activation, Agenda, RefractionKey
from app.expert.trace import (
    EffectOutcome,
    FactEffect,
    MatchedFact,
    Phase,
    RuleFailure,
    RuleFiring,
    Trace,
)

DEFAULT_MAX_STEPS = 10_000


class InferenceLimitError(RuntimeError):
    """Превышен лимит шагов: вероятно, правила переписывают друг друга по кругу."""

    def __init__(self, max_steps: int, last_rules: list[str]) -> None:
        super().__init__(
            f"вывод остановлен после {max_steps} шагов; последние правила: {', '.join(last_rules)}"
        )
        self.max_steps = max_steps
        self.last_rules = last_rules


@dataclass(frozen=True, slots=True)
class ForwardResult:
    """Итог прямого вывода."""

    steps: int
    fired: tuple[str, ...]


def _outcome(change: FactChange, contributed_value: Value | None) -> EffectOutcome:
    before, after = change.before, change.after
    if after is None:
        return EffectOutcome.RETRACTED
    if before is None:
        return EffectOutcome.NEW
    if after.value != contributed_value:
        return EffectOutcome.OUTVOTED
    if before.value != after.value:
        return EffectOutcome.REPLACED
    if after.cf > before.cf:
        return EffectOutcome.STRENGTHENED
    if after.cf < before.cf:
        return EffectOutcome.WEAKENED
    return EffectOutcome.UNCHANGED


def _effect(change: FactChange, value: Value | None = None, cf: float | None = None) -> FactEffect:
    before, after = change.before, change.after
    return FactEffect(
        path=change.path,
        outcome=_outcome(change, value),
        contributed_value=value,
        contributed_cf=cf,
        value_before=before.value if before else None,
        cf_before=before.cf if before else None,
        value_after=after.value if after else None,
        cf_after=after.cf if after else None,
    )


class _ForwardChainer:
    def __init__(
        self,
        rule_set: CompiledRuleSet,
        memory: WorkingMemory,
        trace: Trace,
        phase: Phase,
        max_steps: int,
    ) -> None:
        self.rule_set = rule_set
        self.memory = memory
        self.trace = trace
        self.phase = phase
        self.max_steps = max_steps
        self.agenda = Agenda()
        self.fired_keys: set[RefractionKey] = set()
        self.fired: list[str] = []
        self.step = 0

    def run(self) -> ForwardResult:
        self._reconsider(self.rule_set.of_kind(RuleKind.INFERENCE))
        while len(self.agenda):
            if self.step >= self.max_steps:
                raise InferenceLimitError(self.max_steps, self.fired[-5:])
            activation = self.agenda.pop()
            self.step += 1
            self.fired_keys.add(activation.refraction_key)
            changed = self._fire(activation)
            dependents = {rule.code: rule for p in changed for rule in self.rule_set.dependents(p)}
            self._reconsider(dependents[code] for code in sorted(dependents))
        return ForwardResult(self.step, tuple(self.fired))

    def _reconsider(self, rules: Iterable[CompiledRule]) -> None:
        for rule in rules:
            self.agenda.discard(rule.code)
            try:
                match = rule.condition.evaluate(self.memory)
            except ExprEvalError as exc:
                self.trace.add(RuleFailure(self.step, self.phase, rule.code, str(exc)))
                continue
            if match is None or not is_established(match.cf):
                continue
            activation = Activation(rule, match)
            if activation.refraction_key not in self.fired_keys:
                self.agenda.put(activation)

    def _fire(self, activation: Activation) -> set[str]:
        rule = activation.rule
        cf = conclusion(rule.rule.cf, activation.match.cf)
        source = FactSource.rule(rule.code)
        effects: list[FactEffect] = []
        changed: set[str] = set()
        for action in rule.actions:
            if isinstance(action, CompiledRetract):
                change = self.memory.retract(action.fact)
                effects.append(_effect(change))
            elif isinstance(action, CompiledAssert):
                try:
                    value = (
                        action.expression.evaluate(fact_resolver(self.memory))
                        if action.expression is not None
                        else action.value
                    )
                except ExprEvalError as exc:
                    self.trace.add(RuleFailure(self.step, self.phase, rule.code, str(exc)))
                    continue
                change = self.memory.contribute(
                    action.fact,
                    value,
                    cf,
                    source,
                    specificity=rule.specificity,
                    step=self.step,
                )
                effects.append(_effect(change, _contributed_value(change, source, value), cf))
            else:  # pragma: no cover — схема не пропускает другие действия в inference
                continue
            if change.changed:
                changed.add(change.path)

        self.fired.append(rule.code)
        self.trace.add(
            RuleFiring(
                step=self.step,
                phase=self.phase,
                rule_code=rule.code,
                rule_name=rule.rule.name,
                priority=rule.rule.priority,
                specificity=rule.specificity,
                rule_cf=rule.rule.cf,
                premise_cf=activation.match.cf,
                matched=tuple(MatchedFact(f.path, f.value, f.cf) for f in activation.match.facts),
                effects=tuple(effects),
                explanation=rule.explain.render(fact_resolver(self.memory)),
            )
        )
        return changed


def _contributed_value(change: FactChange, source: FactSource, raw: Value | None) -> Value | None:
    # Значение, которое внесло правило (после нормализации памятью): ищем его вклад.
    after = change.after
    if after is not None and source in after.sources:
        return after.value
    for alternative in after.alternatives if after else ():
        if source in alternative.sources:
            return alternative.value
    return raw


def run_forward(
    rule_set: CompiledRuleSet,
    memory: WorkingMemory,
    *,
    trace: Trace | None = None,
    phase: Phase = Phase.PROFILING,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> ForwardResult:
    """Применяет inference-правила к рабочей памяти, пока агенда не опустеет.

    Память изменяется на месте, каждый шаг пишется в `trace`. При превышении `max_steps`
    бросает `InferenceLimitError`.
    """
    chainer = _ForwardChainer(rule_set, memory, trace or Trace(), phase, max_steps)
    return chainer.run()
