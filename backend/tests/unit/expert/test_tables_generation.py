"""Справочники и генератор правил."""

import pytest
from pydantic import ValidationError

from app.expert.dsl.compiler import compile_rules
from app.expert.dsl.schema import RuleKind
from app.expert.generation import code_part, generate_rules
from app.expert.tables import KnowledgeTables, Preset
from tests.unit.expert.kb_fixtures import small_tables, tables_data


def test_tables_lookup_and_known_values() -> None:
    tables = small_tables()
    assert tables.games[0].base_fps.get("1440p", Preset.HIGH) == 80
    known = tables.known_slot_values()
    assert known.sockets == {"AM4", "AM5"}
    assert "A620" in known.chipsets
    assert [c.id for c in tables.chipsets_by_socket()["AM5"]] == ["B650", "A620", "X870E"]


def test_tables_consistency_errors() -> None:
    data = tables_data()
    data["chipsets"].append({**data["chipsets"][0], "socket": "LGA9999"})
    data["games"].append(data["games"][0])
    with pytest.raises(ValidationError) as info:
        KnowledgeTables.model_validate(data)
    text = str(info.value)
    assert "неизвестный сокет LGA9999" in text
    assert "повторяются B650" in text
    assert "games: повторяются cs2" in text


def test_game_rt_required_needs_supported() -> None:
    data = tables_data()
    data["games"][0]["rt_required"] = True
    with pytest.raises(ValidationError, match="rt_required"):
        KnowledgeTables.model_validate(data)


@pytest.mark.parametrize(
    ("raw", "part"),
    [("cyberpunk_2077", "CYBERPUNK-2077"), ("Mini-ITX", "MINI-ITX"), ("B650E", "B650E")],
)
def test_code_part(raw: str, part: str) -> None:
    assert code_part(raw) == part


def test_generation_is_deterministic_and_compiles() -> None:
    first, second = generate_rules(small_tables()), generate_rules(small_tables())
    assert [r.model_dump() for r in first] == [r.model_dump() for r in second]
    assert [r.code for r in first] == sorted(r.code for r in first)
    compiled = compile_rules(first)
    assert len(compiled.rules) == len(first)


def test_generated_rule_families() -> None:
    codes = {rule.code: rule for rule in generate_rules(small_tables())}
    # GEN-SKT: 2 сокета × (чипсет, память, задел)
    assert {c for c in codes if c.startswith("GEN-SKT")} == {
        f"GEN-SKT-{s}-{k}" for s in ("AM4", "AM5") for k in ("CHIPSET", "MEM", "FUTURE")
    }
    assert codes["GEN-SKT-AM4-FUTURE"].then[0].weight < 0
    # GEN-CHP: TDP у всех, OC — только без разгона, PCIE5 — только PCIe 5.0
    assert "GEN-CHP-A620-OC" in codes
    assert "GEN-CHP-B650-OC" not in codes
    assert "GEN-CHP-X870E-PCIE5" in codes
    assert "GEN-CHP-B650-PCIE5" not in codes
    assert codes["GEN-CHP-A620-TDP"].kind is RuleKind.COMPAT
    # GEN-FF: плата в корпусе, БП в отсеке, размер корпуса, компактность
    assert "GEN-FF-SIZE-MINI" in codes
    assert "GEN-FF-SIZE-MID" not in codes
    assert "GEN-FF-MINI-ITX-COMPACT" in codes
    assert "GEN-FF-ATX-COMPACT" not in codes
    # GEN-GAME: 2 игры × 3 пресета; игре с обязательной трассировкой нужен RT
    games = [c for c in codes if c.startswith("GEN-GAME")]
    assert len(games) == 6
    doom = codes["GEN-GAME-DOOM-DARK-AGES-ULTRA"]
    assert doom.goal is not None
    assert doom.goal.args == {"game": "doom_dark_ages", "preset": "ultra"}
    assert "build.gpu.perf_rt" in str(doom.when.model_dump())
    # GEN-APP: 2 программы × 2 уровня; без требований к VRAM нет условия на видеокарту
    assert "build.gpu.vram_gb" not in str(codes["GEN-APP-OFFICE-PRO"].when.model_dump())
    assert "build.gpu.vram_gb" in str(codes["GEN-APP-BLENDER-PRO"].when.model_dump())
    for rule in codes.values():
        assert rule.origin.value == "generated"
        assert rule.source
        assert rule.source.startswith("tables/")
