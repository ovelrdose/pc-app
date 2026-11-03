"""Рабочая память: вклады, комбинирование CF, конфликты значений, представление товаров."""

import pytest

from app.expert.facts import (
    CATALOG,
    USER,
    FactSource,
    OverlayView,
    WorkingMemory,
    facts_from_mapping,
    frame_facts,
    normalize_value,
)
from app.expert.frames import FRAMES_BY_CATEGORY, Category
from tests.factories import slots

R1, R2, R3 = FactSource.rule("REQ-001"), FactSource.rule("REQ-002"), FactSource.rule("REQ-003")


def test_normalize_value() -> None:
    assert normalize_value(["AM5", "LGA1700"]) == ("AM5", "LGA1700")
    assert normalize_value(Category.CPU) == "cpu"
    with pytest.raises(TypeError):
        normalize_value({"a": 1})
    with pytest.raises(TypeError):
        normalize_value([[1]])


def test_set_fact_replaces_previous_input() -> None:
    memory = WorkingMemory()
    memory.set_fact("user.budget", 100_000)
    change = memory.set_fact("user.budget", 120_000, cf=0.6)
    fact = memory.lookup("user.budget")
    assert fact is not None
    assert (fact.value, fact.cf, fact.sources) == (120_000, 0.6, (USER,))
    assert change.changed


def test_unknown_namespace_is_rejected() -> None:
    with pytest.raises(ValueError, match="пространств"):
        WorkingMemory().set_fact("secret.x", 1)
    with pytest.raises(ValueError, match="пространств"):
        WorkingMemory().set_fact("user", 1)


def test_same_value_from_two_rules_is_combined() -> None:
    memory = WorkingMemory()
    memory.contribute("req.ram_min_gb", 32, 0.24, R1, specificity=1, step=1)
    change = memory.contribute("req.ram_min_gb", 32, 0.5, R2, specificity=1, step=2)
    assert change.after is not None
    assert change.after.cf == pytest.approx(0.62)
    assert change.after.sources == (R1, R2)
    assert change.after.step == 2


def test_repeated_contribution_replaces_not_accumulates() -> None:
    memory = WorkingMemory()
    memory.contribute("req.ram_min_gb", 32, 0.5, R1, specificity=1, step=1)
    memory.contribute("req.ram_min_gb", 32, 0.5, R1, specificity=1, step=2)
    fact = memory.lookup("req.ram_min_gb")
    assert fact is not None
    assert fact.cf == 0.5
    assert fact.step == 1  # ничего не изменилось — свежесть прежняя


def test_conflict_higher_cf_wins_and_loser_kept() -> None:
    memory = WorkingMemory()
    memory.contribute("budget.share.gpu", 0.40, 0.9, R1, specificity=1, step=1)
    memory.contribute("budget.share.gpu", 0.45, 0.6, R2, specificity=3, step=2)
    fact = memory.lookup("budget.share.gpu")
    assert fact is not None
    assert (fact.value, fact.cf) == (0.40, 0.9)
    [alternative] = fact.alternatives
    assert (alternative.value, alternative.cf, alternative.sources) == (0.45, 0.6, (R2,))


def test_conflict_equal_cf_more_specific_wins() -> None:
    memory = WorkingMemory()
    memory.contribute("budget.share.gpu", 0.40, 0.9, R1, specificity=1, step=1)
    memory.contribute("budget.share.gpu", 0.45, 0.9, R2, specificity=3, step=2)
    fact = memory.lookup("budget.share.gpu")
    assert fact is not None
    assert fact.value == 0.45


def test_conflict_full_tie_is_deterministic() -> None:
    first, second = WorkingMemory(), WorkingMemory()
    first.contribute("req.x", "a", 0.5, R2, specificity=1, step=1)
    first.contribute("req.x", "b", 0.5, R1, specificity=1, step=1)
    second.contribute("req.x", "b", 0.5, R1, specificity=1, step=1)
    second.contribute("req.x", "a", 0.5, R2, specificity=1, step=1)
    assert first.as_dict() == second.as_dict() == {"req.x": "b"}


def test_user_fact_beats_rule_with_same_cf() -> None:
    memory = WorkingMemory()
    memory.set_fact("profile.main", "gaming")
    memory.contribute("profile.main", "office", 1.0, R3, specificity=5, step=1)
    assert memory.as_dict() == {"profile.main": "gaming"}


def test_retract_removes_fact() -> None:
    memory = facts_from_mapping({"profile.main": "gaming"})
    change = memory.retract("profile.main")
    assert change.changed
    assert "profile.main" not in memory
    assert not memory.retract("profile.main").changed


def test_iteration_and_len() -> None:
    memory = facts_from_mapping({"user.b": 1, "user.a": 2}, cf=0.7)
    assert [fact.path for fact in memory] == ["user.a", "user.b"]
    assert len(memory) == 2
    assert all(fact.cf == 0.7 for fact in memory)


def test_frame_facts_and_overlay() -> None:
    gpu = FRAMES_BY_CATEGORY[Category.GPU].model_validate(slots(Category.GPU))
    facts = frame_facts("cand", gpu)
    assert facts["cand.vram_gb"].value == 8
    assert facts["cand.category"].value == "gpu"
    assert facts["cand.power_connectors"].value == ("8-pin",)
    assert facts["cand.vram_gb"].sources == (CATALOG,)
    assert "cand.timespy" not in facts  # незаполненные слоты — не факты

    memory = facts_from_mapping({"req.gpu_vram_min_gb": 12})
    view = OverlayView(memory, facts)
    assert view.lookup("cand.vram_gb") is facts["cand.vram_gb"]
    assert view.lookup("req.gpu_vram_min_gb") is memory.lookup("req.gpu_vram_min_gb")
    assert view.lookup("cand.nothing") is None
    with pytest.raises(ValueError, match="пространств"):
        frame_facts("item", gpu)
