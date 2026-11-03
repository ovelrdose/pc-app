"""«Почему не» и разбор невыполнимых требований на реальной базе знаний и каталоге."""

import pytest

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.pipeline import Tier
from app.expert.configurator.plan import Constraints
from app.expert.consultation import Consultation, consult, performance_model
from app.expert.explanation.infeasible import explain_infeasible
from app.expert.explanation.why_not import WhyNot, WhyNotVerdict, why_not
from app.expert.knowledge import KnowledgeSnapshot

WALKTHROUGH = {
    "tasks": {"main": "aaa_gaming", "extra": ["video_editing"]},
    "budget": 170000,
    "monitor": "qhd_144",
    "color": "white",
    "storage_gb": 1000,
}


@pytest.fixture(scope="module")
def walkthrough(knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot) -> Consultation:
    return consult(knowledge, real_catalog, WALKTHROUGH)


def ask(
    consultation: Consultation,
    knowledge: KnowledgeSnapshot,
    catalog: CatalogSnapshot,
    sku: str,
    tier: Tier = Tier.MAXIMUM,
) -> WhyNot:
    model = performance_model(knowledge, consultation.memory)
    result = consultation.result
    return why_not(
        sku,
        result.tiers.get(tier),
        result.plan,
        result.filtering,
        catalog,
        consultation.memory,
        knowledge.compiled,
        model,
    )


def test_not_found_and_in_build(
    walkthrough: Consultation, knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    assert ask(walkthrough, knowledge, real_catalog, "NOPE").verdict is WhyNotVerdict.NOT_FOUND
    gpu = walkthrough.result.tiers[Tier.MAXIMUM].build.skus[3]
    answer = ask(walkthrough, knowledge, real_catalog, gpu)
    assert answer.verdict is WhyNotVerdict.IN_BUILD
    assert not answer.can_replace


def test_over_budget(
    walkthrough: Consultation, knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    answer = ask(walkthrough, knowledge, real_catalog, "SSD-SAMSUNG-990PRO-2TB")
    assert answer.verdict is WhyNotVerdict.OVER_BUDGET
    assert "за бюджет" in answer.reasons[0].message
    assert answer.price_delta_kop is not None
    assert answer.price_delta_kop > 0


def test_better_or_equal_alternative(
    walkthrough: Consultation, knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    answer = ask(walkthrough, knowledge, real_catalog, "SSD-SAMSUNG-990EVOPLUS-1TB", Tier.ECONOMY)
    assert answer.verdict is WhyNotVerdict.BETTER
    assert answer.can_replace
    assert answer.utility_delta_pct is not None
    assert answer.utility_delta_pct >= 0


def test_incompatible_explains_replacement(
    walkthrough: Consultation, knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    # трёхслотовая карта на 340 мм не подходит к корпусу: замена подберёт остальное заново
    answer = ask(walkthrough, knowledge, real_catalog, "GPU-GIGABYTE-RTX5070TI-GAMING-OC")
    assert answer.verdict is WhyNotVerdict.INCOMPATIBLE
    assert (answer.reasons[0].rule_code or "").startswith("CMP-")
    assert answer.can_replace
    assert "подобраны заново" in answer.reasons[-1].message


def test_owned_category(knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot) -> None:
    owned = Constraints(owned=frozenset({"GPU-SAPPHIRE-RX9070XT-PULSE"}))
    consultation = consult(knowledge, real_catalog, {**WALKTHROUGH, "budget": 120000}, owned)
    answer = ask(consultation, knowledge, real_catalog, "GPU-PALIT-RTX5060-DUAL")
    assert answer.verdict is WhyNotVerdict.OWNED


def test_infeasible_report(knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot) -> None:
    answers = {
        "tasks": {"main": "aaa_gaming"},
        "budget": 90000,
        "monitor": "uhd_144",
        "color": "white",
    }
    report = explain_infeasible(knowledge, real_catalog, answers)
    assert report.budget_rub == 90000
    assert report.min_budget_rub is not None
    assert report.min_budget_rub > 90000
    blocking = {item.fact for item in report.blocking}
    assert "req.gpu_raster_min" in blocking
    assert all(item.min_budget_without_rub for item in report.blocking)
    titles = [r.title for r in report.relaxations]
    assert "Монитор «2K (2560×1440), 144–180 Гц» вместо «4K, 120–165 Гц»" in titles
    # для современных игр цель — 60 FPS, поэтому 4K на 60 Гц сборку не удешевляет
    assert not any("60 Гц" in title for title in titles)
    assert [r.min_budget_rub for r in report.relaxations] == sorted(
        r.min_budget_rub for r in report.relaxations
    )
    # вместо «лучшего возможного» — компромисс: 4K → 2K, любой цвет и диск меньше
    assert report.best_effort is None
    assert report.compromise is not None
    assert report.compromise.build.build.price_kop <= 90000 * 100
    # уступка монитора снимает завышенное требование к растру сама: waiver не нужен
    assert report.compromise.answers == {"storage_gb": 500, "color": "any", "monitor": "qhd_144"}
    assert report.compromise.waived == ()


def test_infeasible_suggests_any_memory_type(
    knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    answers = {
        "tasks": {"main": "aaa_gaming"},
        "budget": 100000,
        "monitor": "fhd_144",
        "mem_type": "DDR5",
    }
    report = explain_infeasible(knowledge, real_catalog, answers)
    relaxation = next(r for r in report.relaxations if r.title == "Любой тип памяти")
    assert relaxation.answers == {"mem_type": "any"}
    assert report.min_budget_rub is not None
    assert relaxation.min_budget_rub < report.min_budget_rub


def test_compromise_concedes_in_priority_order(
    knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    answers = {"tasks": {"main": "aaa_gaming"}, "budget": 80000, "monitor": "qhd_144"}
    report = explain_infeasible(knowledge, real_catalog, answers)
    compromise = report.compromise
    assert compromise is not None
    # сначала диск; затем процессор и память — по убыванию важности, до попадания в бюджет
    first_words = [c.title.split(" ")[0] for c in compromise.concessions]
    assert first_words == ["SSD", "Процессор", "Одна"]
    assert compromise.answers == {"storage_gb": 500}
    assert compromise.waived == ("req.cpu_single_min", "req.ram_dual_channel")
    assert compromise.build.build.price_kop <= 80000 * 100
    assert report.best_effort is None  # компромисс заменяет «лучшее возможное»
    # компромисс воспроизводится консультацией с этими ответами и уступками
    again = consult(
        knowledge, real_catalog, {**answers, **compromise.answers}, waived=compromise.waived
    )
    assert again.result.tiers
    assert again.memory.lookup("req.ram_dual_channel") is None


def test_compromise_returns_unneeded_concessions(
    knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    answers = {
        "tasks": {"main": "aaa_gaming"},
        "budget": 100000,
        "monitor": "qhd_144",
        "storage_gb": 2000,
        "rgb": "yes",
    }
    report = explain_infeasible(knowledge, real_catalog, answers)
    assert report.compromise is not None
    titles = [c.title for c in report.compromise.concessions]
    # подсветка дешёвая: уступать её не пришлось, а диск уступается первым
    assert not any("подсветк" in t for t in titles)
    assert titles[0].startswith("SSD")
    assert report.compromise.build.build.price_kop <= 100000 * 100
