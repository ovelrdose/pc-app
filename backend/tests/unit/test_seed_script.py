"""Скрипт seed: проверка файлов без записи в БД."""

import shutil
from pathlib import Path

from scripts.seed import KNOWLEDGE_DIR, main


async def test_dry_run_on_real_catalog_succeeds() -> None:
    assert await main(["--dry-run", "--knowledge-dir", str(KNOWLEDGE_DIR)]) == 0


async def test_errors_abort_before_database(tmp_path: Path) -> None:
    shutil.copytree(KNOWLEDGE_DIR / "tables", tmp_path / "tables")
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "case_fan.csv").write_text(
        "sku,brand,model,size_mm,price_rub\nFAN-X,Arctic,P12,121,900\n", encoding="utf-8"
    )
    # Без --dry-run: при ошибках скрипт обязан выйти до подключения к БД.
    assert await main(["--knowledge-dir", str(tmp_path)]) == 1


async def test_missing_tables_abort(tmp_path: Path) -> None:
    (tmp_path / "catalog").mkdir()
    assert await main(["--dry-run", "--knowledge-dir", str(tmp_path)]) == 1
