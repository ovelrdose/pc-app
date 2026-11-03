"""Прямой вывод: игрушечный пример из вики, CF, конфликты, рефракция, трасса."""

import json

import pytest

from app.expert.dsl.compiler import compile_rules
from app.expert.dsl.schema import Rule
from app.expert.facts import FactSource, WorkingMemory, facts_from_mapping
from app.expert.inference.agenda import Activation, Agenda
from app.expert.inference.forward import InferenceLimitError, run_forward
from app.expert.trace import EffectOutcome, Phase, RuleFailure, RuleFiring, Trace
from tests.unit.expert.rules import assert_, fact, rule

# Игрушечный пример (вики, страница 0): клиентка Аня.
TOY_RULES = [
    rule(
        "PRF-001",
        fact("user.gaming_weight", "ge", 0.5),
        [assert_("profile.main_scenario", "gaming")],
        priority=500,
        explain="Игры — главный сценарий",
    ),
    rule(
        "REQ-001",
        {
            "all": [
                fact("profile.main_scenario", "eq", "gaming"),
                fact("user.resolution", "eq", "1440p"),
            ]
        },
        [assert_("req.gpu_class_min", "mid_plus")],
        priority=400,
    ),
    rule(
        "REQ-002",
        fact("req.gpu_class_min", "in", ["mid_plus", "high"]),
        [assert_("req.gpu_vram_min_gb", 12)],
        priority=400,
    ),
    rule(
        "BUD-001",
        fact("profile.main_scenario", "eq", "gaming"),
        [assert_("budget.gpu_rub", expr="user.budget * 0.45")],
        priority=300,
        explain="На видеокарту {budget.gpu_rub} ₽",
    ),
    rule(
        "BUD-002",
        fact("user.budget", "lt", 50_000),
        [assert_("req.gpu_needed", False)],
        priority=300,
    ),
]

ANYA = {
    "user.gaming_weight": 1.0,
    "user.resolution": "1440p",
    "user.budget": 100_000,
    "user.color": "white",
}


def test_toy_example_order_and_conclusions() -> None:
    memory = facts_from_mapping(ANYA)
    trace = Trace()
    result = run_forward(compile_rules(TOY_RULES), memory, trace=trace)

    # Порядок как в вики: PRF-1 → REQ-1 (приоритет выше BUD-1) → REQ-2 → BUD-1; BUD-2 не сработало.
    assert result.fired == ("PRF-001", "REQ-001", "REQ-002", "BUD-001")
    assert trace.fired_codes() == list(result.fired)
    assert result.steps == 4
    assert memory.as_dict() == {
        **ANYA,
        "profile.main_scenario": "gaming",
        "req.gpu_class_min": "mid_plus",
        "req.gpu_vram_min_gb": 12,
        "budget.gpu_rub": 45_000.0,
    }
    bud = trace.firings()[-1]
    assert bud.explanation == "На видеокарту 45\u00a0000 ₽"
    assert bud.matched[0].path == "profile.main_scenario"
    assert bud.phase is Phase.PROFILING


def test_cf_propagation_example_from_wiki() -> None:
    rules = compile_rules(
        [
            rule(
                "REQ-024", fact("user.editing", "eq", True), [assert_("req.ram_min_gb", 32)], cf=0.8
            ),
        ]
    )
    memory = WorkingMemory()
    memory.set_fact("user.editing", True, cf=0.3)
    trace = Trace()
    run_forward(rules, memory, trace=trace)
    ram = memory.lookup("req.ram_min_gb")
    assert ram is not None
    assert ram.cf == pytest.approx(0.24)
    [firing] = trace.firings()
    assert (firing.rule_cf, firing.premise_cf) == (0.8, 0.3)
    assert firing.effects[0].outcome is EffectOutcome.NEW


def test_two_rules_combine_cf() -> None:
    rules = compile_rules(
        [
            rule(
                "REQ-024", fact("user.editing", "eq", True), [assert_("req.ram_min_gb", 32)], cf=0.8
            ),
            rule(
                "REQ-025", fact("user.render", "eq", True), [assert_("req.ram_min_gb", 32)], cf=0.5
            ),
        ]
    )
    memory = WorkingMemory()
    memory.set_fact("user.editing", True, cf=0.3)
    memory.set_fact("user.render", True)
    trace = Trace()
    run_forward(rules, memory, trace=trace)
    ram = memory.lookup("req.ram_min_gb")
    assert ram is not None
    assert ram.cf == pytest.approx(0.62)
    assert ram.sources == (FactSource.rule("REQ-024"), FactSource.rule("REQ-025"))
    outcomes = [firing.effects[0].outcome for firing in trace.firings()]
    assert outcomes == [EffectOutcome.NEW, EffectOutcome.STRENGTHENED]


def test_refiring_replaces_contribution_instead_of_inflating() -> None:
    rules = compile_rules(
        [
            rule(
                "PRF-001",
                fact("user.a", "exists"),
                [assert_("profile.p", True)],
                cf=0.5,
                priority=900,
            ),
            rule("REQ-001", fact("profile.p", "eq", True), [assert_("req.q", 1)], priority=800),
            rule(
                "PRF-002",
                fact("user.b", "exists"),
                [assert_("profile.p", True)],
                cf=0.5,
                priority=100,
            ),
        ]
    )
    memory = facts_from_mapping({"user.a": 1, "user.b": 1})
    result = run_forward(rules, memory)
    assert result.fired == ("PRF-001", "REQ-001", "PRF-002", "REQ-001")
    q = memory.lookup("req.q")
    assert q is not None
    # После PRF-002 profile.p = 0.75; REQ-001 сработал заново и *заменил* свой вклад: 0.75,
    # а не combine(0.5, 0.75) = 0.875.
    assert q.cf == pytest.approx(0.75)


def test_value_conflict_specific_rule_wins_and_loser_traced() -> None:
    rules = compile_rules(
        [
            rule(
                "BUD-009",
                fact("profile.main", "eq", "gaming"),
                [assert_("budget.share.gpu", 0.40)],
                cf=0.9,
                priority=200,
            ),
            rule(
                "BUD-014",
                {"all": [fact("profile.main", "eq", "gaming"), fact("user.res", "eq", "2160p")]},
                [assert_("budget.share.gpu", 0.45)],
                cf=0.9,
                priority=100,
            ),
        ]
    )
    memory = facts_from_mapping({"profile.main": "gaming", "user.res": "2160p"})
    trace = Trace()
    run_forward(rules, memory, trace=trace)
    share = memory.lookup("budget.share.gpu")
    assert share is not None
    assert share.value == 0.45
    assert [alt.value for alt in share.alternatives] == [0.40]
    first, second = trace.firings()
    assert first.effects[0].outcome is EffectOutcome.NEW
    assert second.effects[0].outcome is EffectOutcome.REPLACED


def test_outvoted_contribution_is_traced() -> None:
    rules = compile_rules(
        [rule("BUD-001", fact("user.x", "exists"), [assert_("budget.share.gpu", 0.3)], cf=0.5)]
    )
    memory = facts_from_mapping({"user.x": 1})
    memory.contribute(
        "budget.share.gpu", 0.4, 0.9, FactSource.rule("BUD-000"), specificity=1, step=0
    )
    trace = Trace()
    run_forward(rules, memory, trace=trace)
    assert trace.firings()[0].effects[0].outcome is EffectOutcome.OUTVOTED
    assert trace.firings()[0].effects[0].contributed_value == 0.3


def test_specificity_then_recency_order() -> None:
    rules = compile_rules(
        [
            rule("REQ-001", fact("user.a", "exists"), [assert_("req.one", 1)]),
            rule(
                "REQ-002",
                {"all": [fact("user.a", "exists"), fact("user.b", "exists")]},
                [assert_("req.two", 1)],
            ),
            rule("PRF-001", fact("user.c", "exists"), [assert_("profile.fresh", 1)], priority=200),
            rule("REQ-003", fact("profile.fresh", "exists"), [assert_("req.three", 1)]),
        ]
    )
    memory = facts_from_mapping({"user.a": 1, "user.b": 1, "user.c": 1})
    result = run_forward(rules, memory)
    # PRF-001 — приоритет; затем REQ-002 (2 листа); затем REQ-003 (свежий факт) раньше REQ-001.
    assert result.fired == ("PRF-001", "REQ-002", "REQ-003", "REQ-001")


def test_retract_and_negation() -> None:
    rules = compile_rules(
        [
            rule(
                "PRF-001",
                fact("user.office", "eq", True),
                [{"action": "retract", "fact": "profile.gpu"}],
                priority=200,
            ),
            rule(
                "REQ-001",
                {"not": fact("profile.gpu", "exists")},
                [assert_("req.igpu", True)],
                priority=100,
            ),
        ]
    )
    memory = facts_from_mapping({"user.office": True, "profile.gpu": "dgpu"})
    trace = Trace()
    run_forward(rules, memory, trace=trace)
    assert "profile.gpu" not in memory
    assert memory.as_dict()["req.igpu"] is True
    assert trace.firings()[0].effects[0].outcome is EffectOutcome.RETRACTED


def test_errors_are_traced_and_do_not_stop_inference() -> None:
    rules = compile_rules(
        [
            rule("REQ-001", {"expr": "user.budget / user.zero > 1"}, [assert_("req.a", 1)]),
            rule(
                "REQ-002",
                fact("user.budget", "exists"),
                [assert_("req.b", expr="user.budget / user.zero"), assert_("req.c", 1)],
            ),
            rule("REQ-003", fact("user.budget", "lt", "много"), [assert_("req.d", 1)]),
        ]
    )
    memory = facts_from_mapping({"user.budget": 100, "user.zero": 0})
    trace = Trace()
    result = run_forward(rules, memory, trace=trace)
    assert result.fired == ("REQ-002",)
    assert memory.as_dict().get("req.c") == 1
    assert "req.b" not in memory
    failures = [e for e in trace.entries if isinstance(e, RuleFailure)]
    assert [f.rule_code for f in failures] == ["REQ-001", "REQ-003", "REQ-002"]
    assert "деление на ноль" in failures[0].message


def test_step_limit() -> None:
    with pytest.raises(InferenceLimitError) as info:
        run_forward(compile_rules(TOY_RULES), facts_from_mapping(ANYA), max_steps=2)
    assert info.value.last_rules == ["PRF-001", "REQ-001"]
    assert "2 шагов" in str(info.value)


def test_deterministic_and_serializable_trace() -> None:
    def run_once() -> str:
        trace = Trace()
        run_forward(compile_rules(TOY_RULES), facts_from_mapping(ANYA), trace=trace)
        return json.dumps(trace.to_jsonable(), ensure_ascii=False)

    first = run_once()
    assert first == run_once()
    entry = json.loads(first)[0]
    assert entry["type"] == "rule_fired"
    assert entry["rule_code"] == "PRF-001"
    assert entry["explanation"] == "Игры — главный сценарий"


def test_rule_with_constant_condition_fires_once() -> None:
    rules = compile_rules([rule("BUD-001", {"expr": "true"}, [assert_("budget.reserve", 0.05)])])
    memory = WorkingMemory()
    assert run_forward(rules, memory).fired == ("BUD-001",)


def test_agenda_pending_order() -> None:
    rules = compile_rules(TOY_RULES)
    memory = facts_from_mapping({**ANYA, "profile.main_scenario": "gaming"})
    agenda = Agenda()
    for compiled in rules.of_kind(rules.rules[0].rule.kind):
        match = compiled.condition.evaluate(memory)
        if match is not None:
            agenda.put(Activation(compiled, match))
    assert [a.rule.code for a in agenda.pending()] == ["PRF-001", "REQ-001", "BUD-001"]
    agenda.discard("PRF-001")
    agenda.discard("nothing")
    assert len(agenda) == 2


def test_firing_records_all_fields() -> None:
    trace = Trace()
    run_forward(compile_rules(TOY_RULES[:1]), facts_from_mapping(ANYA), trace=trace)
    [firing] = trace.entries
    assert isinstance(firing, RuleFiring)
    assert (firing.rule_name, firing.priority, firing.specificity) == ("Правило PRF-001", 500, 1)
    effect = firing.effects[0]
    assert (effect.value_after, effect.cf_after, effect.value_before) == ("gaming", 1.0, None)


def test_non_inference_rules_are_ignored() -> None:
    filter_rule = Rule.model_validate(
        {
            "code": "FLT-001",
            "name": "фильтр",
            "kind": "filter",
            "group": "filter",
            "priority": 1,
            "cf": 1.0,
            "when": {"fact": "user.budget", "op": "exists"},
            "then": [{"action": "reject", "message": "нет"}],
            "explain": "x",
        }
    )
    assert run_forward(compile_rules([filter_rule]), facts_from_mapping(ANYA)).fired == ()
