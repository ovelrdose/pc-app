"""Фреймы категорий комплектующих (наследники фрейма «Комплектующее»)."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from app.expert.frames.base import SLOT_VALUE_PATTERN, Category, Component, slot

SlotValue = Annotated[str, Field(pattern=SLOT_VALUE_PATTERN)]


class VrmTier(StrEnum):
    """Класс подсистемы питания материнской платы."""

    BASIC = "basic"
    MID = "mid"
    HIGH = "high"


class SsdInterface(StrEnum):
    """Интерфейс SSD."""

    SATA = "sata"
    NVME_PCIE3 = "nvme_pcie3"
    NVME_PCIE4 = "nvme_pcie4"
    NVME_PCIE5 = "nvme_pcie5"


class SsdFormFactor(StrEnum):
    """Форм-фактор SSD."""

    M2_2280 = "m2_2280"
    SATA_25 = "2.5"


class PsuEfficiency(StrEnum):
    """Сертификат 80 PLUS блока питания."""

    STANDARD = "80plus"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    TITANIUM = "titanium"


class PsuModularity(StrEnum):
    """Модульность кабелей блока питания."""

    NONE = "none"
    SEMI = "semi"
    FULL = "full"


class CaseSize(StrEnum):
    """Типоразмер корпуса (для пожеланий клиента)."""

    MINI = "mini"
    MID = "mid"
    FULL = "full"


class CoolerType(StrEnum):
    """Тип процессорного охлаждения."""

    AIR = "air"
    AIO = "aio"


class CPU(Component):
    """Фрейм «Процессор»."""

    model_config = ConfigDict(title="Процессор")

    category: Literal[Category.CPU] = slot("Категория", default=Category.CPU)
    socket: SlotValue = slot("Сокет")
    cores: int = slot("Ядер", ge=1, le=128)
    threads: int = slot("Потоков", ge=1, le=256)
    base_ghz: float = slot("Базовая частота", unit="ГГц", gt=0.5, le=7)
    boost_ghz: float = slot("Частота в бусте", unit="ГГц", gt=0.5, le=7)
    tdp_w: int = slot("TDP", unit="Вт", ge=10, le=400)
    igpu: bool = slot("Встроенная графика")
    unlocked: bool = slot("Разблокированный множитель", default=False)
    cooler_included: bool = slot("Кулер в комплекте", default=False)
    mem_types: list[SlotValue] = slot("Поддерживаемые типы памяти", min_length=1)
    perf_single: float | None = slot("Индекс одноядерный", default=None, gt=0, le=1000)
    perf_multi: float | None = slot("Индекс многоядерный", default=None, gt=0, le=1000)
    cinebench_single: int | None = slot("Cinebench 2024 single", default=None, gt=0)
    cinebench_multi: int | None = slot("Cinebench 2024 multi", default=None, gt=0)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        return self.check(self.threads >= self.cores, "потоков не может быть меньше ядер").check(
            self.boost_ghz >= self.base_ghz, "частота в бусте ниже базовой"
        )


class Motherboard(Component):
    """Фрейм «Материнская плата»."""

    model_config = ConfigDict(title="Материнская плата")

    category: Literal[Category.MOTHERBOARD] = slot("Категория", default=Category.MOTHERBOARD)
    socket: SlotValue = slot("Сокет")
    chipset: SlotValue = slot("Чипсет")
    form_factor: SlotValue = slot("Форм-фактор")
    mem_type: SlotValue = slot("Тип памяти")
    mem_slots: int = slot("Слотов памяти", ge=1, le=8)
    max_mem_gb: int = slot("Максимум памяти", unit="ГБ", ge=16, le=1024)
    m2_slots: int = slot("Слотов M.2", ge=0, le=8)
    sata_ports: int = slot("Портов SATA", ge=0, le=12)
    pcie_gen: int = slot("Поколение PCIe слота видеокарты", ge=3, le=6)
    wifi: bool = slot("Wi-Fi", default=False)
    vrm_tier: VrmTier = slot("Класс питания VRM")


class RAM(Component):
    """Фрейм «Оперативная память» (комплект модулей)."""

    model_config = ConfigDict(title="Оперативная память")

    category: Literal[Category.RAM] = slot("Категория", default=Category.RAM)
    mem_type: SlotValue = slot("Тип памяти")
    capacity_gb: int = slot("Объём комплекта", unit="ГБ", ge=4, le=512)
    modules: int = slot("Модулей в комплекте", ge=1, le=8)
    speed_mts: int = slot("Частота", unit="МТ/с", ge=1600, le=12000)
    cl: int = slot("Тайминг CL", ge=8, le=60)
    height_mm: int | None = slot("Высота модуля", unit="мм", default=None, ge=25, le=70)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        return self.check(
            self.capacity_gb % self.modules == 0, "объём не делится поровну между модулями"
        )


class GPU(Component):
    """Фрейм «Видеокарта»."""

    model_config = ConfigDict(title="Видеокарта")

    category: Literal[Category.GPU] = slot("Категория", default=Category.GPU)
    chip: str = slot("Графический чип", min_length=2, max_length=64)
    vram_gb: int = slot("Видеопамять", unit="ГБ", ge=2, le=64)
    tbp_w: int = slot("Энергопотребление (TBP)", unit="Вт", ge=30, le=800)
    length_mm: int | None = slot("Длина", unit="мм", default=None, ge=100, le=400)
    slots: float = slot("Толщина", unit="слотов", ge=1, le=4.5)
    power_connectors: list[SlotValue] = slot("Разъёмы питания", default_factory=list)
    rec_psu_w: int = slot("Рекомендуемый блок питания", unit="Вт", ge=200, le=1600)
    pcie_gen: int = slot("Поколение PCIe", ge=3, le=6)
    perf_raster: float | None = slot("Индекс растеризации", default=None, gt=0, le=2000)
    perf_rt: float | None = slot("Индекс трассировки", default=None, gt=0, le=2000)
    timespy: int | None = slot("3DMark Time Spy", default=None, gt=0)
    steel_nomad: int | None = slot("3DMark Steel Nomad", default=None, gt=0)


class Storage(Component):
    """Фрейм «Накопитель»: общий предок SSD и HDD."""

    capacity_gb: int = slot("Объём", unit="ГБ", ge=120, le=32_000)


class SSD(Storage):
    """Фрейм «SSD»."""

    model_config = ConfigDict(title="SSD")

    category: Literal[Category.SSD] = slot("Категория", default=Category.SSD)
    interface: SsdInterface = slot("Интерфейс")
    form_factor: SsdFormFactor = slot("Форм-фактор")
    read_mbs: int = slot("Скорость чтения", unit="МБ/с", ge=100, le=16_000)
    write_mbs: int = slot("Скорость записи", unit="МБ/с", ge=100, le=16_000)
    tbw: int | None = slot("Ресурс записи", unit="ТБ", default=None, gt=0)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        is_sata = self.interface is SsdInterface.SATA
        return self.check(
            is_sata or self.form_factor is SsdFormFactor.M2_2280, "NVMe-накопитель должен быть M.2"
        )


class HDD(Storage):
    """Фрейм «HDD»."""

    model_config = ConfigDict(title="HDD")

    category: Literal[Category.HDD] = slot("Категория", default=Category.HDD)
    rpm: Literal[5400, 5900, 7200] = slot("Скорость вращения", unit="об/мин")
    cache_mb: int | None = slot("Кэш", unit="МБ", default=None, ge=8, le=1024)


class PSU(Component):
    """Фрейм «Блок питания»."""

    model_config = ConfigDict(title="Блок питания")

    category: Literal[Category.PSU] = slot("Категория", default=Category.PSU)
    wattage: int = slot("Мощность", unit="Вт", ge=300, le=2000)
    efficiency: PsuEfficiency = slot("Сертификат 80 PLUS")
    modular: PsuModularity = slot("Модульность")
    form_factor: SlotValue = slot("Форм-фактор")
    pcie_connectors: list[SlotValue] = slot("Разъёмы питания видеокарты", default_factory=list)


class Case(Component):
    """Фрейм «Корпус»."""

    model_config = ConfigDict(title="Корпус")

    category: Literal[Category.CASE] = slot("Категория", default=Category.CASE)
    size: CaseSize = slot("Типоразмер")
    form_factors: list[SlotValue] = slot("Форм-факторы плат", min_length=1)
    max_gpu_mm: int | None = slot("Макс. длина видеокарты", unit="мм", default=None, ge=150)
    max_cooler_mm: int | None = slot("Макс. высота кулера", unit="мм", default=None, ge=30)
    psu_ff: SlotValue = slot("Форм-фактор блока питания")
    fan_slots: int = slot("Мест под вентиляторы", ge=0, le=16)
    fans_included: int = slot("Вентиляторов в комплекте", default=0, ge=0, le=12)
    radiator_support: list[Literal[120, 140, 240, 280, 360, 420]] = slot(
        "Поддержка радиаторов", unit="мм", default_factory=list
    )
    glass: bool = slot("Стеклянная панель", default=False)


class CPUCooler(Component):
    """Фрейм «Кулер процессора» (воздушный или СЖО)."""

    model_config = ConfigDict(title="Кулер процессора")

    category: Literal[Category.CPU_COOLER] = slot("Категория", default=Category.CPU_COOLER)
    type: CoolerType = slot("Тип")
    sockets: list[SlotValue] = slot("Сокеты", min_length=1)
    height_mm: int | None = slot("Высота", unit="мм", default=None, ge=30, le=200)
    tdp_capacity_w: int = slot("Рассеиваемая мощность", unit="Вт", ge=35, le=400)
    radiator_mm: Literal[120, 140, 240, 280, 360, 420] | None = slot(
        "Размер радиатора СЖО", unit="мм", default=None
    )
    noise_db: float | None = slot("Уровень шума", unit="дБ", default=None, ge=5, le=60)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        is_aio = self.type is CoolerType.AIO
        return self.check(
            is_aio == (self.radiator_mm is not None), "размер радиатора указывается только у СЖО"
        )


class CaseFan(Component):
    """Фрейм «Корпусной вентилятор» (упаковка из одного или нескольких)."""

    model_config = ConfigDict(title="Корпусной вентилятор")

    category: Literal[Category.CASE_FAN] = slot("Категория", default=Category.CASE_FAN)
    size_mm: Literal[80, 92, 120, 140, 200] = slot("Размер", unit="мм")
    quantity: int = slot("Штук в упаковке", default=1, ge=1, le=10)
    pwm: bool = slot("PWM-управление", default=True)
    noise_db: float | None = slot("Уровень шума", unit="дБ", default=None, ge=5, le=60)
    airflow_cfm: float | None = slot("Воздушный поток", unit="CFM", default=None, gt=0, le=200)


ComponentFrame = Annotated[
    CPU | Motherboard | RAM | GPU | SSD | HDD | PSU | Case | CPUCooler | CaseFan,
    Field(discriminator="category"),
]

FRAMES_BY_CATEGORY: dict[Category, type[Component]] = {
    Category.CPU: CPU,
    Category.MOTHERBOARD: Motherboard,
    Category.RAM: RAM,
    Category.GPU: GPU,
    Category.SSD: SSD,
    Category.HDD: HDD,
    Category.PSU: PSU,
    Category.CASE: Case,
    Category.CPU_COOLER: CPUCooler,
    Category.CASE_FAN: CaseFan,
}
