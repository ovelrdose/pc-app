from app.expert.facts import WorkingMemory
from app.expert.game_needs import (
    UNKNOWN_MONITOR_CF,
    compute_game_needs,
    game_need,
    record_game_needs,
)
from app.expert.tables import Preset
from tests.unit.expert.kb_fixtures import small_tables

TABLES = small_tables()
CS2, DOOM = TABLES.games


def test_target_is_comfort_fps_but_not_above_monitor() -> None:
    # CS2 без target_fps: по виду «esports» — 144 кадра, на средних настройках (base 100)
    assert CS2.comfort_fps == 144
    on_60 = game_need(CS2, "1080p", 60)
    assert (on_60.fps, on_60.preset, on_60.gpu_index, on_60.cpu_single) == (
        60,
        Preset.MEDIUM,
        60,
        15,
    )
    assert game_need(CS2, "1080p", 240).fps == 144
    assert game_need(CS2, "1080p", None).fps == 144  # монитор неизвестен — 144 Гц


def test_explicit_target_and_raytracing() -> None:
    competitive = CS2.model_copy(update={"target_fps": 240})
    assert game_need(competitive, "1080p", 240).gpu_index == 240
    assert game_need(competitive, "1080p", 144).gpu_index == 144
    # Doom: обязательная трассировка, высокие настройки (base 80 × 0.6), цель 60
    doom = game_need(DOOM, "1440p", 144)
    assert (doom.preset, doom.fps, doom.gpu_index, doom.cpu_single) == (Preset.HIGH, 60, 125, 30)


def test_record_needs_for_chosen_games() -> None:
    memory = WorkingMemory()
    memory.set_fact("user.games", ["cs2", "doom_dark_ages"])
    memory.set_fact("user.resolution", "1440p")
    memory.set_fact("user.refresh_hz", 144)
    record_game_needs(TABLES, memory)
    assert {k: v for k, v in memory.as_dict().items() if k.startswith("need.")} == {
        "need.gpu_raster": 144,
        "need.gpu_game": "Counter-Strike 2",
        "need.gpu_fps": 144,
        "need.gpu_rt": 125,
        "need.rt_game": "Doom",
        "need.cpu_single": 36,
        "need.cpu_game": "Counter-Strike 2",
        "need.cpu_fps": 144,
    }
    fact = memory.lookup("need.gpu_raster")
    assert fact is not None
    assert fact.cf == 1.0


def test_reference_games_and_unknown_monitor() -> None:
    memory = WorkingMemory()
    memory.set_fact("user.weight.esports", 1.0)
    memory.set_fact("user.weight.aaa_gaming", 0.0)
    record_game_needs(TABLES, memory)
    fact = memory.lookup("need.gpu_raster")
    assert fact is not None
    assert (fact.value, fact.cf) == (144, UNKNOWN_MONITOR_CF)
    needs = compute_game_needs(TABLES, memory)
    assert needs is not None
    assert needs.resolution == "1080p"
    assert needs.rt is None


def test_no_games_no_needs() -> None:
    memory = WorkingMemory()
    memory.set_fact("user.weight.office", 1.0)
    record_game_needs(TABLES, memory)
    assert not any(path.startswith("need.") for path in memory.as_dict())
