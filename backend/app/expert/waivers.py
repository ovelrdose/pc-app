"""Уступки требований: обязательные требования, от которых клиент может отказаться (вики §4.10).

Когда бюджета не хватает даже после уступок в ответах (объём SSD, внешний вид, монитор),
компромиссная сборка снимает выведенные системой требования — по одному, в порядке
`WAIVABLE`. Клиент соглашается на такие уступки явно, и консультация их запоминает: при
подборе, правке и объяснениях эти требования снимаются из рабочей памяти после вывода.
"""

from collections.abc import Collection, Mapping
from types import MappingProxyType

from app.expert.facts import FactView, WorkingMemory

WAIVABLE: Mapping[str, str] = MappingProxyType(
    {
        "req.cpu_single_min": "Процессор слабее рекомендованного",
        "req.ram_dual_channel": "Одна планка памяти вместо двух — вторую можно докупить позже",
        "req.gpu_raster_min": "Видеокарта слабее рекомендованной",
        "req.ram_min_gb": "Меньше оперативной памяти, чем рекомендовано",
        "req.gpu_vram_min_gb": "Меньше видеопамяти, чем рекомендовано",
    }
)
"""Требования, от которых можно отказаться, в порядке уступки: от наименее заметных к самым
заметным. Порядок — знание эксперта: процессор в играх обычно не узкое место, вторая планка
докупается без замены деталей, а слабая видеокарта и малый объём памяти чувствуются сразу.
"""


def waiver_title(path: str, memory: FactView) -> str:
    """Текст уступки для клиента; для видеокарты — с игрой и FPS, ради которых требование."""
    if path == "req.gpu_raster_min":
        game, fps = memory.lookup("need.gpu_game"), memory.lookup("need.gpu_fps")
        if game is not None and fps is not None:
            return (
                f"Видеокарта слабее нужной — {game.value} пойдёт ниже {fps.value} кадров/с "
                "на высоких настройках"
            )
    return WAIVABLE.get(path, path)


def waive(memory: WorkingMemory, waived: Collection[str]) -> None:
    """Снимает требования, от которых клиент отказался (после прямого вывода)."""
    for path in waived:
        if path in WAIVABLE and path in memory:
            memory.retract(path)
