"""Скрипты базы знаний: генерация и валидация на реальных файлах и на копии."""

import shutil
from pathlib import Path

from scripts.generate_rules import KNOWLEDGE_DIR
from scripts.generate_rules import main as generate_main
from scripts.validate_kb import main as validate_main


def test_generated_rules_up_to_date_check() -> None:
    assert generate_main(["--check"]) == 0


def test_validate_real_knowledge_strict() -> None:
    assert validate_main(["--strict"]) == 0


def test_stale_generated_and_broken_rules_detected(tmp_path: Path) -> None:
    copy = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, copy, ignore=shutil.ignore_patterns("catalog", "golden"))
    stale = copy / "rules" / "generated" / "GEN-FF.yaml"
    stale.write_text(stale.read_text(encoding="utf-8") + "\n# правка руками\n", encoding="utf-8")
    assert generate_main(["--check", "--knowledge-dir", str(copy)]) == 1
    assert validate_main(["--knowledge-dir", str(copy)]) == 1
    assert generate_main(["--knowledge-dir", str(copy)]) == 0
    assert validate_main(["--knowledge-dir", str(copy)]) == 0

    broken = copy / "rules" / "manual" / "PRF.yaml"
    broken.write_text("- code: PRF-001\n  name: без полей\n", encoding="utf-8")
    assert validate_main(["--knowledge-dir", str(copy)]) == 1
