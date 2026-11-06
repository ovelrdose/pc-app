"""Golden cases (архитектура §6.3): эталонные ответы и ожидания от консультации.

Кейс задаёт ответы визарда и ожидания: выполнимость, выведенные факты, сработавшие правила,
отсеянные товары, свойства каждого варианта сборки. Исполнитель возвращает список
расхождений; пустой список — кейс пройден.
"""

from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.build import Build
from app.expert.configurator.pipeline import EvaluatedBuild, Tier
from app.expert.configurator.plan import Constraints
from app.expert.consultation import Consultation, consult, performance_model
from app.expert.dsl.compiler import apply_op
from app.expert.dsl.schema import Op
from app.expert.explanation.infeasible import explain_infeasible
from app.expert.explanation.why_not import WhyNotVerdict, why_not
from app.expert.facts import FactView, Value, normalize_value
from app.expert.frames import Category
from app.expert.hypotheses import check_hypothesis
from app.expert.inference.backward import ProofStatus
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.performance import FpsPerformanceModel, estimate_app, estimate_game
from app.expert.tables import RESOLUTIONS, AppLevel, Preset
from app.expert.trace import BuildIssue, CandidateRejected, CombinationRejected, RuleFailure

_OPS = ("eq", "ne", "ge", "le", "gt", "lt", "in", "contains", "between")

type Matcher = str | int | float | bool | dict[str, Any]


def cases_from_json(data: object) -> list["GoldenCase"]:
    """Кейсы из JSON-списка (как хранится в `reference_tables['golden']`); ошибки — `ValueError`."""
    if not isinstance(data, list):
        raise ValueError("golden cases: ожидается список")
    try:
        return [GoldenCase.model_validate(item) for item in data]
    except ValidationError as exc:
        raise ValueError(f"golden cases не проходят схему:\n{exc}") from exc


def cases_to_json(cases: list["GoldenCase"]) -> list[dict[str, Any]]:
    """Кейсы в стабильном JSON для хранения: без умолчаний и пустых значений."""
    return [
        case.model_dump(mode="json", exclude_defaults=True, exclude_none=True) for case in cases
    ]


class GoldenModel(BaseModel):
    """Общая конфигурация моделей кейсов."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Range(GoldenModel):
    """Числовой диапазон."""

    ge: float | None = None
    le: float | None = None


class HypothesisExpect(GoldenModel):
    """Ожидание от проверки гипотезы обратным выводом."""

    predicate: str
    args: dict[str, str | int | float | bool] = Field(default_factory=dict)
    bindings: dict[str, str | int | float | bool] = Field(default_factory=dict)
    status: ProofStatus
    asks: list[str] = Field(default_factory=list, description="переменные, о которых спросят")


class WhyNotExpect(GoldenModel):
    """Ожидание от «почему не эта деталь?»."""

    sku: str
    tier: Tier = Tier.MAXIMUM
    verdict: WhyNotVerdict
    rules: list[str] = Field(default_factory=list)


class InfeasibleExpect(GoldenModel):
    """Ожидание от разбора невыполнимого запроса."""

    blocking: list[str] = Field(default_factory=list, description="пути мешающих требований")
    relaxations: list[str] = Field(default_factory=list, description="подстроки предложений")
    compromise: list[str] | None = Field(
        default=None, description="подстроки уступок компромиссной сборки (в порядке уступки)"
    )
    best_effort: bool = True


class TierExpect(GoldenModel):
    """Ожидания от одного варианта (или от всех вариантов)."""

    max_total_rub: int | None = None
    build: dict[str, Matcher] = Field(default_factory=dict)
    absent: list[Category] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    hypotheses: list[HypothesisExpect] = Field(default_factory=list)
    perf: dict[str, Matcher] = Field(
        default_factory=dict,
        description="fps|ratio.<игра>.<разрешение>.<пресет>, app.<программа>.minutes|basic|pro, "
        "perf.<факт>",
    )


class Expectation(GoldenModel):
    """Ожидания кейса."""

    feasible: bool = True
    min_budget_rub: Range | None = None
    facts: dict[str, Matcher] = Field(default_factory=dict)
    fired: list[str] = Field(default_factory=list)
    not_fired: list[str] = Field(default_factory=list)
    rejected: dict[str, str] = Field(default_factory=dict, description="артикул → код правила")
    trace_rules: list[str] = Field(default_factory=list)
    why_not: list[WhyNotExpect] = Field(default_factory=list)
    infeasible: InfeasibleExpect | None = None
    all_tiers: TierExpect = Field(default_factory=TierExpect)
    economy: TierExpect = Field(default_factory=TierExpect)
    optimum: TierExpect = Field(default_factory=TierExpect)
    maximum: TierExpect = Field(default_factory=TierExpect)


class GoldenCase(GoldenModel):
    """Эталонный кейс."""

    id: str = Field(pattern=r"^G-\d{3}$")
    title: str
    answers: dict[str, Any]
    owned: list[str] = Field(default_factory=list)
    expect: Expectation

    @model_validator(mode="after")
    def _infeasible(self) -> Self:
        if self.expect.min_budget_rub is not None and self.expect.feasible:
            raise ValueError(f"{self.id}: min_budget_rub задают только для невыполнимых кейсов")
        return self


def match(actual: Value | None, matcher: Matcher) -> bool:
    """Проверяет значение по ожиданию: литерал (равенство) или `{ge: 12}`, `{in: [...]}` и т.п."""
    if not isinstance(matcher, dict):
        return actual is not None and actual == normalize_value(matcher)
    unknown = set(matcher) - set(_OPS)
    if unknown:
        raise ValueError(f"неизвестные операторы ожидания: {sorted(unknown)}")
    if actual is None:
        return False
    return all(apply_op(Op(op), actual, normalize_value(raw)) for op, raw in matcher.items())


def perf_value(
    key: str, build: Build, knowledge: KnowledgeSnapshot, model: FpsPerformanceModel
) -> Value | None:
    """Значение прогноза по ключу ожидания golden case."""
    parts = key.split(".")
    if parts[0] == "perf":
        fact = model.perf_facts(build).get(key)
        return fact.value if fact else None
    if parts[0] in ("fps", "ratio") and len(parts) == 4:
        game = next((g for g in knowledge.tables.games if g.id == parts[1]), None)
        if game is None or parts[2] not in RESOLUTIONS:
            raise ValueError(f"неизвестная игра или разрешение в ключе {key}")
        resolution = next(r for r in RESOLUTIONS if r == parts[2])
        fps = estimate_game(build, game, resolution, Preset(parts[3]))
        return fps.fps if parts[0] == "fps" else round(fps.bottleneck_ratio, 3)
    if parts[0] == "app" and len(parts) == 3:
        app = next((a for a in knowledge.tables.applications if a.id == parts[1]), None)
        if app is None:
            raise ValueError(f"неизвестная программа в ключе {key}")
        work = estimate_app(build, app)
        return work.minutes if parts[2] == "minutes" else work.level_ok(AppLevel(parts[2]))
    raise ValueError(f"неизвестный ключ прогноза {key}")


def _check_tier(
    name: str,
    evaluated: EvaluatedBuild,
    expect: TierExpect,
    knowledge: KnowledgeSnapshot,
    model: FpsPerformanceModel,
    memory: FactView,
) -> list[str]:
    problems: list[str] = []
    build = evaluated.build
    for key, matcher in expect.perf.items():
        value = perf_value(key, build, knowledge, model)
        if not match(value, matcher):
            problems.append(f"{name}: прогноз {key} = {value!r}, ожидалось {matcher!r}")
    if expect.max_total_rub is not None and build.price_kop > expect.max_total_rub * 100:
        problems.append(f"{name}: цена {build.price_kop // 100} ₽ > {expect.max_total_rub} ₽")
    for path, matcher in expect.build.items():
        fact = build.facts.get(path)
        value = fact.value if fact else None
        if not match(value, matcher):
            problems.append(f"{name}: {path} = {value!r}, ожидалось {matcher!r}")
    for category in expect.absent:
        if build.get(category) is not None:
            problems.append(f"{name}: в сборке не должно быть {category.value}")
    for hypothesis in expect.hypotheses:
        checked = check_hypothesis(
            knowledge,
            memory,
            build,
            hypothesis.predicate,
            hypothesis.args,
            hypothesis.bindings,
            model,
        )
        label = f"{hypothesis.predicate}{hypothesis.args}"
        if checked.root.status is not hypothesis.status:
            problems.append(
                f"{name}: гипотеза {label} — {checked.root.status.value}, "
                f"ожидалось {hypothesis.status.value}"
            )
        asked = sorted(q.variable for q in checked.questions)
        if asked != sorted(hypothesis.asks):
            problems.append(
                f"{name}: гипотеза {label} спрашивает {asked}, ожидалось {hypothesis.asks}"
            )
    issue_codes = {issue.rule_code for issue in evaluated.issues}
    problems += [f"{name}: нет замечания {c}" for c in expect.issues if c not in issue_codes]
    pref_codes = {p.rule_code for p in evaluated.utility.preferences}
    problems += [f"{name}: нет баллов {c}" for c in expect.preferences if c not in pref_codes]
    return problems


def _trace_codes(consultation: Consultation) -> set[str]:
    codes: set[str] = set(consultation.profiling.fired)
    for entry in consultation.trace.entries:
        traced = isinstance(
            entry, CandidateRejected | CombinationRejected | BuildIssue | RuleFailure
        )
        if traced and entry.rule_code:
            codes.add(entry.rule_code)
    return codes


def check_case(
    case: GoldenCase, knowledge: KnowledgeSnapshot, catalog: CatalogSnapshot
) -> list[str]:
    """Прогоняет кейс и возвращает расхождения с ожиданиями."""
    constraints = Constraints(owned=frozenset(case.owned))
    consultation = consult(knowledge, catalog, case.answers, constraints)
    result, expect = consultation.result, case.expect
    problems: list[str] = []

    for path, matcher in expect.facts.items():
        fact = consultation.memory.lookup(path)
        value = fact.value if fact else None
        if not match(value, matcher):
            problems.append(f"факт {path} = {value!r}, ожидалось {matcher!r}")
    fired = set(consultation.profiling.fired)
    problems += [f"не сработало {code}" for code in expect.fired if code not in fired]
    problems += [f"сработало {code}, а не должно" for code in expect.not_fired if code in fired]
    for sku, code in expect.rejected.items():
        rejection = result.filtering.rejection(sku)
        actual = rejection.rule_code if rejection else None
        if actual != code:
            problems.append(f"{sku}: отсеян правилом {actual}, ожидалось {code}")
    traced = _trace_codes(consultation)
    problems += [f"в трассе нет {code}" for code in expect.trace_rules if code not in traced]

    feasible = result.infeasibility is None
    if feasible != expect.feasible:
        reason = result.infeasibility.reason if result.infeasibility else "сборки подобраны"
        problems.append(f"выполнимость {feasible}, ожидалось {expect.feasible} ({reason})")
        return problems
    if not feasible:
        if expect.infeasible is not None:
            problems += _check_infeasible(case, knowledge, catalog, constraints, expect.infeasible)
        bounds = expect.min_budget_rub
        minimum = result.infeasibility.min_budget_rub if result.infeasibility else None
        if bounds is not None and (
            minimum is None
            or (bounds.ge is not None and minimum < bounds.ge)
            or (bounds.le is not None and minimum > bounds.le)
        ):
            problems.append(f"минимальный бюджет {minimum}, ожидалось {bounds}")
        return problems

    tiers: Mapping[Tier, TierExpect] = {
        Tier.ECONOMY: expect.economy,
        Tier.OPTIMUM: expect.optimum,
        Tier.MAXIMUM: expect.maximum,
    }
    model = performance_model(knowledge, consultation.memory)
    memory = consultation.memory
    for tier, evaluated in result.tiers.items():
        name = f"{tier.value} (все)"
        problems += _check_tier(name, evaluated, expect.all_tiers, knowledge, model, memory)
        problems += _check_tier(tier.value, evaluated, tiers[tier], knowledge, model, memory)
    for item in expect.why_not:
        answer = why_not(
            item.sku,
            result.tiers.get(item.tier),
            result.plan,
            result.filtering,
            catalog,
            memory,
            knowledge.compiled,
            model,
        )
        codes = {reason.rule_code for reason in answer.reasons}
        if answer.verdict is not item.verdict or not set(item.rules) <= codes:
            problems.append(
                f"почему не {item.sku}: {answer.verdict.value} {sorted(c for c in codes if c)}, "
                f"ожидалось {item.verdict.value} {item.rules}"
            )
    return problems


def _check_infeasible(
    case: GoldenCase,
    knowledge: KnowledgeSnapshot,
    catalog: CatalogSnapshot,
    constraints: Constraints,
    expect: InfeasibleExpect,
) -> list[str]:
    report = explain_infeasible(knowledge, catalog, case.answers, constraints)
    problems: list[str] = []
    blocking = {item.fact for item in report.blocking}
    problems += [
        f"не найдено мешающее требование {f}" for f in expect.blocking if f not in blocking
    ]
    titles = [item.title for item in report.relaxations]
    for fragment in expect.relaxations:
        if not any(fragment in title for title in titles):
            problems.append(f"нет предложения «{fragment}» среди {titles}")
    if expect.best_effort and report.best_effort is None and report.compromise is None:
        problems.append("нет ни компромиссной, ни лучшей возможной сборки")
    if expect.compromise is not None:
        compromise = report.compromise
        if compromise is None:
            problems.append("нет компромиссной сборки")
        else:
            got = [c.title for c in compromise.concessions]
            if len(got) != len(expect.compromise) or not all(
                fragment in title for fragment, title in zip(expect.compromise, got, strict=False)
            ):
                problems.append(f"уступки {got}, ожидалось {expect.compromise}")
            if compromise.build.build.price_kop > report.budget_rub * 100:
                problems.append("компромиссная сборка дороже бюджета")
    return problems
