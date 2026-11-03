"""Агенда (набор конфликтов) и стратегия разрешения конфликтов (архитектура §5.5, вики §3.2)."""

from dataclasses import dataclass, field

from app.expert.dsl.compiler import CompiledRule, Match
from app.expert.facts import Value

type RefractionKey = tuple[str, tuple[tuple[str, Value, float], ...]]


@dataclass(frozen=True, slots=True)
class Activation:
    """Правило, условие которого выполнено, вместе с фактами, на которых оно сработало."""

    rule: CompiledRule
    match: Match

    @property
    def recency(self) -> int:
        """Свежесть: шаг, на котором изменился самый новый из использованных фактов."""
        return max((fact.step for fact in self.match.facts), default=0)

    @property
    def refraction_key(self) -> RefractionKey:
        """Одна и та же активация (правило + те же факты) повторно не срабатывает."""
        facts = sorted((f.path, f.value, f.cf) for f in self.match.facts)
        return self.rule.code, tuple(facts)

    def sort_key(self) -> tuple[int, int, int, str]:
        """Порядок: приоритет ↓, специфичность ↓, свежесть ↓, затем код (детерминизм)."""
        return (-self.rule.rule.priority, -self.rule.specificity, -self.recency, self.rule.code)


@dataclass(slots=True)
class Agenda:
    """Набор конфликтов: не больше одной активации на правило (у inference нет переменных)."""

    _activations: dict[str, Activation] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self._activations)

    def put(self, activation: Activation) -> None:
        """Добавляет или заменяет активацию правила."""
        self._activations[activation.rule.code] = activation

    def discard(self, rule_code: str) -> None:
        """Убирает активацию правила, если она есть."""
        self._activations.pop(rule_code, None)

    def pop(self) -> Activation:
        """Извлекает активацию, которая должна сработать первой."""
        best = min(self._activations.values(), key=Activation.sort_key)
        del self._activations[best.rule.code]
        return best

    def pending(self) -> list[Activation]:
        """Активации в порядке срабатывания (для отладки и объяснений)."""
        return sorted(self._activations.values(), key=Activation.sort_key)
