"""Проверка базы знаний: `uv run python -m scripts.validate_kb [--strict]`.

Читает правила из `knowledge/rules/`, справочники из `knowledge/tables/`, проверяет актуальность
сгенерированных правил и запускает статические проверки. `--strict` считает ошибкой и
предупреждения.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import structlog

from app.core.logging import configure_logging
from app.expert.validation import validate_knowledge
from app.services.knowledge_files import KnowledgeFileError, load_rules, load_tables
from scripts.generate_rules import render_files

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

logger = structlog.get_logger("validate_kb")


def main(argv: list[str] | None = None) -> int:
    """Точка входа: 0 — база знаний чистая, 1 — есть ошибки."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="предупреждения тоже ошибки")
    parser.add_argument("--knowledge-dir", type=Path, default=KNOWLEDGE_DIR)
    args = parser.parse_args(argv)
    configure_logging()

    try:
        load_tables(args.knowledge_dir / "tables")
        expected = render_files(args.knowledge_dir)
    except KnowledgeFileError as exc:
        logger.error("tables_invalid", error=str(exc))
        return 1
    generated_dir = args.knowledge_dir / "rules" / "generated"
    stale = [
        name
        for name, text in expected.items()
        if not (generated_dir / name).is_file()
        or (generated_dir / name).read_text(encoding="utf-8") != text
    ]
    loaded = load_rules(args.knowledge_dir / "rules")
    for error in loaded.errors:
        logger.error("rule_invalid", error=error)
    report = validate_knowledge(loaded.rules)
    for finding in report.findings:
        log = logger.error if finding.severity.value == "error" else logger.warning
        log("kb_finding", finding=str(finding))
    if stale:
        logger.error("generated_rules_stale", files=stale, hint="запустите scripts.generate_rules")

    groups = Counter(
        rule.code.rsplit("-", 1)[0]
        if rule.code[:3] != "GEN"
        else "-".join(rule.code.split("-")[:2])
        for rule in loaded.rules
    )
    logger.info(
        "kb_summary",
        rules=report.rules_total,
        errors=len(report.errors) + len(loaded.errors) + len(stale),
        warnings=len(report.warnings),
        groups=dict(sorted(groups.items())),
    )
    failed = bool(report.errors or loaded.errors or stale)
    if args.strict and report.warnings:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
