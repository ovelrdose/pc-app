"""Модель производительности: FPS, видеопамять, трассировка, ОЗУ, программы, бенчмарки."""

import math

import pytest

from app.expert.configurator.build import Build, BuildItem
from app.expert.configurator.plan import Scenario
from app.expert.frames import FRAMES_BY_CATEGORY, Category, Component
from app.expert.performance import (
    FpsPerformanceModel,
    Limiter,
    benchmarks,
    estimate_app,
    estimate_game,
    gpu_indices,
    ram_factor,
    report,
)
from app.expert.tables import AppLevel, Preset
from tests.factories import slots
from tests.unit.expert.kb_fixtures import small_tables

TABLES = small_tables()
CS2, DOOM = TABLES.games
BLENDER, OFFICE = TABLES.applications


def part(category: Category, **overrides: object) -> BuildItem:
    frame: Component = FRAMES_BY_CATEGORY[category].model_validate(slots(category, **overrides))
    return BuildItem(frame)


def build(*items: BuildItem) -> Build:
    return Build.of(items)


REFERENCE = build(
    part(Category.CPU, perf_single=100, perf_multi=100),
    part(Category.GPU, perf_raster=100, perf_rt=100, vram_gb=8),
    part(Category.RAM, capacity_gb=16, modules=2, speed_mts=5600),
)


def test_reference_build_gives_base_fps() -> None:
    estimate = estimate_game(REFERENCE, CS2, "1080p", Preset.HIGH)
    assert estimate.gpu_cap == 80  # базовый FPS × 100 / 100
    assert estimate.cpu_cap == pytest.approx(400 * 0.98)
    assert estimate.fps == 80
    assert estimate.limited_by is Limiter.GPU
    assert estimate.vram_ok
    assert (estimate.low, estimate.high) == pytest.approx((68, 92))
    assert estimate.gpu_utilization == 1.0


def test_cpu_bound_and_utilization() -> None:
    weak_cpu = build(part(Category.CPU, perf_single=10), part(Category.GPU, perf_raster=200))
    estimate = estimate_game(weak_cpu, CS2, "1080p", Preset.HIGH)
    assert estimate.limited_by is Limiter.CPU
    assert estimate.fps == estimate.cpu_cap == 40
    assert estimate.gpu_utilization == pytest.approx(40 / 160)


def test_vram_penalty() -> None:
    small = build(part(Category.CPU), part(Category.GPU, perf_raster=100, vram_gb=6))
    estimate = estimate_game(small, CS2, "1080p", Preset.HIGH)
    assert not estimate.vram_ok
    assert estimate.gpu_cap == pytest.approx(80 * 0.7)


def test_raytracing_required_uses_rt_index() -> None:
    estimate = estimate_game(REFERENCE, DOOM, "1080p", Preset.HIGH)
    assert estimate.raytracing
    assert estimate.gpu_cap == pytest.approx(80 * 0.6)
    optional = estimate_game(REFERENCE, CS2, "1080p", Preset.HIGH, raytracing=True)
    assert optional.raytracing


def test_integrated_and_missing_graphics() -> None:
    with_igpu = build(part(Category.CPU, igpu=True))
    assert gpu_indices(with_igpu) == (12.0, 0.0, 2.0)
    nothing = build(part(Category.CPU, igpu=False))
    assert gpu_indices(nothing) == (0.0, 0.0, 0.0)
    estimate = estimate_game(nothing, CS2, "1080p", Preset.HIGH)
    assert estimate.fps == 0
    assert math.isinf(estimate.bottleneck_ratio)


@pytest.mark.parametrize(
    ("ram", "factor"),
    [
        ({"capacity_gb": 8, "modules": 1, "mem_type": "DDR4", "speed_mts": 2666}, 0.85),
        ({"capacity_gb": 16, "modules": 2, "speed_mts": 5600}, 0.98),
        ({"capacity_gb": 32, "modules": 2, "speed_mts": 6000}, 1.03),
        ({"capacity_gb": 64, "modules": 2, "speed_mts": 6400}, 1.04),
        ({"capacity_gb": 16, "modules": 1, "speed_mts": 5600}, 0.93),
    ],
)
def test_ram_factor(ram: dict[str, object], factor: float) -> None:
    assert ram_factor(build(part(Category.RAM, **ram))) == pytest.approx(factor)
    assert ram_factor(Build()) == 1.0


def test_applications() -> None:
    rig = build(
        part(Category.CPU, perf_single=150, perf_multi=200),
        part(Category.GPU, perf_raster=140),
    )
    blender = estimate_app(rig, BLENDER)
    assert blender.workload_index == 140
    assert blender.minutes == pytest.approx(4.0 * 100 / 140, abs=0.01)
    assert blender.level_ok(AppLevel.BASIC)
    assert blender.level_ok(AppLevel.PRO)
    office = estimate_app(rig, OFFICE)
    assert office.workload_index == 150
    assert estimate_app(Build(), OFFICE).minutes == math.inf
    mixed = OFFICE.model_copy(update={"workload": "mixed"})
    assert estimate_app(rig, mixed).workload_index == 170
    multi = OFFICE.model_copy(update={"workload": "cpu_multi"})
    assert estimate_app(rig, multi).workload_index == 200


def test_benchmarks_known_and_estimated() -> None:
    rig = build(
        part(Category.CPU, perf_single=100, perf_multi=100, cinebench_single=120),
        part(Category.GPU, perf_raster=200, timespy=21000),
    )
    values = {b.name: (b.value, b.estimated) for b in benchmarks(rig)}
    assert values["cinebench_single"] == (120, False)
    assert values["cinebench_multi"] == (945, True)
    assert values["timespy"] == (21000, False)
    assert values["steel_nomad"] == (5200, True)
    assert benchmarks(Build()) == []


def test_fps_model_scores_and_perf_facts() -> None:
    model = FpsPerformanceModel(
        TABLES, resolution="1080p", refresh_hz=60, games=["cs2"], primary=Scenario.ESPORTS
    )
    scores = model.scenario_scores(REFERENCE)
    # FPS эталона ограничен частотой монитора × 1.25 = 75 и нормирован к 100
    assert scores[Scenario.ESPORTS] == pytest.approx(100)  # FPS обрезан до 60 × 1.25, SSD нет
    assert scores[Scenario.AAA_GAMING] == 0  # типовых AAA-игр в маленьком справочнике нет
    with_doom = FpsPerformanceModel(TABLES, games=["cs2", "doom_dark_ages"])
    assert with_doom.scenario_scores(REFERENCE)[Scenario.AAA_GAMING] == pytest.approx(100)
    facts = model.perf_facts(REFERENCE)
    assert facts["perf.limited_by"].value == "gpu"
    assert facts["perf.fps_avg"].value == 80
    assert model.perf_facts(REFERENCE) is facts  # кэш
    assert model.perf_facts(build(part(Category.CPU, igpu=False))) == {}
    no_esports = FpsPerformanceModel(TABLES.model_copy(update={"games": [DOOM]}))
    assert no_esports.gaming_score(REFERENCE, Scenario.ESPORTS) == 0.0


def test_report() -> None:
    fps, apps = report(REFERENCE, TABLES, ["cs2", "nope"], ["1080p"], [Preset.HIGH], ["office"])
    assert [(f.game, f.resolution, f.preset) for f in fps] == [("cs2", "1080p", Preset.HIGH)]
    assert [a.app for a in apps] == ["office"]
