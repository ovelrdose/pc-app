"""Статические проверки базы знаний: каждая проверка на минимальном примере."""

from typing import Any

from app.expert.dsl.schema import Rule
from app.expert.validation import Severity, validate_knowledge
from tests.unit.expert.rules import assert_, fact, rule


def checks(rules: list[Rule]) -> set[tuple[str, str | None]]:
    report = validate_knowledge(rules)
    return {(f.check, f.rule_code) for f in report.findings}


def kinded(code: str, kind: str, when: dict[str, Any], action: dict[str, Any]) -> Rule:
    return rule(code, when, [action], kind=kind)


REJECT = {"action": "reject", "message": "нет"}


def test_clean_set() -> None:
    rules = [
        rule("PRF-001", fact("user.budget", "ge", 1), [assert_("profile.budget_class", "mid")]),
        kinded("FLT-001", "filter", fact("cand.vram_gb", "lt", 8), REJECT),
        kinded(
            "SCR-001",
            "score",
            {
                "all": [
                    fact("profile.budget_class", "eq", "mid"),
                    fact("build.gpu.vram_gb", "ge", 8),
                ]
            },
            {"action": "prefer", "weight": 1},
        ),
    ]
    report = validate_knowledge(rules)
    assert report.ok
    assert report.findings == []
    assert report.rules_total == 3


def test_duplicate_codes_stop_further_checks() -> None:
    same = rule("PRF-001", fact("user.budget", "ge", 1), [assert_("profile.main", "office")])
    report = validate_knowledge([same, same])
    assert [(f.check, f.severity) for f in report.findings] == [("unique", Severity.ERROR)]


def test_unknown_paths_and_types() -> None:
    found = checks(
        [
            rule("PRF-001", fact("user.nope", "eq", 1), [assert_("profile.main", "office")]),
            rule("PRF-002", fact("user.color", "gt", 1), [assert_("profile.main", "office")]),
            rule(
                "PRF-003", fact("user.color", "eq", "purple"), [assert_("profile.main", "office")]
            ),
            rule(
                "PRF-004", fact("user.budget", "eq", "много"), [assert_("profile.main", "office")]
            ),
            rule("PRF-005", fact("user.budget", "ge", 1), [assert_("profile.main", "chess")]),
            rule(
                "PRF-006",
                fact("user.budget", "eq", ref="user.color"),
                [assert_("profile.main", "office")],
            ),
            rule(
                "PRF-007", fact("user.budget", "contains", 1), [assert_("profile.main", "office")]
            ),
            rule(
                "PRF-008",
                fact("user.color", "in", ["white", "teal"]),
                [assert_("profile.main", "office")],
            ),
            rule(
                "PRF-009",
                {"expr": "user.budget > 1"},
                [assert_("profile.main", "office")],
                explain="Бюджет {user.nothing}",
            ),
        ]
    )
    assert ("paths", "PRF-001") in found
    for code in ("PRF-002", "PRF-003", "PRF-004", "PRF-005", "PRF-006", "PRF-007", "PRF-008"):
        assert ("types", code) in found, code
    assert ("paths", "PRF-009") in found


def test_cannot_derive_input_or_computed_facts() -> None:
    found = checks(
        [
            rule("REQ-001", fact("user.budget", "ge", 1), [assert_("req.need.gpu", True)]),
            rule("REQ-002", fact("user.budget", "ge", 1), [assert_("req.unknown", 1)]),
        ]
    )
    assert ("paths", "REQ-002") in found


def test_compile_errors_reported() -> None:
    found = checks(
        [rule("PRF-001", {"expr": "user.budget >"}, [assert_("profile.main", "office")])]
    )
    assert ("compile", "PRF-001") in found


def test_cycle_detected() -> None:
    found = checks(
        [
            rule("PRF-001", fact("profile.gaming", "ge", 0.1), [assert_("profile.creator", 1)]),
            rule("PRF-002", fact("profile.creator", "ge", 0.1), [assert_("profile.gaming", 1)]),
        ]
    )
    assert ("cycle", "PRF-001") in found or ("cycle", "PRF-002") in found


def test_contradiction_detected() -> None:
    found = checks(
        [
            rule("PRF-001", fact("user.budget", "ge", 1), [assert_("profile.main", "office")]),
            rule("PRF-002", fact("user.budget", "ge", 1), [assert_("profile.main", "esports")]),
        ]
    )
    assert ("contradiction", "PRF-002") in found


def test_unreachable_premise() -> None:
    found = checks(
        [rule("REQ-001", fact("profile.compact", "eq", True), [assert_("req.rgb", True)])]
    )
    assert ("unreachable", "REQ-001") in found


def test_redundant_specific_rule() -> None:
    general = rule("REQ-001", fact("user.budget", "ge", 1), [assert_("req.rgb", True)])
    specific = rule(
        "REQ-002",
        {"all": [fact("user.budget", "ge", 1), fact("user.rgb", "eq", True)]},
        [assert_("req.rgb", True)],
    )
    report = validate_knowledge([general, specific])
    assert any(f.check == "redundancy" and f.rule_code == "REQ-002" for f in report.warnings)


def test_unused_output_and_missing_subject() -> None:
    found = checks(
        [
            rule("REQ-001", fact("user.budget", "ge", 1), [assert_("req.rgb", True)]),
            rule("REQ-002", fact("user.budget", "ge", 1), [assert_("req.need.gpu", True)]),
            kinded("FLT-001", "filter", fact("user.budget", "lt", 1), REJECT),
        ]
    )
    assert ("unused", "REQ-001") in found
    assert ("unused", "REQ-002") not in found  # читает конфигуратор
    assert ("subject", "FLT-001") in found


def test_goal_predicates() -> None:
    data = {
        "code": "GOL-001",
        "name": "цель",
        "kind": "goal",
        "group": "goal",
        "priority": 1,
        "cf": 1.0,
        "goal": {"predicate": "ok"},
        "explain": "x",
        "when": {"all": [{"goal": {"predicate": "fps_at_least"}}, {"goal": {"predicate": "nope"}}]},
    }
    found = checks([Rule.model_validate(data)])
    assert ("goal", "GOL-001") in found
