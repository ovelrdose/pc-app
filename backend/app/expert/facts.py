"""Факты и рабочая память консультации (архитектура §5.2, §5.4).

Каждый источник (ответ пользователя, правило) вносит в факт свой *вклад*: значение и CF.
Повторный вклад того же источника заменяет прежний, поэтому повторное срабатывание правила
не раздувает уверенность. Вклады с одинаковым значением комбинируются по MYCIN, при разных
значениях побеждает большая уверенность, затем большая специфичность правила (ADR 0002).
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Protocol

from app.expert.certainty import clamp, combine_all
from app.expert.frames import Component

type Scalar = str | int | float | bool
type Value = Scalar | tuple[Scalar, ...]

NAMESPACES: frozenset[str] = frozenset(
    {"user", "need", "profile", "req", "budget", "cand", "build", "perf"}
)

USER_SPECIFICITY = 1_000_000
"""Специфичность вкладов пользователя и каталога: они важнее любого правила."""


def normalize_value(value: object) -> Value:
    """Приводит значение к неизменяемому виду: перечисления — к строкам, списки — к кортежам."""
    if isinstance(value, Enum):
        return normalize_value(value.value)
    if isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list | tuple):
        items: list[Scalar] = []
        for item in value:
            normalized = normalize_value(item)
            if isinstance(normalized, tuple):
                raise TypeError("вложенные списки в фактах не поддерживаются")
            items.append(normalized)
        return tuple(items)
    raise TypeError(f"недопустимый тип значения факта: {type(value).__name__}")


class SourceKind(StrEnum):
    """Откуда пришёл вклад в факт."""

    USER = "user"
    CATALOG = "catalog"
    COMPUTED = "computed"
    RULE = "rule"


@dataclass(frozen=True, slots=True, order=True)
class FactSource:
    """Источник вклада: вид и код правила (для `RULE`)."""

    kind: SourceKind
    rule_code: str | None = None

    @classmethod
    def rule(cls, code: str) -> "FactSource":
        """Источник — правило с кодом `code`."""
        return cls(SourceKind.RULE, code)

    def __str__(self) -> str:
        return self.rule_code if self.rule_code else self.kind.value


USER = FactSource(SourceKind.USER)
CATALOG = FactSource(SourceKind.CATALOG)
COMPUTED = FactSource(SourceKind.COMPUTED)


@dataclass(frozen=True, slots=True)
class Contribution:
    """Вклад одного источника в факт."""

    value: Value
    cf: float
    source: FactSource
    specificity: int


@dataclass(frozen=True, slots=True)
class Alternative:
    """Значение факта, проигравшее конфликт (остаётся для объяснений)."""

    value: Value
    cf: float
    sources: tuple[FactSource, ...]


@dataclass(frozen=True, slots=True)
class Fact:
    """Итоговый факт: значение-победитель, его CF и источники."""

    path: str
    value: Value
    cf: float
    sources: tuple[FactSource, ...]
    step: int = 0
    alternatives: tuple[Alternative, ...] = ()


@dataclass(frozen=True, slots=True)
class FactChange:
    """Изменение факта в результате действия."""

    path: str
    before: Fact | None
    after: Fact | None

    @property
    def changed(self) -> bool:
        """Изменилось значение или уверенность."""
        if self.before is None or self.after is None:
            return self.before is not self.after
        return (self.before.value, self.before.cf) != (self.after.value, self.after.cf)


class FactView(Protocol):
    """То, из чего условия правил читают факты."""

    def lookup(self, path: str) -> Fact | None:
        """Факт по пути или `None`."""
        ...


@dataclass(slots=True)
class WorkingMemory:
    """Рабочая память консультации («блокнот»). Изменяемая, живёт один вывод."""

    _contributions: dict[str, dict[FactSource, Contribution]] = field(default_factory=dict)
    _facts: dict[str, Fact] = field(default_factory=dict)

    def lookup(self, path: str) -> Fact | None:
        """Факт по пути или `None` (порог уверенности не учитывается)."""
        return self._facts.get(path)

    def __contains__(self, path: object) -> bool:
        return path in self._facts

    def __iter__(self) -> Iterator[Fact]:
        return iter(sorted(self._facts.values(), key=lambda fact: fact.path))

    def __len__(self) -> int:
        return len(self._facts)

    def set_fact(
        self, path: str, value: object, cf: float = 1.0, source: FactSource = USER
    ) -> FactChange:
        """Записывает входной факт (ответ, данные каталога), заменяя все прежние вклады."""
        self._contributions.pop(path, None)
        return self.contribute(path, value, cf, source, specificity=USER_SPECIFICITY, step=0)

    def contribute(
        self,
        path: str,
        value: object,
        cf: float,
        source: FactSource,
        *,
        specificity: int,
        step: int,
    ) -> FactChange:
        """Добавляет или заменяет вклад источника и пересчитывает факт."""
        _check_path(path)
        contribution = Contribution(normalize_value(value), clamp(cf), source, specificity)
        self._contributions.setdefault(path, {})[source] = contribution
        return self._resolve(path, step)

    def retract(self, path: str) -> FactChange:
        """Снимает факт целиком (все вклады)."""
        before = self._facts.pop(path, None)
        self._contributions.pop(path, None)
        return FactChange(path, before, None)

    def as_dict(self) -> dict[str, Value]:
        """Значения всех фактов (для тестов и отладки)."""
        return {fact.path: fact.value for fact in self}

    def _resolve(self, path: str, step: int) -> FactChange:
        before = self._facts.get(path)
        groups: dict[Value, list[Contribution]] = {}
        for contribution in self._contributions[path].values():
            groups.setdefault(contribution.value, []).append(contribution)

        ranked = sorted(
            (
                (
                    combine_all(c.cf for c in group),
                    max(c.specificity for c in group),
                    value,
                    tuple(sorted(c.source for c in group)),
                )
                for value, group in groups.items()
            ),
            # Больший CF, затем большая специфичность; дальше — детерминированно по источникам.
            key=lambda item: (-item[0], -item[1], item[3]),
        )
        cf, _, value, sources = ranked[0]
        alternatives = tuple(Alternative(v, c, s) for c, _, v, s in ranked[1:])
        unchanged = before is not None and (before.value, before.cf) == (value, cf)
        after = Fact(
            path=path,
            value=value,
            cf=cf,
            sources=sources,
            step=before.step if unchanged and before is not None else step,
            alternatives=alternatives,
        )
        self._facts[path] = after
        return FactChange(path, before, after)


@dataclass(frozen=True, slots=True)
class OverlayView:
    """Рабочая память плюс то, что «в руках» (кандидат, сборка): `cand.*`, `build.*`."""

    base: FactView
    overlay: Mapping[str, Fact]

    def lookup(self, path: str) -> Fact | None:
        """Сначала то, что в руках, затем рабочая память."""
        fact = self.overlay.get(path)
        return fact if fact is not None else self.base.lookup(path)


def frame_facts(prefix: str, frame: Component) -> dict[str, Fact]:
    """Представляет компонент каталога фактами `<prefix>.<слот>` с CF 1.0."""
    _check_path(f"{prefix}.x")
    facts: dict[str, Fact] = {}
    for name, raw in frame.model_dump().items():
        if raw is None:
            continue
        path = f"{prefix}.{name}"
        facts[path] = Fact(path, normalize_value(raw), 1.0, (CATALOG,))
    return facts


def _check_path(path: str) -> None:
    namespace = path.split(".", 1)[0]
    if "." not in path or namespace not in NAMESPACES:
        raise ValueError(f"путь факта «{path}» вне допустимых пространств имён")


def facts_from_mapping(values: Mapping[str, object], cf: float = 1.0) -> WorkingMemory:
    """Рабочая память из словаря «путь → значение» (ответы пользователя)."""
    memory = WorkingMemory()
    for path, value in values.items():
        memory.set_fact(path, value, cf)
    return memory
