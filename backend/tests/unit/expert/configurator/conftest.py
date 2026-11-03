"""Общие данные тестов конфигуратора: реальный стартовый каталог и тестовые правила."""

from pathlib import Path
from typing import Any

import pytest

from app.expert.catalog import CatalogEntry, CatalogSnapshot
from app.expert.dsl.compiler import CompiledRuleSet, compile_rules
from app.expert.dsl.schema import Rule
from app.expert.facts import WorkingMemory
from app.services.catalog_csv import read_catalog_dir

KNOWLEDGE_DIR = Path(__file__).resolve().parents[5] / "knowledge"


def _rule(
    code: str, kind: str, when: dict[str, Any], then: list[dict[str, Any]], **kw: Any
) -> Rule:
    return Rule.model_validate(
        {
            "code": code,
            "name": kw.pop("name", code),
            "kind": kind,
            "group": "test",
            "priority": kw.pop("priority", 500),
            "cf": kw.pop("cf", 1.0),
            "when": when,
            "then": then,
            "explain": kw.pop("explain", code),
        }
    )


def compat(code: str, when: dict[str, Any], message: str) -> Rule:
    return _rule(code, "compat", when, [{"action": "reject", "message": message}])


def flt(code: str, when: dict[str, Any], message: str) -> Rule:
    return _rule(code, "filter", when, [{"action": "reject", "message": message}])


def ex(source: str) -> dict[str, str]:
    return {"expr": source}


TEST_RULES: list[Rule] = [
    compat(
        "CMP-001",
        {"fact": "build.cpu.socket", "op": "ne", "ref": "build.motherboard.socket"},
        "Сокет {build.cpu.socket} не подходит к плате {build.motherboard.socket}",
    ),
    compat(
        "CMP-002",
        {"fact": "build.ram.mem_type", "op": "ne", "ref": "build.motherboard.mem_type"},
        "Память {build.ram.mem_type}, а плата — {build.motherboard.mem_type}",
    ),
    compat(
        "CMP-003",
        ex("not contains(build.cpu.mem_types, build.motherboard.mem_type)"),
        "Процессор не поддерживает {build.motherboard.mem_type}",
    ),
    compat(
        "CMP-004",
        ex("not contains(build.case.form_factors, build.motherboard.form_factor)"),
        "Плата {build.motherboard.form_factor} не помещается в корпус",
    ),
    compat(
        "CMP-005",
        {"fact": "build.gpu.length_mm", "op": "gt", "ref": "build.case.max_gpu_mm"},
        "Видеокарта {build.gpu.length_mm} мм длиннее {build.case.max_gpu_mm} мм",
    ),
    compat(
        "CMP-006",
        {"fact": "build.cpu_cooler.height_mm", "op": "gt", "ref": "build.case.max_cooler_mm"},
        "Кулер {build.cpu_cooler.height_mm} мм не влезает",
    ),
    compat(
        "CMP-007",
        ex("not contains(build.cpu_cooler.sockets, build.cpu.socket)"),
        "Кулер не поддерживает {build.cpu.socket}",
    ),
    compat(
        "CMP-008",
        ex("build.psu.wattage < build.total.power_w * 1.3"),
        "БП {build.psu.wattage} Вт слабоват",
    ),
    compat(
        "CMP-009",
        {"fact": "build.psu.wattage", "op": "lt", "ref": "build.gpu.rec_psu_w"},
        "Видеокарте нужен БП от {build.gpu.rec_psu_w} Вт",
    ),
    compat(
        "CMP-010",
        ex("build.case.psu_ff == 'SFX' and build.psu.form_factor != 'SFX'"),
        "В корпус ставится только SFX",
    ),
    compat(
        "CMP-011",
        {"fact": "build.cpu_cooler.tdp_capacity_w", "op": "lt", "ref": "build.cpu.tdp_w"},
        "Кулер не справится с TDP {build.cpu.tdp_w} Вт",
    ),
    compat(
        "CMP-012",
        ex(
            "build.cpu_cooler.type == 'aio' and "
            "not contains(build.case.radiator_support, build.cpu_cooler.radiator_mm)"
        ),
        "Радиатор не ставится в корпус",
    ),
    compat(
        "CMP-013",
        ex("build.ssd.form_factor == 'm2_2280' and build.motherboard.m2_slots < 1"),
        "Нет слота M.2",
    ),
    compat(
        "CMP-014",
        ex("build.hdd.capacity_gb > 0 and build.motherboard.sata_ports < 1"),
        "Нет портов SATA",
    ),
    compat(
        "CMP-015",
        {"fact": "build.ram.modules", "op": "gt", "ref": "build.motherboard.mem_slots"},
        "Планок больше, чем слотов",
    ),
    flt("FLT-001", {"fact": "cand.in_stock", "op": "eq", "value": False}, "Нет в наличии"),
    flt(
        "FLT-002",
        {
            "all": [
                {"fact": "cand.category", "op": "eq", "value": "gpu"},
                {"fact": "cand.vram_gb", "op": "lt", "ref": "req.gpu_vram_min_gb"},
            ]
        },
        "Видеопамяти {cand.vram_gb} ГБ, нужно от {req.gpu_vram_min_gb}",
    ),
    flt(
        "FLT-003",
        {
            "all": [
                {"fact": "user.color", "op": "eq", "value": "white"},
                {"fact": "cand.category", "op": "eq", "value": "case"},
                {"fact": "cand.color", "op": "ne", "value": "white"},
            ]
        },
        "Корпус не белый",
    ),
    flt(
        "FLT-004",
        {
            "all": [
                {"fact": "req.need.gpu", "op": "eq", "value": False},
                {"fact": "cand.category", "op": "eq", "value": "cpu"},
                {"fact": "cand.igpu", "op": "eq", "value": False},
            ]
        },
        "Без видеокарты нужен процессор со встроенной графикой",
    ),
    flt(
        "FLT-005",
        {
            "all": [
                {"fact": "cand.category", "op": "eq", "value": "ram"},
                {"fact": "cand.capacity_gb", "op": "lt", "ref": "req.ram_min_gb"},
            ]
        },
        "Памяти {cand.capacity_gb} ГБ, нужно от {req.ram_min_gb}",
    ),
    _rule(
        "SCR-001",
        "score",
        {
            "all": [
                {"fact": "user.future_proof", "op": "eq", "value": True},
                {"fact": "build.cpu.socket", "op": "eq", "value": "AM5"},
            ]
        },
        [{"action": "prefer", "weight": 5, "message": "Платформа AM5 — задел на будущее"}],
    ),
    _rule(
        "BAL-001",
        "score",
        ex("build.gpu.perf_raster > build.cpu.perf_single * 2.5"),
        [{"action": "prefer", "weight": -10, "message": "Процессор слабоват для видеокарты"}],
    ),
    _rule(
        "VAL-001",
        "validate",
        {"fact": "build.ram.modules", "op": "eq", "value": 1},
        [{"action": "warn", "message": "Одна планка памяти — нет двухканального режима"}],
    ),
    _rule(
        "VAL-002",
        "validate",
        {"fact": "build.ssd.capacity_gb", "op": "lt", "ref": "req.storage_min_gb"},
        [{"action": "error", "message": "Накопитель меньше {req.storage_min_gb} ГБ"}],
    ),
    _rule(
        "VAL-003",
        "validate",
        {
            "all": [
                {"fact": "profile.weight.aaa_gaming", "op": "ge", "value": 0.5},
                {"fact": "build.gpu.vram_gb", "op": "lt", "value": 12},
            ]
        },
        [
            {
                "action": "suggest",
                "category": "gpu",
                "target": "vram_12",
                "message": "Для новых игр лучше видеокарта с 12+ ГБ",
            }
        ],
    ),
]


@pytest.fixture(scope="session")
def rule_set() -> CompiledRuleSet:
    return compile_rules(TEST_RULES)


@pytest.fixture(scope="session")
def catalog() -> CatalogSnapshot:
    result = read_catalog_dir(KNOWLEDGE_DIR / "catalog")
    assert result.ok
    return CatalogSnapshot.build(1, (CatalogEntry(record.frame) for record in result.records))


def profile(**facts: Any) -> WorkingMemory:
    """Рабочая память после профилирования: ключи с `__` вместо точек."""
    memory = WorkingMemory()
    for key, value in facts.items():
        cf = 1.0
        if isinstance(value, tuple):
            value, cf = value
        memory.set_fact(key.replace("__", "."), value, cf)
    return memory


GAMER = {"profile__weight__aaa_gaming": 1.0, "profile__weight__esports": 0.3}
OFFICE = {"profile__weight__office": 1.0, "req__need__gpu": False}
EDITOR = {"profile__weight__video_editing": 1.0, "profile__weight__aaa_gaming": 0.3}
