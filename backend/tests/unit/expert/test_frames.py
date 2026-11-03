"""Фреймы: наследование, ограничения слотов, умолчания, дискриминатор категории."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.expert.frames import (
    CPU,
    FRAMES_BY_CATEGORY,
    RAM,
    SSD,
    Category,
    Color,
    ComponentFrame,
    CPUCooler,
)
from tests.factories import slots


@pytest.mark.parametrize("category", list(Category))
def test_valid_slots_build_every_frame(category: Category) -> None:
    frame = FRAMES_BY_CATEGORY[category].model_validate(slots(category))
    assert frame.category is category
    # Наследование: общие слоты «Комплектующего» есть у каждого потомка, с умолчаниями.
    assert frame.in_stock is True
    assert frame.color is Color.BLACK


def test_name_defaults_to_brand_and_model() -> None:
    cpu = CPU.model_validate(slots(Category.CPU))
    assert cpu.name == "AMD Ryzen 5 7600"


def test_explicit_name_is_kept() -> None:
    cpu = CPU.model_validate(slots(Category.CPU, name="Ryzen 5 7600 OEM"))
    assert cpu.name == "Ryzen 5 7600 OEM"


def test_frames_are_immutable() -> None:
    cpu = CPU.model_validate(slots(Category.CPU))
    with pytest.raises(ValidationError):
        cpu.cores = 8  # type: ignore[misc]  # проверяем, что присваивание запрещено


def test_discriminated_union_picks_frame_by_category() -> None:
    adapter: TypeAdapter[ComponentFrame] = TypeAdapter(ComponentFrame)
    frame = adapter.validate_python({**slots(Category.RAM), "category": "ram"})
    assert isinstance(frame, RAM)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"threads": 4}, "потоков не может быть меньше ядер"),
        ({"boost_ghz": 3.0}, "частота в бусте ниже базовой"),
        ({"cores": 0}, "cores"),
        ({"socket": "AM5; DROP"}, "socket"),
        ({"sku": "lower-case"}, "sku"),
        ({"price_kop": 0}, "price_kop"),
        ({"mem_types": []}, "mem_types"),
        ({"unknown_slot": 1}, "unknown_slot"),
    ],
)
def test_cpu_constraints(overrides: dict[str, object], fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        CPU.model_validate(slots(Category.CPU, **overrides))


def test_ram_capacity_must_split_evenly() -> None:
    with pytest.raises(ValidationError, match="поровну"):
        RAM.model_validate(slots(Category.RAM, capacity_gb=24, modules=5))


def test_nvme_ssd_must_be_m2() -> None:
    with pytest.raises(ValidationError, match=r"M\.2"):
        SSD.model_validate(slots(Category.SSD, form_factor="2.5"))


def test_sata_ssd_may_be_25_inch() -> None:
    ssd = SSD.model_validate(slots(Category.SSD, interface="sata", form_factor="2.5"))
    assert ssd.form_factor.value == "2.5"


def test_aio_requires_radiator_and_air_forbids_it() -> None:
    with pytest.raises(ValidationError, match="радиатора"):
        CPUCooler.model_validate(slots(Category.CPU_COOLER, type="aio"))
    with pytest.raises(ValidationError, match="радиатора"):
        CPUCooler.model_validate(slots(Category.CPU_COOLER, radiator_mm=240))
    aio = CPUCooler.model_validate(
        slots(Category.CPU_COOLER, type="aio", radiator_mm=240, height_mm=None)
    )
    assert aio.radiator_mm == 240


def test_json_schema_carries_titles_and_units() -> None:
    schema = FRAMES_BY_CATEGORY[Category.GPU].model_json_schema()
    assert schema["title"] == "Видеокарта"
    length = schema["properties"]["length_mm"]
    assert length["title"] == "Длина"
    assert length["unit"] == "мм"
