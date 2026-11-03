"""Чтение и запись файлов знаний `knowledge/`: справочники и правила в YAML."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.expert.dsl.schema import Rule
from app.expert.golden import GoldenCase
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.questionnaire import Questionnaire
from app.expert.tables import KnowledgeTables

TABLE_FILES = ("sockets", "chipsets", "form_factors", "games", "applications")
RETIRED_FILE = "retired.yaml"


class KnowledgeFileError(ValueError):
    """Файл знаний не читается или не проходит схему."""


class RetiredRule(BaseModel):
    """Правило, выведенное из базы: его код больше не используется, при импорте оно выключается."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^[A-Z]{3}-\d{3}$")
    retired_at: date
    reason: str = Field(min_length=1, max_length=300)


@dataclass(slots=True)
class RuleFileResult:
    """Правила из файлов и ошибки разбора по файлам."""

    rules: list[Rule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files: dict[str, int] = field(default_factory=dict)
    retired: list[RetiredRule] = field(default_factory=list)


def _read_yaml(path: Path) -> Any:  # noqa: ANN401 — структура YAML проверяется схемой дальше
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KnowledgeFileError(f"нет файла {path}") from exc
    except yaml.YAMLError as exc:
        raise KnowledgeFileError(f"{path.name}: не YAML: {exc}") from exc


def load_tables(directory: Path) -> KnowledgeTables:
    """Читает все справочники `tables/*.yaml` и проверяет их вместе."""
    data: dict[str, Any] = {}
    for name in TABLE_FILES:
        content = _read_yaml(directory / f"{name}.yaml")
        if not isinstance(content, dict):
            raise KnowledgeFileError(f"{name}.yaml: ожидается словарь")
        data[name] = content if name == "form_factors" else content.get(name)
    try:
        return KnowledgeTables.model_validate(data)
    except ValidationError as exc:
        raise KnowledgeFileError(f"справочники не проходят схему:\n{exc}") from exc


def load_retired(directory: Path) -> list[RetiredRule]:
    """Реестр выведенных правил `rules/retired.yaml` (нет файла — пустой)."""
    path = directory / RETIRED_FILE
    if not path.exists():
        return []
    content = _read_yaml(path) or []
    if not isinstance(content, list):
        raise KnowledgeFileError(f"{RETIRED_FILE}: ожидается список")
    try:
        retired = [RetiredRule.model_validate(item) for item in content]
    except ValidationError as exc:
        raise KnowledgeFileError(f"{RETIRED_FILE} не проходит схему:\n{exc}") from exc
    codes = [r.code for r in retired]
    duplicates = sorted({c for c in codes if codes.count(c) > 1})
    if duplicates:
        raise KnowledgeFileError(f"{RETIRED_FILE}: повторяются {', '.join(duplicates)}")
    return retired


def load_rules(directory: Path) -> RuleFileResult:
    """Читает правила из `rules/manual/*.yaml` и `rules/generated/*.yaml`.

    Код из реестра выведенных правил (`rules/retired.yaml`) в файлах правил — ошибка: коды не
    переиспользуются.
    """
    result = RuleFileResult(retired=load_retired(directory))
    for sub in ("manual", "generated"):
        for path in sorted((directory / sub).glob("*.yaml")):
            label = f"{sub}/{path.name}"
            content = _read_yaml(path) or []
            if not isinstance(content, list):
                result.errors.append(f"{label}: ожидается список правил")
                continue
            result.files[label] = len(content)
            for index, item in enumerate(content, start=1):
                code = item.get("code", f"#{index}") if isinstance(item, dict) else f"#{index}"
                try:
                    result.rules.append(Rule.model_validate(item))
                except ValidationError as exc:
                    messages = "; ".join(
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                    )
                    result.errors.append(f"{label}: {code}: {messages}")
    retired = {r.code for r in result.retired}
    result.errors += [
        f"{rule.code}: код выведен из базы ({RETIRED_FILE}) и не переиспользуется"
        for rule in result.rules
        if rule.code in retired
    ]
    return result


def dump_rules(rules: list[Rule]) -> str:
    """YAML правил в стабильном виде: без умолчаний и в порядке полей схемы."""
    data = [
        rule.model_dump(mode="json", by_alias=True, exclude_defaults=True, exclude_none=True)
        for rule in rules
    ]
    for item, rule in zip(data, rules, strict=True):
        # kind, priority и cf важны для чтения даже при значениях по умолчанию.
        item.setdefault("kind", rule.kind.value)
    text: str = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
    return text


def load_questionnaire(path: Path) -> Questionnaire:
    """Читает анкету визарда `questionnaire.yaml`."""
    try:
        return Questionnaire.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise KnowledgeFileError(f"{path.name} не проходит схему:\n{exc}") from exc


def load_knowledge(directory: Path, version: str = "files") -> KnowledgeSnapshot:
    """Собирает снимок базы знаний из файлов `knowledge/`; ошибки — `KnowledgeFileError`."""
    rules = load_rules(directory / "rules")
    if rules.errors:
        raise KnowledgeFileError("правила не проходят схему:\n" + "\n".join(rules.errors))
    return KnowledgeSnapshot.build(
        version,
        rules.rules,
        load_tables(directory / "tables"),
        load_questionnaire(directory / "questionnaire.yaml"),
    )


def load_golden(directory: Path) -> list[GoldenCase]:
    """Читает эталонные кейсы `golden/*.yaml`."""
    cases: list[GoldenCase] = []
    for path in sorted(directory.glob("*.yaml")):
        content = _read_yaml(path) or []
        try:
            cases += [GoldenCase.model_validate(item) for item in content]
        except ValidationError as exc:
            raise KnowledgeFileError(f"{path.name} не проходит схему:\n{exc}") from exc
    return cases
