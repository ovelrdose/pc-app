"""Безопасный интерпретатор выражений и шаблоны объяснений."""

import pytest

from app.expert.dsl.expr import (
    ExprEvalError,
    ExprSyntaxError,
    MissingFactError,
    compile_expr,
    compile_template,
    format_value,
)
from app.expert.facts import Value

FACTS: dict[str, Value] = {
    "build.psu.wattage": 550,
    "build.cpu.tdp_w": 65,
    "build.gpu.tbp_w": 250,
    "build.gpu.chip": "GeForce RTX 5070",
    "build.case.form_factors": ("ATX", "Micro-ATX"),
    "user.white": True,
    "budget.share.gpu": 0.45,
    "req.zero": 0,
}


def resolve(path: str) -> Value:
    if path not in FACTS:
        raise MissingFactError(path)
    return FACTS[path]


def run(source: str) -> Value:
    return compile_expr(source).evaluate(resolve)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("build.psu.wattage < (build.cpu.tdp_w + build.gpu.tbp_w + 75) * 1.3", False),
        ("build.psu.wattage < (build.cpu.tdp_w + build.gpu.tbp_w + 175) * 1.3", True),
        ("ceil((build.cpu.tdp_w + build.gpu.tbp_w + 75) * 1.3)", 507),
        ("floor(10 / 4)", 2),
        ("10 // 4 + 10 % 4", 4),
        ("-build.cpu.tdp_w + +1", -64),
        ("abs(-3.5)", 3.5),
        ("round(2.345, 2)", 2.35),
        ("round(2.5)", 2),
        ("min(3, 1, 2)", 1),
        ("max([3, 1, 2])", 3),
        ("len(build.case.form_factors)", 2),
        ("contains(build.case.form_factors, 'ATX')", True),
        ("contains(build.gpu.chip, 'RTX')", True),
        ("'ATX' in build.case.form_factors", True),
        ("'E-ATX' not in build.case.form_factors", True),
        ("'RTX' in build.gpu.chip", True),
        ("100 < build.psu.wattage <= 550", True),
        ("100 < build.psu.wattage < 200", False),
        ("build.gpu.chip == 'GeForce RTX 5070' and user.white", True),
        ("not user.white or false", False),
        ("1 if user.white else 2", 1),
        ("build.gpu.chip != 'x'", True),
        ("'a' < 'b'", True),
    ],
)
def test_evaluation(source: str, expected: Value) -> None:
    assert run(source) == expected


def test_paths_are_collected() -> None:
    expression = compile_expr("build.psu.wattage < build.cpu.tdp_w + 10")
    assert expression.paths == {"build.psu.wattage", "build.cpu.tdp_w"}


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("__import__('os').system('ls')", "неизвестная функция"),
        ("(1).__class__", "путь факта"),
        ("build.psu.__class__", "недопустимая часть пути"),
        ("open.x", "пространство имён"),
        ("x + 1", "неизвестное имя"),
        ("build.cpu.tdp_w ** 2", "Pow"),
        ("build.case.form_factors[0]", "Subscript"),
        ("lambda: 1", "Lambda"),
        ("[i for i in build.case.form_factors]", "ListComp"),
        ("min(1, key=abs)", "именованные"),
        ("min(*build.case.form_factors)", "распакованные"),
        ("ceil(1, 2)", "число аргументов"),
        ("len()", "число аргументов"),
        ("{'a': 1}", "Dict"),
        ("b'x' == b'x'", "константа"),
        ("None", "константа"),
        ("1 +", "синтаксическая"),
        ("   ", "пустое"),
        ("1 + " * 300 + "1", "длиннее"),
        ("+".join(["1"] * 150), "сложное"),
        ("x := 1", "синтаксическая"),
    ],
)
def test_rejected_constructs(source: str, fragment: str) -> None:
    with pytest.raises(ExprSyntaxError, match=fragment):
        compile_expr(source)


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("build.psu.wattage / req.zero", "деление на ноль"),
        ("build.psu.wattage % req.zero", "деление на ноль"),
        ("build.gpu.chip + 1", "ожидается число"),
        ("build.gpu.chip < 5", "нельзя сравнить"),
        ("user.white < 1", "нельзя сравнить"),
        ("1 in build.psu.wattage", "справа ожидается список"),
        ("1 in build.gpu.chip", "слева ожидается строка"),
        ("build.psu.wattage and true", "логическое"),
        ("len(build.psu.wattage)", "len"),
        ("contains(build.psu.wattage, 1)", "contains"),
        ("round(1.5, 9)", "round"),
        ("min([])", "нет аргументов"),
        ("max([])", "нет аргументов"),
        ("[[1]]", "вложенные"),
        ("100000000 * 100000000", "слишком большое"),
    ],
)
def test_evaluation_errors(source: str, fragment: str) -> None:
    with pytest.raises(ExprEvalError, match=fragment):
        run(source)


def test_missing_fact() -> None:
    with pytest.raises(MissingFactError) as info:
        run("build.ram.capacity_gb >= 16")
    assert info.value.path == "build.ram.capacity_gb"


def test_short_circuit_skips_missing_fact() -> None:
    assert run("false and build.ram.capacity_gb >= 16") is False
    assert run("true or build.ram.capacity_gb >= 16") is True


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (True, "да"),
        (False, "нет"),
        (12.0, "12"),
        (0.455, "0,46"),
        (2.5, "2,5"),
        (("a", 1), "a, 1"),
        (999, "999"),
        (5520, "5\u00a0520"),
        (170000, "170\u00a0000"),
        (1_250_000.0, "1\u00a0250\u00a0000"),
        (-12500, "-12\u00a0500"),
    ],
)
def test_format_value(value: Value, text: str) -> None:
    assert format_value(value) == text


def test_template_rendering() -> None:
    template = compile_template(
        "БП {build.psu.wattage} Вт слабоват: нужно ≥ "
        "{ceil((build.cpu.tdp_w + build.gpu.tbp_w + 75) * 1.3)} Вт {{без скобок}}"
    )
    assert template.paths == {"build.psu.wattage", "build.cpu.tdp_w", "build.gpu.tbp_w"}
    assert template.render(resolve) == "БП 550 Вт слабоват: нужно ≥ 507 Вт {без скобок}"


def test_template_missing_value_shows_question_mark() -> None:
    assert compile_template("ОЗУ {build.ram.capacity_gb} ГБ").render(resolve) == "ОЗУ ? ГБ"


@pytest.mark.parametrize("source", ["{build.psu.wattage", "a } b", "{x{build.psu.wattage}"])
def test_template_unbalanced_braces(source: str) -> None:
    with pytest.raises(ExprSyntaxError):
        compile_template(source)


def test_template_without_placeholders() -> None:
    template = compile_template("Просто текст")
    assert template.render(resolve) == "Просто текст"
    assert template.paths == frozenset()
