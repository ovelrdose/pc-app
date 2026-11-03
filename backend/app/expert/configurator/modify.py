"""Итеративные правки сборки (архитектура §7.5, вики §4.8).

Правка превращается в новые ограничения поиска (фиксации, исключения, доли бюджета), после
чего подбор запускается заново с этапа фильтрации. Профилирование не повторяется. Результат —
новая сборка того же варианта и разница с прежней.
"""

from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

from app.expert.catalog import CatalogEntry, CatalogSnapshot
from app.expert.configurator.build import Build, BuildItem
from app.expert.configurator.checks import CompatChecker
from app.expert.configurator.filtering import filter_candidates
from app.expert.configurator.pipeline import (
    ConfigResult,
    EvaluatedBuild,
    Tier,
    configure,
    resolve_constraints,
)
from app.expert.configurator.plan import Constraints, build_plan
from app.expert.configurator.search import SearchSettings
from app.expert.configurator.utility import PerformanceModel
from app.expert.dsl.compiler import CompiledRuleSet
from app.expert.facts import FactView
from app.expert.frames import Category
from app.expert.frames.components import FRAMES_BY_CATEGORY
from app.expert.trace import Trace


class EditKind(StrEnum):
    """Команда правки."""

    REPLACE = "replace"
    CHEAPER = "cheaper"
    PRICIER = "pricier"
    LOCK = "lock"
    UNLOCK = "unlock"
    SHIFT_BUDGET = "shift_budget"
    EXCLUDE_SKU = "exclude_sku"
    EXCLUDE_BRAND = "exclude_brand"


@dataclass(frozen=True, slots=True)
class Edit:
    """Правка: команда и её параметры."""

    kind: EditKind
    category: Category | None = None
    sku: str | None = None
    brand: str | None = None
    to_category: Category | None = None


class EditError(ValueError):
    """Правку нельзя применить (нет более дешёвого варианта, деталь имеющаяся и т.п.)."""


@dataclass(frozen=True, slots=True)
class ItemChange:
    """Изменение одной категории."""

    category: Category
    before_sku: str | None
    after_sku: str | None
    delta_kop: int


@dataclass(frozen=True, slots=True)
class BuildDiff:
    """Разница между сборками: изменённые категории и цена."""

    changes: tuple[ItemChange, ...]
    price_delta_kop: int


@dataclass(frozen=True, slots=True)
class EditOutcome:
    """Итог правки: новые ограничения, новый подбор, новая сборка варианта и разница."""

    constraints: Constraints
    result: ConfigResult
    build: EvaluatedBuild | None
    diff: BuildDiff | None


def diff_builds(before: Build, after: Build) -> BuildDiff:
    """Сравнивает сборки по категориям."""
    changes: list[ItemChange] = []
    for category in Category:
        old, new = before.get(category), after.get(category)
        old_sku = old.frame.sku if old else None
        new_sku = new.frame.sku if new else None
        if old_sku != new_sku:
            delta = (new.price_kop if new else 0) - (old.price_kop if old else 0)
            changes.append(ItemChange(category, old_sku, new_sku, delta))
    return BuildDiff(tuple(changes), after.price_kop - before.price_kop)


def _brand(catalog: CatalogSnapshot, sku: str) -> str | None:
    entry = catalog.get(sku)
    return entry.frame.brand.lower() if entry else None


def _require_category(edit: Edit) -> Category:
    if edit.category is None:
        raise EditError(f"для правки {edit.kind.value} нужна категория")
    return edit.category


def _neighbour(
    memory: FactView,
    rule_set: CompiledRuleSet,
    catalog: CatalogSnapshot,
    constraints: Constraints,
    current: Build,
    category: Category,
    *,
    cheaper: bool,
) -> CatalogEntry:
    item = current.get(category)
    if item is None:
        raise EditError(f"в сборке нет категории {category.value}")
    if item.owned:
        raise EditError("имеющуюся у вас деталь нельзя заменить на дешевле или дороже")
    unlocked = dict(constraints.locked)
    unlocked.pop(category, None)
    free = replace(constraints, locked=MappingProxyType(unlocked))
    plan = build_plan(memory, free)
    trace = Trace()
    candidates = filter_candidates(catalog, plan, memory, rule_set, free, trace).candidates
    checker = CompatChecker(rule_set, plan.order, memory, trace)
    price = item.frame.price_kop
    entries = [
        e
        for e in candidates.get(category, ())
        if (e.frame.price_kop < price) == cheaper and e.frame.price_kop != price
    ]
    entries.sort(key=lambda e: (e.frame.price_kop, e.sku), reverse=cheaper)
    # Остальные незафиксированные детали подберутся заново, поэтому совместимость проверяется
    # только с зафиксированными и имеющимися деталями.
    fixed = [i for i in current.items if (i.locked or i.owned) and i.category is not category]
    for entry in entries:
        if checker.on_replaced(Build.of([*fixed, BuildItem(entry.frame)]), category) is None:
            return entry
    direction = "дешевле" if cheaper else "дороже"
    raise EditError(f"совместимого варианта {direction} в категории {category.value} нет")


def edit_constraints(
    memory: FactView,
    rule_set: CompiledRuleSet,
    catalog: CatalogSnapshot,
    constraints: Constraints,
    current: Build,
    edit: Edit,
) -> Constraints:
    """Переводит правку в новые ограничения поиска."""
    locked = dict(constraints.locked)
    match edit.kind:
        case EditKind.REPLACE:
            category = _require_category(edit)
            entry = catalog.get(edit.sku or "")
            if entry is None or entry.frame.category is not category:
                raise EditError(f"товар {edit.sku} не найден в категории {category.value}")
            locked[category] = entry.sku
        case EditKind.CHEAPER | EditKind.PRICIER:
            category = _require_category(edit)
            entry = _neighbour(
                memory,
                rule_set,
                catalog,
                constraints,
                current,
                category,
                cheaper=edit.kind is EditKind.CHEAPER,
            )
            locked[category] = entry.sku
        case EditKind.LOCK:
            category = _require_category(edit)
            item = current.get(category)
            if item is None:
                raise EditError(f"в сборке нет категории {category.value}")
            locked[category] = item.frame.sku
        case EditKind.UNLOCK:
            category = _require_category(edit)
            item = current.get(category)
            if item is not None and item.owned:
                raise EditError("имеющаяся у вас деталь всегда остаётся в сборке")
            locked.pop(category, None)
        case EditKind.SHIFT_BUDGET:
            return _shift_constraints(catalog, constraints, current, edit, keep_others=True)
        case EditKind.EXCLUDE_SKU:
            if not edit.sku or catalog.get(edit.sku) is None:
                raise EditError(f"товар {edit.sku} не найден")
            if edit.sku in constraints.owned:
                raise EditError("имеющуюся у вас деталь нельзя исключить")
            locked = {c: s for c, s in locked.items() if s != edit.sku}
            return replace(
                constraints,
                locked=MappingProxyType(locked),
                excluded_skus=constraints.excluded_skus | {edit.sku},
            )
        case EditKind.EXCLUDE_BRAND:
            if not edit.brand:
                raise EditError("не указан бренд")
            brand = edit.brand.lower()
            locked = {
                category: sku
                for category, sku in locked.items()
                if sku in constraints.owned or _brand(catalog, sku) != brand
            }
            return replace(
                constraints,
                locked=MappingProxyType(locked),
                excluded_brands=constraints.excluded_brands | {edit.brand},
            )
    return replace(constraints, locked=MappingProxyType(locked))


def _title(category: Category) -> str:
    title = FRAMES_BY_CATEGORY[category].model_config.get("title")
    return str(title) if title else category.value


def _shift_constraints(
    catalog: CatalogSnapshot,
    constraints: Constraints,
    current: Build,
    edit: Edit,
    *,
    keep_others: bool,
) -> Constraints:
    """«Сэкономить на одной категории, вложить в другую» (вики §4.8).

    В категории-источнике остаются только товары дешевле нынешнего, в категории-получателе —
    дороже. Остальные детали закрепляются (`keep_others`), чтобы изменились только эти две; если
    так не собирается (новой видеокарте нужен БП мощнее), остальное подбирается заново.
    """
    source, target = _require_category(edit), edit.to_category
    if target is None or target is source:
        raise EditError("нужны две разные категории: откуда взять деньги и куда вложить")
    items = {category: current.get(category) for category in (source, target)}
    for category, item in items.items():
        if item is None:
            raise EditError(f"в сборке нет категории {category.value}")
        if item.owned:
            raise EditError("имеющуюся у вас деталь нельзя заменить")
    source_price = items[source].price_kop  # type: ignore[union-attr]
    target_price = items[target].price_kop  # type: ignore[union-attr]
    excluded = {
        e.sku
        for e in catalog.entries
        if (e.frame.category is source and e.frame.price_kop >= source_price)
        or (e.frame.category is target and e.frame.price_kop <= target_price)
    }
    if not any(e.frame.category is source and e.sku not in excluded for e in catalog.entries):
        raise EditError(
            f"{_title(source)}: в сборке уже самый дешёвый вариант, экономить не на чем"
        )
    if not any(e.frame.category is target and e.sku not in excluded for e in catalog.entries):
        raise EditError(f"{_title(target)}: в сборке уже самый дорогой вариант")
    locked = {c: s for c, s in constraints.locked.items() if c not in (source, target)}
    if keep_others:
        locked |= {
            i.category: i.frame.sku for i in current.items if i.category not in (source, target)
        }
    return replace(
        constraints,
        locked=MappingProxyType(locked),
        excluded_skus=constraints.excluded_skus | excluded,
    )


def apply_edit(
    memory: FactView,
    rule_set: CompiledRuleSet,
    catalog: CatalogSnapshot,
    constraints: Constraints,
    current: Build,
    tier: Tier,
    edit: Edit,
    *,
    model: PerformanceModel | None = None,
    settings: SearchSettings | None = None,
) -> EditOutcome:
    """Применяет правку и подбирает новую сборку того же варианта."""
    resolved = resolve_constraints(catalog, constraints)
    new_constraints = edit_constraints(memory, rule_set, catalog, resolved, current, edit)
    result = configure(memory, rule_set, catalog, new_constraints, model=model, settings=settings)
    evaluated = result.tiers.get(tier)
    if evaluated is None and edit.kind is EditKind.SHIFT_BUDGET:
        # с остальными деталями не сошлось — разрешаем подобрать их заново
        new_constraints = _shift_constraints(catalog, resolved, current, edit, keep_others=False)
        result = configure(
            memory, rule_set, catalog, new_constraints, model=model, settings=settings
        )
        evaluated = result.tiers.get(tier)
    if evaluated is None and edit.kind is EditKind.SHIFT_BUDGET:
        raise EditError("не получилось: в бюджете нет сборки, где эта деталь дешевле, а та — лучше")
    diff = diff_builds(current, evaluated.build) if evaluated is not None else None
    return EditOutcome(new_constraints, result, evaluated, diff)
