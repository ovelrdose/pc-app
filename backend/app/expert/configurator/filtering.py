"""Этап 2: фильтрация кандидатов (вики §4.3).

Каждый товар нужной категории подставляется как `cand.*` и проверяется filter-правилами.
Правила видят только обязательные требования. Встроенные проверки: статус «активен» (§17),
исключения клиента. Имеющиеся и зафиксированные детали не фильтруются.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.expert.catalog import CatalogEntry, CatalogSnapshot
from app.expert.certainty import is_established
from app.expert.configurator.plan import Constraints, SearchPlan
from app.expert.configurator.views import MandatoryView
from app.expert.dsl.compiler import CompiledMessageAction, CompiledRuleSet, fact_resolver
from app.expert.dsl.expr import ExprEvalError
from app.expert.dsl.schema import RuleKind
from app.expert.facts import FactView, OverlayView, frame_facts
from app.expert.frames import Category, ComponentStatus
from app.expert.trace import CandidateRejected, Phase, RuleFailure, Trace

STATUS_REASONS: Mapping[ComponentStatus, str] = MappingProxyType(
    {
        ComponentStatus.INCOMPLETE: "карточка товара заполняется, пока недоступен для подбора",
        ComponentStatus.NEEDS_KB: "характеристики товара пока неизвестны базе знаний",
        ComponentStatus.INACTIVE: "снят с продажи",
    }
)


@dataclass(frozen=True, slots=True)
class Rejection:
    """Почему товар не допущен к подбору."""

    sku: str
    category: Category
    rule_code: str | None
    message: str


@dataclass(frozen=True, slots=True)
class FilterResult:
    """Допустимые кандидаты по категориям и причины отсева."""

    candidates: Mapping[Category, tuple[CatalogEntry, ...]]
    rejections: tuple[Rejection, ...]

    def rejection(self, sku: str) -> Rejection | None:
        """Причина отсева товара или `None`, если он допущен."""
        return next((r for r in self.rejections if r.sku == sku), None)


def _check(
    entry: CatalogEntry,
    view: FactView,
    rule_set: CompiledRuleSet,
    trace: Trace,
) -> Rejection | None:
    frame = entry.frame
    candidate = OverlayView(view, frame_facts("cand", frame))
    rules = sorted(rule_set.of_kind(RuleKind.FILTER), key=lambda r: (-r.rule.priority, r.code))
    for rule in rules:
        try:
            match = rule.condition.evaluate(candidate)
        except ExprEvalError as exc:
            trace.add(RuleFailure(0, Phase.FILTERING, rule.code, f"{frame.sku}: {exc}"))
            continue
        if match is None or not is_established(match.cf):
            continue
        action = next(a for a in rule.actions if isinstance(a, CompiledMessageAction))
        resolve = fact_resolver(candidate)
        message = action.message.render(resolve) if action.message else rule.rule.name
        return Rejection(frame.sku, frame.category, rule.code, message)
    return None


def filter_candidates(
    catalog: CatalogSnapshot,
    plan: SearchPlan,
    memory: FactView,
    rule_set: CompiledRuleSet,
    constraints: Constraints,
    trace: Trace,
) -> FilterResult:
    """Отбирает кандидатов для каждой категории плана."""
    view = MandatoryView(memory)
    candidates: dict[Category, tuple[CatalogEntry, ...]] = {}
    rejections: list[Rejection] = []

    for category in plan.order:
        locked = constraints.locked.get(category)
        if locked is not None:
            entry = catalog.get(locked)
            candidates[category] = (entry,) if entry is not None else ()
            continue
        kept: list[CatalogEntry] = []
        for entry in catalog.of_category(category):
            frame = entry.frame
            rejection: Rejection | None = None
            if entry.status is not ComponentStatus.ACTIVE:
                rejection = Rejection(frame.sku, category, None, STATUS_REASONS[entry.status])
            elif frame.sku in constraints.excluded_skus:
                rejection = Rejection(frame.sku, category, None, "исключён по вашему выбору")
            elif frame.brand.lower() in {b.lower() for b in constraints.excluded_brands}:
                rejection = Rejection(
                    frame.sku, category, None, f"бренд {frame.brand} исключён по вашему выбору"
                )
            else:
                rejection = _check(entry, view, rule_set, trace)
            if rejection is None:
                kept.append(entry)
                continue
            rejections.append(rejection)
            trace.add(
                CandidateRejected(
                    Phase.FILTERING,
                    rejection.sku,
                    category.value,
                    rejection.rule_code,
                    rejection.message,
                )
            )
        candidates[category] = tuple(kept)
    return FilterResult(MappingProxyType(candidates), tuple(rejections))
