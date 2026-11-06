"""DTO админки (этап 9, ADR 0010): каталог, правила, база знаний, пользователи."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.expert.dsl.schema import RuleKind, RuleOrigin
from app.expert.frames import ComponentStatus
from app.models.user import UserRole

# --- Каталог -----------------------------------------------------------------------------------


class ComponentPatchIn(BaseModel):
    """Служебная правка компонента: наличие и статус (снять с продажи / вернуть к продаже)."""

    in_stock: bool | None = None
    status: ComponentStatus | None = None


class CatalogImportOut(BaseModel):
    """Отчёт импорта CSV категории (ADR 0010 п.1)."""

    import_id: uuid.UUID
    status: str
    dry_run: bool
    created: int
    updated: int
    unchanged: int
    catalog_revision: int
    status_counts: dict[str, int]
    errors: list[str]
    warnings: list[str]


# --- Правила -----------------------------------------------------------------------------------


class RuleOut(BaseModel):
    """Правило рабочей копии; `body` — правило целиком по схеме DSL (для редактора)."""

    code: str
    kind: RuleKind
    group: str
    name: str
    priority: int
    cf: float
    enabled: bool
    origin: RuleOrigin
    source: str | None
    explain: str
    revision: int
    updated_by: uuid.UUID | None
    updated_at: datetime
    body: dict[str, Any]
    warning: str | None = None
    """Предупреждение (например, ручная правка сгенерированного правила — override)."""


class RulePage(BaseModel):
    items: list[RuleOut]
    total: int
    limit: int
    offset: int


class RuleRevisionOut(BaseModel):
    revision: int
    body: dict[str, Any]
    change_type: str
    author_id: uuid.UUID | None
    created_at: datetime


class RuleDetailOut(BaseModel):
    rule: RuleOut
    revisions: list[RuleRevisionOut]


class RuleTestIn(BaseModel):
    """Входные факты изолированного прогона: `{path: value}` или `{path: {value, cf}}`."""

    facts: dict[str, Any]


class RuleTestActionOut(BaseModel):
    action: str
    fact: str | None = None
    value: Any = None
    message: str | None = None
    weight: float | None = None
    category: str | None = None
    target: str | None = None


class RuleTestFactOut(BaseModel):
    path: str
    value: Any
    cf: float


class RuleTestOut(BaseModel):
    matched: bool
    premise_cf: float | None
    actions: list[RuleTestActionOut]
    facts_after: list[RuleTestFactOut]
    failures: list[str]


# --- База знаний -------------------------------------------------------------------------------


class GoldenReportOut(BaseModel):
    passed: int
    failed: int
    failures: dict[str, list[str]]


class ValidateReportOut(BaseModel):
    """Отчёт stateless-валидации черновика (ADR 0010 п.3); ничего не записывает."""

    rules_total: int
    errors: list[str]
    warnings: list[str]
    golden: GoldenReportOut
    checksum: str
    matches_latest: bool


class KbStatusOut(BaseModel):
    """Лёгкий статус черновика: контрольная сумма, совпадение со снимком, число правил.

    Собирается одним чтением из БД: без компиляции и эталонных кейсов.
    """

    checksum: str
    matches_latest: bool
    rules_total: int


class PublishOut(BaseModel):
    snapshot_id: int
    version: int
    created: bool
    rules: int
    warnings: int
    golden_cases: int
    statuses_changed: int


class SnapshotOut(BaseModel):
    id: int
    version: int
    checksum: str
    comment: str | None
    published_by: uuid.UUID | None
    published_at: datetime
    rules: int
    warnings: int
    golden: int


class RegenerateOut(BaseModel):
    """Diff регенерации табличных правил (ADR 0010 п.5)."""

    dry_run: bool
    created: list[str]
    updated: list[str]
    removed: list[str]
    overrides: list[str]
    """Правила-override (origin manual с source из tables/), которые не трогаем."""


class VocabularyOut(BaseModel):
    """Факт словаря для конструктора условий: путь, тип, роль, название, допустимые значения."""

    path: str
    type: str
    role: str
    title: str
    values: list[Any]


class ReferenceOut(BaseModel):
    """Справочник, анкета или golden cases целиком (как в `reference_tables`)."""

    name: str
    data: Any


# --- Пользователи ------------------------------------------------------------------------------


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserAdminPage(BaseModel):
    items: list[UserAdminOut]
    total: int
    limit: int
    offset: int


class UserPatchIn(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
