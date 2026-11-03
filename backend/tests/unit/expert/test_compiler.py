"""Компиляция и вычисление условий: CF посылки, операторы, порог, индексы."""

from typing import Any

import pytest

from app.expert.dsl.compiler import (
    CompiledAssert,
    CompiledMessageAction,
    CompiledRetract,
    KnowledgeCompileError,
    apply_op,
    compile_condition,
    compile_rule,
    compile_rules,
)
from app.expert.dsl.expr import ExprEvalError
from app.expert.dsl.schema import Op, Rule, RuleKind
from app.expert.facts import WorkingMemory
from tests.unit.expert.rules import assert_, fact, rule


def memory(**facts: tuple[Any, float]) -> WorkingMemory:
    result = WorkingMemory()
    for key, (value, cf) in facts.items():
        result.set_fact(key.replace("__", "."), value, cf)
    return result


def condition(when: dict[str, Any]):  # type: ignore[no-untyped-def]
    return compile_condition(rule("REQ-900", when, [assert_("req.x", 1)]).when)


MEM = memory(
    user__gaming=(True, 0.7),
    user__editing=(True, 0.3),
    user__weak=(True, 0.1),
    user__resolution=("1440p", 1.0),
    user__budget=(120_000, 1.0),
    user__colors=(["white", "silver"], 1.0),
    build__cpu__socket=("AM5", 1.0),
    build__mb__socket=("AM5", 0.9),
)


def test_all_takes_minimum_and_collects_facts() -> None:
    match = condition(
        {"all": [fact("user.gaming", "eq", True), fact("user.resolution", "eq", "1440p")]}
    ).evaluate(MEM)
    assert match is not None
    assert match.cf == 0.7
    assert [f.path for f in match.facts] == ["user.gaming", "user.resolution"]


def test_any_takes_maximum() -> None:
    match = condition(
        {"any": [fact("user.gaming", "eq", True), fact("user.editing", "eq", True)]}
    ).evaluate(MEM)
    assert match is not None
    assert match.cf == 0.7
    assert [f.path for f in match.facts] == ["user.gaming"]


def test_any_none_matched() -> None:
    assert condition({"any": [fact("user.gaming", "eq", False)]}).evaluate(MEM) is None


def test_not_inverts_cf() -> None:
    weak = condition({"not": fact("user.editing", "eq", True)}).evaluate(MEM)
    assert weak is not None
    assert weak.cf == pytest.approx(0.7)
    assert condition({"not": fact("user.gaming", "exists")}).evaluate(MEM) is not None
    strong = memory(user__x=(True, 0.9))
    assert condition({"not": fact("user.x", "exists")}).evaluate(strong) is None
    absent = condition({"not": fact("user.nothing", "exists")}).evaluate(MEM)
    assert absent is not None
    assert absent.cf == 1.0


def test_fact_below_threshold_is_invisible() -> None:
    assert condition(fact("user.weak", "exists")).evaluate(MEM) is None
    assert condition(fact("user.weak", "eq", True)).evaluate(MEM) is None
    assert condition({"expr": "user.weak"}).evaluate(MEM) is None


def test_ref_compares_two_facts_with_min_cf() -> None:
    match = condition(fact("build.cpu.socket", "eq", ref="build.mb.socket")).evaluate(MEM)
    assert match is not None
    assert match.cf == 0.9
    assert condition(fact("build.cpu.socket", "ne", ref="build.mb.socket")).evaluate(MEM) is None
    assert condition(fact("build.cpu.socket", "eq", ref="build.x.socket")).evaluate(MEM) is None


def test_expr_leaf_cf_is_min_of_used_facts() -> None:
    match = condition({"expr": "user.gaming and user.budget > 100000"}).evaluate(MEM)
    assert match is not None
    assert match.cf == 0.7
    constant = condition({"expr": "1 < 2"}).evaluate(MEM)
    assert constant is not None
    assert (constant.cf, constant.facts) == (1.0, ())
    assert condition({"expr": "user.budget > 500000"}).evaluate(MEM) is None


def test_expr_leaf_must_be_boolean() -> None:
    with pytest.raises(ExprEvalError, match="да/нет"):
        condition({"expr": "user.budget + 1"}).evaluate(MEM)


@pytest.mark.parametrize(
    ("op", "left", "right", "expected"),
    [
        (Op.EQ, 1, 1, True),
        (Op.NE, "a", "b", True),
        (Op.LT, 1, 2, True),
        (Op.LE, 2, 2, True),
        (Op.GT, 3, 2, True),
        (Op.GE, 1, 2, False),
        (Op.IN, "AM5", ("AM4", "AM5"), True),
        (Op.NOT_IN, "AM5", ("AM4", "AM5"), False),
        (Op.CONTAINS, ("white", "silver"), "white", True),
        (Op.CONTAINS, "GeForce RTX", "RTX", True),
        (Op.BETWEEN, 5, (1, 10), True),
        (Op.BETWEEN, 11, (1, 10), False),
    ],
)
def test_apply_op(op: Op, left: Any, right: Any, expected: bool) -> None:
    assert apply_op(op, left, right) is expected


@pytest.mark.parametrize(
    ("op", "left", "right", "fragment"),
    [
        (Op.LT, "a", 1, "нельзя сравнить"),
        (Op.IN, "a", "abc", "список"),
        (Op.CONTAINS, 5, 1, "contains"),
        (Op.BETWEEN, 5, (1,), "between"),
    ],
)
def test_apply_op_type_errors(op: Op, left: Any, right: Any, fragment: str) -> None:
    with pytest.raises(ExprEvalError, match=fragment):
        apply_op(op, left, right)


def test_list_values_in_conditions() -> None:
    assert condition(fact("user.colors", "contains", "white")).evaluate(MEM) is not None
    assert condition(fact("user.resolution", "in", ["1080p", "1440p"])).evaluate(MEM) is not None


def test_goal_leaf_is_not_evaluable_forward() -> None:
    goal_rule = Rule.model_validate(
        {
            "code": "GOL-001",
            "name": "цель",
            "kind": "goal",
            "group": "goal",
            "priority": 1,
            "cf": 1.0,
            "goal": {"predicate": "ok"},
            "when": {"all": [{"goal": {"predicate": "sub"}}, fact("build.x.y", "exists")]},
            "explain": "x",
        }
    )
    compiled = compile_rule(goal_rule)
    assert compiled.specificity == 2
    assert compiled.reads == {"build.x.y"}
    with pytest.raises(ExprEvalError, match="обратным выводом"):
        compiled.condition.evaluate(MEM)


def test_compiled_rule_properties() -> None:
    compiled = compile_rule(
        rule(
            "BUD-001",
            {"all": [fact("user.gaming", "eq", True), {"expr": "user.budget > 1"}]},
            [assert_("budget.share.gpu", expr="0.3 + 0.1"), {"action": "retract", "fact": "req.y"}],
        )
    )
    assert compiled.specificity == 2
    assert compiled.reads == {"user.gaming", "user.budget"}
    assert compiled.writes == {"budget.share.gpu", "req.y"}
    assert isinstance(compiled.actions[0], CompiledAssert)
    assert isinstance(compiled.actions[1], CompiledRetract)


def test_message_actions_compile_templates() -> None:
    compiled = compile_rule(
        rule(
            "VAL-001",
            fact("build.cpu.socket", "exists"),
            [
                {"action": "warn", "message": "Сокет {build.cpu.socket}"},
                {"action": "suggest", "category": "gpu", "target": "high", "message": "x"},
            ],
            kind="validate",
        )
    )
    warn, suggest = compiled.actions
    assert isinstance(warn, CompiledMessageAction)
    assert warn.message is not None
    assert warn.message.paths == {"build.cpu.socket"}
    assert isinstance(suggest, CompiledMessageAction)
    assert (suggest.category, suggest.target) == ("gpu", "high")
    score = compile_rule(
        rule(
            "SCR-001",
            fact("user.gaming", "exists"),
            [{"action": "prefer", "weight": 3}],
            kind="score",
        )
    )
    assert isinstance(score.actions[0], CompiledMessageAction)
    assert score.actions[0].weight == 3


def test_rule_set_indexes() -> None:
    rule_set = compile_rules(
        [
            rule("REQ-002", fact("user.gaming", "eq", True), [assert_("req.a", 1)]),
            rule("REQ-001", fact("user.gaming", "exists"), [assert_("req.b", 1)]),
            rule("REQ-003", fact("user.x", "exists"), [assert_("req.c", 1)], enabled=False),
            rule(
                "FLT-001",
                fact("cand.vram_gb", "lt", ref="req.a"),
                [{"action": "reject", "message": "мало"}],
                kind="filter",
            ),
        ]
    )
    assert [r.code for r in rule_set.rules] == ["FLT-001", "REQ-001", "REQ-002"]
    assert [r.code for r in rule_set.of_kind(RuleKind.INFERENCE)] == ["REQ-001", "REQ-002"]
    assert [r.code for r in rule_set.dependents("user.gaming")] == ["REQ-001", "REQ-002"]
    assert rule_set.dependents("req.a") == ()  # фильтры не участвуют в прямом выводе
    assert rule_set.of_kind(RuleKind.GOAL) == ()


def test_compile_errors_are_collected() -> None:
    with pytest.raises(KnowledgeCompileError) as info:
        compile_rules(
            [
                rule("REQ-001", {"expr": "user.x **"}, [assert_("req.a", 1)]),
                rule("REQ-002", fact("user.x", "exists"), [assert_("req.a", expr="open.x")]),
                rule("REQ-003", fact("user.x", "exists"), [assert_("req.a", 1)], explain="{x"),
                rule("REQ-004", fact("user.x", "exists"), [assert_("req.a", 1)]),
                rule("REQ-004", fact("user.x", "exists"), [assert_("req.a", 1)]),
            ]
        )
    codes = [error.code for error in info.value.errors]
    assert codes == ["REQ-001", "REQ-002", "REQ-003", "REQ-004"]
    assert "повторяется" in str(info.value)
