"""Справочники базы знаний (`knowledge/tables/*.yaml`): схемы и проверки согласованности."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.expert.configurator.plan import Scenario
from app.expert.frames import KnownSlotValues
from app.expert.frames.base import SLOT_VALUE_PATTERN

Slug = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=40)]
SlotValue = Annotated[str, Field(pattern=SLOT_VALUE_PATTERN)]
Resolution = Literal["1080p", "1440p", "2160p"]
RESOLUTIONS: tuple[Resolution, ...] = ("1080p", "1440p", "2160p")


DEFAULT_TARGET_FPS: Mapping[str, int] = {"esports": 144, "aaa": 60}
"""Комфортный FPS для снимков БЗ, где у игр ещё не было поля target_fps."""


class Preset(StrEnum):
    """Пресет графики."""

    MEDIUM = "medium"
    HIGH = "high"
    ULTRA = "ultra"


class AppLevel(StrEnum):
    """Уровень работы в программе."""

    BASIC = "basic"
    PRO = "pro"


class TableModel(BaseModel):
    """Общая конфигурация справочников."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Socket(TableModel):
    """Сокет процессора."""

    id: SlotValue
    vendor: Literal["amd", "intel"]
    mem_types: list[SlotValue] = Field(min_length=1)
    perspective: bool = Field(description="Платформа ещё получит новые процессоры")
    release_year: int = Field(ge=2010, le=2035)


class Chipset(TableModel):
    """Чипсет материнской платы."""

    id: SlotValue
    socket: SlotValue
    tier: Literal["entry", "mainstream", "enthusiast"]
    cpu_overclock: bool
    gpu_pcie_gen: int = Field(ge=3, le=6)
    m2_pcie_gen: int = Field(ge=3, le=6)
    max_cpu_tdp_w: int = Field(ge=35, le=400, description="Типичный предел платы по TDP CPU")


class BoardFormFactor(TableModel):
    """Форм-фактор материнской платы."""

    id: SlotValue
    rank: int = Field(ge=1, le=9, description="Больше — крупнее")
    width_mm: int = Field(ge=100, le=400)
    height_mm: int = Field(ge=100, le=400)


class PsuFormFactor(TableModel):
    """Форм-фактор блока питания и куда он ставится."""

    id: SlotValue
    fits_case_psu: list[SlotValue] = Field(min_length=1)


class CaseSizeRule(TableModel):
    """Какой самый крупный форм-фактор платы уместен в корпусе этого размера."""

    size: Literal["mini", "mid", "full"]
    max_board_rank: int = Field(ge=1, le=9)


class FormFactors(TableModel):
    """Справочник форм-факторов."""

    motherboard: list[BoardFormFactor] = Field(min_length=1)
    psu: list[PsuFormFactor] = Field(min_length=1)
    case_sizes: list[CaseSizeRule] = Field(min_length=1)


class PresetNumbers(TableModel):
    """Значения по пресетам."""

    medium: float = Field(gt=0)
    high: float = Field(gt=0)
    ultra: float = Field(gt=0)


class ResolutionTable(TableModel):
    """Значения по разрешениям и пресетам."""

    p1080: PresetNumbers = Field(alias="1080p")
    p1440: PresetNumbers = Field(alias="1440p")
    p2160: PresetNumbers = Field(alias="2160p")

    def get(self, resolution: Resolution, preset: Preset) -> float:
        """Значение для разрешения и пресета."""
        row = {"1080p": self.p1080, "1440p": self.p1440, "2160p": self.p2160}[resolution]
        return float(getattr(row, preset.value))


class Game(TableModel):
    """Игра: нагрузка и требования (эталон: RTX 4060 и Ryzen 5 7600)."""

    id: Slug
    title: str = Field(min_length=1, max_length=100)
    kind: Literal["esports", "aaa"]
    rt_supported: bool
    rt_required: bool = False
    base_fps: ResolutionTable = Field(description="FPS на эталонной видеокарте")
    cpu_fps_cap: float = Field(gt=0, description="Потолок FPS на эталонном процессоре")
    vram_need: ResolutionTable = Field(description="Нужно видеопамяти, ГБ")
    ram_min_gb: int = Field(ge=4, le=128)
    target_fps: int | None = Field(
        default=None,
        ge=30,
        le=360,
        description="Комфортный FPS; выше частоты монитора не требуется",
    )

    @property
    def comfort_fps(self) -> int:
        """Комфортный FPS игры; в снимках БЗ без этого поля — по виду игры."""
        if self.target_fps is not None:
            return self.target_fps
        return DEFAULT_TARGET_FPS[self.kind]

    @model_validator(mode="after")
    def _rt(self) -> Self:
        if self.rt_required and not self.rt_supported:
            raise ValueError("rt_required без rt_supported")
        return self


class AppRequirements(TableModel):
    """Требования программы на одном уровне работы."""

    ram_min_gb: int = Field(ge=4, le=512)
    vram_min_gb: int = Field(ge=0, le=64, description="0 — хватит встроенной графики")
    cpu_cores_min: int = Field(ge=1, le=128)
    min_index: int = Field(ge=1, le=1000, description="Минимальный индекс нагрузки, эталон = 100")


class Application(TableModel):
    """Программа и её требования."""

    id: Slug
    title: str = Field(min_length=1, max_length=100)
    scenario: Scenario
    workload: Literal["cpu_single", "cpu_multi", "gpu", "mixed"]
    task: str = Field(min_length=1, max_length=100, description="Типовая операция")
    ref_minutes: float = Field(gt=0, description="Время операции на эталонной системе, мин")
    basic: AppRequirements
    pro: AppRequirements


class KnowledgeTables(TableModel):
    """Все справочники вместе; проверяет ссылки между ними."""

    sockets: list[Socket]
    chipsets: list[Chipset]
    form_factors: FormFactors
    games: list[Game]
    applications: list[Application]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        problems: list[str] = []
        for name, ids in (
            ("sockets", [s.id for s in self.sockets]),
            ("chipsets", [c.id for c in self.chipsets]),
            ("games", [g.id for g in self.games]),
            ("applications", [a.id for a in self.applications]),
            ("form_factors.motherboard", [f.id for f in self.form_factors.motherboard]),
        ):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            if duplicates:
                problems.append(f"{name}: повторяются {', '.join(duplicates)}")
        sockets = {s.id for s in self.sockets}
        problems += [
            f"чипсет {c.id}: неизвестный сокет {c.socket}"
            for c in self.chipsets
            if c.socket not in sockets
        ]
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def known_slot_values(self) -> KnownSlotValues:
        """Значения слотов, которые знает база знаний (для статуса `needs_kb`)."""
        return KnownSlotValues(
            sockets=frozenset(s.id for s in self.sockets),
            chipsets=frozenset(c.id for c in self.chipsets),
            form_factors=frozenset(f.id for f in self.form_factors.motherboard),
        )

    def chipsets_by_socket(self) -> Mapping[str, list[Chipset]]:
        """Чипсеты, сгруппированные по сокету (в порядке справочника)."""
        result: dict[str, list[Chipset]] = {s.id: [] for s in self.sockets}
        for chipset in self.chipsets:
            result[chipset.socket].append(chipset)
        return result
