"""Встроенные предикаты обратного вывода, которые вычисляет модель производительности."""

from collections.abc import Mapping

from app.expert.configurator.build import Build
from app.expert.dsl.expr import format_value
from app.expert.facts import Scalar
from app.expert.inference.backward import Builtin, NodeKind, ProofNode, ProofStatus
from app.expert.performance import estimate_app, estimate_game
from app.expert.tables import RESOLUTIONS, AppLevel, KnowledgeTables, Preset, Resolution

PRESET_TITLES: Mapping[Preset, str] = {
    Preset.MEDIUM: "средних",
    Preset.HIGH: "высоких",
    Preset.ULTRA: "ультра",
}


def _failed(label: str, detail: str) -> ProofNode:
    return ProofNode(NodeKind.BUILTIN, label, ProofStatus.FAILED, detail=detail)


def _resolution(value: Scalar | None) -> Resolution | None:
    return next((r for r in RESOLUTIONS if r == value), None)


def make_builtins(build: Build, tables: KnowledgeTables) -> dict[str, Builtin]:
    """Предикаты `fps_at_least`, `vram_enough`, `bench_at_least` для конкретной сборки."""
    games = {game.id: game for game in tables.games}
    apps = {app.id: app for app in tables.applications}

    def fps_at_least(args: Mapping[str, Scalar]) -> ProofNode:
        game = games.get(str(args.get("game")))
        resolution = _resolution(args.get("resolution"))
        target = args.get("fps")
        if game is None or resolution is None or not isinstance(target, int | float):
            return _failed("FPS ≥ целевого", f"неверные аргументы: {dict(args)}")
        preset = Preset(str(args.get("preset", Preset.HIGH.value)))
        estimate = estimate_game(build, game, resolution, preset)
        label = (
            f"{game.title}, {resolution}, {PRESET_TITLES[preset]} настройки: "
            f"FPS ≥ {format_value(target)}"
        )
        limiter = "процессор" if estimate.limited_by.value == "cpu" else "видеокарта"
        detail = (
            f"≈ {estimate.fps:.0f} FPS ({estimate.low:.0f}–{estimate.high:.0f}); "
            f"потолок видеокарты {estimate.gpu_cap:.0f}, процессора {estimate.cpu_cap:.0f}; "
            f"ограничивает {limiter}"
        )
        status = ProofStatus.PROVED if estimate.fps >= target else ProofStatus.FAILED
        return ProofNode(
            NodeKind.BUILTIN,
            label,
            status,
            1.0 if status is ProofStatus.PROVED else 0.0,
            detail=detail,
            value=estimate.fps,
        )

    def vram_enough(args: Mapping[str, Scalar]) -> ProofNode:
        game = games.get(str(args.get("game")))
        resolution = _resolution(args.get("resolution"))
        if game is None or resolution is None:
            return _failed("Хватает видеопамяти", f"неверные аргументы: {dict(args)}")
        preset = Preset(str(args.get("preset", Preset.HIGH.value)))
        estimate = estimate_game(build, game, resolution, preset)
        label = f"Видеопамять ≥ {format_value(estimate.vram_need_gb)} ГБ"
        detail = f"в сборке {format_value(estimate.vram_gb)} ГБ"
        status = ProofStatus.PROVED if estimate.vram_ok else ProofStatus.FAILED
        return ProofNode(
            NodeKind.BUILTIN,
            label,
            status,
            1.0 if estimate.vram_ok else 0.0,
            detail=detail,
            value=estimate.vram_gb,
        )

    def bench_at_least(args: Mapping[str, Scalar]) -> ProofNode:
        app = apps.get(str(args.get("app")))
        if app is None:
            return _failed("Производительность программы", f"неизвестная программа {args}")
        level = AppLevel(str(args.get("level", AppLevel.BASIC.value)))
        need = app.basic.min_index if level is AppLevel.BASIC else app.pro.min_index
        estimate = estimate_app(build, app)
        label = f"{app.title}: индекс нагрузки ≥ {need}"
        detail = (
            f"индекс {estimate.workload_index:.0f}; «{app.task}» ≈ {estimate.minutes:.1f} мин "
            f"(эталон {app.ref_minutes:g} мин)"
        )
        ok = estimate.level_ok(level)
        return ProofNode(
            NodeKind.BUILTIN,
            label,
            ProofStatus.PROVED if ok else ProofStatus.FAILED,
            1.0 if ok else 0.0,
            detail=detail,
            value=estimate.workload_index,
        )

    return {
        "fps_at_least": fps_at_least,
        "vram_enough": vram_enough,
        "bench_at_least": bench_at_least,
    }
