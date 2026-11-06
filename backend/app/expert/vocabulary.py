"""Словарь фактов: какие пути существуют и какого они типа (фрейм «Профиль клиента»).

Пути `user.*` — входы (ответы визарда), `profile.*`, `req.*`, `budget.*` — выводы правил.
Пути `cand.*` и `build.<категория>.*` берутся из фреймов комплектующих. Валидатор базы знаний
проверяет по словарю, что правило не ссылается на несуществующий факт и сравнивает значения
подходящего типа.
"""

import types
import typing
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, StrEnum
from types import MappingProxyType

from app.expert.configurator.plan import Scenario
from app.expert.frames import FRAMES_BY_CATEGORY, Category


class FactType(StrEnum):
    """Тип значения факта."""

    NUMBER = "number"
    BOOL = "bool"
    STR = "str"
    LIST = "list"


class FactRole(StrEnum):
    """Кто устанавливает факт."""

    INPUT = "input"
    DERIVED = "derived"
    CATALOG = "catalog"
    COMPUTED = "computed"


@dataclass(frozen=True, slots=True)
class FactSpec:
    """Описание пути факта."""

    path: str
    type: FactType
    role: FactRole
    title: str
    values: tuple[str | int | float, ...] = ()


RESOLUTIONS = ("1080p", "1440p", "2160p")
REFRESH_RATES = (60, 75, 120, 144, 165, 240, 360)
COLORS = ("black", "white", "any")
CASE_SIZES = ("mini", "mid", "full", "any")
CPU_BRANDS = ("amd", "intel", "any")
GPU_BRANDS = ("nvidia", "amd", "any")
MEM_TYPES = ("DDR4", "DDR5", "any")
GAMING_TIERS = ("none", "light", "mid", "high", "extreme")
BUDGET_CLASSES = ("entry", "low", "mid", "high", "premium")
SCENARIOS = tuple(s.value for s in Scenario)
CATEGORIES = tuple(c.value for c in Category)


def _spec(
    path: str,
    type_: FactType,
    role: FactRole,
    title: str,
    values: tuple[str | int | float, ...] = (),
) -> FactSpec:
    return FactSpec(path, type_, role, title, values)


def _profile_specs() -> list[FactSpec]:
    n, b, s, lst = FactType.NUMBER, FactType.BOOL, FactType.STR, FactType.LIST
    i, d, c = FactRole.INPUT, FactRole.DERIVED, FactRole.COMPUTED
    specs = [
        _spec("user.budget", n, i, "Бюджет, ₽"),
        _spec("user.resolution", s, i, "Разрешение монитора", RESOLUTIONS),
        _spec("user.refresh_hz", n, i, "Частота монитора, Гц", REFRESH_RATES),
        _spec("user.games", lst, i, "Игры клиента"),
        _spec("user.apps", lst, i, "Программы клиента"),
        _spec("user.color", s, i, "Цвет сборки", COLORS),
        _spec("user.rgb", b, i, "Нужна RGB-подсветка"),
        _spec("user.glass", b, i, "Нужна стеклянная панель"),
        _spec("user.case_size", s, i, "Размер корпуса", CASE_SIZES),
        _spec("user.storage_gb", n, i, "Нужный объём SSD, ГБ"),
        _spec("user.archive", b, i, "Нужен HDD для архива"),
        _spec("user.future_proof", b, i, "Важен задел на будущее"),
        _spec("user.cpu_brand", s, i, "Предпочтение бренда CPU", CPU_BRANDS),
        _spec("user.gpu_brand", s, i, "Предпочтение бренда GPU", GPU_BRANDS),
        _spec("user.mem_type", s, i, "Тип оперативной памяти", MEM_TYPES),
        _spec("user.wifi", b, i, "Нужен Wi-Fi"),
        _spec("user.target_fps", n, i, "Комфортный FPS (спрашивается при проверке гипотез)"),
        _spec("profile.main", s, d, "Главный сценарий", SCENARIOS),
        _spec("profile.secondary", s, d, "Второй сценарий", SCENARIOS),
        _spec("profile.gaming", n, d, "Игровой вес"),
        _spec("profile.creator", n, d, "Вес творческих задач"),
        _spec("profile.workstation", b, d, "Рабочая станция"),
        _spec("profile.gaming_tier", s, d, "Класс игровой нагрузки", GAMING_TIERS),
        _spec("profile.budget_class", s, d, "Класс бюджета", BUDGET_CLASSES),
        _spec("profile.high_refresh", b, d, "Высокая частота монитора"),
        _spec("profile.aesthetic", b, d, "Важен внешний вид"),
        _spec("profile.compact", b, d, "Компактная сборка"),
        _spec("profile.ram_heavy", b, d, "Задачи требуют много памяти"),
        _spec("profile.gpu_compute", b, d, "Вычисления на видеокарте"),
        _spec("profile.multitask", b, d, "Несколько тяжёлых задач одновременно"),
        _spec("profile.no_dgpu", b, d, "Дискретная видеокарта не нужна"),
        _spec("profile.raytracing", b, d, "Важна трассировка лучей"),
        _spec("req.gpu_vram_min_gb", n, d, "Минимум видеопамяти, ГБ"),
        _spec("req.gpu_raster_min", n, d, "Мощность видеокарты в играх (индекс, RTX 4060 = 100)"),
        _spec("req.gpu_rt_min", n, d, "Видеокарта с трассировкой (индекс, RTX 4060 = 100)"),
        _spec("req.cpu_single_min", n, d, "Скорость CPU на одно ядро (индекс, Ryzen 5 7600 = 100)"),
        _spec("req.cpu_multi_min", n, d, "Скорость CPU на всех ядрах (индекс, Ryzen 5 7600 = 100)"),
        _spec("req.cpu_cores_min", n, d, "Минимум ядер CPU"),
        _spec("req.cpu_igpu", b, d, "Нужна встроенная графика"),
        _spec("req.ram_min_gb", n, d, "Минимум ОЗУ, ГБ"),
        _spec("req.ram_dual_channel", b, d, "Нужны две планки"),
        _spec("req.storage_min_gb", n, d, "Минимум SSD, ГБ"),
        _spec("req.storage_nvme", b, d, "Нужен NVMe"),
        _spec("req.hdd_min_gb", n, d, "Минимум HDD, ГБ"),
        _spec("req.psu_headroom", n, d, "Запас мощности БП (доля)"),
        _spec("req.psu_quality", b, d, "Нужен качественный БП (Gold+)"),
        _spec("req.wifi", b, d, "Нужен Wi-Fi на плате"),
        _spec("req.color", s, d, "Цвет корпуса", ("black", "white")),
        _spec("req.rgb", b, d, "Нужна подсветка"),
        _spec("req.glass", b, d, "Нужна стеклянная панель"),
        _spec("req.case_size", s, d, "Размер корпуса", ("mini", "mid", "full")),
        _spec("req.cpu_brand", s, d, "Бренд CPU", ("amd", "intel")),
        _spec("req.gpu_brand", s, d, "Бренд GPU", ("nvidia", "amd")),
        _spec("req.mem_type", s, d, "Тип оперативной памяти", ("DDR4", "DDR5")),
        _spec("req.cooler_margin", n, d, "Запас кулера по TDP (доля)"),
        _spec("req.vrm_min", s, d, "Минимальный класс VRM", ("basic", "mid", "high")),
        _spec("req.extra_fans", n, d, "Сколько вентиляторов докупить"),
        _spec("need.gpu_raster", n, c, "Индекс видеокарты для комфортного FPS в играх клиента"),
        _spec("need.gpu_game", s, c, "Самая требовательная к видеокарте игра клиента"),
        _spec("need.gpu_fps", n, c, "Комфортный FPS в этой игре"),
        _spec("need.gpu_rt", n, c, "Индекс трассировки для игр с обязательной трассировкой"),
        _spec("need.rt_game", s, c, "Самая требовательная игра с обязательной трассировкой"),
        _spec("need.cpu_single", n, c, "Одноядерный индекс процессора для комфортного FPS"),
        _spec("need.cpu_game", s, c, "Самая требовательная к процессору игра клиента"),
        _spec("need.cpu_fps", n, c, "Комфортный FPS в этой игре"),
        _spec("budget.first_category", s, d, "Что подбирать первым", CATEGORIES),
    ]
    for scenario in SCENARIOS:
        specs.append(_spec(f"user.weight.{scenario}", n, i, f"Вес сценария {scenario} (ответ)"))
        specs.append(_spec(f"profile.weight.{scenario}", n, d, f"Вес сценария {scenario}"))
    for category in CATEGORIES:
        specs.append(_spec(f"req.need.{category}", b, d, f"Нужна категория {category}"))
        specs.append(_spec(f"budget.share.{category}", n, d, f"Доля бюджета: {category}"))
    return specs


VOCABULARY: Mapping[str, FactSpec] = MappingProxyType({s.path: s for s in _profile_specs()})

BUILD_TOTALS: Mapping[str, FactSpec] = MappingProxyType(
    {
        "perf.fps_avg": _spec(
            "perf.fps_avg", FactType.NUMBER, FactRole.COMPUTED, "Средний FPS в играх клиента"
        ),
        "perf.bottleneck_ratio": _spec(
            "perf.bottleneck_ratio",
            FactType.NUMBER,
            FactRole.COMPUTED,
            "Соотношение CPU/GPU: < 1 — упор в процессор",
        ),
        "perf.gpu_utilization": _spec(
            "perf.gpu_utilization",
            FactType.NUMBER,
            FactRole.COMPUTED,
            "На сколько процессор раскрывает видеокарту (0…1)",
        ),
        "perf.limited_by": _spec(
            "perf.limited_by",
            FactType.STR,
            FactRole.COMPUTED,
            "Что ограничивает FPS",
            ("cpu", "gpu"),
        ),
        "build.total.price_rub": _spec(
            "build.total.price_rub", FactType.NUMBER, FactRole.COMPUTED, "Цена сборки, ₽"
        ),
        "build.total.power_w": _spec(
            "build.total.power_w", FactType.NUMBER, FactRole.COMPUTED, "Оценка потребления, Вт"
        ),
        "build.total.parts": _spec(
            "build.total.parts", FactType.NUMBER, FactRole.COMPUTED, "Деталей в сборке"
        ),
    }
)


def annotation_type(annotation: object) -> tuple[FactType, tuple[str | int | float, ...]]:
    """Тип факта и допустимые значения по аннотации слота фрейма."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return annotation_type(args[0])
    if origin is list:
        return FactType.LIST, ()
    if origin is typing.Literal:
        values = typing.get_args(annotation)
        kind = FactType.NUMBER if all(isinstance(v, int) for v in values) else FactType.STR
        return kind, tuple(values)
    if origin is typing.Annotated:
        return annotation_type(typing.get_args(annotation)[0])
    if annotation is bool:
        return FactType.BOOL, ()
    if annotation in (int, float):
        return FactType.NUMBER, ()
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return FactType.STR, tuple(str(item.value) for item in annotation)
    return FactType.STR, ()


def _slot_specs(prefix: str, category: Category, role: FactRole) -> dict[str, FactSpec]:
    frame = FRAMES_BY_CATEGORY[category]
    specs: dict[str, FactSpec] = {}
    for name, info in frame.model_fields.items():
        kind, values = annotation_type(info.annotation)
        if name == "category":
            values = ()
        specs[f"{prefix}.{name}"] = FactSpec(
            f"{prefix}.{name}", kind, role, info.title or name, values
        )
    return specs


def _component_specs() -> tuple[dict[str, FactSpec], dict[str, list[FactSpec]]]:
    build: dict[str, FactSpec] = {}
    cand: dict[str, list[FactSpec]] = {}
    for category in Category:
        prefix = f"build.{category.value}"
        build.update(_slot_specs(prefix, category, FactRole.CATALOG))
        for flag, title in (("owned", "Деталь уже есть у клиента"), ("locked", "Зафиксирована")):
            path = f"{prefix}.{flag}"
            build[path] = FactSpec(path, FactType.BOOL, FactRole.COMPUTED, title)
        for path, spec in _slot_specs("cand", category, FactRole.CATALOG).items():
            cand.setdefault(path, []).append(spec)
    return build, cand


_BUILD_SPECS, _CAND_SPECS = _component_specs()


def lookup(path: str) -> FactSpec | None:
    """Описание пути факта или `None`, если такого факта нет.

    Для `cand.<слот>` слот может быть у нескольких категорий; если типы совпадают, допустимые
    значения объединяются.
    """
    spec = VOCABULARY.get(path) or BUILD_TOTALS.get(path) or _BUILD_SPECS.get(path)
    if spec is not None:
        return spec
    variants = _CAND_SPECS.get(path)
    if not variants:
        return None
    kinds = {variant.type for variant in variants}
    kind = variants[0].type if len(kinds) == 1 else FactType.STR
    values: list[str | int | float] = []
    for variant in variants:
        values.extend(v for v in variant.values if v not in values)
    open_values = any(not variant.values for variant in variants)
    return FactSpec(
        path, kind, FactRole.CATALOG, variants[0].title, () if open_values else tuple(values)
    )


def input_paths() -> frozenset[str]:
    """Пути, которые устанавливает пользователь."""
    return frozenset(p for p, s in VOCABULARY.items() if s.role is FactRole.INPUT)


def all_specs() -> list[FactSpec]:
    """Все известные факты: входы пользователя, выводы правил, слоты `build.*` и `cand.*`.

    Публичный словарь фактов для конструктора условий админки: путь, тип, роль,
    название и допустимые значения (если слот — перечисление). Чистая функция, без IO.
    """
    merged: dict[str, FactSpec] = {}
    for source in (VOCABULARY, BUILD_TOTALS, _BUILD_SPECS):
        merged.update(source)
    for path, variants in _CAND_SPECS.items():
        merged[path] = lookup(path) or variants[0]
    return [merged[path] for path in sorted(merged)]
