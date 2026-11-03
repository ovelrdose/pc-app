"""Требования к железу по играм клиента (ADR 0008).

Для каждой игры цель — комфортный FPS (`Game.comfort_fps`), но не выше частоты монитора: кадры
сверх неё монитор не покажет. Соревновательные игры считаются на средних настройках (в них
играют ради кадров), остальные — на высоких. Нужный индекс видеокарты и процессора получается
обращением формулы прогноза FPS (вики §5.3): FPS = base_fps × индекс / 100.

Результат записывается вычисляемыми фактами `need.*`; требования `req.*` из них выводят правила.
Если монитор неизвестен, берётся Full HD и частота `UNKNOWN_REFRESH_HZ`, а уверенность фактов
снижается до `UNKNOWN_MONITOR_CF`, чтобы требования стали желательными, а не обязательными.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.expert.facts import COMPUTED, FactView, WorkingMemory
from app.expert.tables import RESOLUTIONS, Game, KnowledgeTables, Preset, Resolution

DEFAULT_GAMES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "esports": ("cs2", "valorant", "dota2"),
        "aaa": ("cyberpunk_2077", "rdr2", "baldurs_gate_3", "alan_wake_2"),
    }
)
"""Типовой набор игр по виду для модели производительности, если клиент не назвал свои."""

REFERENCE_GAMES: Mapping[str, str] = MappingProxyType({"esports": "cs2", "aaa": "cyberpunk_2077"})
"""Эталонная игра вида для требований, если клиент игр не назвал: самые известные ориентиры.
Самая тяжёлая игра типового набора (Alan Wake 2) завысила бы требование для клиента, который о
ней не говорил; названные клиентом игры, наоборот, учитываются все.
"""

KIND_SCENARIO: Mapping[str, str] = MappingProxyType({"esports": "esports", "aaa": "aaa_gaming"})
"""Вид игры → сценарий, вес которого показывает, что клиент в такие игры играет."""

KIND_PRESET: Mapping[str, Preset] = MappingProxyType({"esports": Preset.MEDIUM, "aaa": Preset.HIGH})
"""Настройки графики, на которых считается требование."""

RT_COST = 0.6
"""Доля FPS, остающаяся при трассировке лучей; общая с моделью производительности."""

UNKNOWN_REFRESH_HZ = 144
"""Частота, которую предполагаем, если монитор неизвестен."""

UNKNOWN_MONITOR_CF = 0.5
"""Уверенность требований по играм при неизвестном мониторе."""


@dataclass(frozen=True, slots=True)
class GameNeed:
    """Что нужно одной игре для комфортного FPS."""

    game: Game
    fps: int
    preset: Preset
    gpu_index: float
    cpu_single: float


@dataclass(frozen=True, slots=True)
class GameNeeds:
    """Требования по всем играм клиента; самая требовательная игра определяет итог."""

    resolution: Resolution
    needs: tuple[GameNeed, ...]

    @property
    def gpu(self) -> GameNeed | None:
        """Самая требовательная к растеризации игра (без обязательной трассировки)."""
        raster = [n for n in self.needs if not n.game.rt_required]
        return max(raster, key=lambda n: n.gpu_index, default=None)

    @property
    def rt(self) -> GameNeed | None:
        """Самая требовательная игра с обязательной трассировкой лучей."""
        rt = [n for n in self.needs if n.game.rt_required]
        return max(rt, key=lambda n: n.gpu_index, default=None)

    @property
    def cpu(self) -> GameNeed | None:
        """Самая требовательная к процессору игра."""
        return max(self.needs, key=lambda n: n.cpu_single, default=None)


def game_need(
    game: Game, resolution: Resolution, refresh_hz: float | None, *, preset: Preset | None = None
) -> GameNeed:
    """Индексы видеокарты и процессора, при которых игра выдаёт комфортный FPS."""
    preset = preset or KIND_PRESET[game.kind]
    monitor = refresh_hz if refresh_hz else UNKNOWN_REFRESH_HZ
    fps = int(min(game.comfort_fps, monitor))
    base = game.base_fps.get(resolution, preset) * (RT_COST if game.rt_required else 1.0)
    return GameNeed(
        game=game,
        fps=fps,
        preset=preset,
        gpu_index=round(100 * fps / base),
        cpu_single=round(100 * fps / game.cpu_fps_cap),
    )


def client_games(tables: KnowledgeTables, memory: FactView) -> list[Game]:
    """Игры клиента; если он их не назвал — эталонные игры заявленных игровых сценариев."""
    by_id = {game.id: game for game in tables.games}
    chosen = memory.lookup("user.games")
    if chosen is not None and isinstance(chosen.value, tuple) and chosen.value:
        return [by_id[g] for g in chosen.value if isinstance(g, str) and g in by_id]
    games: list[Game] = []
    for kind, game_id in REFERENCE_GAMES.items():
        weight = memory.lookup(f"user.weight.{KIND_SCENARIO[kind]}")
        value = weight.value if weight is not None else 0
        if isinstance(value, int | float) and value > 0 and game_id in by_id:
            games.append(by_id[game_id])
    return games


def compute_game_needs(tables: KnowledgeTables, memory: FactView) -> GameNeeds | None:
    """Требования по играм клиента или `None`, если игр нет."""
    games = client_games(tables, memory)
    if not games:
        return None
    resolution: Resolution = "1080p"
    fact = memory.lookup("user.resolution")
    for option in RESOLUTIONS:
        if fact is not None and fact.value == option:
            resolution = option
    refresh = memory.lookup("user.refresh_hz")
    refresh_hz = float(refresh.value) if refresh and isinstance(refresh.value, int) else None
    needs = [game_need(game, resolution, refresh_hz) for game in games]
    return GameNeeds(resolution=resolution, needs=tuple(needs))


def record_game_needs(tables: KnowledgeTables, memory: WorkingMemory) -> None:
    """Записывает факты `need.*` (вики §5.7). Без игр ничего не записывает."""
    needs = compute_game_needs(tables, memory)
    if needs is None:
        return
    cf = 1.0 if memory.lookup("user.resolution") is not None else UNKNOWN_MONITOR_CF
    facts: dict[str, object] = {}
    if (gpu := needs.gpu) is not None:
        facts |= {
            "need.gpu_raster": gpu.gpu_index,
            "need.gpu_game": gpu.game.title,
            "need.gpu_fps": gpu.fps,
        }
    if (rt := needs.rt) is not None:
        facts |= {"need.gpu_rt": rt.gpu_index, "need.rt_game": rt.game.title}
    if (cpu := needs.cpu) is not None:
        facts |= {
            "need.cpu_single": cpu.cpu_single,
            "need.cpu_game": cpu.game.title,
            "need.cpu_fps": cpu.fps,
        }
    for path, value in facts.items():
        memory.set_fact(path, value, cf, COMPUTED)
