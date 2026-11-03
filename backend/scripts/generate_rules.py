"""Генерация табличных правил: `uv run python -m scripts.generate_rules [--check]`.

Читает `knowledge/tables/*.yaml` и пишет `knowledge/rules/generated/GEN-*.yaml`.
С `--check` ничего не пишет и завершается с ошибкой, если файлы устарели.
"""

import argparse
import sys
from pathlib import Path

import structlog

from app.core.logging import configure_logging
from app.expert.dsl.schema import Rule
from app.expert.generation import GENERATED_FILES, generate_rules
from app.services.knowledge_files import dump_rules, load_tables

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"
HEADER = (
    "# СГЕНЕРИРОВАНО scripts/generate_rules.py из knowledge/tables/. НЕ ПРАВИТЬ РУКАМИ:\n"
    "# правьте справочник и запустите генератор заново.\n"
)

logger = structlog.get_logger("generate_rules")


def render_files(knowledge_dir: Path) -> dict[str, str]:
    """Содержимое файлов сгенерированных правил: имя файла → текст."""
    rules = generate_rules(load_tables(knowledge_dir / "tables"))
    by_file: dict[str, list[Rule]] = {name: [] for name in GENERATED_FILES.values()}
    for rule in rules:
        by_file[GENERATED_FILES[rule.group]].append(rule)
    return {f"{name}.yaml": HEADER + dump_rules(items) for name, items in by_file.items()}


def main(argv: list[str] | None = None) -> int:
    """Точка входа: 0 — успех (или файлы актуальны), 1 — файлы устарели (`--check`)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="только проверить актуальность")
    parser.add_argument("--knowledge-dir", type=Path, default=KNOWLEDGE_DIR)
    args = parser.parse_args(argv)
    configure_logging()

    target = args.knowledge_dir / "rules" / "generated"
    files = render_files(args.knowledge_dir)
    stale = sorted(
        name
        for name, text in files.items()
        if not (target / name).is_file() or (target / name).read_text(encoding="utf-8") != text
    )
    if args.check:
        if stale:
            logger.error("generated_rules_stale", files=stale)
            return 1
        logger.info("generated_rules_up_to_date")
        return 0
    target.mkdir(parents=True, exist_ok=True)
    for name in stale:
        (target / name).write_text(files[name], encoding="utf-8")
    counts = {
        name: sum(line.startswith("- code:") for line in text.splitlines())
        for name, text in files.items()
    }
    logger.info("generated_rules_written", changed=stale, rules=counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
