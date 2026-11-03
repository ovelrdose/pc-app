"""Статусы компонентов (архитектура §17)."""

import pytest

from app.expert.frames import (
    FRAMES_BY_CATEGORY,
    Category,
    ComponentStatus,
    KnownSlotValues,
    compute_status,
)
from tests.factories import slots

KNOWN = KnownSlotValues(
    sockets=frozenset({"AM5", "LGA1700"}),
    chipsets=frozenset({"B650"}),
    form_factors=frozenset({"ATX", "Micro-ATX"}),
)


def frame(category: Category, **overrides: object):  # type: ignore[no-untyped-def]
    return FRAMES_BY_CATEGORY[category].model_validate(slots(category, **overrides))


@pytest.mark.parametrize("category", list(Category))
def test_complete_known_component_is_active(category: Category) -> None:
    result = compute_status(frame(category), known=KNOWN)
    assert result.status is ComponentStatus.ACTIVE
    assert result.issues == ()


@pytest.mark.parametrize(
    ("category", "missing"),
    [
        (Category.CPU, "perf_single"),
        (Category.CPU, "perf_multi"),
        (Category.GPU, "perf_raster"),
        (Category.GPU, "perf_rt"),
        (Category.GPU, "length_mm"),
        (Category.CASE, "max_gpu_mm"),
        (Category.CASE, "max_cooler_mm"),
        (Category.CPU_COOLER, "height_mm"),
    ],
)
def test_missing_model_data_makes_incomplete(category: Category, missing: str) -> None:
    result = compute_status(frame(category, **{missing: None}), known=None)
    assert result.status is ComponentStatus.INCOMPLETE
    assert result.issues == (f"{missing} не заполнен",)


def test_aio_cooler_without_height_is_active() -> None:
    aio = frame(Category.CPU_COOLER, type="aio", radiator_mm=360, height_mm=None)
    assert compute_status(aio, known=None).status is ComponentStatus.ACTIVE


def test_unknown_socket_needs_kb() -> None:
    result = compute_status(frame(Category.CPU, socket="AM6"), known=KNOWN)
    assert result.status is ComponentStatus.NEEDS_KB
    assert result.issues == ("сокет AM6 отсутствует в sockets",)


def test_motherboard_reports_every_unknown_value() -> None:
    board = frame(Category.MOTHERBOARD, socket="AM6", chipset="X970", form_factor="BTX")
    result = compute_status(board, known=KNOWN)
    assert result.status is ComponentStatus.NEEDS_KB
    assert len(result.issues) == 3


def test_cooler_needs_only_one_known_socket() -> None:
    cooler = frame(Category.CPU_COOLER, sockets=["AM5", "AM6"])
    assert compute_status(cooler, known=KNOWN).status is ComponentStatus.ACTIVE
    cooler = frame(Category.CPU_COOLER, sockets=["AM6"])
    assert compute_status(cooler, known=KNOWN).status is ComponentStatus.NEEDS_KB


def test_kb_check_skipped_without_published_kb() -> None:
    result = compute_status(frame(Category.CPU, socket="AM6"), known=None)
    assert result.status is ComponentStatus.ACTIVE


def test_incomplete_takes_precedence_over_needs_kb() -> None:
    cpu = frame(Category.CPU, socket="AM6", perf_single=None)
    assert compute_status(cpu, known=KNOWN).status is ComponentStatus.INCOMPLETE


def test_discontinued_is_inactive_regardless_of_data() -> None:
    cpu = frame(Category.CPU, perf_single=None)
    result = compute_status(cpu, known=KNOWN, discontinued=True)
    assert result.status is ComponentStatus.INACTIVE
