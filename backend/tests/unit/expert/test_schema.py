"""Схема правил: примеры из архитектуры разбираются, ошибки одного правила ловятся сразу."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.expert.dsl.schema import (
    AllCondition,
    ExprCondition,
    GoalCondition,
    NotCondition,
    Rule,
    RuleKind,
    parse_rules,
)

BUD_014: dict[str, Any] = {
    "code": "BUD-014",
    "name": "4K-гейминг смещает бюджет в видеокарту",
    "kind": "inference",
    "group": "budget",
    "priority": 500,
    "cf": 0.9,
    "when": {
        "all": [
            {"fact": "user.resolution", "op": "eq", "value": "2160p"},
            {"fact": "profile.gaming_weight", "op": "ge", "value": 0.5},
        ]
    },
    "then": [
        {"action": "assert", "fact": "budget.share.gpu", "value": 0.45},
        {"action": "assert", "fact": "budget.share.cpu", "value": 0.18},
    ],
    "explain": "Для игр в 4K главная нагрузка ложится на видеокарту.",
}

CMP_021: dict[str, Any] = {
    "code": "CMP-021",
    "name": "Запас мощности блока питания",
    "kind": "compat",
    "group": "compatibility",
    "priority": 900,
    "cf": 1.0,
    "when": {"expr": "build.psu.wattage < (build.cpu.tdp_w + build.gpu.tbp_w + 75) * 1.3"},
    "then": [
        {
            "action": "reject",
            "message": "БП {build.psu.wattage} Вт слабоват: нужно ≥ "
            "{ceil((build.cpu.tdp_w + build.gpu.tbp_w + 75) * 1.3)} Вт",
        }
    ],
    "explain": "Блоку питания нужен запас 30%.",
}

GOAL: dict[str, Any] = {
    "code": "GEN-GAME-CP2077-ULTRA",
    "name": "Cyberpunk 2077 на ультра",
    "kind": "goal",
    "group": "games",
    "priority": 100,
    "cf": 1.0,
    "origin": "generated",
    "source": "tables/games.yaml#cyberpunk_2077",
    "goal": {"predicate": "runs_game", "args": {"game": "cyberpunk_2077", "preset": "ultra"}},
    "when": {
        "all": [
            {
                "goal": {
                    "predicate": "fps_at_least",
                    "args": {"game": "cyberpunk_2077", "resolution": "$resolution"},
                }
            },
            {"fact": "build.gpu.vram_gb", "op": "ge", "value": 12},
        ]
    },
    "explain": "Cyberpunk 2077 на ультра требует ≥12 ГБ видеопамяти.",
}


def test_architecture_examples_parse() -> None:
    bud, cmp_, goal = parse_rules([BUD_014, CMP_021, GOAL])
    assert isinstance(bud.when, AllCondition)
    assert bud.kind is RuleKind.INFERENCE
    assert isinstance(cmp_.when, ExprCondition)
    assert goal.goal is not None
    assert goal.goal.args == {"game": "cyberpunk_2077", "preset": "ultra"}
    assert isinstance(goal.when, AllCondition)
    subgoal = goal.when.all[0]
    assert isinstance(subgoal, GoalCondition)
    assert subgoal.goal.args["resolution"] == "$resolution"


def test_not_condition_uses_alias() -> None:
    data = {**BUD_014, "when": {"not": {"fact": "user.resolution", "op": "exists"}}}
    parsed = Rule.model_validate(data)
    assert isinstance(parsed.when, NotCondition)


def with_(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {**base, **changes}


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        (with_(CMP_021, cf=0.9), "cf всегда 1.0"),
        (with_(BUD_014, cf=0), "не может быть равен 0"),
        (with_(BUD_014, code="BUD-14"), "code"),
        (with_(BUD_014, code="bud-014"), "code"),
        (with_(BUD_014, then=[]), "хотя бы одно действие"),
        (with_(BUD_014, then=[{"action": "reject", "message": "x"}]), "недопустимо для вида"),
        (with_(CMP_021, then=[{"action": "assert", "fact": "req.x", "value": 1}]), "недопустимо"),
        (
            with_(BUD_014, then=[{"action": "assert", "fact": "user.budget", "value": 1}]),
            "не может писать в user",
        ),
        (
            with_(BUD_014, then=[{"action": "assert", "fact": "req.x", "value": 1, "expr": "1"}]),
            "ровно одно из value или expr",
        ),
        (with_(BUD_014, origin="generated"), "source"),
        (with_(GOAL, goal=None), "должна быть цель"),
        (with_(GOAL, then=[{"action": "warn", "message": "x"}]), "нет действий"),
        (with_(BUD_014, goal=GOAL["goal"]), "только у правил вида goal"),
        (with_(BUD_014, when=GOAL["when"]), "подцели бывают только"),
        (with_(BUD_014, when={"fact": "secret.x", "op": "exists"}), "пространство имён"),
        (with_(BUD_014, when={"fact": "user.x", "op": "eq", "ref": "secret.y"}), "пространство"),
        (with_(BUD_014, when={"fact": "user.x", "op": "exists", "value": 1}), "exists"),
        (with_(BUD_014, when={"fact": "user.x", "op": "eq"}), "ровно одно из value или ref"),
        (with_(BUD_014, when={"fact": "user.x", "op": "in", "value": 1}), "нужен список"),
        (with_(BUD_014, when={"fact": "user.x", "op": "between", "value": [1]}), "[от, до]"),
        (with_(BUD_014, when={"fact": "user.x", "op": "between", "ref": "user.y"}), "between"),
        (with_(BUD_014, when={"fact": "User.X", "op": "exists"}), "fact"),
        (with_(BUD_014, when={"all": []}), "all"),
        (with_(BUD_014, unknown=1), "unknown"),
    ],
)
def test_invalid_rules(data: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        Rule.model_validate(data)


def test_other_kinds_accept_their_actions() -> None:
    base = {**BUD_014, "when": {"fact": "build.gpu.vram_gb", "op": "lt", "value": 8}}
    Rule.model_validate({**base, "kind": "filter", "then": [{"action": "reject", "message": "x"}]})
    Rule.model_validate({**base, "kind": "score", "then": [{"action": "prefer", "weight": -5}]})
    Rule.model_validate(
        {
            **base,
            "kind": "validate",
            "then": [
                {"action": "warn", "message": "a"},
                {"action": "error", "message": "b"},
                {"action": "suggest", "category": "gpu", "target": "high", "message": "c"},
            ],
        }
    )
