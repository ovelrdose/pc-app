"""Общие фикстуры проверок базы знаний: реальные файлы knowledge/."""

from pathlib import Path

import pytest

from app.expert.catalog import CatalogEntry, CatalogSnapshot
from app.expert.frames import compute_status
from app.expert.knowledge import KnowledgeSnapshot
from app.services.catalog_csv import read_catalog_dir
from app.services.knowledge_files import load_knowledge

KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "knowledge"


@pytest.fixture(scope="session")
def knowledge() -> KnowledgeSnapshot:
    return load_knowledge(KNOWLEDGE_DIR)


@pytest.fixture(scope="session")
def real_catalog(knowledge: KnowledgeSnapshot) -> CatalogSnapshot:
    records = read_catalog_dir(KNOWLEDGE_DIR / "catalog").records
    known = knowledge.known_slot_values
    return CatalogSnapshot.build(
        1, (CatalogEntry(r.frame, compute_status(r.frame, known=known).status) for r in records)
    )
