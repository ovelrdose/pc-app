"""Сериализация ограничений сборки и PDF-спецификация."""

import uuid
from datetime import UTC, datetime
from types import MappingProxyType

from app.expert.configurator.pipeline import Tier
from app.expert.configurator.plan import Constraints
from app.expert.frames import Category
from app.schemas.consultations import BuildDetail, BuildItemOut, IssueOut, PerformanceOut
from app.services.build_context import constraints_from_json, constraints_to_json
from app.services.pdf import render_html, render_pdf, rub


def test_constraints_roundtrip() -> None:
    constraints = Constraints(
        owned=frozenset({"GPU-A"}),
        locked=MappingProxyType({Category.GPU: "GPU-A", Category.CPU: "CPU-B"}),
        excluded_skus=frozenset({"SSD-X"}),
        excluded_brands=frozenset({"MSI"}),
        share_overrides=MappingProxyType({Category.SSD: 0.2}),
    )
    data = constraints_to_json(constraints)
    assert data["locked"] == {"cpu": "CPU-B", "gpu": "GPU-A"}
    assert constraints_from_json(data) == constraints
    assert constraints_from_json({}) == Constraints()


def detail() -> BuildDetail:
    item = BuildItemOut(
        category=Category.GPU,
        component_id=uuid.uuid4(),
        sku="GPU-A",
        name="RX 9070 <b>",
        brand="PowerColor",
        price_kop=8_720_000,
        locked=False,
        owned=True,
    )
    return BuildDetail(
        id=uuid.uuid4(),
        tier=Tier.OPTIMUM,
        parent_build_id=None,
        total_price_kop=0,
        utility=1.0,
        items=[item],
        title=None,
        is_saved=False,
        created_at=datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
        consultation_id=uuid.uuid4(),
        kb_version="v1",
        catalog_revision=3,
        performance=PerformanceOut(games=[], apps=[], benchmarks=[], balance={}, disclaimer="±15%"),
        issues=[IssueOut(rule_code="VAL-001", action="warn", message="Одна планка")],
        preferences=[],
    )


def test_rub_formatting() -> None:
    assert rub(12_599_000) == "125 990 ₽"


def test_html_escapes_and_contains_sections() -> None:
    html = render_html(detail(), ["Игры — главный сценарий"])
    assert "Сборщик" in html
    assert "Вариант «Оптимум»" in html
    assert "RX 9070 &lt;b&gt;" in html
    assert "у вас уже есть" in html
    assert "Одна планка" in html
    assert "Игры — главный сценарий" in html


def test_pdf_renders() -> None:
    assert render_pdf(detail(), []).startswith(b"%PDF")
