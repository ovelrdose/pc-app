"""План подбора из фактов и структура сборки."""

import pytest

from app.expert.catalog import CatalogEntry, CatalogSnapshot
from app.expert.configurator.build import Build, BuildItem
from app.expert.configurator.pipeline import EvaluatedBuild, select_tiers
from app.expert.configurator.plan import (
    DEFAULT_SHARES,
    Constraints,
    PlanError,
    Scenario,
    build_plan,
)
from app.expert.configurator.utility import IndexPerformanceModel, Utility
from app.expert.frames import FRAMES_BY_CATEGORY, Category, Component, ComponentStatus
from tests.factories import slots
from tests.unit.expert.configurator.conftest import profile


def frame(category: Category, **overrides: object) -> Component:
    return FRAMES_BY_CATEGORY[category].model_validate(slots(category, **overrides))


def test_plan_defaults() -> None:
    plan = build_plan(profile(user__budget=100_000), Constraints())
    assert plan.budget_kop == 10_000_000
    assert Category.HDD not in plan.order
    # вентиляторы — необязательная категория при корпусе: в плане есть, доли бюджета нет
    assert plan.order[-1] is Category.CASE_FAN
    assert plan.optional == {Category.CASE_FAN}
    assert Category.CASE_FAN not in plan.shares
    assert plan.order[0] is Category.CPU
    assert sum(plan.shares.values()) == pytest.approx(1.0)
    assert dict(plan.weights) == {Scenario.OFFICE: 1.0}
    paid = [c for c in plan.order if c not in plan.optional]
    expected = DEFAULT_SHARES[Category.GPU] / sum(DEFAULT_SHARES[c] for c in paid)
    assert plan.shares[Category.GPU] == pytest.approx(expected)


def test_plan_from_facts() -> None:
    plan = build_plan(
        profile(
            user__budget=200_000,
            req__need__gpu=False,
            req__need__hdd=True,
            budget__share__ssd=0.5,
            budget__first_category="ssd",
            profile__weight__aaa_gaming=1.5,
            profile__weight__esports=(0.9, 0.1),
        ),
        Constraints(locked={Category.CASE_FAN: "FAN-X"}),
    )
    assert Category.GPU not in plan.order
    assert {Category.HDD, Category.CASE_FAN} <= set(plan.order)
    assert plan.order[0] is Category.SSD
    assert plan.shares[Category.SSD] > 0.3
    assert dict(plan.weights) == {Scenario.AAA_GAMING: 1.0}  # обрезано до 1; cf 0.1 не виден


@pytest.mark.parametrize(
    ("facts", "fragment"),
    [
        ({}, "бюджет"),
        ({"user__budget": 0}, "бюджет"),
        ({"user__budget": "много"}, "числом"),
        ({"user__budget": 1, "req__need__gpu": "да"}, "да/нет"),
        ({"user__budget": 1, "budget__first_category": "monitor"}, "неизвестная категория"),
    ],
)
def test_plan_errors(facts: dict[str, object], fragment: str) -> None:
    with pytest.raises(PlanError, match=fragment):
        build_plan(profile(**facts), Constraints())


def test_build_facts_and_prices() -> None:
    cpu = BuildItem(frame(Category.CPU))
    gpu = BuildItem(frame(Category.GPU), owned=True, locked=True)
    build = Build().with_item(cpu).with_item(gpu)
    assert build.price_kop == cpu.frame.price_kop
    assert build.est_power_w == 65 + 115 + 75
    assert build.facts["build.gpu.owned"].value is True
    assert build.facts["build.total.power_w"].value == 255
    assert build.facts["build.cpu.socket"].value == "AM5"
    assert build.skus == ("CPU-AMD-R5-7600", "GPU-TEST-4060")
    assert Build.of([gpu, cpu]).skus == build.skus
    assert build.get(Category.RAM) is None
    with pytest.raises(ValueError, match="уже есть"):
        build.with_item(cpu)


def test_catalog_snapshot() -> None:
    entries = [
        CatalogEntry(frame(Category.CPU)),
        CatalogEntry(frame(Category.GPU), ComponentStatus.INCOMPLETE),
    ]
    snapshot = CatalogSnapshot.build(7, entries)
    assert snapshot.get("GPU-TEST-4060").status is ComponentStatus.INCOMPLETE
    assert snapshot.get("NOPE") is None
    assert [e.sku for e in snapshot.of_category(Category.CPU)] == ["CPU-AMD-R5-7600"]
    with pytest.raises(ValueError, match="повторяются"):
        CatalogSnapshot.build(1, entries + entries[:1])


def test_index_model_without_gpu_uses_igpu() -> None:
    model = IndexPerformanceModel()
    with_igpu = Build.of([BuildItem(frame(Category.CPU, igpu=True))])
    without = Build.of([BuildItem(frame(Category.CPU, igpu=False))])
    assert (
        model.scenario_scores(with_igpu)[Scenario.ESPORTS]
        > model.scenario_scores(without)[Scenario.ESPORTS]
    )
    small_ram = Build.of([BuildItem(frame(Category.RAM, capacity_gb=8, modules=1))])
    big_ram = Build.of([BuildItem(frame(Category.RAM, capacity_gb=64, modules=2))])
    assert model.scenario_scores(big_ram)[Scenario.OFFICE] == 0  # без CPU производительности нет
    assert small_ram.items[0].frame.category is Category.RAM


def test_select_tiers_edge_cases() -> None:
    assert select_tiers([]) == {}
    build = Build.of([BuildItem(frame(Category.CPU))])
    only = EvaluatedBuild(build, Utility(10.0, {}), ())
    tiers = select_tiers([only])
    assert {e.build.skus for e in tiers.values()} == {build.skus}


def test_case_fans_required_when_asked() -> None:
    plan = build_plan(profile(user__budget=100_000, req__need__case_fan=True), Constraints())
    assert Category.CASE_FAN in plan.order
    assert not plan.optional
    without_case = build_plan(profile(user__budget=100_000, req__need__case=False), Constraints())
    assert Category.CASE_FAN not in without_case.order
