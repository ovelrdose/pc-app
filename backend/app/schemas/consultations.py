"""DTO консультаций, сборок, объяснений и гипотез."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.expert.configurator.modify import EditKind
from app.expert.configurator.pipeline import Tier
from app.expert.explanation.why_not import WhyNotVerdict
from app.expert.frames import Category
from app.expert.inference.backward import NodeKind, ProofStatus

type JsonScalar = str | int | float | bool | None


# --- Анкета ---------------------------------------------------------------------------------------


class OptionOut(BaseModel):
    """Вариант ответа."""

    value: str | int
    label: str


class QuestionOut(BaseModel):
    """Вопрос визарда (варианты из справочников уже подставлены)."""

    id: str
    type: str
    title: str
    options: list[OptionOut]
    allow_unknown: bool
    min: float | None = None
    max: float | None = None
    step: float | None = None
    extra_title: str | None = None
    """Для вопроса tasks: текст вопроса о дополнительных задачах."""


class StepOut(BaseModel):
    """Шаг визарда."""

    id: str
    title: str
    questions: list[QuestionOut]


class QuestionnaireOut(BaseModel):
    """Анкета визарда из опубликованной базы знаний."""

    kb_version: str
    steps: list[StepOut]


class GoalOut(BaseModel):
    """Гипотеза, которую можно проверить («потянет ли»)."""

    predicate: str
    args: dict[str, str]
    title: str
    needs: list[str] = Field(description="переменные, которые понадобятся: resolution, target_fps")


# --- Консультация и сборки ------------------------------------------------------------------------


class ConsultationCreate(BaseModel):
    """Ответы визарда и имеющиеся у клиента детали."""

    answers: dict[str, Any] = Field(description="id вопроса → ответ (см. GET /questionnaire)")
    owned_component_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    waived_requirements: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="требования, от которых клиент отказался (уступки компромиссной сборки)",
    )


class WaivedOut(BaseModel):
    """Требование, от которого клиент отказался."""

    fact: str
    title: str


class BuildItemOut(BaseModel):
    """Деталь сборки."""

    category: Category
    component_id: uuid.UUID
    sku: str
    name: str
    brand: str
    price_kop: int
    locked: bool
    owned: bool


class OwnedComponentOut(BaseModel):
    """Деталь, которая уже есть у клиента."""

    component_id: uuid.UUID
    category: Category
    sku: str
    name: str
    brand: str
    price_kop: int


class BuildSummary(BaseModel):
    """Краткая карточка сборки."""

    id: uuid.UUID
    tier: Tier
    parent_build_id: uuid.UUID | None
    total_price_kop: int
    utility: float
    items: list[BuildItemOut]
    title: str | None
    is_saved: bool
    created_at: datetime


class InfeasibleBrief(BaseModel):
    """Почему подбор не дал результата (кратко; подробно — GET …/infeasible)."""

    reason: str
    min_budget_rub: int | None
    empty_categories: list[Category]


class ConsultationOut(BaseModel):
    """Консультация и её сборки."""

    id: uuid.UUID
    status: Literal["created", "completed", "infeasible"]
    answers: dict[str, Any]
    owned: list[OwnedComponentOut] = Field(description="детали, которые уже есть у клиента")
    waived: list[WaivedOut] = Field(description="требования, от которых клиент отказался")
    profile: dict[str, JsonScalar | list[JsonScalar]] = Field(
        description="ключевые выводы профилирования (profile.*, req.*)"
    )
    kb_version: str | None
    catalog_revision: int | None
    builds: list[BuildSummary]
    infeasibility: InfeasibleBrief | None
    created_at: datetime


class FpsOut(BaseModel):
    """Прогноз FPS в игре."""

    game: str
    title: str
    resolution: str
    preset: str
    fps: float
    low: float
    high: float
    limited_by: str
    bottleneck_ratio: float
    vram_ok: bool


class AppOut(BaseModel):
    """Прогноз для программы."""

    app: str
    title: str
    task: str
    minutes: float
    reference_minutes: float
    basic_ok: bool
    pro_ok: bool


class BenchmarkOut(BaseModel):
    """Бенчмарк: значение из карточки или оценка."""

    name: str
    value: float
    estimated: bool


class PerformanceOut(BaseModel):
    """Прогноз производительности сборки (оценка по референсным тестам, ±15%)."""

    games: list[FpsOut]
    apps: list[AppOut]
    benchmarks: list[BenchmarkOut]
    balance: dict[str, JsonScalar]
    disclaimer: str


class IssueOut(BaseModel):
    """Предупреждение, совет или ошибка проверки."""

    rule_code: str
    action: str
    message: str
    category: str | None = None
    target: str | None = None


class PreferenceOut(BaseModel):
    """Баллы score-правила."""

    rule_code: str
    delta: float
    message: str


class BuildDetail(BuildSummary):
    """Полная карточка сборки."""

    consultation_id: uuid.UUID
    kb_version: str
    catalog_revision: int
    performance: PerformanceOut
    issues: list[IssueOut]
    preferences: list[PreferenceOut]


class BuildPatch(BaseModel):
    """Сохранить или переименовать сборку."""

    title: str | None = Field(default=None, max_length=200)
    is_saved: bool | None = None


# --- Объяснения -----------------------------------------------------------------------------------


class EffectOut(BaseModel):
    """Что правило сделало с фактом."""

    path: str
    outcome: str
    value: JsonScalar | list[JsonScalar]
    cf: float | None


class ReasoningStepOut(BaseModel):
    """Шаг профилирования."""

    step: int
    rule_code: str
    rule_name: str
    explanation: str
    rule_cf: float
    premise_cf: float
    matched: list[dict[str, Any]]
    effects: list[EffectOut]


class ExplanationOut(BaseModel):
    """«Почему эта сборка»: рассуждение, вклад сценариев, баллы и замечания."""

    reasoning: list[ReasoningStepOut]
    utility: float
    scenario_contributions: dict[str, float]
    preferences: list[PreferenceOut]
    issues: list[IssueOut]


class ReasonOut(BaseModel):
    """Причина в ответе «почему не»."""

    rule_code: str | None
    message: str


class WhyNotOut(BaseModel):
    """Ответ на «почему не этот товар»."""

    component_id: uuid.UUID
    sku: str
    verdict: WhyNotVerdict
    reasons: list[ReasonOut]
    can_replace: bool
    price_delta_kop: int | None
    utility_delta_pct: float | None
    fps_delta_pct: float | None


class AlternativeOut(WhyNotOut):
    """Совместимая замена детали."""

    name: str
    price_kop: int


class HypothesisRequest(BaseModel):
    """Гипотеза: цель и аргументы, ответы на вопросы системы."""

    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
    args: dict[str, str | int | float] = Field(default_factory=dict)
    bindings: dict[str, str | int | float] = Field(
        default_factory=dict, description="ответы на вопросы: target_fps, resolution"
    )


class NeedInputOut(BaseModel):
    """Вопрос клиенту."""

    variable: str
    question: str
    options: list[str | int | float | bool]


class ProofNodeOut(BaseModel):
    """Узел дерева доказательства."""

    kind: NodeKind
    label: str
    status: ProofStatus
    cf: float
    rule_code: str | None
    detail: str | None
    value: JsonScalar | list[JsonScalar]
    children: list["ProofNodeOut"]


class HypothesisOut(BaseModel):
    """Результат проверки гипотезы."""

    status: ProofStatus
    tree: ProofNodeOut
    questions: list[NeedInputOut]


class ModificationRequest(BaseModel):
    """Правка сборки."""

    kind: EditKind
    category: Category | None = None
    component_id: uuid.UUID | None = None
    brand: str | None = Field(default=None, max_length=64)
    to_category: Category | None = Field(
        default=None, description="shift_budget: куда вложить сэкономленное на `category`"
    )


class ItemChangeOut(BaseModel):
    """Изменение категории."""

    category: Category
    before: BuildItemOut | None
    after: BuildItemOut | None
    delta_kop: int


class ModificationOut(BaseModel):
    """Новая сборка после правки и разница с прежней."""

    build: BuildDetail
    changes: list[ItemChangeOut]
    price_delta_kop: int
    fps_avg_before: float | None
    fps_avg_after: float | None


class CompareRequest(BaseModel):
    """Сборки для сравнения."""

    build_ids: list[uuid.UUID] = Field(min_length=2, max_length=3)


class CompareRowOut(BaseModel):
    """Строка таблицы сравнения: категория и детали каждой сборки."""

    category: Category
    items: list[BuildItemOut | None]


class CompareOut(BaseModel):
    """Сравнение сборок."""

    builds: list[BuildSummary]
    rows: list[CompareRowOut]
    games: list[list[FpsOut]]
    balance: list[dict[str, JsonScalar]]


class BlockingOut(BaseModel):
    """Требование, которое делает сборку дороже бюджета."""

    fact: str
    title: str
    value: JsonScalar | list[JsonScalar]
    rules: list[str]
    min_budget_without_rub: int | None


class RelaxationOut(BaseModel):
    """Вариант ослабить ответы."""

    title: str
    answers: dict[str, Any]
    min_budget_rub: int


class BestEffortOut(BaseModel):
    """Лучшая сборка в бюджете без обязательных требований (не сохраняется)."""

    total_price_kop: int
    items: list[BuildItemOut]
    unmet: list[str]


class ConcessionOut(BaseModel):
    """Одна уступка компромиссной сборки."""

    title: str
    answers: dict[str, Any] = Field(description="изменённые ответы")
    waived: list[str] = Field(description="снятые требования")


class CompromiseOut(BaseModel):
    """Сборка в бюджете ценой уступок (не сохраняется: принять — новая консультация)."""

    concessions: list[ConcessionOut]
    answers: dict[str, Any] = Field(description="все изменённые ответы")
    waived: list[str] = Field(description="все снятые требования")
    total_price_kop: int
    items: list[BuildItemOut]


class InfeasibleOut(BaseModel):
    """Разбор невыполнимого запроса."""

    budget_rub: int
    min_budget_rub: int | None
    blocking: list[BlockingOut]
    relaxations: list[RelaxationOut]
    compromise: CompromiseOut | None
    best_effort: BestEffortOut | None


ProofNodeOut.model_rebuild()
