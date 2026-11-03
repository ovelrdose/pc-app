"""Golden cases из knowledge/golden/*.yaml (архитектура §6.3)."""

import pytest
import yaml

from app.expert.catalog import CatalogSnapshot
from app.expert.golden import GoldenCase, check_case
from app.expert.knowledge import KnowledgeSnapshot
from tests.kb.conftest import KNOWLEDGE_DIR


def load_cases() -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for path in sorted((KNOWLEDGE_DIR / "golden").glob("*.yaml")):
        cases += [GoldenCase.model_validate(item) for item in yaml.safe_load(path.read_text())]
    return cases


CASES = load_cases()


def test_case_ids_are_unique() -> None:
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 15


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_golden_case(
    case: GoldenCase, knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    problems = check_case(case, knowledge, real_catalog)
    assert problems == [], f"{case.id} «{case.title}»:\n" + "\n".join(problems)
