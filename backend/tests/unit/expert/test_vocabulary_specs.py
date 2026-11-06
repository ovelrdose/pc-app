"""Публичный словарь фактов `all_specs()` для конструктора условий админки."""

from app.expert.vocabulary import FactRole, FactType, all_specs, lookup


def test_all_specs_covers_every_lookup_path() -> None:
    specs = {spec.path: spec for spec in all_specs()}
    # каждый путь, который умеет разрешать lookup(), есть в all_specs()
    for path in (
        "user.budget",
        "profile.weight.office",
        "req.need.gpu",
        "budget.share.gpu",
        "build.cpu.socket",
        "build.case.owned",
        "build.total.price_rub",
        "perf.fps_avg",
        "cand.socket",
        "cand.price_kop",
    ):
        assert path in specs, path
        assert lookup(path) is not None


def test_all_specs_fields_and_roles() -> None:
    specs = {spec.path: spec for spec in all_specs()}
    budget = specs["user.budget"]
    assert (budget.type, budget.role) == (FactType.NUMBER, FactRole.INPUT)
    assert specs["user.resolution"].values == ("1080p", "1440p", "2160p")
    # открытые строки (сокеты, чипсеты) допустимых значений не имеют
    assert specs["build.cpu.socket"].values == ()
    assert specs["cand.socket"].values == ()
    # слоты компонентов — роль catalog, веса сценариев — derived
    assert specs["build.ram.capacity_gb"].role == FactRole.CATALOG
    assert specs["budget.share.gpu"].role == FactRole.DERIVED


def test_all_specs_is_sorted_and_unique() -> None:
    paths = [spec.path for spec in all_specs()]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
