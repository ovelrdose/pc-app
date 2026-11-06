"""База знаний в БД (архитектура §6.1): импорт из файлов, валидация и публикация снимков, статусы.

Сбор черновика и проверки (компиляция, статические проверки §6.2, golden cases) общие для
stateless-валидации (`validate_draft`) и публикации (`publish`): оба собирают черновик через
`_draft` и прогоняют `_check_bundle`. Golden cases живут в `reference_tables['golden']`
(ADR 0010 п.2): их заливает `import_files` (seed), валидация и публикация читают из БД.

Долгий CPU-прогон `_check_bundle` (статические проверки + эталонные кейсы) выполняется
в worker-потоке (`asyncio.to_thread`), чтобы не блокировать event loop. Перед прогоном
фаза чтения фиксируется (`session.commit`): транзакция пустая, а соединение возвращается
в пул и не занято, пока поток считает. Запись (снимок, статусы) идёт новой транзакцией
после прогона; завершающий commit делает вызывающая сторона (зависимость запроса, seed).
"""

import hashlib
import json
import uuid
from asyncio import to_thread
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.expert.catalog import CatalogSnapshot
from app.expert.dsl.compiler import KnowledgeCompileError
from app.expert.dsl.schema import Rule
from app.expert.frames import ComponentStatus, KnownSlotValues, compute_status
from app.expert.golden import GoldenCase, cases_from_json, cases_to_json, check_case
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.validation import validate_knowledge
from app.models import KbSnapshotRow, RuleRow
from app.repositories.components import ComponentRepository, row_to_frame
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.meta import MetaRepository
from app.services.knowledge_files import (
    TABLE_FILES,
    KnowledgeFileError,
    load_golden,
    load_questionnaire,
    load_rules,
    load_tables,
)
from app.services.snapshot_cache import snapshot_from_row

logger = structlog.get_logger(__name__)

QUESTIONNAIRE = "questionnaire"
GOLDEN = "golden"


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


@dataclass(frozen=True, slots=True)
class GoldenReport:
    """Итог прогона эталонных кейсов."""

    passed: int
    failed: int
    failures: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class DraftReport:
    """Итог проверок черновика (stateless-валидация или публикация)."""

    rules_total: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    golden: GoldenReport
    checksum: str
    matches_latest: bool


@dataclass(frozen=True, slots=True)
class DraftStatus:
    """Лёгкий статус черновика для панели админки: без компиляции и эталонных кейсов."""

    checksum: str
    matches_latest: bool
    rules_total: int


@dataclass(frozen=True, slots=True)
class _Draft:
    """Собранный черновик: включённые правила, скомпилированный снимок и контрольная сумма."""

    rules: list[dict[str, Any]]
    snapshot: KnowledgeSnapshot
    tables: dict[str, Any]
    questionnaire: Any
    golden: list[GoldenCase]
    checksum: str


def rule_body(rule: Rule) -> dict[str, Any]:
    """Правило в виде JSON для хранения (как в YAML-файлах)."""
    data: dict[str, Any] = rule.model_dump(mode="json", by_alias=True, exclude_none=True)
    return data


async def import_files(session: AsyncSession, knowledge_dir: Path) -> ImportReport:
    """Загружает правила, справочники, анкету и golden cases из `knowledge/` в рабочую копию.

    Новые правила добавляются, изменившиеся получают новую ревизию с записью в историю;
    правила из реестра выведенных (`rules/retired.yaml`) выключаются с записью в историю;
    остальные правила, которых нет в файлах (например, созданные в админке), не трогаются.
    """
    loaded = load_rules(knowledge_dir / "rules")
    if loaded.errors:
        raise KnowledgeFileError("правила не проходят схему:\n" + "\n".join(loaded.errors))
    tables = load_tables(knowledge_dir / "tables")
    questionnaire = load_questionnaire(knowledge_dir / "questionnaire.yaml")
    cases = load_golden(knowledge_dir / "golden")

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
    if await repo.upsert_table(GOLDEN, cases_to_json(cases)):
        changed.append(GOLDEN)
    await session.flush()
    logger.info(
        "kb_imported", created=created, updated=updated, unchanged=unchanged, retired=retired
    )
    return ImportReport(created, updated, unchanged, tuple(changed), tuple(retired))


def _new_row(rule: Rule, body: dict[str, Any]) -> RuleRow:
    row = RuleRow(code=rule.code, revision=1)
    _apply(row, rule, body)
    return row


def build_rule_row(rule: Rule, *, author_id: uuid.UUID | None = None) -> RuleRow:
    """Новая строка рабочей копии из DSL-правила (ревизия 1); автор — для истории."""
    row = _new_row(rule, rule_body(rule))
    row.updated_by = author_id
    return row


def apply_rule_row(row: RuleRow, rule: Rule, *, author_id: uuid.UUID | None = None) -> None:
    """Записывает DSL-правило в строку рабочей копии; автор — для истории."""
    _apply(row, rule, rule_body(rule))
    if author_id is not None:
        row.updated_by = author_id


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


def _stored_golden(stored: dict[str, Any]) -> list[GoldenCase]:
    """Golden cases из рабочей копии; битые данные — `KnowledgeValidationError` (409)."""
    raw = stored.get(GOLDEN)
    if not raw:
        return []
    try:
        return cases_from_json(raw)
    except ValueError as exc:
        raise KnowledgeValidationError(str(exc)) from exc


async def _draft(session: AsyncSession) -> _Draft:
    """Собирает черновик рабочей копии и компилирует его; ошибки компиляции — 409."""
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
    golden = _stored_golden(stored)
    return _Draft(
        rules, snapshot, tables, questionnaire, golden, _checksum(rules, tables, questionnaire)
    )


def _check_bundle(
    draft: _Draft,
    *,
    golden: list[GoldenCase],
    catalog: CatalogSnapshot | None,
    matches_latest: bool,
) -> DraftReport:
    """Статические проверки §6.2 и golden cases собранного черновика (без записи в БД)."""
    report = validate_knowledge(list(draft.snapshot.rules))
    failures: dict[str, list[str]] = {}
    checked = 0
    if golden and catalog is not None:
        checked = len(golden)
        failures = {
            case.id: problems
            for case in golden
            if (problems := check_case(case, draft.snapshot, catalog))
        }
    golden_report = GoldenReport(checked - len(failures), len(failures), failures)
    return DraftReport(
        rules_total=len(draft.snapshot.rules),
        errors=tuple(str(finding) for finding in report.errors),
        warnings=tuple(str(finding) for finding in report.warnings),
        golden=golden_report,
        checksum=draft.checksum,
        matches_latest=matches_latest,
    )


async def validate_draft(
    session: AsyncSession,
    *,
    golden: list[GoldenCase] | None = None,
    catalog: CatalogSnapshot | None = None,
) -> DraftReport:
    """Stateless-проверка черновика: компиляция, §6.2, golden cases; ничего не записывает.

    `golden=None` — эталоны из рабочей копии (`reference_tables['golden']`).
    Проверки выполняются в worker-потоке; перед ними фаза чтения фиксируется, чтобы
    соединение с БД до конца прогона оставалось в пуле.
    """
    draft = await _draft(session)
    latest = await KnowledgeRepository(session).latest_snapshot_ref()
    # Чтение закончено: транзакция пустая, commit возвращает соединение в пул до прогона.
    await session.commit()
    return await to_thread(
        _check_bundle,
        draft,
        golden=draft.golden if golden is None else golden,
        catalog=catalog,
        matches_latest=latest is not None and latest[2] == draft.checksum,
    )


async def draft_status(session: AsyncSession) -> DraftStatus:
    """Лёгкий статус черновика: контрольная сумма, совпадение с последним снимком, число правил.

    Только чтение из БД: без компиляции, статических проверок и эталонных кейсов,
    поэтому отвечает сразу, в отличие от полной проверки `validate_draft`.
    """
    repo = KnowledgeRepository(session)
    rows = await repo.rules()
    rules = [row.body for row in rows if row.enabled]
    stored = await repo.tables()
    tables = {name: stored[name] for name in TABLE_FILES if name in stored}
    questionnaire = stored.get(QUESTIONNAIRE)
    checksum = _checksum(rules, tables, questionnaire)
    latest = await repo.latest_snapshot_ref()
    return DraftStatus(
        checksum=checksum,
        matches_latest=latest is not None and latest[2] == checksum,
        rules_total=len(rules),
    )


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
    published_by: uuid.UUID | None = None,
) -> PublishReport:
    """Проверяет рабочую копию и публикует её неизменяемым снимком.

    Проверки: компиляция, статические проверки (§6.2), golden cases (ADR 0010 п.2: по умолчанию
    эталоны читаются из рабочей копии БД, `golden` — явное переопределение). При любой ошибке
    бросает `KnowledgeValidationError` и снимок не создаётся. Если содержимое совпадает
    с последним снимком, новый не создаётся.

    Проверки выполняются в worker-потоке: фаза чтения фиксируется до прогона и соединение
    с БД остаётся в пуле; запись снимка и статусов идёт новой транзакцией после прогона,
    завершающий commit — у вызывающей стороны.
    """
    draft = await _draft(session)
    checked = draft.golden if golden is None else golden
    latest = await KnowledgeRepository(session).latest_snapshot_ref()
    latest_id, latest_version, latest_checksum = latest or (0, 0, "")
    # Чтение закончено: транзакция пустая, commit возвращает соединение в пул до прогона.
    await session.commit()
    result = await to_thread(
        _check_bundle,
        draft,
        golden=checked,
        catalog=catalog,
        matches_latest=bool(latest) and latest_checksum == draft.checksum,
    )
    if result.errors:
        raise KnowledgeValidationError(
            f"ошибок: {len(result.errors)}", findings=list(result.errors)
        )
    if result.golden.failed:
        raise KnowledgeValidationError(
            f"не прошли эталонные кейсы: {', '.join(sorted(result.golden.failures))}",
            golden=result.golden.failures,
        )

    repo = KnowledgeRepository(session)
    statuses = await recompute_statuses(session, draft.snapshot.known_slot_values)
    if latest and latest_checksum == draft.checksum:
        return PublishReport(
            latest_id, latest_version, False, result.rules_total, len(result.warnings), 0, statuses
        )
    row = KbSnapshotRow(
        version=await repo.next_version(),
        rules=draft.rules,
        tables=draft.tables,
        questionnaire=draft.questionnaire,
        checksum=draft.checksum,
        validation_report={
            "warnings": list(result.warnings),
            "golden": [case.id for case in checked] if catalog is not None else [],
        },
        comment=comment,
        published_by=published_by,
    )
    repo.add_snapshot(row)
    await session.flush()
    logger.info("kb_published", version=row.version, rules=result.rules_total, statuses=statuses)
    golden_count = len(checked) if catalog is not None else 0
    return PublishReport(
        row.id, row.version, True, result.rules_total, len(result.warnings), golden_count, statuses
    )


async def republish(
    session: AsyncSession,
    *,
    snapshot_id: int,
    comment: str | None = None,
    catalog: CatalogSnapshot | None = None,
    published_by: uuid.UUID | None = None,
) -> PublishReport:
    """Повторная публикация содержимого ранее опубликованного снимка новой версией (§6.1, откат).

    Черновик рабочей копии не меняется. Снимок проходит те же проверки (компиляция, §6.2,
    golden cases из рабочей копии на текущем каталоге); checksum совпадает со старым — это норма.
    Проверки выполняются в worker-потоке: фаза чтения фиксируется до прогона, запись нового
    снимка и статусов идёт новой транзакцией после прогона.
    """
    repo = KnowledgeRepository(session)
    source = await repo.snapshot(snapshot_id)
    if source is None:
        raise NotFoundError(f"Снимок базы знаний {snapshot_id} не найден", snapshot_id=snapshot_id)
    source_version = source.version
    try:
        snapshot = snapshot_from_row(
            f"republish v{source_version}", source.rules, source.tables, source.questionnaire
        )
    except (KnowledgeCompileError, ValueError) as exc:
        raise KnowledgeValidationError(str(exc)) from exc
    stored = await repo.tables()
    draft = _Draft(
        source.rules,
        snapshot,
        source.tables,
        source.questionnaire,
        _stored_golden(stored),
        source.checksum,
    )
    # Чтение закончено: транзакция пустая, commit возвращает соединение в пул до прогона.
    await session.commit()
    result = await to_thread(
        _check_bundle, draft, golden=draft.golden, catalog=catalog, matches_latest=False
    )
    if result.errors:
        raise KnowledgeValidationError(
            f"ошибок: {len(result.errors)}", findings=list(result.errors)
        )
    if result.golden.failed:
        raise KnowledgeValidationError(
            f"не прошли эталонные кейсы: {', '.join(sorted(result.golden.failures))}",
            golden=result.golden.failures,
        )
    statuses = await recompute_statuses(session, snapshot.known_slot_values)
    row = KbSnapshotRow(
        version=await repo.next_version(),
        rules=source.rules,
        tables=source.tables,
        questionnaire=source.questionnaire,
        checksum=source.checksum,
        validation_report={
            "warnings": list(result.warnings),
            "golden": [case.id for case in draft.golden] if catalog is not None else [],
        },
        comment=comment or f"повторная публикация версии {source_version}",
        published_by=published_by,
    )
    repo.add_snapshot(row)
    await session.flush()
    logger.info(
        "kb_republished",
        version=row.version,
        source_version=source_version,
        rules=result.rules_total,
    )
    golden_count = len(draft.golden) if catalog is not None else 0
    return PublishReport(
        row.id, row.version, True, result.rules_total, len(result.warnings), golden_count, statuses
    )
