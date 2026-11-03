"""Консультация целиком: ответы → профилирование → подбор трёх вариантов (вики §4.1)."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.pipeline import ConfigResult, configure
from app.expert.configurator.plan import Constraints, Scenario
from app.expert.configurator.search import SearchSettings
from app.expert.facts import FactView, WorkingMemory
from app.expert.inference.forward import ForwardResult, run_forward
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.performance import FpsPerformanceModel
from app.expert.questionnaire import answers_to_memory
from app.expert.tables import RESOLUTIONS, Resolution
from app.expert.trace import Trace
from app.expert.waivers import waive


@dataclass(frozen=True, slots=True)
class Consultation:
    """Итог консультации: рабочая память после профилирования, вывод и подбор."""

    memory: WorkingMemory
    profiling: ForwardResult
    result: ConfigResult
    trace: Trace


def performance_model(knowledge: KnowledgeSnapshot, memory: FactView) -> FpsPerformanceModel:
    """Модель полезности для клиента: его разрешение, частота монитора и игры."""
    resolution: Resolution = "1080p"
    fact = memory.lookup("user.resolution")
    for option in RESOLUTIONS:
        if fact is not None and fact.value == option:
            resolution = option
    refresh = memory.lookup("user.refresh_hz")
    games = memory.lookup("user.games")
    main = memory.lookup("profile.main")
    return FpsPerformanceModel(
        knowledge.tables,
        resolution=resolution,
        refresh_hz=float(refresh.value) if refresh and isinstance(refresh.value, int) else None,
        games=[str(g) for g in games.value] if games and isinstance(games.value, tuple) else (),
        primary=Scenario.ESPORTS if main and main.value == "esports" else Scenario.AAA_GAMING,
    )


def consult(
    knowledge: KnowledgeSnapshot,
    catalog: CatalogSnapshot,
    answers: Mapping[str, object],
    constraints: Constraints | None = None,
    *,
    settings: SearchSettings | None = None,
    waived: Collection[str] = (),
) -> Consultation:
    """Проводит консультацию: ответы визарда → факты → прямой вывод → конфигуратор.

    `waived` — требования, от которых клиент отказался (уступки компромиссной сборки).
    """
    trace = Trace()
    memory = answers_to_memory(knowledge.questionnaire, answers, knowledge.tables)
    profiling = run_forward(knowledge.compiled, memory, trace=trace)
    waive(memory, waived)
    result = configure(
        memory,
        knowledge.compiled,
        catalog,
        constraints,
        model=performance_model(knowledge, memory),
        settings=settings,
        trace=trace,
    )
    return Consultation(memory, profiling, result, trace)
