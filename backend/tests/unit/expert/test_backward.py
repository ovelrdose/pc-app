"""Обратный вывод: цели, подцели, переменные, вопросы клиенту, встроенные предикаты."""

from typing import Any

from app.expert.configurator.build import Build, BuildItem
from app.expert.dsl.compiler import compile_rules
from app.expert.dsl.schema import Rule
from app.expert.facts import OverlayView, Scalar, WorkingMemory
from app.expert.frames import FRAMES_BY_CATEGORY, Category
from app.expert.inference.backward import (
    Askable,
    BackwardChainer,
    NodeKind,
    ProofNode,
    ProofStatus,
    fact_title,
)
from app.expert.performance.predicates import make_builtins
from tests.factories import slots
from tests.unit.expert.kb_fixtures import small_tables


def goal_rule(code: str, predicate: str, when: dict[str, Any], **head: Scalar) -> Rule:
    return Rule.model_validate(
        {
            "code": code,
            "name": f"Цель {code}",
            "kind": "goal",
            "group": "goal",
            "priority": 1,
            "cf": 0.9,
            "goal": {"predicate": predicate, "args": head},
            "when": when,
            "explain": "Объяснение {build.gpu.vram_gb}",
        }
    )


GPU = BuildItem(FRAMES_BY_CATEGORY[Category.GPU].model_validate(slots(Category.GPU, vram_gb=8)))
CPU = BuildItem(FRAMES_BY_CATEGORY[Category.CPU].model_validate(slots(Category.CPU)))
BUILD = Build.of([CPU, GPU])

RULES = compile_rules(
    [
        goal_rule("GOL-001", "big_vram", {"fact": "build.gpu.vram_gb", "op": "ge", "value": 12}),
        goal_rule(
            "GOL-002",
            "has_gpu",
            {
                "all": [
                    {"fact": "build.gpu.vram_gb", "op": "ge", "value": 4},
                    {"expr": "build.cpu.cores >= 4"},
                ]
            },
        ),
        goal_rule(
            "GOL-003",
            "either",
            {"any": [{"goal": {"predicate": "big_vram"}}, {"goal": {"predicate": "has_gpu"}}]},
        ),
        goal_rule("GOL-004", "not_big", {"not": {"goal": {"predicate": "big_vram"}}}),
        goal_rule(
            "GOL-005",
            "plays",
            {
                "goal": {
                    "predicate": "fps_at_least",
                    "args": {
                        "game": "$game",
                        "preset": "high",
                        "resolution": "$resolution",
                        "fps": "$fps",
                    },
                }
            },
            game="$game",
        ),
        goal_rule("GOL-006", "white", {"fact": "user.color", "op": "eq", "value": "white"}),
        goal_rule("GOL-007", "loop", {"goal": {"predicate": "loop"}}),
        goal_rule(
            "GOL-008", "for_cs2", {"fact": "build.gpu.vram_gb", "op": "ge", "value": 1}, game="cs2"
        ),
        goal_rule(
            "GOL-009",
            "weird",
            {
                "all": [
                    {"expr": "build.hdd.capacity_gb > 0"},
                    {"expr": "build.cpu.socket > 1"},
                    {"fact": "build.cpu.socket", "op": "lt", "value": 3},
                ]
            },
        ),
        goal_rule(
            "GOL-010",
            "mystery",
            {"goal": {"predicate": "fps_at_least", "args": {"fps": "$secret"}}},
        ),
    ]
)


def chainer(memory: WorkingMemory | None = None) -> BackwardChainer:
    view = OverlayView(memory or WorkingMemory(), BUILD.facts)
    return BackwardChainer(
        RULES,
        view,
        builtins=make_builtins(BUILD, small_tables()),
        askable={"resolution": Askable("user.resolution", "Разрешение?", ("1080p",))},
    )


def statuses(node: ProofNode) -> list[ProofStatus]:
    return [node.status, *(s for child in node.children for s in statuses(child))]


def test_fact_goal_failed_with_reason() -> None:
    node = chainer().prove("big_vram")
    assert node.status is ProofStatus.FAILED
    rule = node.children[0]
    assert (rule.kind, rule.rule_code, rule.detail) == (NodeKind.RULE, "GOL-001", "Объяснение 8")
    leaf = rule.children[0]
    assert leaf.label == "Видеокарта — видеопамять ≥ 12"
    assert leaf.detail == "на самом деле: 8"


def test_all_with_expr_proved_and_cf() -> None:
    node = chainer().prove("has_gpu")
    assert node.status is ProofStatus.PROVED
    assert node.cf == 0.9


def test_any_and_not_over_subgoals() -> None:
    assert chainer().prove("either").status is ProofStatus.PROVED
    assert chainer().prove("not_big").status is ProofStatus.PROVED


def test_variables_from_bindings_facts_and_questions() -> None:
    asked = chainer().prove("plays", {"game": "cs2"}, {"fps": 60})
    assert asked.status is ProofStatus.UNKNOWN
    assert [q.variable for q in asked.questions()] == ["resolution"]
    assert asked.questions()[0].options == ("1080p",)
    memory = WorkingMemory()
    memory.set_fact("user.resolution", "1080p")
    proved = chainer(memory).prove("plays", {"game": "cs2"}, {"fps": 60})
    assert proved.status is ProofStatus.PROVED
    builtin = proved.children[0].children[0]
    assert builtin.kind is NodeKind.BUILTIN
    assert builtin.value == 80
    failed = chainer(memory).prove("plays", {"game": "cs2"}, {"fps": 200})
    assert failed.status is ProofStatus.FAILED
    mystery = chainer().prove("mystery")
    assert [q.variable for q in mystery.questions()] == ["secret"]


def test_unknown_user_fact_and_missing_rules() -> None:
    assert chainer().prove("white").status is ProofStatus.UNKNOWN
    nothing = chainer().prove("nonexistent")
    assert (nothing.status, nothing.detail) == (ProofStatus.FAILED, "нет правил для этой цели")
    assert chainer().prove("loop").status is ProofStatus.FAILED


def test_head_constants_must_match() -> None:
    assert chainer().prove("for_cs2", {"game": "cs2"}).status is ProofStatus.PROVED
    assert chainer().prove("for_cs2", {"game": "dota2"}).detail == "нет правил для этой цели"


def test_missing_values_and_type_errors_fail() -> None:
    node = chainer().prove("weird")
    leaves = node.children[0].children[0].children
    assert [leaf.status for leaf in leaves] == [ProofStatus.FAILED] * 3
    assert "нет значения build.hdd.capacity_gb" in (leaves[0].detail or "")
    assert "нельзя сравнить" in (leaves[1].detail or "")


def test_builtins_directly() -> None:
    builtins = make_builtins(BUILD, small_tables())
    vram = builtins["vram_enough"]({"game": "cs2", "preset": "ultra", "resolution": "1080p"})
    assert vram.status is ProofStatus.FAILED  # нужно 10, есть 8
    bench = builtins["bench_at_least"]({"app": "office", "level": "basic"})
    assert bench.status is ProofStatus.PROVED
    for name, args in [
        ("fps_at_least", {"game": "x"}),
        ("vram_enough", {}),
        ("bench_at_least", {"app": "x"}),
    ]:
        assert builtins[name](args).status is ProofStatus.FAILED


def test_fact_titles() -> None:
    assert fact_title("build.ram.capacity_gb") == "Оперативная память — объём комплекта"
    assert fact_title("user.budget") == "Бюджет, ₽"
    assert fact_title("unknown.path") == "unknown.path"
