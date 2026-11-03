"""Преобразование фрейм ↔ строка БД и схемы фреймов для API."""

import pytest

from app.expert.frames import FRAMES_BY_CATEGORY, Category, ComponentStatus
from app.models import ComponentRow, ComponentSource
from app.repositories.components import row_to_frame, split_frame
from app.services.catalog import list_frames
from tests.factories import slots


@pytest.mark.parametrize("category", list(Category))
def test_split_and_restore_roundtrip(category: Category) -> None:
    frame = FRAMES_BY_CATEGORY[category].model_validate(slots(category))
    columns, specs, perf = split_frame(frame)
    assert "price_kop" in columns
    assert "price_kop" not in specs
    assert not set(perf) & set(specs)
    row = ComponentRow(
        **columns,
        specs=specs,
        perf=perf,
        source=ComponentSource.MANUAL,
        status=ComponentStatus.ACTIVE,
        status_issues=[],
    )
    assert row_to_frame(row) == frame


def test_perf_slots_go_to_perf_and_skip_empty() -> None:
    frame = FRAMES_BY_CATEGORY[Category.CPU].model_validate(
        slots(Category.CPU, perf_multi=None, cinebench_single=120)
    )
    _, specs, perf = split_frame(frame)
    assert perf == {"perf_single": 100.0, "cinebench_single": 120}
    assert "perf_single" not in specs
    assert specs["socket"] == "AM5"


def test_list_frames_covers_all_categories() -> None:
    frames = list_frames()
    assert [frame.category for frame in frames] == list(Category)
    titles = {frame.category: frame.title for frame in frames}
    assert titles[Category.CPU] == "Процессор"
