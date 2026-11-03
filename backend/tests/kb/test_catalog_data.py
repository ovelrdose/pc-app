"""Проверки данных каталога `knowledge/catalog`: формат, статусы, покрытие платформ."""

from collections import Counter
from functools import cache
from pathlib import Path

import pytest

from app.expert.frames import (
    CPU,
    GPU,
    PSU,
    RAM,
    Case,
    Category,
    Component,
    ComponentStatus,
    CPUCooler,
    Motherboard,
    compute_status,
)
from app.expert.knowledge import KnowledgeSnapshot
from app.services.catalog_csv import CatalogDirResult, read_catalog_dir

KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "knowledge"
MIN_PER_CATEGORY = 5


@cache
def catalog() -> CatalogDirResult:
    return read_catalog_dir(KNOWLEDGE_DIR / "catalog")


def frames[T: Component](frame_type: type[T]) -> list[T]:
    return [r.frame for r in catalog().records if isinstance(r.frame, frame_type)]


def test_knowledge_layout_exists() -> None:
    for sub in ("catalog", "tables", "rules/manual", "rules/generated", "golden"):
        assert (KNOWLEDGE_DIR / sub).is_dir(), sub


def test_catalog_files_parse_without_errors() -> None:
    result = catalog()
    assert result.missing_files == []
    assert result.errors == {}, "\n".join(
        f"{file}: {error}" for file, errors in result.errors.items() for error in errors
    )


def test_every_category_has_enough_items() -> None:
    counts = Counter(record.frame.category for record in catalog().records)
    thin = {c.value: counts[c] for c in Category if counts[c] < MIN_PER_CATEGORY}
    assert not thin, f"мало позиций: {thin}"


def test_every_item_has_price_source_and_date() -> None:
    for record in catalog().records:
        assert record.price_note, record.frame.sku
        assert record.price_checked_at is not None, record.frame.sku


def test_no_incomplete_items_in_seed_catalog() -> None:
    incomplete = {
        record.frame.sku: compute_status(record.frame, known=None).issues
        for record in catalog().records
        if compute_status(record.frame, known=None).status is not ComponentStatus.ACTIVE
    }
    assert not incomplete


def test_no_needs_kb_items_in_seed_catalog(knowledge: KnowledgeSnapshot) -> None:
    """Позиции с платформенными значениями вне справочников БЗ (сокеты, чипсеты, форм-факторы,
    типы памяти) не должны попадать в сид: сначала дополняются справочники (§17 архитектуры)."""
    known = knowledge.known_slot_values
    needs_kb = {
        record.frame.sku: compute_status(record.frame, known=known).issues
        for record in catalog().records
        if compute_status(record.frame, known=known).status is ComponentStatus.NEEDS_KB
    }
    assert not needs_kb


def test_every_cpu_socket_has_motherboard_and_cooler() -> None:
    board_sockets = {board.socket for board in frames(Motherboard)}
    cooler_sockets = {socket for cooler in frames(CPUCooler) for socket in cooler.sockets}
    for cpu in frames(CPU):
        assert cpu.socket in board_sockets, f"нет платы под {cpu.socket}"
        assert cpu.socket in cooler_sockets, f"нет кулера под {cpu.socket}"


@pytest.mark.parametrize("mem_type", ["DDR4", "DDR5"])
def test_every_memory_type_has_ram_kits(mem_type: str) -> None:
    assert any(board.mem_type == mem_type for board in frames(Motherboard))
    assert any(kit.mem_type == mem_type for kit in frames(RAM))


def test_every_board_form_factor_fits_some_case() -> None:
    case_form_factors = {ff for case in frames(Case) for ff in case.form_factors}
    for board in frames(Motherboard):
        assert board.form_factor in case_form_factors, board.sku


def test_every_gpu_has_psu_and_case() -> None:
    max_psu = max(psu.wattage for psu in frames(PSU))
    max_gpu_length = max(case.max_gpu_mm or 0 for case in frames(Case))
    for gpu in frames(GPU):
        assert gpu.rec_psu_w <= max_psu, gpu.sku
        assert (gpu.length_mm or 0) <= max_gpu_length, gpu.sku


def test_office_build_possible_without_gpu() -> None:
    assert any(cpu.igpu and cpu.in_stock for cpu in frames(CPU))
