"""Правки сборки (вики §4.8): новые ограничения, пересчёт и разница."""

import pytest

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.build import Build
from app.expert.configurator.modify import (
    Edit,
    EditError,
    EditKind,
    EditOutcome,
    apply_edit,
    diff_builds,
)
from app.expert.configurator.pipeline import Tier, configure
from app.expert.configurator.plan import Constraints
from app.expert.dsl.compiler import CompiledRuleSet
from app.expert.facts import WorkingMemory
from app.expert.frames import Category
from tests.unit.expert.configurator.conftest import GAMER, profile

BUDGET = 150_000


@pytest.fixture(scope="module")
def memory() -> WorkingMemory:
    return profile(user__budget=BUDGET, **GAMER)


@pytest.fixture(scope="module")
def optimum(memory: WorkingMemory, rule_set: CompiledRuleSet, catalog: CatalogSnapshot) -> Build:
    return configure(memory, rule_set, catalog).tiers[Tier.OPTIMUM].build


def edit(
    memory: WorkingMemory,
    rule_set: CompiledRuleSet,
    catalog: CatalogSnapshot,
    build: Build,
    change: Edit,
    constraints: Constraints | None = None,
) -> EditOutcome:
    return apply_edit(
        memory, rule_set, catalog, constraints or Constraints(), build, Tier.OPTIMUM, change
    )


def test_cheaper_gpu(
    memory: WorkingMemory, rule_set: CompiledRuleSet, catalog: CatalogSnapshot, optimum: Build
) -> None:
    outcome = edit(memory, rule_set, catalog, optimum, Edit(EditKind.CHEAPER, Category.GPU))
    old, new = optimum.frame(Category.GPU), outcome.build.build.frame(Category.GPU)
    assert new.price_kop < old.price_kop
    assert outcome.constraints.locked[Category.GPU] == new.sku
    gpu_change = next(c for c in outcome.diff.changes if c.category is Category.GPU)
    assert gpu_change.delta_kop < 0
    assert outcome.build.build.price_kop <= BUDGET * 100


def test_pricier_gpu(
    memory: WorkingMemory, rule_set: CompiledRuleSet, catalog: CatalogSnapshot, optimum: Build
) -> None:
    cheaper = edit(memory, rule_set, catalog, optimum, Edit(EditKind.CHEAPER, Category.GPU))
    start = cheaper.build.build
    outcome = edit(
        memory, rule_set, catalog, start, Edit(EditKind.PRICIER, Category.GPU), cheaper.constraints
    )
    assert outcome.build is not None
    assert outcome.build.build.frame(Category.GPU).price_kop > start.frame(Category.GPU).price_kop


def test_replace_lock_unlock(
    memory: WorkingMemory, rule_set: CompiledRuleSet, catalog: CatalogSnapshot, optimum: Build
) -> None:
    replaced = edit(
        memory,
        rule_set,
        catalog,
        optimum,
        Edit(EditKind.REPLACE, Category.SSD, sku="SSD-SAMSUNG-990EVOPLUS-1TB"),
    )
    assert replaced.build.build.frame(Category.SSD).sku == "SSD-SAMSUNG-990EVOPLUS-1TB"

    locked = edit(memory, rule_set, catalog, optimum, Edit(EditKind.LOCK, Category.CPU))
    assert locked.constraints.locked[Category.CPU] == optimum.frame(Category.CPU).sku
    assert locked.build.build.get(Category.CPU).locked

    unlocked = edit(
        memory,
        rule_set,
        catalog,
        locked.build.build,
        Edit(EditKind.UNLOCK, Category.CPU),
        locked.constraints,
    )
    assert Category.CPU not in unlocked.constraints.locked


def test_exclude_current_gpu_and_brand(
    memory: WorkingMemory, rule_set: CompiledRuleSet, catalog: CatalogSnapshot, optimum: Build
) -> None:
    gpu_sku = optimum.frame(Category.GPU).sku
    outcome = edit(memory, rule_set, catalog, optimum, Edit(EditKind.EXCLUDE_SKU, sku=gpu_sku))
    assert outcome.build.build.frame(Category.GPU).sku != gpu_sku
    assert outcome.result.filtering.rejection(gpu_sku).message == "исключён по вашему выбору"

    brand = optimum.frame(Category.CASE).brand
    by_brand = edit(memory, rule_set, catalog, optimum, Edit(EditKind.EXCLUDE_BRAND, brand=brand))
    assert all(i.frame.brand != brand for i in by_brand.build.build.items)


def test_shift_budget(
    memory: WorkingMemory, rule_set: CompiledRuleSet, catalog: CatalogSnapshot, optimum: Build
) -> None:
    outcome = edit(
        memory,
        rule_set,
        catalog,
        optimum,
        Edit(EditKind.SHIFT_BUDGET, Category.SSD, to_category=Category.GPU),
    )
    assert outcome.build is not None
    assert outcome.diff is not None
    after = outcome.build.build
    ssd_before, ssd_after = optimum.get(Category.SSD), after.get(Category.SSD)
    gpu_before, gpu_after = optimum.get(Category.GPU), after.get(Category.GPU)
    assert ssd_before
    assert ssd_after
    assert gpu_before
    assert gpu_after
    assert ssd_after.price_kop < ssd_before.price_kop  # сэкономили на SSD
    assert gpu_after.price_kop > gpu_before.price_kop  # и вложили в видеокарту
    changed = {change.category for change in outcome.diff.changes}
    assert changed <= {Category.SSD, Category.GPU}  # остальное не трогали
    assert after.price_kop <= outcome.result.plan.budget_kop

    # корпус в этой сборке уже самый дешёвый — экономить на нём нечего
    with pytest.raises(EditError, match="самый дешёвый"):
        edit(
            memory,
            rule_set,
            catalog,
            optimum,
            Edit(EditKind.SHIFT_BUDGET, Category.CASE, to_category=Category.GPU),
        )


def test_diff_builds(optimum: Build) -> None:
    same = diff_builds(optimum, optimum)
    assert (same.changes, same.price_delta_kop) == ((), 0)


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (Edit(EditKind.CHEAPER), "нужна категория"),
        (Edit(EditKind.REPLACE, Category.GPU, sku="CPU-AMD-R5-7500F"), "не найден в категории"),
        (Edit(EditKind.LOCK, Category.HDD), "нет категории"),
        (Edit(EditKind.CHEAPER, Category.HDD), "нет категории"),
        (Edit(EditKind.SHIFT_BUDGET, Category.GPU), "две разные категории"),
        (Edit(EditKind.SHIFT_BUDGET, Category.GPU, to_category=Category.HDD), "нет категории"),
        (Edit(EditKind.EXCLUDE_SKU, sku="NOPE"), "не найден"),
        (Edit(EditKind.EXCLUDE_BRAND), "не указан бренд"),
    ],
)
def test_edit_errors(
    memory: WorkingMemory,
    rule_set: CompiledRuleSet,
    catalog: CatalogSnapshot,
    optimum: Build,
    change: Edit,
    fragment: str,
) -> None:
    with pytest.raises(EditError, match=fragment):
        edit(memory, rule_set, catalog, optimum, change)


def test_no_cheaper_option(
    memory: WorkingMemory, rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    economy = configure(memory, rule_set, catalog).tiers[Tier.ECONOMY].build
    with pytest.raises(EditError, match="дешевле"):
        edit(memory, rule_set, catalog, economy, Edit(EditKind.CHEAPER, Category.GPU))


def test_owned_part_cannot_be_changed(
    memory: WorkingMemory, rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    owned = Constraints(owned=frozenset({"GPU-PALIT-RTX5060-DUAL"}))
    build = configure(memory, rule_set, catalog, owned).tiers[Tier.OPTIMUM].build
    for change, fragment in [
        (Edit(EditKind.CHEAPER, Category.GPU), "имеющуюся"),
        (Edit(EditKind.UNLOCK, Category.GPU), "имеющаяся"),
        (Edit(EditKind.EXCLUDE_SKU, sku="GPU-PALIT-RTX5060-DUAL"), "имеющуюся"),
    ]:
        with pytest.raises(EditError, match=fragment):
            edit(memory, rule_set, catalog, build, change, owned)
