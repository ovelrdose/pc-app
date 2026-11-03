"""Вычисление статуса компонента: готов ли он к участию в подборе (архитектура §17)."""

from dataclasses import dataclass
from enum import StrEnum

from app.expert.frames.base import Component
from app.expert.frames.components import CPU, GPU, RAM, Case, CoolerType, CPUCooler, Motherboard


class ComponentStatus(StrEnum):
    """Статус компонента в каталоге."""

    ACTIVE = "active"
    INCOMPLETE = "incomplete"
    NEEDS_KB = "needs_kb"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True)
class KnownSlotValues:
    """Значения слотов, известные справочникам опубликованной базы знаний."""

    sockets: frozenset[str]
    chipsets: frozenset[str]
    form_factors: frozenset[str]
    mem_types: frozenset[str]


@dataclass(frozen=True, slots=True)
class StatusResult:
    """Статус и причины, по которым компонент не активен."""

    status: ComponentStatus
    issues: tuple[str, ...]


# Слоты, без которых модель производительности и проверки габаритов не работают.
_REQUIRED_FOR_MODEL: dict[type[Component], tuple[str, ...]] = {
    CPU: ("perf_single", "perf_multi"),
    GPU: ("perf_raster", "perf_rt", "length_mm"),
    Case: ("max_gpu_mm", "max_cooler_mm"),
}


def _missing_data(frame: Component) -> list[str]:
    required = list(_REQUIRED_FOR_MODEL.get(type(frame), ()))
    if isinstance(frame, CPUCooler) and frame.type is CoolerType.AIR:
        required.append("height_mm")
    return [f"{name} не заполнен" for name in required if getattr(frame, name) is None]


def _unknown_values(frame: Component, known: KnownSlotValues) -> list[str]:
    checks: list[tuple[str, str, frozenset[str]]] = []
    if isinstance(frame, CPU):
        checks.append(("сокет", frame.socket, known.sockets))
        checks += [("тип памяти", mem_type, known.mem_types) for mem_type in frame.mem_types]
    elif isinstance(frame, Motherboard):
        checks += [
            ("сокет", frame.socket, known.sockets),
            ("чипсет", frame.chipset, known.chipsets),
            ("форм-фактор", frame.form_factor, known.form_factors),
            ("тип памяти", frame.mem_type, known.mem_types),
        ]
    elif isinstance(frame, RAM):
        checks.append(("тип памяти", frame.mem_type, known.mem_types))
    # Кулеру достаточно одного известного сокета: остальные просто не будут использованы.
    elif isinstance(frame, CPUCooler) and not known.sockets.intersection(frame.sockets):
        checks.append(("сокет", "|".join(frame.sockets), known.sockets))
    # Типы памяти перечислены в справочнике сокетов (sockets.yaml, поле mem_types).
    table_names = {
        "сокет": "sockets",
        "чипсет": "chipsets",
        "форм-фактор": "form_factors",
        "тип памяти": "sockets",
    }
    return [
        f"{label} {value} отсутствует в {table_names[label]}"
        for label, value, values in checks
        if value not in values
    ]


def compute_status(
    frame: Component, *, known: KnownSlotValues | None, discontinued: bool = False
) -> StatusResult:
    """Определяет статус компонента.

    `known` — значения из справочников опубликованной БЗ; `None`, пока БЗ не опубликована,
    тогда проверка на `needs_kb` пропускается.
    """
    if discontinued:
        return StatusResult(ComponentStatus.INACTIVE, ())
    missing = _missing_data(frame)
    if missing:
        return StatusResult(ComponentStatus.INCOMPLETE, tuple(missing))
    if known is not None:
        unknown = _unknown_values(frame, known)
        if unknown:
            return StatusResult(ComponentStatus.NEEDS_KB, tuple(unknown))
    return StatusResult(ComponentStatus.ACTIVE, ())
