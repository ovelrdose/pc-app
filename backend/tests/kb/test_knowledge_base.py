"""База знаний целиком: объём, чистота валидатора, актуальность генерации, анкета, статусы."""

from collections import Counter

from app.expert.catalog import CatalogSnapshot
from app.expert.frames import ComponentStatus
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.questionnaire import check_fact_types
from app.expert.validation import validate_knowledge
from app.services.knowledge_files import load_rules
from scripts.generate_rules import render_files
from tests.kb.conftest import KNOWLEDGE_DIR

MANUAL_GROUPS = ("PRF", "REQ", "BUD", "FLT", "CMP", "BAL", "SCR", "VAL", "GOL")
GENERATED_GROUPS = ("GEN-SKT", "GEN-CHP", "GEN-FF", "GEN-GAME", "GEN-APP")


def group_of(code: str) -> str:
    return "-".join(code.split("-")[:2]) if code.startswith("GEN-") else code.split("-")[0]


def test_rule_files_parse() -> None:
    result = load_rules(KNOWLEDGE_DIR / "rules")
    assert result.errors == []


def test_at_least_500_rules_in_all_groups(knowledge: KnowledgeSnapshot) -> None:
    counts = Counter(group_of(rule.code) for rule in knowledge.rules)
    assert sum(counts.values()) >= 500
    for group in (*MANUAL_GROUPS, *GENERATED_GROUPS):
        assert counts[group] > 0, group


def test_validator_is_clean(knowledge: KnowledgeSnapshot) -> None:
    report = validate_knowledge(list(knowledge.rules))
    assert report.errors == [], "\n".join(map(str, report.errors))
    assert report.warnings == [], "\n".join(map(str, report.warnings))


def test_generated_rules_are_up_to_date() -> None:
    generated = KNOWLEDGE_DIR / "rules" / "generated"
    for name, text in render_files(KNOWLEDGE_DIR).items():
        assert (generated / name).read_text(encoding="utf-8") == text, (
            f"{name} устарел: запустите uv run python -m scripts.generate_rules"
        )


def test_generated_rules_marked(knowledge: KnowledgeSnapshot) -> None:
    for rule in knowledge.rules:
        is_generated = rule.code.startswith("GEN-")
        assert (rule.origin.value == "generated") == is_generated, rule.code
        assert (rule.source is not None) == is_generated, rule.code


def test_questionnaire_matches_vocabulary(knowledge: KnowledgeSnapshot) -> None:
    assert check_fact_types(knowledge.questionnaire) == []
    ids = [q.id for q in knowledge.questionnaire.questions]
    assert len(ids) == len(set(ids))


def test_tables_cover_catalog(real_catalog: CatalogSnapshot) -> None:
    not_active = {
        e.sku: e.status for e in real_catalog.entries if e.status is not ComponentStatus.ACTIVE
    }
    assert not_active == {}, "справочники не знают сокетов/чипсетов/форм-факторов каталога"


def test_approved_tables_size(knowledge: KnowledgeSnapshot) -> None:
    tables = knowledge.tables
    assert len(tables.games) == 50
    assert len(tables.applications) == 20
    assert sum(game.kind == "esports" for game in tables.games) == 13
