"""Фреймовая модель: схемы комплектующих, ограничения слотов, статусы."""

from app.expert.frames.base import (
    COLUMN_SLOTS,
    PERF_SLOTS,
    Category,
    Color,
    Component,
)
from app.expert.frames.components import (
    CPU,
    FRAMES_BY_CATEGORY,
    GPU,
    HDD,
    PSU,
    RAM,
    SSD,
    Case,
    CaseFan,
    ComponentFrame,
    CPUCooler,
    Motherboard,
)
from app.expert.frames.status import (
    ComponentStatus,
    KnownSlotValues,
    StatusResult,
    compute_status,
)

__all__ = [
    "COLUMN_SLOTS",
    "CPU",
    "FRAMES_BY_CATEGORY",
    "GPU",
    "HDD",
    "PERF_SLOTS",
    "PSU",
    "RAM",
    "SSD",
    "CPUCooler",
    "Case",
    "CaseFan",
    "Category",
    "Color",
    "Component",
    "ComponentFrame",
    "ComponentStatus",
    "KnownSlotValues",
    "Motherboard",
    "StatusResult",
    "compute_status",
]
