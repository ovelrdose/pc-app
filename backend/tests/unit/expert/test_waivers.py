from app.expert.facts import WorkingMemory
from app.expert.waivers import WAIVABLE, waive, waiver_title


def test_waive_removes_only_waivable_requirements() -> None:
    memory = WorkingMemory()
    memory.set_fact("req.cpu_single_min", 85)
    memory.set_fact("req.color", "white")
    waive(memory, ["req.cpu_single_min", "req.color", "req.gpu_raster_min"])
    assert "req.cpu_single_min" not in memory
    assert "req.color" in memory  # цвет уступается ответом, а не снятием требования


def test_gpu_waiver_names_game_and_fps() -> None:
    memory = WorkingMemory()
    assert waiver_title("req.gpu_raster_min", memory) == WAIVABLE["req.gpu_raster_min"]
    memory.set_fact("need.gpu_game", "Cyberpunk 2077")
    memory.set_fact("need.gpu_fps", 60)
    assert waiver_title("req.gpu_raster_min", memory) == (
        "Видеокарта слабее нужной — Cyberpunk 2077 пойдёт ниже 60 кадров/с на высоких настройках"
    )
    assert waiver_title("req.ram_min_gb", memory) == WAIVABLE["req.ram_min_gb"]
