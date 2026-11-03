"""Проверка гипотез клиента обратным выводом: «потянет ли сборка игру X на настройках Y?»."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.expert.configurator.build import Build
from app.expert.facts import FactView, OverlayView, Scalar
from app.expert.inference.backward import Askable, BackwardChainer, NeedInput, ProofNode
from app.expert.knowledge import KnowledgeSnapshot
from app.expert.performance import FpsPerformanceModel
from app.expert.performance.predicates import make_builtins

ASKABLE: Mapping[str, Askable] = MappingProxyType(
    {
        "resolution": Askable(
            "user.resolution", "В каком разрешении вы играете?", ("1080p", "1440p", "2160p")
        ),
        "target_fps": Askable(
            "user.target_fps",
            "Какой FPS для вас комфортен?",
            (30, 60, 90, 120, 144, 165, 240),
        ),
    }
)
"""Переменные целей, которые можно взять из ответов клиента или спросить."""


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """Результат проверки гипотезы: дерево доказательства и вопросы клиенту."""

    predicate: str
    args: Mapping[str, Scalar]
    root: ProofNode
    questions: tuple[NeedInput, ...]


def check_hypothesis(
    knowledge: KnowledgeSnapshot,
    memory: FactView,
    build: Build,
    predicate: str,
    args: Mapping[str, Scalar] | None = None,
    bindings: Mapping[str, Scalar] | None = None,
    model: FpsPerformanceModel | None = None,
) -> Hypothesis:
    """Доказывает цель для сборки. `bindings` — ответы на вопросы (`target_fps`, `resolution`)."""
    perf = model.perf_facts(build) if model is not None else {}
    view = OverlayView(memory, {**build.facts, **perf})
    chainer = BackwardChainer(
        knowledge.compiled, view, builtins=make_builtins(build, knowledge.tables), askable=ASKABLE
    )
    root = chainer.prove(predicate, args, bindings)
    return Hypothesis(predicate, dict(args or {}), root, tuple(root.questions()))
