"""Модель производительности (архитектура §8, вики страница 5).

FPS в игре — меньший из двух «потолков»: видеокарты (базовый FPS на эталонной RTX 4060 × индекс
GPU × штраф за видеопамять) и процессора (потолок на эталонном Ryzen 5 7600 × одноядерный
индекс × поправка на ОЗУ). Время операции в программе — эталонное время × 100 / индекс нагрузки.
Это оценка по референсным тестам, поэтому показывается с разбросом ±15%.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from app.expert.configurator.build import Build
from app.expert.configurator.plan import Scenario
from app.expert.configurator.utility import SCENARIO_MIX, storage_factor
from app.expert.facts import COMPUTED, Fact, Value
from app.expert.frames import CPU, GPU, RAM, Category
from app.expert.game_needs import DEFAULT_GAMES as KIND_DEFAULTS
from app.expert.game_needs import RT_COST
from app.expert.tables import (
    RESOLUTIONS,
    AppLevel,
    Application,
    Game,
    KnowledgeTables,
    Preset,
    Resolution,
)

SPREAD = 0.15
"""Разброс прогноза: ±15%."""

VRAM_PENALTY = 0.7
"""Множитель потолка видеокарты, если видеопамяти меньше, чем нужно игре."""


IGPU_RASTER = 12.0
IGPU_VRAM_GB = 2.0

BALANCE_CORRIDOR = (0.85, 1.5)
"""Коридор нормы соотношения CPU/GPU по умолчанию (вики §5.4)."""

# Эталонные результаты бенчмарков (Ryzen 5 7600 и RTX 4060 = индекс 100).
REFERENCE_BENCH: Mapping[str, float] = MappingProxyType(
    {"cinebench_single": 112, "cinebench_multi": 945, "timespy": 10500, "steel_nomad": 2600}
)

DEFAULT_GAMES: Mapping[Scenario, tuple[str, ...]] = MappingProxyType(
    {Scenario.ESPORTS: KIND_DEFAULTS["esports"], Scenario.AAA_GAMING: KIND_DEFAULTS["aaa"]}
)
"""Типовой набор игр сценария, если клиент не назвал свои."""


class Limiter(StrEnum):
    """Что ограничивает FPS."""

    GPU = "gpu"
    CPU = "cpu"


@dataclass(frozen=True, slots=True)
class FpsEstimate:
    """Прогноз FPS в игре на заданных настройках."""

    game: str
    resolution: Resolution
    preset: Preset
    raytracing: bool
    fps: float
    gpu_cap: float
    cpu_cap: float
    vram_need_gb: float
    vram_gb: float

    @property
    def low(self) -> float:
        """Нижняя граница прогноза."""
        return self.fps * (1 - SPREAD)

    @property
    def high(self) -> float:
        """Верхняя граница прогноза."""
        return self.fps * (1 + SPREAD)

    @property
    def vram_ok(self) -> bool:
        """Видеопамяти хватает."""
        return self.vram_gb >= self.vram_need_gb

    @property
    def limited_by(self) -> Limiter:
        """Кто ограничивает FPS."""
        return Limiter.CPU if self.cpu_cap < self.gpu_cap else Limiter.GPU

    @property
    def bottleneck_ratio(self) -> float:
        """Соотношение CPU/GPU: < 1 — упор в процессор, > 1 — в видеокарту."""
        return self.cpu_cap / self.gpu_cap if self.gpu_cap > 0 else float("inf")

    @property
    def gpu_utilization(self) -> float:
        """На сколько процессор раскрывает видеокарту (0…1)."""
        return min(1.0, self.bottleneck_ratio)


@dataclass(frozen=True, slots=True)
class AppEstimate:
    """Прогноз для программы: индекс нагрузки и время типовой операции."""

    app: str
    workload_index: float
    minutes: float
    basic_ok: bool
    pro_ok: bool

    def level_ok(self, level: AppLevel) -> bool:
        """Хватает ли производительности для уровня работы."""
        return self.basic_ok if level is AppLevel.BASIC else self.pro_ok


@dataclass(frozen=True, slots=True)
class Benchmark:
    """Результат бенчмарка: значение из карточки или оценка по индексу."""

    name: str
    value: float
    estimated: bool


# --- Показатели сборки ----------------------------------------------------------------------------


def ram_factor(build: Build) -> float:
    """Поправка на ОЗУ (0.85–1.05): объём, частота и двухканальный режим."""
    ram = build.frame(Category.RAM)
    if not isinstance(ram, RAM):
        return 1.0
    if ram.capacity_gb <= 8:
        factor = 0.88
    elif ram.capacity_gb <= 16:
        factor = 0.98
    elif ram.capacity_gb <= 32:
        factor = 1.01
    else:
        factor = 1.02
    if ram.modules == 1:
        factor -= 0.05
    if ram.mem_type == "DDR5" and ram.speed_mts >= 6000:
        factor += 0.02
    elif ram.mem_type == "DDR4" and ram.speed_mts < 3200:
        factor -= 0.02
    return min(1.05, max(0.85, factor))


def cpu_indices(build: Build) -> tuple[float, float]:
    """Одноядерный и многоядерный индексы процессора (0, если процессора нет)."""
    cpu = build.frame(Category.CPU)
    if not isinstance(cpu, CPU):
        return 0.0, 0.0
    return cpu.perf_single or 0.0, cpu.perf_multi or 0.0


def gpu_indices(build: Build) -> tuple[float, float, float]:
    """Растеризация, трассировка и видеопамять; без видеокарты — встроенная графика."""
    gpu = build.frame(Category.GPU)
    if isinstance(gpu, GPU):
        return gpu.perf_raster or 0.0, gpu.perf_rt or 0.0, float(gpu.vram_gb)
    cpu = build.frame(Category.CPU)
    if isinstance(cpu, CPU) and cpu.igpu:
        return IGPU_RASTER, 0.0, IGPU_VRAM_GB
    return 0.0, 0.0, 0.0


def estimate_game(
    build: Build,
    game: Game,
    resolution: Resolution,
    preset: Preset,
    *,
    raytracing: bool = False,
) -> FpsEstimate:
    """Прогноз FPS в игре (вики §5.3). Игры с обязательной трассировкой считаются с RT."""
    rt = raytracing or game.rt_required
    raster, rt_index, vram = gpu_indices(build)
    single, _ = cpu_indices(build)
    base = game.base_fps.get(resolution, preset)
    gpu_index = rt_index if rt else raster
    gpu_cap = base * (RT_COST if rt else 1.0) * gpu_index / 100
    need = game.vram_need.get(resolution, preset)
    if vram < need:
        gpu_cap *= VRAM_PENALTY
    cpu_cap = game.cpu_fps_cap * single / 100 * ram_factor(build)
    return FpsEstimate(
        game=game.id,
        resolution=resolution,
        preset=preset,
        raytracing=rt,
        fps=round(min(gpu_cap, cpu_cap), 1),
        gpu_cap=round(gpu_cap, 1),
        cpu_cap=round(cpu_cap, 1),
        vram_need_gb=need,
        vram_gb=vram,
    )


def workload_index(build: Build, app: Application) -> float:
    """Индекс нагрузки программы: по тому, что она использует (вики §5.5)."""
    single, multi = cpu_indices(build)
    raster, _, _ = gpu_indices(build)
    match app.workload:
        case "cpu_single":
            return single
        case "cpu_multi":
            return multi
        case "gpu":
            return raster
        case _:
            return (multi + raster) / 2


def estimate_app(build: Build, app: Application) -> AppEstimate:
    """Время типовой операции и достаточность производительности для уровней работы."""
    index = workload_index(build, app)
    minutes = app.ref_minutes * 100 / index if index > 0 else float("inf")
    return AppEstimate(
        app=app.id,
        workload_index=round(index, 1),
        minutes=round(minutes, 2),
        basic_ok=index >= app.basic.min_index,
        pro_ok=index >= app.pro.min_index,
    )


def benchmarks(build: Build) -> list[Benchmark]:
    """Бенчмарки: значения из карточек деталей или оценка по индексам."""
    single, multi = cpu_indices(build)
    raster, _, _ = gpu_indices(build)
    cpu, gpu = build.frame(Category.CPU), build.frame(Category.GPU)
    known: dict[str, float | None] = {
        "cinebench_single": cpu.cinebench_single if isinstance(cpu, CPU) else None,
        "cinebench_multi": cpu.cinebench_multi if isinstance(cpu, CPU) else None,
        "timespy": gpu.timespy if isinstance(gpu, GPU) else None,
        "steel_nomad": gpu.steel_nomad if isinstance(gpu, GPU) else None,
    }
    index = {
        "cinebench_single": single,
        "cinebench_multi": multi,
        "timespy": raster,
        "steel_nomad": raster,
    }
    result: list[Benchmark] = []
    for name, value in known.items():
        if value is not None:
            result.append(Benchmark(name, float(value), estimated=False))
        elif index[name] > 0:
            result.append(Benchmark(name, round(REFERENCE_BENCH[name] * index[name] / 100), True))
    return result


# --- Полезность для конфигуратора ----------------------------------------------------------------


class FpsPerformanceModel:
    """Модель полезности по прогнозу FPS (заменяет временную модель на индексах, ADR 0005).

    Игровые сценарии оцениваются по FPS в играх клиента (или типовом наборе) на его разрешении,
    относительно эталонной сборки = 100. FPS выше частоты монитора × 1.25 не добавляет пользы.
    Неигровые сценарии — по смеси индексов, как раньше.
    """

    def __init__(
        self,
        tables: KnowledgeTables,
        *,
        resolution: Resolution = "1080p",
        refresh_hz: float | None = None,
        games: Sequence[str] = (),
        preset: Preset = Preset.HIGH,
        primary: Scenario = Scenario.AAA_GAMING,
    ) -> None:
        self.preset = preset
        self.primary = primary if primary in DEFAULT_GAMES else Scenario.AAA_GAMING
        self._perf_cache: dict[tuple[str, ...], Mapping[str, Fact]] = {}
        self.resolution = resolution
        self.fps_cap = refresh_hz * 1.25 if refresh_hz else None
        by_id = {game.id: game for game in tables.games}
        chosen = [by_id[g] for g in games if g in by_id]
        self.games: dict[Scenario, list[Game]] = {}
        for scenario, kind in ((Scenario.ESPORTS, "esports"), (Scenario.AAA_GAMING, "aaa")):
            own = [g for g in chosen if g.kind == kind]
            self.games[scenario] = own or [by_id[g] for g in DEFAULT_GAMES[scenario] if g in by_id]

    def _reference(self, game: Game) -> float:
        # Эталон считается так же, как прогноз: с поправкой на обязательную трассировку.
        base = game.base_fps.get(self.resolution, self.preset) * (
            RT_COST if game.rt_required else 1.0
        )
        fps = min(base, game.cpu_fps_cap)
        return min(fps, self.fps_cap) if self.fps_cap else fps

    def gaming_score(self, build: Build, scenario: Scenario) -> float:
        """Средний FPS в играх сценария относительно эталонной сборки, ×100."""
        games = self.games.get(scenario, [])
        if not games:
            return 0.0
        total = 0.0
        for game in games:
            fps = estimate_game(build, game, self.resolution, self.preset).fps
            if self.fps_cap:
                fps = min(fps, self.fps_cap)
            total += fps / self._reference(game)
        return 100 * total / len(games)

    def estimates(self, build: Build) -> list[FpsEstimate]:
        """Прогноз по играм главного игрового сценария клиента на его настройках."""
        return [
            estimate_game(build, game, self.resolution, self.preset)
            for game in self.games[self.primary]
        ]

    def perf_facts(self, build: Build) -> Mapping[str, Fact]:
        """Факты `perf.*` для правил баланса: средний FPS и соотношение CPU/GPU по играм клиента.

        Считаются, когда в сборке есть процессор и графика (дискретная или встроенная).
        """
        cached = self._perf_cache.get(build.skus)
        if cached is not None:
            return cached
        facts: dict[str, Fact] = {}
        estimates = self.estimates(build)
        if estimates and all(e.gpu_cap > 0 and e.cpu_cap > 0 for e in estimates):
            ratio = sum(e.bottleneck_ratio for e in estimates) / len(estimates)
            utilization = sum(e.gpu_utilization for e in estimates) / len(estimates)
            values: dict[str, Value] = {
                "perf.fps_avg": round(sum(e.fps for e in estimates) / len(estimates), 1),
                "perf.bottleneck_ratio": round(ratio, 3),
                "perf.gpu_utilization": round(utilization, 3),
                "perf.limited_by": Limiter.CPU.value if ratio < 1 else Limiter.GPU.value,
            }
            facts = {path: Fact(path, value, 1.0, (COMPUTED,)) for path, value in values.items()}
        self._perf_cache[build.skus] = facts
        return facts

    def scenario_scores(self, build: Build) -> Mapping[Scenario, float]:
        """Производительность по сценариям для полезности."""
        single, multi = cpu_indices(build)
        raster, rt, _ = gpu_indices(build)
        storage = storage_factor(build)
        ram = ram_factor(build)
        scores: dict[Scenario, float] = {}
        for scenario, (a, b, c, d) in SCENARIO_MIX.items():
            scores[scenario] = (a * single + b * multi + c * raster + d * rt) * ram * storage
        esports = self.gaming_score(build, Scenario.ESPORTS)
        aaa = self.gaming_score(build, Scenario.AAA_GAMING)
        scores[Scenario.ESPORTS] = esports * storage
        scores[Scenario.AAA_GAMING] = aaa * storage
        scores[Scenario.STREAMING] = 0.5 * max(esports, aaa) + 0.5 * scores[Scenario.STREAMING]
        return scores


def report(
    build: Build,
    tables: KnowledgeTables,
    games: Iterable[str],
    resolutions: Iterable[Resolution] = RESOLUTIONS,
    presets: Iterable[Preset] = tuple(Preset),
    apps: Iterable[str] = (),
) -> tuple[list[FpsEstimate], list[AppEstimate]]:
    """Прогноз для карточки сборки: FPS в играх по разрешениям/пресетам и время в программах."""
    by_game = {game.id: game for game in tables.games}
    by_app = {app.id: app for app in tables.applications}
    resolution_list, preset_list = list(resolutions), list(presets)
    fps = [
        estimate_game(build, by_game[g], r, p)
        for g in games
        if g in by_game
        for r in resolution_list
        for p in preset_list
    ]
    return fps, [estimate_app(build, by_app[a]) for a in apps if a in by_app]
