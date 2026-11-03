from pathlib import Path

import pytest

from app.services.knowledge_files import KnowledgeFileError, load_retired, load_rules

RULE = """- code: REQ-901
  name: Тестовое правило
  kind: inference
  group: requirements
  priority: 600
  cf: 0.6
  when: { fact: user.budget, op: exists }
  then: [{ action: assert, fact: req.ram_min_gb, value: 16 }]
  explain: Тест.
"""


def make_rules(tmp_path: Path, retired: str | None) -> Path:
    (tmp_path / "manual").mkdir()
    (tmp_path / "generated").mkdir()
    (tmp_path / "manual" / "REQ.yaml").write_text(RULE, encoding="utf-8")
    if retired is not None:
        (tmp_path / "retired.yaml").write_text(retired, encoding="utf-8")
    return tmp_path


def test_without_registry_nothing_is_retired(tmp_path: Path) -> None:
    result = load_rules(make_rules(tmp_path, None))
    assert (result.errors, result.retired, [r.code for r in result.rules]) == ([], [], ["REQ-901"])


def test_retired_code_cannot_be_reused(tmp_path: Path) -> None:
    registry = '- { code: REQ-901, retired_at: 2026-10-30, reason: "заменено" }\n'
    result = load_rules(make_rules(tmp_path, registry))
    assert [r.code for r in result.retired] == ["REQ-901"]
    assert result.errors == ["REQ-901: код выведен из базы (retired.yaml) и не переиспользуется"]


@pytest.mark.parametrize(
    ("registry", "fragment"),
    [
        ("code: REQ-901\n", "ожидается список"),
        ('- { code: req-1, retired_at: 2026-10-30, reason: "x" }\n', "не проходит схему"),
        (
            '- { code: REQ-001, retired_at: 2026-10-30, reason: "x" }\n'
            '- { code: REQ-001, retired_at: 2026-10-30, reason: "y" }\n',
            "повторяются REQ-001",
        ),
    ],
)
def test_registry_errors(tmp_path: Path, registry: str, fragment: str) -> None:
    (tmp_path / "retired.yaml").write_text(registry, encoding="utf-8")
    with pytest.raises(KnowledgeFileError, match=fragment):
        load_retired(tmp_path)
