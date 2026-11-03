"""Генератор правил из справочников (архитектура §6.4).

Чистая детерминированная функция: справочники → список правил, отсортированный по коду.
Каждое правило получает `origin: generated` и `source: tables/<файл>.yaml#<ключ>`.
"""

import re
from typing import Any

from app.expert.dsl.expr import format_value
from app.expert.dsl.schema import Rule
from app.expert.tables import RESOLUTIONS, AppLevel, KnowledgeTables, Preset

PRESET_TITLES = {Preset.MEDIUM: "средних", Preset.HIGH: "высоких", Preset.ULTRA: "ультра"}
LEVEL_TITLES = {AppLevel.BASIC: "базовой", AppLevel.PRO: "профессиональной"}
LEVEL_NAMES = {AppLevel.BASIC: "базовый", AppLevel.PRO: "профессиональный"}


def code_part(value: str) -> str:
    """Часть кода правила из идентификатора: `cyberpunk_2077` → `CYBERPUNK-2077`."""
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def _rule(
    code: str,
    name: str,
    kind: str,
    group: str,
    source: str,
    when: dict[str, Any],
    explain: str,
    *,
    then: list[dict[str, Any]] | None = None,
    goal: dict[str, Any] | None = None,
    priority: int,
    cf: float = 1.0,
) -> Rule:
    data: dict[str, Any] = {
        "code": code,
        "name": name,
        "kind": kind,
        "group": group,
        "priority": priority,
        "cf": cf,
        "origin": "generated",
        "source": source,
        "when": when,
        "explain": explain,
    }
    if then is not None:
        data["then"] = then
    if goal is not None:
        data["goal"] = goal
    return Rule.model_validate(data)


def _fact(path: str, op: str, value: object = None) -> dict[str, Any]:
    leaf: dict[str, Any] = {"fact": path, "op": op}
    if value is not None:
        leaf["value"] = value
    return leaf


def _reject(message: str) -> list[dict[str, Any]]:
    return [{"action": "reject", "message": message}]


def socket_rules(tables: KnowledgeTables) -> list[Rule]:
    """GEN-SKT: сокет ↔ чипсет ↔ тип памяти, перспективность платформы."""
    rules: list[Rule] = []
    by_socket = tables.chipsets_by_socket()
    for socket in tables.sockets:
        part, source = code_part(socket.id), f"tables/sockets.yaml#{socket.id}"
        chipsets = [c.id for c in by_socket[socket.id]]
        mem = ", ".join(socket.mem_types)
        rules.append(
            _rule(
                f"GEN-SKT-{part}-CHIPSET",
                f"Процессор {socket.id} — только на платах с чипсетами своей платформы",
                "compat",
                "gen_socket",
                source,
                {
                    "all": [
                        _fact("build.cpu.socket", "eq", socket.id),
                        _fact("build.motherboard.chipset", "not_in", chipsets),
                    ]
                },
                f"Процессоры {socket.id} работают только с чипсетами {', '.join(chipsets)}.",
                then=_reject(
                    "Плата на чипсете {build.motherboard.chipset} не поддерживает процессоры "
                    f"{socket.id}"
                ),
                priority=900,
            )
        )
        rules.append(
            _rule(
                f"GEN-SKT-{part}-MEM",
                f"Платформа {socket.id} работает только с памятью {mem}",
                "compat",
                "gen_socket",
                source,
                {
                    "all": [
                        _fact("build.cpu.socket", "eq", socket.id),
                        _fact("build.ram.mem_type", "not_in", socket.mem_types),
                    ]
                },
                f"Контроллер памяти процессоров {socket.id} поддерживает только {mem}.",
                then=_reject(f"Память {{build.ram.mem_type}} не подходит к платформе {socket.id}"),
                priority=900,
            )
        )
        weight, verdict = (
            (6.0, "ещё получит новые процессоры — можно будет обновить только CPU")
            if socket.perspective
            else (-3.0, "больше не получит новых процессоров — апгрейд потребует замены платы")
        )
        rules.append(
            _rule(
                f"GEN-SKT-{part}-FUTURE",
                f"Задел на будущее: платформа {socket.id}",
                "score",
                "gen_socket",
                source,
                {
                    "all": [
                        _fact("user.future_proof", "eq", True),
                        _fact("build.cpu.socket", "eq", socket.id),
                    ]
                },
                f"Платформа {socket.id} {verdict}.",
                then=[
                    {
                        "action": "prefer",
                        "weight": weight,
                        "message": f"Платформа {socket.id} {verdict}",
                    }
                ],
                priority=300,
                cf=0.8,
            )
        )
    return rules


def chipset_rules(tables: KnowledgeTables) -> list[Rule]:
    """GEN-CHP: предел TDP плат, разгон, PCIe 5.0."""
    rules: list[Rule] = []
    for chipset in tables.chipsets:
        part, source = code_part(chipset.id), f"tables/chipsets.yaml#{chipset.id}"
        on_chipset = _fact("build.motherboard.chipset", "eq", chipset.id)
        rules.append(
            _rule(
                f"GEN-CHP-{part}-TDP",
                f"Платы на {chipset.id} рассчитаны на CPU до {chipset.max_cpu_tdp_w} Вт",
                "compat",
                "gen_chipset",
                source,
                {"all": [on_chipset, _fact("build.cpu.tdp_w", "gt", chipset.max_cpu_tdp_w)]},
                f"Подсистема питания типичных плат на {chipset.id} рассчитана на процессоры "
                f"с TDP до {chipset.max_cpu_tdp_w} Вт: мощнее — перегрев и сброс частот.",
                then=_reject(
                    f"Платы на {chipset.id} рассчитаны на процессоры до "
                    f"{chipset.max_cpu_tdp_w} Вт, а у этого {{build.cpu.tdp_w}} Вт"
                ),
                priority=900,
            )
        )
        if not chipset.cpu_overclock:
            rules.append(
                _rule(
                    f"GEN-CHP-{part}-OC",
                    f"Чипсет {chipset.id} не поддерживает разгон процессора",
                    "validate",
                    "gen_chipset",
                    source,
                    {"all": [on_chipset, _fact("build.cpu.unlocked", "eq", True)]},
                    f"На {chipset.id} разблокированный множитель процессора не пригодится.",
                    then=[
                        {
                            "action": "warn",
                            "message": f"На чипсете {chipset.id} разгон процессора недоступен: "
                            "переплата за разблокированный множитель не окупится",
                        }
                    ],
                    priority=400,
                )
            )
        if chipset.gpu_pcie_gen >= 5:
            rules.append(
                _rule(
                    f"GEN-CHP-{part}-PCIE5",
                    f"Чипсет {chipset.id}: слот видеокарты PCIe 5.0",
                    "score",
                    "gen_chipset",
                    source,
                    {"all": [_fact("user.future_proof", "eq", True), on_chipset]},
                    f"Платы на {chipset.id} получают PCIe 5.0 для видеокарт будущих поколений.",
                    then=[
                        {
                            "action": "prefer",
                            "weight": 2.0,
                            "message": f"PCIe 5.0 на {chipset.id} — запас для новых видеокарт",
                        }
                    ],
                    priority=300,
                    cf=0.7,
                )
            )
    return rules


def form_factor_rules(tables: KnowledgeTables) -> list[Rule]:
    """GEN-FF: плата и БП в корпусе, размер корпуса, компактность."""
    rules: list[Rule] = []
    boards = tables.form_factors.motherboard
    for board in boards:
        part, source = code_part(board.id), f"tables/form_factors.yaml#motherboard.{board.id}"
        rules.append(
            _rule(
                f"GEN-FF-{part}-CASE",
                f"Плата {board.id} должна поддерживаться корпусом",
                "compat",
                "gen_form_factor",
                source,
                {
                    "expr": f"build.motherboard.form_factor == '{board.id}' and "
                    f"not contains(build.case.form_factors, '{board.id}')"
                },
                f"Плата {board.id} ({board.width_mm}×{board.height_mm} мм) крепится только "
                "в корпус с соответствующими стойками.",
                then=_reject(f"Корпус не рассчитан на плату {board.id}"),
                priority=900,
            )
        )
        bonus = max(boards, key=lambda b: b.rank).rank - board.rank - 1
        if bonus > 0:
            rules.append(
                _rule(
                    f"GEN-FF-{part}-COMPACT",
                    f"Компактная сборка: плата {board.id}",
                    "score",
                    "gen_form_factor",
                    source,
                    {
                        "all": [
                            _fact("profile.compact", "eq", True),
                            _fact("build.motherboard.form_factor", "eq", board.id),
                        ]
                    },
                    f"Плата {board.id} позволяет собрать компактный компьютер.",
                    then=[
                        {
                            "action": "prefer",
                            "weight": float(bonus * 2),
                            "message": f"Плата {board.id} подходит для компактной сборки",
                        }
                    ],
                    priority=300,
                    cf=0.8,
                )
            )
    for psu in tables.form_factors.psu:
        part, source = code_part(psu.id), f"tables/form_factors.yaml#psu.{psu.id}"
        rules.append(
            _rule(
                f"GEN-FF-PSU-{part}",
                f"Блок питания {psu.id} должен встать в отсек корпуса",
                "compat",
                "gen_form_factor",
                source,
                {
                    "all": [
                        _fact("build.psu.form_factor", "eq", psu.id),
                        _fact("build.case.psu_ff", "not_in", psu.fits_case_psu),
                    ]
                },
                f"Блок питания {psu.id} ставится в отсеки: {', '.join(psu.fits_case_psu)}.",
                then=_reject(f"Блок питания {psu.id} не встанет в отсек {{build.case.psu_ff}}"),
                priority=900,
            )
        )
    for size in tables.form_factors.case_sizes:
        too_big = [b.id for b in boards if b.rank > size.max_board_rank]
        if not too_big:
            continue
        rules.append(
            _rule(
                f"GEN-FF-SIZE-{code_part(size.size)}",
                f"Корпус «{size.size}»: только платы до нужного размера",
                "filter",
                "gen_form_factor",
                f"tables/form_factors.yaml#case_sizes.{size.size}",
                {
                    "all": [
                        _fact("req.case_size", "eq", size.size),
                        _fact("cand.category", "eq", "motherboard"),
                        _fact("cand.form_factor", "in", too_big),
                    ]
                },
                f"В корпус размера «{size.size}» не поместятся платы {', '.join(too_big)}.",
                then=_reject("Плата {cand.form_factor} крупнее выбранного размера корпуса"),
                priority=800,
            )
        )
    return rules


def game_rules(tables: KnowledgeTables) -> list[Rule]:
    """GEN-GAME: «игра пойдёт на пресете» для каждой игры и пресета (цели обратного вывода)."""
    rules: list[Rule] = []
    for game in tables.games:
        for preset in Preset:
            args = {"game": game.id, "preset": preset.value}
            conditions: list[dict[str, Any]] = [
                {
                    "goal": {
                        "predicate": "fps_at_least",
                        "args": {**args, "resolution": "$resolution", "fps": "$target_fps"},
                    }
                },
                {
                    "goal": {
                        "predicate": "vram_enough",
                        "args": {**args, "resolution": "$resolution"},
                    }
                },
                _fact("build.ram.capacity_gb", "ge", game.ram_min_gb),
            ]
            if game.rt_required:
                conditions.append(_fact("build.gpu.perf_rt", "exists"))
            vram = ", ".join(
                f"{res} — {format_value(game.vram_need.get(res, preset))} ГБ" for res in RESOLUTIONS
            )
            rt_note = (
                " Игре обязательно нужна видеокарта с трассировкой лучей."
                if game.rt_required
                else ""
            )
            rules.append(
                _rule(
                    f"GEN-GAME-{code_part(game.id)}-{code_part(preset.value)}",
                    f"{game.title}: {PRESET_TITLES[preset]} настройки",
                    "goal",
                    "gen_game",
                    f"tables/games.yaml#{game.id}",
                    {"all": conditions},
                    f"{game.title} на {PRESET_TITLES[preset]} настройках: FPS не ниже целевого, "
                    f"видеопамяти ({vram}) и ОЗУ от {game.ram_min_gb} ГБ.{rt_note}",
                    goal={"predicate": "runs_game", "args": args},
                    priority=100,
                )
            )
    return rules


def application_rules(tables: KnowledgeTables) -> list[Rule]:
    """GEN-APP: «программа подходит для работы на уровне» (цели обратного вывода)."""
    rules: list[Rule] = []
    for app in tables.applications:
        for level in AppLevel:
            req = app.basic if level is AppLevel.BASIC else app.pro
            args = {"app": app.id, "level": level.value}
            conditions: list[dict[str, Any]] = [
                {"goal": {"predicate": "bench_at_least", "args": args}},
                _fact("build.ram.capacity_gb", "ge", req.ram_min_gb),
                _fact("build.cpu.cores", "ge", req.cpu_cores_min),
            ]
            if req.vram_min_gb > 0:
                conditions.append(_fact("build.gpu.vram_gb", "ge", req.vram_min_gb))
            vram = f", видеопамять от {req.vram_min_gb} ГБ" if req.vram_min_gb else ""
            rules.append(
                _rule(
                    f"GEN-APP-{code_part(app.id)}-{code_part(level.value)}",
                    f"{app.title}: {LEVEL_NAMES[level]} уровень",
                    "goal",
                    "gen_app",
                    f"tables/applications.yaml#{app.id}",
                    {"all": conditions},
                    f"Для {LEVEL_TITLES[level]} работы в {app.title} нужно ОЗУ от "
                    f"{req.ram_min_gb} ГБ, процессор от {req.cpu_cores_min} ядер{vram}.",
                    goal={"predicate": "runs_app", "args": args},
                    priority=100,
                )
            )
    return rules


GENERATED_FILES: dict[str, str] = {
    "gen_socket": "GEN-SKT",
    "gen_chipset": "GEN-CHP",
    "gen_form_factor": "GEN-FF",
    "gen_game": "GEN-GAME",
    "gen_app": "GEN-APP",
}
"""Группа сгенерированных правил → имя файла в `knowledge/rules/generated/`."""


def generate_rules(tables: KnowledgeTables) -> list[Rule]:
    """Все сгенерированные правила, отсортированные по коду."""
    rules = [
        *socket_rules(tables),
        *chipset_rules(tables),
        *form_factor_rules(tables),
        *game_rules(tables),
        *application_rules(tables),
    ]
    return sorted(rules, key=lambda rule: rule.code)
