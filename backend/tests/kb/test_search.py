"""Поиск лучом на реальном каталоге: тупик луча не должен оставлять клиента без сильных сборок."""

from app.expert.catalog import CatalogSnapshot
from app.expert.configurator.pipeline import Tier
from app.expert.configurator.search import SearchSettings
from app.expert.consultation import consult
from app.expert.frames import Case, CaseFan, Category
from app.expert.knowledge import KnowledgeSnapshot

COMPACT = {
    "tasks": {"main": "aaa_gaming"},
    "budget": 200000,
    "monitor": "fhd_144",
    "case_size": "mini",
}


def test_dead_end_beam_is_retried_wider(
    knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    # Лучшие 30 веток к шагу «корпус» — все с высокой памятью или трёхслотовой видеокартой,
    # ни одна не влезает в компактный корпус. Без повтора остаются только дешёвые сборки.
    no_retry = SearchSettings(retry_width_factor=1)
    narrow = consult(knowledge, real_catalog, COMPACT, settings=no_retry)
    wide = consult(knowledge, real_catalog, COMPACT)
    narrow_max = narrow.result.tiers[Tier.MAXIMUM]
    wide_max = wide.result.tiers[Tier.MAXIMUM]
    assert narrow_max.build.price_kop < 0.6 * 200_000 * 100
    assert wide_max.build.price_kop > 0.9 * 200_000 * 100
    assert wide_max.utility.total > 1.5 * narrow_max.utility.total


def test_every_case_gets_at_least_two_fans(
    knowledge: KnowledgeSnapshot, real_catalog: CatalogSnapshot
) -> None:
    # Самый дешёвый белый корпус — без вентиляторов: к нему докупается набор (CMP-024)
    answers = {
        "tasks": {"main": "aaa_gaming"},
        "budget": 150000,
        "monitor": "qhd_144",
        "color": "white",
    }
    for evaluated in consult(knowledge, real_catalog, answers).result.tiers.values():
        build = evaluated.build
        case, fans = build.frame(Category.CASE), build.frame(Category.CASE_FAN)
        assert isinstance(case, Case)
        bought = fans.quantity if isinstance(fans, CaseFan) else 0
        assert case.fans_included + bought >= 2, build.skus
