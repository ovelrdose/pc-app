"""Подбор трёх вариантов на реальном каталоге: критерий этапа 3 и сценарии вики §4."""

import sys
import time
from types import MappingProxyType
from typing import Any

import pytest

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.checks import CompatChecker
from app.expert.configurator.pipeline import (
    ConfigResult,
    ConfigurationError,
    Tier,
    configure,
)
from app.expert.configurator.plan import Constraints
from app.expert.dsl.compiler import CompiledRuleSet
from app.expert.frames import CPU, GPU, RAM, SSD, Case, Category
from app.expert.trace import CandidateRejected, Trace
from tests.unit.expert.configurator.conftest import EDITOR, GAMER, OFFICE, profile

PROFILES = {"gamer": GAMER, "office": OFFICE, "editor": EDITOR}


def run(
    rule_set: CompiledRuleSet,
    catalog: CatalogSnapshot,
    constraints: Constraints | None = None,
    /,
    **facts: Any,
) -> ConfigResult:
    return configure(profile(**facts), rule_set, catalog, constraints)


def assert_valid(result: ConfigResult, rule_set: CompiledRuleSet, budget_rub: int) -> None:
    """Инварианты: полная, совместимая, в бюджете, только активные товары в наличии."""
    assert result.infeasibility is None
    assert set(result.tiers) == set(Tier)
    checker = CompatChecker(rule_set, result.plan.order, profile(), Trace())
    for tier, evaluated in result.tiers.items():
        build = evaluated.build
        assert build.price_kop <= budget_rub * 100, tier
        missing = set(result.plan.order) - build.categories - result.plan.optional
        cpu = build.frame(Category.CPU)
        if Category.CPU_COOLER in missing:
            assert isinstance(cpu, CPU)
            assert cpu.cooler_included
            missing.discard(Category.CPU_COOLER)
        assert not missing, (tier, missing)
        assert checker.violations(build) == [], (tier, build.skus)
        for item in build.items:
            assert item.frame.in_stock or item.owned, item.frame.sku
    tiers = result.tiers
    assert tiers[Tier.ECONOMY].build.price_kop <= tiers[Tier.OPTIMUM].build.price_kop
    assert tiers[Tier.MAXIMUM].utility.total >= tiers[Tier.OPTIMUM].utility.total
    assert tiers[Tier.OPTIMUM].utility.total >= 0.9 * tiers[Tier.MAXIMUM].utility.total


@pytest.mark.parametrize("budget", [60_000, 100_000, 150_000, 250_000, 500_000])
@pytest.mark.parametrize("who", list(PROFILES))
def test_builds_are_compatible_and_fit_budget(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot, who: str, budget: int
) -> None:
    if who != "office" and budget < 100_000:
        pytest.skip("игровая сборка дешевле ~86 000 ₽ на текущих ценах невозможна")
    result = run(rule_set, catalog, user__budget=budget, **PROFILES[who])
    assert_valid(result, rule_set, budget)


def test_more_budget_gives_more_utility(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    low = run(rule_set, catalog, user__budget=120_000, **GAMER).tiers[Tier.MAXIMUM]
    high = run(rule_set, catalog, user__budget=300_000, **GAMER).tiers[Tier.MAXIMUM]
    assert high.utility.total > low.utility.total
    assert high.build.price_kop > 0.75 * 300_000 * 100  # остаток бюджета потрачен


def test_gamer_gets_gpu_office_does_not(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    gamer = run(rule_set, catalog, user__budget=150_000, **GAMER)
    office = run(rule_set, catalog, user__budget=60_000, **OFFICE)
    assert Category.GPU in gamer.tiers[Tier.MAXIMUM].build.categories
    for evaluated in office.tiers.values():
        assert Category.GPU not in evaluated.build.categories
        cpu = evaluated.build.frame(Category.CPU)
        assert isinstance(cpu, CPU)
        assert cpu.igpu
    rejected = office.filtering.rejection("CPU-INTEL-I5-12400F")
    assert rejected is not None
    assert rejected.rule_code == "FLT-004"


def test_mandatory_requirement_filters_desirable_does_not(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    strict = run(rule_set, catalog, user__budget=150_000, req__gpu_vram_min_gb=12, **GAMER)
    for evaluated in strict.tiers.values():
        gpu = evaluated.build.frame(Category.GPU)
        assert isinstance(gpu, GPU)
        assert gpu.vram_gb >= 12
    rejection = strict.filtering.rejection("GPU-PALIT-RTX5060-DUAL")
    assert rejection is not None
    assert rejection.message == "Видеопамяти 8 ГБ, нужно от 12"

    soft = run(rule_set, catalog, user__budget=150_000, req__gpu_vram_min_gb=(12, 0.4), **GAMER)
    assert soft.filtering.rejection("GPU-PALIT-RTX5060-DUAL") is None


def test_out_of_stock_and_white_case(rule_set: CompiledRuleSet, catalog: CatalogSnapshot) -> None:
    result = run(rule_set, catalog, user__budget=150_000, user__color="white", **GAMER)
    assert_valid(result, rule_set, 150_000)
    for evaluated in result.tiers.values():
        case = evaluated.build.frame(Category.CASE)
        assert isinstance(case, Case)
        assert case.color.value == "white"
    out_of_stock = result.filtering.rejection("CPU-AMD-R5-5600G")
    assert out_of_stock is not None
    assert out_of_stock.message == "Нет в наличии"
    assert any(
        isinstance(e, CandidateRejected) and e.sku == "CPU-AMD-R5-5600G"
        for e in result.trace.entries
    )


def test_minimum_budget_from_architecture_is_infeasible(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    result = run(rule_set, catalog, user__budget=35_000, **OFFICE)
    assert result.tiers == {}
    assert result.infeasibility is not None
    assert result.infeasibility.min_budget_rub is not None
    assert 35_000 < result.infeasibility.min_budget_rub < 60_000
    assert "больше бюджета" in result.infeasibility.reason


def test_empty_category_is_reported(rule_set: CompiledRuleSet, catalog: CatalogSnapshot) -> None:
    result = run(rule_set, catalog, user__budget=500_000, req__gpu_vram_min_gb=64, **GAMER)
    assert result.infeasibility is not None
    assert result.infeasibility.empty_categories == (Category.GPU,)


def test_validation_error_discards_builds(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    big = Constraints(locked=MappingProxyType({Category.SSD: "SSD-KINGSTON-NV3-2TB"}))
    result = run(rule_set, catalog, big, user__budget=200_000, req__storage_min_gb=2000, **EDITOR)
    assert result.tiers
    for evaluated in result.tiers.values():
        ssd = evaluated.build.frame(Category.SSD)
        assert isinstance(ssd, SSD)
        assert ssd.capacity_gb >= 2000


def test_all_builds_failing_validation_are_explained(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    small = Constraints(locked=MappingProxyType({Category.SSD: "SSD-KINGSTON-NV3-500"}))
    result = run(rule_set, catalog, small, user__budget=200_000, req__storage_min_gb=2000, **EDITOR)
    assert not result.tiers
    assert result.infeasibility is not None
    assert result.infeasibility.blocking_rules == ("VAL-002",)
    assert result.infeasibility.min_budget_rub is None
    assert "не прошли проверку" in result.infeasibility.reason
    assert "больше бюджета" not in result.infeasibility.reason


def test_warnings_suggestions_and_preferences(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    result = run(rule_set, catalog, user__budget=100_000, user__future_proof=True, **GAMER)
    economy = result.tiers[Tier.ECONOMY]
    ram = economy.build.frame(Category.RAM)
    assert isinstance(ram, RAM)
    if ram.modules == 1:
        assert [w.rule_code for w in economy.warnings] == ["VAL-001"]
    gpu = economy.build.frame(Category.GPU)
    assert isinstance(gpu, GPU)
    if gpu.vram_gb < 12:
        assert [s.target for s in economy.suggestions] == ["vram_12"]
    cpu = result.tiers[Tier.MAXIMUM].build.frame(Category.CPU)
    assert isinstance(cpu, CPU)
    codes = [p.rule_code for p in result.tiers[Tier.MAXIMUM].utility.preferences]
    assert ("SCR-001" in codes) == (cpu.socket == "AM5")


def test_owned_gpu_costs_nothing_and_must_fit(
    rule_set: CompiledRuleSet, catalog: CatalogSnapshot
) -> None:
    owned = "GPU-SAPPHIRE-RX9070XT-PULSE"
    result = run(
        rule_set, catalog, Constraints(owned=frozenset({owned})), user__budget=100_000, **GAMER
    )
    assert_valid(result, rule_set, 100_000)
    for evaluated in result.tiers.values():
        item = evaluated.build.get(Category.GPU)
        assert item is not None
        assert (item.frame.sku, item.owned, item.locked, item.price_kop) == (owned, True, True, 0)
        case = evaluated.build.frame(Category.CASE)
        assert isinstance(case, Case)
        assert (case.max_gpu_mm or 0) >= 314


def test_locked_and_excluded(rule_set: CompiledRuleSet, catalog: CatalogSnapshot) -> None:
    constraints = Constraints(
        locked={Category.CPU: "CPU-INTEL-I5-14400F"}, excluded_brands=frozenset({"kingston"})
    )
    result = run(rule_set, catalog, constraints, user__budget=150_000, **GAMER)
    assert_valid(result, rule_set, 150_000)
    for evaluated in result.tiers.values():
        assert evaluated.build.frame(Category.CPU).sku == "CPU-INTEL-I5-14400F"
        assert all(item.frame.brand != "Kingston" for item in evaluated.build.items)


def test_unknown_owned_or_locked_part(rule_set: CompiledRuleSet, catalog: CatalogSnapshot) -> None:
    with pytest.raises(ConfigurationError, match="не найдена"):
        run(rule_set, catalog, Constraints(owned=frozenset({"NOPE-1"})), user__budget=1)
    with pytest.raises(ConfigurationError, match="не подходит"):
        run(
            rule_set,
            catalog,
            Constraints(locked={Category.GPU: "CPU-AMD-R5-7500F"}),
            user__budget=100_000,
        )


def test_distinct_merges_equal_tiers(rule_set: CompiledRuleSet, catalog: CatalogSnapshot) -> None:
    result = run(rule_set, catalog, user__budget=150_000, **GAMER)
    groups = result.distinct()
    assert sum(len(tiers) for tiers, _ in groups) == 3
    assert len({evaluated.build.skus for _, evaluated in groups}) == len(groups)


def test_deterministic_and_fast(rule_set: CompiledRuleSet, catalog: CatalogSnapshot) -> None:
    started = time.perf_counter()
    first = run(rule_set, catalog, user__budget=180_000, **EDITOR)
    elapsed = time.perf_counter() - started
    second = run(rule_set, catalog, user__budget=180_000, **EDITOR)
    assert {t: e.build.skus for t, e in first.tiers.items()} == {
        t: e.build.skus for t, e in second.tiers.items()
    }
    assert first.trace.to_jsonable() == second.trace.to_jsonable()
    if sys.gettrace() is None:  # под coverage код в разы медленнее — время не показательно
        assert elapsed < 3.0  # вики §4.4: «1–3 секунды на весь подбор»
