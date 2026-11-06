"""Админка базы знаний (ADR 0010 п.2–7): правила, валидация, публикация, снимки, экспорт,
справочники, регенерация. Проверки черновика общие с публикацией — в `knowledge_store`.
"""

import io
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
import yaml
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.expert.certainty import clamp, conclusion, is_established
from app.expert.dsl.compiler import (
    CompiledAssert,
    CompiledMessageAction,
    CompiledRetract,
    CompiledRule,
    compile_rule,
    fact_resolver,
)
from app.expert.dsl.expr import ExprEvalError, ExprSyntaxError
from app.expert.dsl.schema import MANUAL_PREFIXES, Rule, RuleKind, RuleOrigin
from app.expert.facts import FactSource, WorkingMemory
from app.expert.generation import generate_rules
from app.expert.golden import cases_from_json, cases_to_json
from app.expert.questionnaire import Questionnaire
from app.expert.tables import KnowledgeTables
from app.models import RuleRevisionRow, RuleRow, UserRow
from app.repositories.knowledge import KnowledgeRepository
from app.services.knowledge_files import TABLE_FILES, dump_rules
from app.services.knowledge_store import (
    GOLDEN,
    QUESTIONNAIRE,
    DraftReport,
    DraftStatus,
    GoldenReport,
    KnowledgeValidationError,
    PublishReport,
    apply_rule_row,
    build_rule_row,
    rule_body,
)
from app.services.knowledge_store import (
    draft_status as store_status,
)
from app.services.knowledge_store import (
    publish as store_publish,
)
from app.services.knowledge_store import (
    republish as store_republish,
)
from app.services.knowledge_store import (
    validate_draft as store_validate,
)
from app.services.snapshot_cache import SnapshotCache

logger = structlog.get_logger(__name__)

_MANUAL_CODE = re.compile(r"^([A-Z]{3})-(\d{3})$")

OVERRIDE_WARNING = (
    "Правило было сгенерировано из справочника; ручная правка переводит его в origin: manual "
    "(override) — регенерация его больше не перезаписывает."
)


class RuleCodeInvalidError(DomainError):
    """Код нового правила не по формату PREFIX-NNN или префикс не из словаря (§6.5)."""

    status = 422
    code = "rule-code-invalid"
    title = "Недопустимый код правила"


class RuleExistsError(ConflictError):
    """Код правила занят; коды не переиспользуются."""

    code = "rule-exists"
    title = "Код правила занят"


class RuleBrokenError(ConflictError):
    """Сохранённое правило не проходит схему DSL (повреждена рабочая копия)."""

    code = "rule-broken"
    title = "Правило повреждено"


class GoalRuleTestError(DomainError):
    """Изолированный прогон неприменим к goal-правилам (нужен обратный вывод со сборкой)."""

    status = 422
    code = "goal-rule-test-unsupported"
    title = "Goal-правила тестируются на сборке"


class RuleTestFactError(DomainError):
    """Входной факт теста правила некорректен (путь, cf, значение)."""

    status = 422
    code = "rule-test-fact-invalid"
    title = "Некорректный входной факт"


class ReferenceValidationError(DomainError):
    """Справочник, анкета или golden cases не проходят схему ядра."""

    status = 422
    code = "reference-invalid"
    title = "Справочник не проходит схему"


@dataclass(frozen=True, slots=True)
class RuleTestAction:
    """Одно действие сработавшего правила (для ответа теста)."""

    action: str
    fact: str | None = None
    value: Any = None
    message: str | None = None
    weight: float | None = None
    category: str | None = None
    target: str | None = None


@dataclass(frozen=True, slots=True)
class RuleTestFact:
    """Факт рабочей памяти после прогона."""

    path: str
    value: Any
    cf: float


@dataclass(frozen=True, slots=True)
class RuleTestResult:
    """Итог изолированного прямого вывода на заданных фактах (ADR 0010 п.4)."""

    matched: bool
    premise_cf: float | None
    actions: tuple[RuleTestAction, ...]
    facts_after: tuple[RuleTestFact, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegenerateReport:
    """Diff регенерации табличных правил (ADR 0010 п.5)."""

    dry_run: bool
    created: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]
    overrides: tuple[str, ...]


def _rule_out(row: RuleRow) -> dict[str, Any]:
    """Словарь RuleOut из строки рабочей копии (без предупреждения по умолчанию)."""
    return {
        "code": row.code,
        "kind": row.kind,
        "group": row.group,
        "name": row.name,
        "priority": row.priority,
        "cf": row.cf,
        "enabled": row.enabled,
        "origin": row.origin,
        "source": row.source,
        "explain": row.explain,
        "revision": row.revision,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at,
        "body": row.body,
    }


def _revision_out(row: RuleRevisionRow) -> dict[str, Any]:
    return {
        "revision": row.revision,
        "body": row.body,
        "change_type": row.change_type,
        "author_id": row.author_id,
        "created_at": row.created_at,
    }


class KnowledgeAdminService:
    """Сценарии инженера знаний: правила, публикация, снимки, справочники."""

    def __init__(self, session: AsyncSession, cache: SnapshotCache) -> None:
        self.session = session
        self.cache = cache
        self.repo = KnowledgeRepository(session)

    # --- Правила: чтение -------------------------------------------------------------------------

    async def list_rules(
        self,
        *,
        group: str | None,
        kind: RuleKind | None,
        origin: RuleOrigin | None,
        enabled: bool | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Страница правил рабочей копии по фильтрам админки."""
        rows, total = await self.repo.list_rules(
            group=group,
            kind=kind.value if kind is not None else None,
            origin=origin.value if origin is not None else None,
            enabled=enabled,
            search=search,
            limit=limit,
            offset=offset,
        )
        return [_rule_out(row) for row in rows], total

    async def rule_detail(self, code: str) -> dict[str, Any]:
        """Правило и история его ревизий, новые первыми."""
        row = await self._row_or_404(code)
        revisions = await self.repo.revisions(code)
        return {"rule": _rule_out(row), "revisions": [_revision_out(r) for r in revisions]}

    # --- Правила: изменения ----------------------------------------------------------------------

    async def create_rule(self, rule: Rule, *, author: UserRow) -> dict[str, Any]:
        """Создаёт ручное правило; код PREFIX-NNN уникален и не переиспользуется."""
        match = _MANUAL_CODE.fullmatch(rule.code)
        if rule.code.startswith("GEN-") or match is None or match.group(1) not in MANUAL_PREFIXES:
            known = ", ".join(sorted(MANUAL_PREFIXES))
            raise RuleCodeInvalidError(
                f"Код нового правила: PREFIX-NNN с префиксом из {known}; "
                "коды GEN-* создаёт только генератор"
            )
        if await self.repo.rule(rule.code) is not None:
            raise RuleExistsError(f"Правило {rule.code} уже есть; коды не переиспользуются")
        row = build_rule_row(rule, author_id=author.id)
        self.repo.add_rule(row)
        await self.session.flush()  # история ссылается на правило: сначала само правило
        self.repo.add_revision(row, "create")
        # вторая фиксация: дочитать server-default колонки до чтения строки в ответе
        await self.session.flush()
        logger.info("rule_created", code=rule.code, author_id=str(author.id))
        return _rule_out(row)

    async def replace_rule(self, code: str, rule: Rule, *, author: UserRow) -> dict[str, Any]:
        """Полная замена правила (новая ревизия); правка сгенерированного — override с
        предупреждением в ответе (ADR 0010 п.7)."""
        if rule.code != code:
            raise RuleCodeInvalidError(
                f"Код в теле ({rule.code}) должен совпадать с путём ({code})"
            )
        row = await self._row_or_404(code)
        warning: str | None = None
        effective = rule
        if row.origin == RuleOrigin.GENERATED.value and rule.origin is RuleOrigin.GENERATED:
            effective = rule.model_copy(update={"origin": RuleOrigin.MANUAL})
            warning = OVERRIDE_WARNING
        apply_rule_row(row, effective, author_id=author.id)
        row.revision += 1
        # onupdate-значение задаём явно: иначе колонка «истекает» после flush,
        # и чтение её в ответе тянет синхронный refresh (MissingGreenlet в async).
        row.updated_at = datetime.now(UTC)
        await self.session.flush()
        self.repo.add_revision(row, "update")
        # вторая фиксация: дочитать server-default колонки до чтения строки в ответе
        await self.session.flush()
        logger.info("rule_replaced", code=code, author_id=str(author.id), override=bool(warning))
        return {**_rule_out(row), "warning": warning}

    async def retire_rule(self, code: str, *, author: UserRow) -> dict[str, Any]:
        """Выводит правило из базы (enabled=false, новая ревизия); физически удалить нельзя —
        на правило ссылается история (FK). Повторный вызов для выведенного правила — без правок."""
        row = await self._row_or_404(code)
        if row.enabled:
            row.enabled = False
            row.body = {**row.body, "enabled": False}
            row.revision += 1
            row.updated_by = author.id
            row.updated_at = datetime.now(UTC)
            await self.session.flush()
            self.repo.add_revision(row, "retire")
            # вторая фиксация: дочитать server-default колонки до чтения строки в ответе
            await self.session.flush()
            logger.info("rule_retired", code=code, author_id=str(author.id))
        return _rule_out(row)

    async def test_rule(self, code: str, facts: Mapping[str, Any]) -> RuleTestResult:
        """Изолированный прямой вывод одного сохранённого правила на заданных фактах
        (ADR 0010 п.4); для goal-правил — 422. Некомпилируемое условие — 409 rule-broken."""
        row = await self._row_or_404(code)
        rule = self._stored_rule(row)
        if rule.kind is RuleKind.GOAL:
            raise GoalRuleTestError(
                "Изолированный прогон не поддерживается для goal-правил: подцели требуют "
                "обратного вывода со сборкой. Проверяйте через «Потянет ли?» на сборке."
            )
        try:
            compiled = compile_rule(rule)
        except ExprSyntaxError as exc:
            raise RuleBrokenError(
                f"Сохранённое правило {row.code} не компилируется: {exc}"
            ) from exc
        memory = self._memory_from_facts(facts)
        failures: list[str] = []
        try:
            match = compiled.condition.evaluate(memory)
        except ExprEvalError as exc:
            match, failures = None, [f"условие: {exc}"]
        matched = match is not None and is_established(match.cf)
        premise_cf = match.cf if match is not None else None
        actions: list[RuleTestAction] = []
        if matched and match is not None:
            cf = conclusion(rule.cf, match.cf)
            for action in compiled.actions:
                actions.extend(self._apply_action(rule, compiled, action, memory, cf, failures))
        facts_after = tuple(RuleTestFact(f.path, f.value, f.cf) for f in memory)
        return RuleTestResult(matched, premise_cf, tuple(actions), facts_after, tuple(failures))

    # --- Валидация и публикация ------------------------------------------------------------------

    async def validate(self) -> DraftReport:
        """Stateless-проверка черновика на текущем каталоге; отчёт, ничего не записывая."""
        catalog = (await self.cache.catalog(self.session)).snapshot
        try:
            return await store_validate(self.session, catalog=catalog)
        except KnowledgeValidationError as exc:
            detail = exc.detail or str(exc)
            return DraftReport(0, (detail,), (), GoldenReport(0, 0, {}), "", False)

    async def status(self) -> DraftStatus:
        """Лёгкий статус черновика для панели БЗ: только чтение, без компиляции и кейсов."""
        return await store_status(self.session)

    async def publish(self, *, comment: str | None, author: UserRow) -> PublishReport:
        """Публикует черновик теми же проверками, что и валидация.

        Любая ошибка — `KnowledgeValidationError` (409 `kb-invalid`), снимок не создаётся.
        """
        catalog = (await self.cache.catalog(self.session)).snapshot
        return await store_publish(
            self.session, comment=comment, catalog=catalog, published_by=author.id
        )

    # --- Снимки и экспорт ------------------------------------------------------------------------

    async def snapshots(self) -> list[dict[str, Any]]:
        """Все опубликованные снимки, новые первыми, с кратким отчётом."""
        result = []
        for row in await self.repo.snapshots():
            report = row.validation_report or {}
            result.append(
                {
                    "id": row.id,
                    "version": row.version,
                    "checksum": row.checksum,
                    "comment": row.comment,
                    "published_by": row.published_by,
                    "published_at": row.published_at,
                    "rules": len(row.rules),
                    "warnings": len(report.get("warnings", [])),
                    "golden": len(report.get("golden", [])),
                }
            )
        return result

    async def republish(self, *, snapshot_id: int, author: UserRow) -> PublishReport:
        """Повторная публикация содержимого старого снимка новой версией (откат, §6.1)."""
        catalog = (await self.cache.catalog(self.session)).snapshot
        return await store_republish(
            self.session, snapshot_id=snapshot_id, catalog=catalog, published_by=author.id
        )

    async def export_zip(self) -> bytes:
        """Zip с деревом как в `knowledge/`: правила, справочники, анкета, golden cases.

        Семантический round-trip: после замены файлов `knowledge/` повторный seed даёт
        created=0, updated=0 и не создаёт новый снимок (ADR 0010 п.6).
        """
        stored = await self.repo.tables()
        files: dict[str, str] = {}
        manual: dict[str, list[Rule]] = {}
        generated: dict[str, list[Rule]] = {}
        for row in await self.repo.rules():
            rule = Rule.model_validate(row.body)
            if rule.code.startswith("GEN-"):
                name = "-".join(rule.code.split("-")[:2])
                generated.setdefault(f"{name}.yaml", []).append(rule)
            else:
                manual.setdefault(f"{rule.code.split('-')[0]}.yaml", []).append(rule)
        for name, items in sorted(manual.items()):
            files[f"rules/manual/{name}"] = dump_rules(sorted(items, key=lambda r: r.code))
        for name, items in sorted(generated.items()):
            files[f"rules/generated/{name}"] = dump_rules(sorted(items, key=lambda r: r.code))
        tables_raw = {name: stored[name] for name in TABLE_FILES if name in stored}
        if tables_raw:
            tables = KnowledgeTables.model_validate(tables_raw)
            data = tables.model_dump(mode="json", by_alias=True)
            for name in TABLE_FILES:
                if name not in data:
                    continue
                payload: Any = data[name] if name == "form_factors" else {name: data[name]}
                files[f"tables/{name}.yaml"] = yaml.safe_dump(
                    payload, allow_unicode=True, sort_keys=False, width=100
                )
        if stored.get(QUESTIONNAIRE) is not None:
            questionnaire = Questionnaire.model_validate(stored[QUESTIONNAIRE])
            files["questionnaire.yaml"] = yaml.safe_dump(
                questionnaire.model_dump(mode="json"),
                allow_unicode=True,
                sort_keys=False,
                width=100,
            )
        raw_golden = stored.get(GOLDEN) or []
        files["golden/cases.yaml"] = yaml.safe_dump(
            cases_to_json(cases_from_json(raw_golden)),
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(files):
                archive.writestr(name, files[name])
        return buffer.getvalue()

    # --- Справочники и регенерация ---------------------------------------------------------------

    async def reference(self, name: str | None = None) -> dict[str, Any]:
        """Все справочники, анкета и golden cases (`name=None`) или один по имени."""
        stored = await self.repo.tables()
        if name is None:
            return stored
        if name not in stored:
            raise NotFoundError(f"Справочник {name} не найден", reference=name)
        return {"name": name, "data": stored[name]}

    async def replace_reference(self, name: str, data: Any) -> dict[str, Any]:  # noqa: ANN401
        """Заменяет справочник целиком с валидацией Pydantic-схемами ядра (ADR 0010 п.7)."""
        stored = await self.repo.tables()
        if name in TABLE_FILES:
            merged = {table: stored.get(table) for table in TABLE_FILES}
            merged[name] = data
            try:
                tables = KnowledgeTables.model_validate(merged)
            except ValidationError as exc:
                raise ReferenceValidationError(f"{name} не проходит схему:\n{exc}") from exc
            canonical = tables.model_dump(mode="json", by_alias=True)[name]
        elif name == QUESTIONNAIRE:
            try:
                questionnaire = Questionnaire.model_validate(data)
            except ValidationError as exc:
                raise ReferenceValidationError(f"questionnaire не проходит схему:\n{exc}") from exc
            canonical = questionnaire.model_dump(mode="json")
        elif name == GOLDEN:
            try:
                cases = cases_from_json(data)
            except ValueError as exc:
                raise ReferenceValidationError(str(exc)) from exc
            canonical = cases_to_json(cases)
        else:
            known = ", ".join((*TABLE_FILES, QUESTIONNAIRE, GOLDEN))
            raise NotFoundError(f"Справочник {name} не найден; доступны: {known}")
        await self.repo.upsert_table(name, canonical)
        await self.session.flush()
        logger.info("reference_replaced", name=name)
        return {"name": name, "data": canonical}

    async def regenerate(self, *, dry_run: bool, author: UserRow) -> RegenerateReport:
        """Перегенерация табличных правил в черновик из справочников рабочей копии (ADR 0010 п.5).

        Считается diff по кодам с `origin: generated` (created/updated/removed); правила-override
        (`origin: manual` с source из `tables/…`) не трогаются и перечисляются в отчёте.
        `dry_run=True` — только отчёт, без записи.
        """
        stored = await self.repo.tables()
        tables_raw = {name: stored[name] for name in TABLE_FILES if name in stored}
        try:
            tables = KnowledgeTables.model_validate(tables_raw)
        except ValidationError as exc:
            raise ReferenceValidationError(f"справочники не проходят схему:\n{exc}") from exc
        generated = {rule.code: rule for rule in generate_rules(tables)}
        existing = await self.repo.generated_rules()
        override_rows = [
            row
            for row in await self.repo.rules()
            if row.origin == RuleOrigin.MANUAL.value
            and row.source is not None
            and row.source.startswith("tables/")
        ]
        overrides = tuple(row.code for row in override_rows)
        # override занял код сгенерированного правила: генератор его не пересоздаёт
        override_codes = set(overrides)
        by_code = {row.code: row for row in existing}
        created = [
            rule
            for code, rule in generated.items()
            if code not in by_code and code not in override_codes
        ]
        updated = [
            (by_code[code], rule)
            for code, rule in generated.items()
            if code in by_code and by_code[code].body != rule_body(rule)
        ]
        removed = [row for code, row in by_code.items() if code not in generated]
        if not dry_run:
            history: list[tuple[RuleRow, str]] = []
            for rule in created:
                row = build_rule_row(rule, author_id=author.id)
                self.repo.add_rule(row)
                history.append((row, "regenerate"))
            for row, rule in updated:
                apply_rule_row(row, rule, author_id=author.id)
                row.revision += 1
                row.updated_at = datetime.now(UTC)
                history.append((row, "regenerate"))
            for row in removed:
                row.enabled = False
                row.body = {**row.body, "enabled": False}
                row.revision += 1
                row.updated_by = author.id
                row.updated_at = datetime.now(UTC)
                history.append((row, "retire"))
            await self.session.flush()
            for row, change_type in history:
                self.repo.add_revision(row, change_type)
            await self.session.flush()
            logger.info(
                "rules_regenerated",
                created=len(created),
                updated=len(updated),
                removed=len(removed),
                author_id=str(author.id),
            )
        return RegenerateReport(
            dry_run=dry_run,
            created=tuple(rule.code for rule in created),
            updated=tuple(rule.code for rule, _ in updated),
            removed=tuple(row.code for row in removed),
            overrides=overrides,
        )

    # --- Служебное -------------------------------------------------------------------------------

    async def _row_or_404(self, code: str) -> RuleRow:
        row = await self.repo.rule(code)
        if row is None:
            raise NotFoundError(f"Правило {code} не найдено", rule_code=code)
        return row

    @staticmethod
    def _stored_rule(row: RuleRow) -> Rule:
        try:
            return Rule.model_validate(row.body)
        except ValidationError as exc:
            raise RuleBrokenError(
                f"Сохранённое правило {row.code} не проходит схему: {exc}"
            ) from exc

    @staticmethod
    def _memory_from_facts(facts: Mapping[str, Any]) -> WorkingMemory:
        memory = WorkingMemory()
        for path, raw in facts.items():
            value, cf = _split_fact(path, raw)
            try:
                memory.set_fact(path, value, cf)
            except (TypeError, ValueError) as exc:
                raise RuleTestFactError(f"{path}: {exc}") from exc
        return memory

    @staticmethod
    def _apply_action(
        rule: Rule,
        compiled: CompiledRule,
        action: CompiledAssert | CompiledRetract | CompiledMessageAction,
        memory: WorkingMemory,
        cf: float,
        failures: list[str],
    ) -> list[RuleTestAction]:
        if isinstance(action, CompiledAssert):
            try:
                value = (
                    action.expression.evaluate(fact_resolver(memory))
                    if action.expression is not None
                    else action.value
                )
                memory.contribute(
                    action.fact,
                    value,
                    cf,
                    FactSource.rule(rule.code),
                    specificity=compiled.specificity,
                    step=1,
                )
                return [RuleTestAction(action="assert", fact=action.fact, value=value)]
            except ExprEvalError as exc:
                failures.append(f"действие assert {action.fact}: {exc}")
                return []
        if isinstance(action, CompiledRetract):
            memory.retract(action.fact)
            return [RuleTestAction(action="retract", fact=action.fact)]
        message: str | None = None
        if action.message is not None:
            try:
                message = action.message.render(fact_resolver(memory))
            except ExprEvalError as exc:
                failures.append(f"действие {action.action}: {exc}")
        return [
            RuleTestAction(
                action=action.action,
                message=message,
                weight=action.weight,
                category=action.category,
                target=action.target,
            )
        ]


def _split_fact(path: str, raw: Any) -> tuple[Any, float]:  # noqa: ANN401
    """Входной факт теста: значение или `{value, cf}`; cf по умолчанию 1.0."""
    if isinstance(raw, dict) and "value" in raw:
        try:
            cf = clamp(float(raw.get("cf", 1.0)))
        except (TypeError, ValueError) as exc:
            raise RuleTestFactError(f"{path}: cf должен быть числом") from exc
        return raw["value"], cf
    return raw, 1.0
