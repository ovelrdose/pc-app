"""Базовый фрейм «Комплектующее» и общие перечисления слотов."""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Значения сокетов, чипсетов, форм-факторов и типов памяти — открытые строки, а не перечисления:
# новая платформа добавляется в справочники базы знаний без изменения кода (статус `needs_kb`).
SLOT_VALUE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9.+\- ]{0,31}$"
SKU_PATTERN = r"^[A-Z0-9][A-Z0-9\-]{2,63}$"

# Слоты, которые хранятся в `components.perf`, а не в `components.specs`.
PERF_SLOTS: frozenset[str] = frozenset(
    {
        "perf_single",
        "perf_multi",
        "perf_raster",
        "perf_rt",
        "cinebench_single",
        "cinebench_multi",
        "timespy",
        "steel_nomad",
    }
)

# Слоты, которые хранятся отдельными колонками таблицы `components`.
COLUMN_SLOTS: frozenset[str] = frozenset(
    {"sku", "category", "brand", "model", "name", "price_kop", "in_stock"}
)


class Category(StrEnum):
    """Категория комплектующего; определяет фрейм."""

    CPU = "cpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    GPU = "gpu"
    SSD = "ssd"
    HDD = "hdd"
    PSU = "psu"
    CASE = "case"
    CPU_COOLER = "cpu_cooler"
    CASE_FAN = "case_fan"


class Color(StrEnum):
    """Основной цвет детали (для пожеланий по внешнему виду)."""

    BLACK = "black"
    WHITE = "white"
    SILVER = "silver"
    GRAY = "gray"
    RED = "red"
    BLUE = "blue"
    PINK = "pink"
    OTHER = "other"


def slot(title: str, *, unit: str | None = None, **constraints: Any) -> Any:  # noqa: ANN401
    """Описывает слот фрейма: русское название, единицы измерения и ограничения."""
    extra: dict[str, Any] = {"unit": unit} if unit else {}
    return Field(title=title, json_schema_extra=extra or None, **constraints)


class FrameModel(BaseModel):
    """Общая конфигурация фреймов: неизменяемые, без лишних полей."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class Component(FrameModel):
    """Фрейм «Комплектующее»: слоты, общие для всех категорий."""

    category: Category = slot("Категория")
    sku: str = slot("Артикул", pattern=SKU_PATTERN)
    brand: str = slot("Бренд", min_length=1, max_length=64)
    model: str = slot("Модель", min_length=1, max_length=128)
    name: str = slot("Название", min_length=1, max_length=200)
    price_kop: int = slot("Цена", unit="коп.", gt=0, le=100_000_000_00)
    in_stock: bool = slot("В наличии", default=True)
    release_year: int | None = slot("Год выпуска", default=None, ge=2010, le=2035)
    color: Color = slot("Цвет", default=Color.BLACK)
    rgb: bool = slot("RGB-подсветка", default=False)

    @model_validator(mode="before")
    @classmethod
    def _default_name(cls, data: Any) -> Any:  # noqa: ANN401
        # Демон «по умолчанию»: название собирается из бренда и модели.
        if isinstance(data, dict) and not data.get("name") and data.get("brand"):
            return {**data, "name": f"{data['brand']} {data.get('model', '')}".strip()}
        return data

    def check(self, condition: bool, message: str) -> Self:
        """Возвращает себя или бросает `ValueError` с сообщением для пользователя."""
        if not condition:
            raise ValueError(message)
        return self
