"""Трасса вывода — журнал рассуждений, основа объяснений (вики, страница 6)."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from app.expert.facts import Value


class Phase(StrEnum):
    """Этап конвейера, на котором сделана запись."""

    PROFILING = "profiling"
    FILTERING = "filtering"
    SEARCH = "search"
    SCORING = "scoring"
    VALIDATION = "validation"
    BACKWARD = "backward"


class EffectOutcome(StrEnum):
    """Чем закончилось действие над фактом."""

    NEW = "new"
    STRENGTHENED = "strengthened"
    WEAKENED = "weakened"
    REPLACED = "replaced"
    UNCHANGED = "unchanged"
    OUTVOTED = "outvoted"
    RETRACTED = "retracted"


@dataclass(frozen=True, slots=True)
class MatchedFact:
    """Факт, на котором сработало условие."""

    path: str
    value: Value
    cf: float


@dataclass(frozen=True, slots=True)
class FactEffect:
    """Что действие сделало с фактом: было → стало, и вклад самого правила."""

    path: str
    outcome: EffectOutcome
    contributed_value: Value | None
    contributed_cf: float | None
    value_before: Value | None
    cf_before: float | None
    value_after: Value | None
    cf_after: float | None


@dataclass(frozen=True, slots=True)
class RuleFiring:
    """Срабатывание правила."""

    step: int
    phase: Phase
    rule_code: str
    rule_name: str
    priority: int
    specificity: int
    rule_cf: float
    premise_cf: float
    matched: tuple[MatchedFact, ...]
    effects: tuple[FactEffect, ...]
    explanation: str
    type: str = "rule_fired"


@dataclass(frozen=True, slots=True)
class RuleFailure:
    """Правило не удалось вычислить (например, деление на ноль в формуле)."""

    step: int
    phase: Phase
    rule_code: str
    message: str
    type: str = "rule_failed"


@dataclass(frozen=True, slots=True)
class CandidateRejected:
    """Товар отсеян на этапе фильтрации (правилом или встроенной проверкой)."""

    phase: Phase
    sku: str
    category: str
    rule_code: str | None
    message: str
    type: str = "candidate_rejected"


@dataclass(frozen=True, slots=True)
class CombinationRejected:
    """Сочетание деталей отброшено правилом совместимости (первые случаи на правило)."""

    phase: Phase
    skus: tuple[str, ...]
    rule_code: str
    message: str
    type: str = "combination_rejected"


@dataclass(frozen=True, slots=True)
class BuildIssue:
    """Ошибка, предупреждение, совет или баллы по готовой сборке."""

    phase: Phase
    build_skus: tuple[str, ...]
    rule_code: str
    action: str
    message: str
    weight: float | None = None
    type: str = "build_issue"


type TraceEntry = RuleFiring | RuleFailure | CandidateRejected | CombinationRejected | BuildIssue


@dataclass(slots=True)
class Trace:
    """Журнал записей в порядке появления."""

    entries: list[TraceEntry] = field(default_factory=list)

    def add(self, entry: TraceEntry) -> None:
        """Добавляет запись."""
        self.entries.append(entry)

    def firings(self) -> list[RuleFiring]:
        """Только срабатывания правил."""
        return [entry for entry in self.entries if isinstance(entry, RuleFiring)]

    def fired_codes(self) -> list[str]:
        """Коды сработавших правил по порядку."""
        return [entry.rule_code for entry in self.firings()]

    def to_jsonable(self) -> list[dict[str, Any]]:
        """Трасса в виде, пригодном для JSON (хранится вместе со сборкой)."""
        return [asdict(entry) for entry in self.entries]
