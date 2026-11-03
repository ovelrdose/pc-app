"""«Почему не вот эта деталь?» (вики §6.2): отсеяна, не нужна, несовместима, дорога или хуже."""

from dataclasses import dataclass
from enum import StrEnum

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.build import Build, BuildItem
from app.expert.configurator.checks import CompatChecker, validate_build
from app.expert.configurator.filtering import FilterResult
from app.expert.configurator.pipeline import EvaluatedBuild
from app.expert.configurator.plan import SearchPlan
from app.expert.configurator.utility import PerformanceModel, evaluate_utility
from app.expert.dsl.compiler import CompiledRuleSet
from app.expert.dsl.expr import format_number, format_value
from app.expert.facts import FactView
from app.expert.trace import Trace


class WhyNotVerdict(StrEnum):
    """Почему деталь не в сборке."""

    NOT_FOUND = "not_found"
    IN_BUILD = "in_build"
    NOT_NEEDED = "not_needed"
    OWNED = "owned"
    UNAVAILABLE = "unavailable"
    FILTERED = "filtered"
    INCOMPATIBLE = "incompatible"
    OVER_BUDGET = "over_budget"
    WORSE = "worse"
    BETTER = "better"


@dataclass(frozen=True, slots=True)
class Reason:
    """Причина: правило (или встроенная проверка) и текст для клиента."""

    rule_code: str | None
    message: str


@dataclass(frozen=True, slots=True)
class WhyNot:
    """Ответ на «почему не»."""

    sku: str
    verdict: WhyNotVerdict
    reasons: tuple[Reason, ...] = ()
    price_delta_kop: int | None = None
    utility_delta_pct: float | None = None
    fps_delta_pct: float | None = None

    @property
    def can_replace(self) -> bool:
        """Деталь можно попробовать подставить правкой «Заменить» (остальное подберётся заново)."""
        return self.verdict in (
            WhyNotVerdict.WORSE,
            WhyNotVerdict.BETTER,
            WhyNotVerdict.INCOMPATIBLE,
        )


def _avg_fps(build: Build, model: PerformanceModel) -> float | None:
    fact = model.perf_facts(build).get("perf.fps_avg")
    return float(fact.value) if fact is not None and isinstance(fact.value, int | float) else None


def _need_reason(memory: FactView, category: str) -> Reason:
    fact = memory.lookup(f"req.need.{category}")
    rule = next((str(s) for s in fact.sources if s.rule_code), None) if fact else None
    return Reason(rule, "эта категория для ваших задач не нужна")


def why_not(
    sku: str,
    evaluated: EvaluatedBuild | None,
    plan: SearchPlan,
    filtering: FilterResult,
    catalog: CatalogSnapshot,
    memory: FactView,
    rule_set: CompiledRuleSet,
    model: PerformanceModel,
) -> WhyNot:
    """Объясняет, почему товар `sku` не попал в сборку `evaluated`, и оценивает замену.

    `plan` и `filtering` — план и результат фильтрации той консультации, к которой относится
    сборка (их можно восстановить по ответам клиента, не повторяя поиск).
    """
    entry = catalog.get(sku)
    if entry is None or evaluated is None:
        return WhyNot(sku, WhyNotVerdict.NOT_FOUND, (Reason(None, "товар или сборка не найдены"),))
    build, category = evaluated.build, entry.frame.category
    current = build.get(category)
    if current is not None and current.frame.sku == sku:
        return WhyNot(sku, WhyNotVerdict.IN_BUILD, (Reason(None, "этот товар уже в сборке"),))
    if category not in plan.order:
        return WhyNot(sku, WhyNotVerdict.NOT_NEEDED, (_need_reason(memory, category.value),))
    if current is not None and current.owned:
        reason = Reason(None, f"у вас уже есть {current.frame.name} — эта категория не покупается")
        return WhyNot(sku, WhyNotVerdict.OWNED, (reason,))
    rejection = filtering.rejection(sku)
    if rejection is not None:
        verdict = WhyNotVerdict.FILTERED if rejection.rule_code else WhyNotVerdict.UNAVAILABLE
        return WhyNot(sku, verdict, (Reason(rejection.rule_code, rejection.message),))

    items = [i for i in build.items if i.category is not category]
    replaced = Build.of([*items, BuildItem(entry.frame)])
    price_delta = replaced.price_kop - build.price_kop
    checker = CompatChecker(rule_set, plan.order, memory, Trace())
    violations = checker.violations_for(replaced, category)
    errors = [
        i
        for i in validate_build(replaced, memory, rule_set, Trace(), model.perf_facts(replaced))
        if i.action == "error"
    ]
    if violations or errors:
        reasons = [Reason(v.rule_code, v.message) for v in violations]
        reasons += [Reason(e.rule_code, e.message) for e in errors]
        reasons.append(
            Reason(
                None,
                "это несовместимость с текущими деталями: если подставить товар правкой "
                "«Заменить», остальные детали будут подобраны заново",
            )
        )
        return WhyNot(sku, WhyNotVerdict.INCOMPATIBLE, tuple(reasons), price_delta)
    if replaced.price_kop > plan.budget_kop:
        over = (replaced.price_kop - plan.budget_kop) // 100
        reason = Reason(None, f"с ним сборка выходит за бюджет на {format_number(over)} ₽")
        return WhyNot(sku, WhyNotVerdict.OVER_BUDGET, (reason,), price_delta)

    before = evaluated.utility.total
    after = evaluate_utility(replaced, plan, model, memory, rule_set, Trace()).total
    utility_delta = round(100 * (after - before) / before, 1) if before else None
    fps_before, fps_after = _avg_fps(build, model), _avg_fps(replaced, model)
    fps_delta = (
        round(100 * (fps_after - fps_before) / fps_before, 1)
        if fps_before and fps_after is not None
        else None
    )
    if after < before:
        text = f"подходит, но для ваших задач хуже на {format_value(abs(utility_delta or 0.0))}%"
        if fps_delta is not None and fps_delta < 0:
            text += f" (FPS в ваших играх −{format_value(abs(fps_delta))}%)"
        verdict = WhyNotVerdict.WORSE
    else:
        text = "подходит и даже не хуже текущего выбора — можно подставить в сборку"
        verdict = WhyNotVerdict.BETTER
    return WhyNot(sku, verdict, (Reason(None, text),), price_delta, utility_delta, fps_delta)
