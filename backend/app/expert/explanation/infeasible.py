"""Невыполнимые требования (архитектура §7.7, вики §4.10).

Если подходящих сборок нет, система:
1. находит требования, которые делают сборку дороже бюджета: снимает обязательное требование
   по одному и смотрит, сколько стоит самая дешёвая совместимая сборка без него;
2. предлагает ослабить ответы: монитор попроще, объём SSD, пожелания к виду и брендам;
3. собирает компромисс: уступает пожелания клиента по порядку приоритета (`CONCESSION_ORDER`),
   пока самая дешёвая сборка не уложится в бюджет, и подбирает лучшую сборку с этими уступками;
4. если уступок не хватило — показывает лучшую возможную сборку в бюджете и какие требования
   она не выполняет.
"""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.build import Build
from app.expert.configurator.filtering import filter_candidates
from app.expert.configurator.pipeline import (
    EvaluatedBuild,
    Tier,
    cheapest_price_kop,
    configure,
    resolve_constraints,
)
from app.expert.configurator.plan import MANDATORY_CF, Constraints, build_plan
from app.expert.consultation import performance_model
from app.expert.dsl.compiler import CompiledRuleSet
from app.expert.dsl.schema import RuleKind
from app.expert.facts import WorkingMemory
from app.expert.inference.forward import run_forward
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.questionnaire import Option, Questionnaire, answers_to_memory
from app.expert.trace import Trace
from app.expert.vocabulary import REFRESH_RATES, RESOLUTIONS, lookup
from app.expert.waivers import WAIVABLE, waive, waiver_title

MAX_RELAXATIONS = 5
STORAGE_STEPS = (500, 1000, 2000, 4000)


@dataclass(frozen=True, slots=True)
class BlockingRequirement:
    """Обязательное требование, без которого сборка дешевле."""

    fact: str
    title: str
    value: object
    rules: tuple[str, ...]
    min_budget_without_rub: int | None


@dataclass(frozen=True, slots=True)
class Relaxation:
    """Вариант ослабить ответы клиента и сколько тогда стоит самая дешёвая сборка."""

    title: str
    answers: Mapping[str, object]
    min_budget_rub: int


@dataclass(frozen=True, slots=True)
class Concession:
    """Одна уступка клиента: изменённые ответы или снятые требования."""

    title: str
    answers: Mapping[str, object]
    waived: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Compromise:
    """Сборка в бюджете ценой уступок: что уступили и что получилось."""

    concessions: tuple[Concession, ...]
    answers: Mapping[str, object]
    waived: tuple[str, ...]
    build: EvaluatedBuild


@dataclass(frozen=True, slots=True)
class InfeasibleReport:
    """Разбор невыполнимого запроса."""

    budget_rub: int
    min_budget_rub: int | None
    blocking: tuple[BlockingRequirement, ...]
    relaxations: tuple[Relaxation, ...]
    best_effort: EvaluatedBuild | None
    unmet: tuple[str, ...]
    compromise: Compromise | None = None


def _rub(kop: int | None) -> int | None:
    return None if kop is None else -(-kop // 100)


def _filter_requirements(memory: WorkingMemory, rule_set: CompiledRuleSet) -> list[str]:
    """Обязательные требования, которые читают фильтры."""
    read = {p for r in rule_set.of_kind(RuleKind.FILTER) for p in r.reads}
    return sorted(
        fact.path
        for fact in memory
        if fact.path.startswith("req.") and fact.path in read and fact.cf >= MANDATORY_CF
    )


def _without(memory: WorkingMemory, paths: list[str]) -> WorkingMemory:
    """Копия рабочей памяти без указанных фактов (итоговые значения, без истории вкладов)."""
    copy = WorkingMemory()
    for fact in memory:
        if fact.path not in paths:
            copy.set_fact(fact.path, fact.value, fact.cf, fact.sources[0])
    return copy


def _monitor(option: Option) -> tuple[int, int] | None:
    facts = option.facts or {}
    resolution, refresh = facts.get("user.resolution"), facts.get("user.refresh_hz")
    if resolution not in RESOLUTIONS or not isinstance(refresh, int):
        return None
    return RESOLUTIONS.index(str(resolution)), refresh


def _monitor_patch(
    question_id: str, current: Option, target: Option
) -> tuple[str, dict[str, object]]:
    return f"Монитор «{target.label}» вместо «{current.label}»", {question_id: target.value}


def _monitor_relaxations(
    questionnaire: Questionnaire, answers: Mapping[str, object]
) -> list[tuple[str, dict[str, object]]]:
    """Монитор попроще: та же картинка с меньшей частотой и меньшее разрешение (вики §4.10)."""
    variants: list[tuple[str, dict[str, object]]] = []
    for question in questionnaire.questions:
        monitors = {o.value: (o, m) for o in question.options if (m := _monitor(o)) is not None}
        current = monitors.get(str(answers.get(question.id)))
        if current is None:
            continue
        option, (resolution, refresh) = current
        same = [(m, o) for o, m in monitors.values() if m[0] == resolution and m[1] < refresh]
        if same:
            variants.append(_monitor_patch(question.id, option, max(same, key=lambda c: c[0])[1]))
        below = [m[0] for _, m in monitors.values() if m[0] < resolution]
        if below:
            # следующее разрешение вниз: частота не выше нынешней, а если такой нет — наименьшая
            step = [(m, o) for o, m in monitors.values() if m[0] == max(below)]
            slower = [c for c in step if c[0][1] <= refresh]
            target = max(slower, key=lambda c: c[0]) if slower else min(step, key=lambda c: c[0])
            variants.append(_monitor_patch(question.id, option, target[1]))
    return variants


def _relaxed_answers(
    questionnaire: Questionnaire, answers: Mapping[str, object]
) -> list[tuple[str, dict[str, object]]]:
    variants = _monitor_relaxations(questionnaire, answers)
    resolution = answers.get("resolution")
    if resolution in RESOLUTIONS and resolution != RESOLUTIONS[0]:
        lower = RESOLUTIONS[RESOLUTIONS.index(str(resolution)) - 1]
        variants.append((f"Разрешение {lower} вместо {resolution}", {"resolution": lower}))
    refresh = answers.get("refresh_hz")
    if refresh in REFRESH_RATES and refresh != REFRESH_RATES[0]:
        index = REFRESH_RATES.index(int(str(refresh)))
        lower_hz = next((r for r in reversed(REFRESH_RATES[:index]) if r <= 144), REFRESH_RATES[0])
        variants.append((f"Частота {lower_hz} Гц вместо {refresh}", {"refresh_hz": lower_hz}))
    storage = answers.get("storage_gb")
    if storage in STORAGE_STEPS and storage != STORAGE_STEPS[0]:
        smaller = STORAGE_STEPS[STORAGE_STEPS.index(int(str(storage))) - 1]
        variants.append((f"SSD {smaller} ГБ вместо {storage}", {"storage_gb": smaller}))
    for key in SOFT_WISHES:
        if (wish := _soft_patch(answers, key)) is not None:
            variants.append(wish)
    return variants


SOFT_WISHES: Mapping[str, tuple[object, str]] = {
    "color": ("any", "Любой цвет корпуса"),
    "glass": ("no", "Корпус без стекла"),
    "rgb": ("no", "Без подсветки"),
    "case_size": ("any", "Любой размер корпуса"),
    "wifi": ("no", "Без Wi-Fi на плате"),
    "archive": ("no", "Без жёсткого диска для архива"),
    "cpu_brand": ("any", "Любой производитель процессора"),
    "gpu_brand": ("any", "Любой производитель видеокарты"),
    "mem_type": ("any", "Любой тип памяти"),
}
"""Пожелания, от которых можно отказаться: ответ «без пожелания» и текст уступки."""


def _soft_patch(answers: Mapping[str, object], key: str) -> tuple[str, dict[str, object]] | None:
    value, title = SOFT_WISHES[key]
    if key in answers and answers[key] not in (value, "unknown", "no", "any"):
        return title, {key: value}
    return None


type Step = Callable[[Questionnaire, Mapping[str, object], _Ladder], list[Concession]]
"""Шаг лестницы уступок: (анкета, исходные ответы, текущее состояние) → варианты уступки."""


@dataclass(slots=True)
class _Ladder:
    """Текущее состояние лестницы уступок: ответы, снятые требования и рабочая память."""

    answers: dict[str, object]
    waived: set[str]
    memory: WorkingMemory


def _wish_step(key: str) -> Step:
    def step(_: Questionnaire, __: Mapping[str, object], state: _Ladder) -> list[Concession]:
        wish = _soft_patch(state.answers, key)
        return [Concession(wish[0], wish[1])] if wish else []

    return step


def _storage_step(
    _: Questionnaire, original: Mapping[str, object], state: _Ladder
) -> list[Concession]:
    # Объём, не указанный клиентом, задают правила (например, «игры: SSD от 1 ТБ»); ответ клиента
    # их перекрывает, поэтому пробуем объёмы от большего к меньшему — подойдёт первый, что дешевле.
    storage = state.answers.get("storage_gb")
    lower = [s for s in STORAGE_STEPS if storage not in STORAGE_STEPS or s < int(str(storage))]
    before = original.get("storage_gb")
    return [Concession(f"SSD {s} ГБ вместо {before}", {"storage_gb": s}) for s in reversed(lower)]


def _monitor_step(
    questionnaire: Questionnaire, original: Mapping[str, object], state: _Ladder
) -> list[Concession]:
    variants: list[Concession] = []
    for _, patch in _monitor_relaxations(questionnaire, state.answers):
        [(question_id, value)] = patch.items()
        question = next(q for q in questionnaire.questions if q.id == question_id)
        labels = {o.value: o.label for o in question.options}
        before = labels.get(str(original.get(question_id)), str(original.get(question_id)))
        title = f"Монитор «{labels.get(str(value), value)}» вместо «{before}»"
        variants.append(Concession(title, patch))
    return variants


def _waiver_step(path: str) -> Step:
    def step(_: Questionnaire, __: Mapping[str, object], state: _Ladder) -> list[Concession]:
        fact = state.memory.lookup(path)
        if path in state.waived or fact is None or fact.cf < MANDATORY_CF:
            return []
        return [Concession(waiver_title(path, state.memory), {}, (path,))]

    return step


CONCESSION_ORDER: tuple[tuple[Step, bool], ...] = (
    (_wish_step("archive"), False),
    (_storage_step, True),
    (_wish_step("rgb"), False),
    (_wish_step("glass"), False),
    (_wish_step("wifi"), False),
    (_wish_step("cpu_brand"), False),
    (_wish_step("gpu_brand"), False),
    (_wish_step("mem_type"), False),
    (_wish_step("case_size"), False),
    (_wish_step("color"), False),
    (_monitor_step, True),
    *((_waiver_step(path), False) for path in WAIVABLE),
)
"""Порядок уступок в компромиссной сборке (вики §4.10): сначала то, что меньше всего меняет
опыт клиента, — архив и объём SSD (диск легко докупить), затем внешний вид и бренды, потом
монитор попроще и в последнюю очередь требования, которые вывела система (`WAIVABLE`):
от них зависит производительность. Второй элемент — можно ли повторять шаг
(SSD 2 ТБ → 1 ТБ → 500 ГБ, монитор на ступень ниже и ещё раз).
"""


def explain_infeasible(
    knowledge: KnowledgeSnapshot,
    catalog: CatalogSnapshot,
    answers: Mapping[str, object],
    constraints: Constraints | None = None,
    waived: Collection[str] = (),
) -> InfeasibleReport:
    """Разбирает невыполнимый запрос: что мешает, как ослабить, что можно собрать.

    `waived` — требования, от которых клиент уже отказался в этой консультации.
    """
    constraints = constraints or Constraints()
    rules = knowledge.compiled
    memory = _profile(knowledge, answers, waived)
    budget_fact = memory.lookup("user.budget")
    budget_rub = int(str(budget_fact.value)) if budget_fact else 0
    minimum = _rub(cheapest_price_kop(memory, rules, catalog, constraints))

    blocking: list[BlockingRequirement] = []
    for path in _filter_requirements(memory, rules):
        fact = memory.lookup(path)
        if fact is None:
            continue
        without = _rub(cheapest_price_kop(_without(memory, [path]), rules, catalog, constraints))
        if without is not None and (minimum is None or without < minimum * 0.97):
            spec = lookup(path)
            blocking.append(
                BlockingRequirement(
                    path,
                    spec.title if spec else path,
                    fact.value,
                    tuple(str(s) for s in fact.sources if s.rule_code),
                    without,
                )
            )
    blocking.sort(key=lambda b: b.min_budget_without_rub or 0)

    relaxations: list[Relaxation] = []
    for title, patch in _relaxed_answers(knowledge.questionnaire, answers):
        price = _cheapest_rub(knowledge, catalog, {**answers, **patch}, waived, constraints)
        if price is not None and (minimum is None or price < minimum):
            relaxations.append(Relaxation(title, patch, price))
    relaxations.sort(key=lambda r: r.min_budget_rub)

    compromise = _compromise(
        knowledge, catalog, answers, set(waived), constraints, budget_rub, minimum
    )
    best, unmet = (
        (None, ()) if compromise else _best_effort(knowledge, catalog, memory, constraints)
    )
    return InfeasibleReport(
        budget_rub,
        minimum,
        tuple(blocking),
        tuple(relaxations[:MAX_RELAXATIONS]),
        best,
        unmet,
        compromise,
    )


def _profile(
    knowledge: KnowledgeSnapshot, answers: Mapping[str, object], waived: Collection[str]
) -> WorkingMemory:
    memory = answers_to_memory(knowledge.questionnaire, answers, knowledge.tables)
    run_forward(knowledge.compiled, memory)
    waive(memory, waived)
    return memory


def _cheapest_rub(
    knowledge: KnowledgeSnapshot,
    catalog: CatalogSnapshot,
    answers: Mapping[str, object],
    waived: Collection[str],
    constraints: Constraints,
) -> int | None:
    memory = _profile(knowledge, answers, waived)
    return _rub(cheapest_price_kop(memory, knowledge.compiled, catalog, constraints))


def _apply(
    answers: Mapping[str, object], waived: Collection[str], concessions: list[Concession]
) -> tuple[dict[str, object], set[str]]:
    result, removed = dict(answers), set(waived)
    for concession in concessions:
        result.update(concession.answers)
        removed.update(concession.waived)
    return result, removed


def _compromise(
    knowledge: KnowledgeSnapshot,
    catalog: CatalogSnapshot,
    answers: Mapping[str, object],
    waived: set[str],
    constraints: Constraints,
    budget_rub: int,
    minimum: int | None,
) -> Compromise | None:
    """Сборка в бюджете ценой уступок (вики §4.10).

    Уступки принимаются по порядку `CONCESSION_ORDER`, только если удешевляют самую дешёвую
    сборку, пока она не уложится в бюджет. Затем лишние уступки возвращаются: от более важных
    к менее важным, если без уступки бюджета всё ещё хватает.
    """
    questionnaire = knowledge.questionnaire
    state = _Ladder(dict(answers), set(waived), _profile(knowledge, answers, waived))
    required = state.memory.lookup("req.storage_min_gb")
    # для текстов уступок: объём SSD, который требовался до уступки (ответ или вывод правил)
    original = {**({"storage_gb": required.value} if required else {}), **answers}
    price = minimum
    accepted: dict[tuple[frozenset[str], tuple[str, ...]], Concession] = {}
    for step, repeat in CONCESSION_ORDER:
        while price is None or price > budget_rub:
            for concession in step(questionnaire, original, state):
                trial_answers = {**state.answers, **concession.answers}
                trial_waived = state.waived | set(concession.waived)
                memory = _profile(knowledge, trial_answers, trial_waived)
                candidate = _rub(
                    cheapest_price_kop(memory, knowledge.compiled, catalog, constraints)
                )
                if candidate is not None and (price is None or candidate < price):
                    state = _Ladder(trial_answers, trial_waived, memory)
                    price = candidate
                    # повтор шага (SSD ещё на ступень меньше) заменяет прежнюю уступку того же вида
                    accepted[(frozenset(concession.answers), concession.waived)] = concession
                    break
            else:
                break
            if not repeat:
                break
    if price is None or price > budget_rub:
        return None

    kept = list(accepted.values())
    for concession in reversed(list(accepted.values())):
        trial = [c for c in kept if c is not concession]
        candidate = _cheapest_rub(knowledge, catalog, *_apply(answers, waived, trial), constraints)
        if candidate is not None and candidate <= budget_rub:
            kept = trial
    final_answers, final_waived = _apply(answers, waived, kept)
    memory = _profile(knowledge, final_answers, final_waived)
    result = configure(
        memory,
        knowledge.compiled,
        catalog,
        constraints,
        model=performance_model(knowledge, memory),
    )
    build = result.tiers.get(Tier.MAXIMUM)
    if build is None:
        return None
    patch = {key: value for c in kept for key, value in c.answers.items()}
    new_waivers = tuple(path for c in kept for path in c.waived)
    return Compromise(tuple(kept), patch, new_waivers, build)


def _best_effort(
    knowledge: KnowledgeSnapshot,
    catalog: CatalogSnapshot,
    memory: WorkingMemory,
    constraints: Constraints,
) -> tuple[EvaluatedBuild | None, tuple[str, ...]]:
    """Лучшая сборка в бюджете без обязательных требований и список невыполненных."""
    rules = knowledge.compiled
    relaxed = _without(memory, _filter_requirements(memory, rules))
    result = configure(
        relaxed, rules, catalog, constraints, model=performance_model(knowledge, memory)
    )
    best = result.tiers.get(Tier.MAXIMUM)
    if best is None:
        return None, ()
    return best, _unmet(best.build, memory, rules, catalog, constraints)


def _unmet(
    build: Build,
    memory: WorkingMemory,
    rules: CompiledRuleSet,
    catalog: CatalogSnapshot,
    constraints: Constraints,
) -> tuple[str, ...]:
    """Какие обязательные требования нарушают детали сборки (тексты фильтров)."""
    resolved = resolve_constraints(catalog, constraints)
    plan = build_plan(memory, resolved)
    only_build = replace(
        resolved,
        excluded_skus=frozenset(e.sku for e in catalog.entries if e.sku not in build.skus),
    )
    filtering = filter_candidates(catalog, plan, memory, rules, only_build, Trace())
    return tuple(
        f"{rejection.message} ({rejection.rule_code})"
        for rejection in filtering.rejections
        if rejection.sku in build.skus and rejection.rule_code
    )
