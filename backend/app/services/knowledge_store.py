"""База знаний в БД (архитектура §6.1): импорт из файлов, публикация снимков, статусы каталога."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.expert.catalog import CatalogSnapshot
from app.expert.dsl.compiler import KnowledgeCompileError
from app.expert.dsl.schema import Rule
from app.expert.frames import ComponentStatus, KnownSlotValues, compute_status
from app.expert.golden import GoldenCase, check_case
from app.expert.validation import validate_knowledge
from app.models import KbSnapshotRow, RuleRow
from app.repositories.components import ComponentRepository, row_to_frame
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.meta import MetaRepository
from app.services.knowledge_files import (
    TABLE_FILES,
    KnowledgeFileError,
    load_questionnaire,
    load_rules,
    load_tables,
)
from app.services.snapshot_cache import snapshot_from_row

logger = structlog.get_logger(__name__)

QUESTIONNAIRE = "questionnaire"


class KnowledgeValidationError(ConflictError):
    """База знаний не прошла проверки и не может быть опубликована."""

    code = "kb-invalid"
    title = "База знаний не прошла проверку"


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Итог импорта файлов знаний в рабочую копию."""

    created: int
    updated: int
    unchanged: int
    tables_changed: tuple[str, ...]
    retired: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PublishReport:
    """Итог публикации."""

    snapshot_id: int
    version: int
    created: bool
    rules: int
    warnings: int
    golden_cases: int
    statuses_changed: int


def rule_body(rule: Rule) -> dict[str, Any]:
    """Правило в виде JSON для хранения (как в YAML-файлах)."""
    data: dict[str, Any] = rule.model_dump(mode="json", by_alias=True, exclude_none=True)
    return data


async def import_files(session: AsyncSession, knowledge_dir: Path) -> ImportReport:
    """Загружает правила, справочники и анкету из `knowledge/` в рабочую копию.

    Новые правила добавляются, изменившиеся получают новую ревизию с записью в историю;
    правила из реестра выведенных (`rules/retired.yaml`) выключаются с записью в историю;
    остальные правила, которых нет в файлах (например, созданные в админке), не трогаются.
    """
    loaded = load_rules(knowledge_dir / "rules")
    if loaded.errors:
        raise KnowledgeFileError("правила не проходят схему:\n" + "\n".join(loaded.errors))
    tables = load_tables(knowledge_dir / "tables")
    questionnaire = load_questionnaire(knowledge_dir / "questionnaire.yaml")

    repo = KnowledgeRepository(session)
    existing = {row.code: row for row in await repo.rules()}
    created = updated = unchanged = 0
    history: list[tuple[RuleRow, str]] = []
    for rule in loaded.rules:
        body = rule_body(rule)
        row = existing.get(rule.code)
        if row is None:
            row = _new_row(rule, body)
            repo.add_rule(row)
            history.append((row, "seed"))
            created += 1
        elif row.body != body:
            _apply(row, rule, body)
            row.revision += 1
            history.append((row, "import"))
            updated += 1
        else:
            unchanged += 1
    retired: list[str] = []
    for item in loaded.retired:
        row = existing.get(item.code)
        if row is not None and row.enabled:
            row.enabled = False
            row.body = {**row.body, "enabled": False}
            row.revision += 1
            history.append((row, "retire"))
            retired.append(item.code)
    await session.flush()  # история ссылается на правила: сначала сами правила
    for row, change_type in history:
        repo.add_revision(row, change_type)

    table_data = tables.model_dump(mode="json", by_alias=True)
    changed = [name for name in TABLE_FILES if await repo.upsert_table(name, table_data[name])]
    if await repo.upsert_table(QUESTIONNAIRE, questionnaire.model_dump(mode="json")):
        changed.append(QUESTIONNAIRE)
    await session.flush()
    logger.info(
        "kb_imported", created=created, updated=updated, unchanged=unchanged, retired=retired
    )
    return ImportReport(created, updated, unchanged, tuple(changed), tuple(retired))


def _new_row(rule: Rule, body: dict[str, Any]) -> RuleRow:
    row = RuleRow(code=rule.code, revision=1)
    _apply(row, rule, body)
    return row


def _apply(row: RuleRow, rule: Rule, body: dict[str, Any]) -> None:
    row.kind = rule.kind.value
    row.group = rule.group
    row.name = rule.name
    row.priority = rule.priority
    row.cf = rule.cf
    row.enabled = rule.enabled
    row.origin = rule.origin.value
    row.source = rule.source
    row.body = body
    row.explain = rule.explain


def _checksum(rules: list[dict[str, Any]], tables: dict[str, Any], questionnaire: Any) -> str:  # noqa: ANN401
    payload = json.dumps(
        {"rules": rules, "tables": tables, "questionnaire": questionnaire},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def recompute_statuses(session: AsyncSession, known: KnownSlotValues) -> int:
    """Пересчитывает статусы каталога по справочникам опубликованной БЗ (архитектура §17)."""
    changed = 0
    for row in await ComponentRepository(session).all():
        if row.status is ComponentStatus.INACTIVE:
            continue
        status = compute_status(row_to_frame(row), known=known)
        issues = list(status.issues)
        if (row.status, row.status_issues) != (status.status, issues):
            row.status, row.status_issues = status.status, issues
            changed += 1
    if changed:
        await session.flush()
        await MetaRepository(session).bump_catalog_revision()
    return changed


async def publish(
    session: AsyncSession,
    *,
    comment: str | None = None,
    golden: list[GoldenCase] | None = None,
    catalog: CatalogSnapshot | None = None,
) -> PublishReport:
    """Проверяет рабочую копию и публикует её неизменяемым снимком.

    Проверки: компиляция, статические проверки (§6.2), golden cases (если переданы вместе с
    каталогом). Если содержимое совпадает с последним снимком, новый не создаётся.
    """
    repo = KnowledgeRepository(session)
    rows = [row for row in await repo.rules() if row.enabled]
    rules = [row.body for row in rows]
    stored = await repo.tables()
    tables = {name: stored[name] for name in TABLE_FILES if name in stored}
    questionnaire = stored.get(QUESTIONNAIRE)
    try:
        snapshot = snapshot_from_row("draft", rules, tables, questionnaire)
    except (KnowledgeCompileError, ValueError) as exc:
        raise KnowledgeValidationError(str(exc)) from exc
    report = validate_knowledge(list(snapshot.rules))
    if report.errors:
        raise KnowledgeValidationError(
            f"ошибок: {len(report.errors)}", findings=[str(f) for f in report.errors]
        )
    golden = golden or []
    if golden and catalog is not None:
        failures = {
            case.id: problems
            for case in golden
            if (problems := check_case(case, snapshot, catalog))
        }
        if failures:
            raise KnowledgeValidationError(
                f"не прошли эталонные кейсы: {', '.join(sorted(failures))}", golden=failures
            )

    checksum = _checksum(rules, tables, questionnaire)
    latest = await repo.latest_snapshot()
    statuses = await recompute_statuses(session, snapshot.known_slot_values)
    if latest is not None and latest.checksum == checksum:
        return PublishReport(
            latest.id, latest.version, False, len(rules), len(report.warnings), 0, statuses
        )
    row = KbSnapshotRow(
        version=await repo.next_version(),
        rules=rules,
        tables=tables,
        questionnaire=questionnaire,
        checksum=checksum,
        validation_report={
            "warnings": [str(f) for f in report.warnings],
            "golden": [case.id for case in golden] if catalog is not None else [],
        },
        comment=comment,
    )
    repo.add_snapshot(row)
    await session.flush()
    logger.info("kb_published", version=row.version, rules=len(rules), statuses=statuses)
    golden_count = len(golden) if catalog is not None else 0
    return PublishReport(
        row.id, row.version, True, len(rules), len(report.warnings), golden_count, statuses
    )
