"""Безопасный интерпретатор выражений правил и шаблонов объяснений.

Текст разбирается стандартным `ast.parse`, но **не исполняется** Python: дерево проверяется по
белому списку узлов и вычисляется собственным обходом. Доступны арифметика, сравнения, логика,
пути фактов (`build.psu.wattage`) и функции из `FUNCTIONS`. Никаких атрибутов объектов,
индексов, импортов, лямбд, возведения в степень и вызова произвольного кода.
"""

import ast
import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from app.expert.facts import NAMESPACES, Scalar, Value

MAX_SOURCE_LENGTH = 500
MAX_NODES = 200
MAX_MAGNITUDE = 1e15
SEGMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")
CONSTANT_NAMES: dict[str, Value] = {"true": True, "false": False}

type Resolver = Callable[[str], Value]


class ExprSyntaxError(ValueError):
    """Выражение не разбирается или использует запрещённые конструкции."""


class ExprEvalError(ValueError):
    """Ошибка при вычислении: деление на ноль, несовместимые типы и т.п."""


class MissingFactError(ExprEvalError):
    """Выражение ссылается на факт, которого нет (или он ниже порога уверенности)."""

    def __init__(self, path: str) -> None:
        super().__init__(f"нет факта {path}")
        self.path = path


def _number(value: Value, what: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExprEvalError(f"{what}: ожидается число, получено «{value}»")
    return value


def _fn_min(*args: Value) -> Value:
    items = args[0] if len(args) == 1 and isinstance(args[0], tuple) else args
    if not items:
        raise ExprEvalError("min: нет аргументов")
    return min(_number(item, "min") for item in items)


def _fn_max(*args: Value) -> Value:
    items = args[0] if len(args) == 1 and isinstance(args[0], tuple) else args
    if not items:
        raise ExprEvalError("max: нет аргументов")
    return max(_number(item, "max") for item in items)


def _fn_ceil(value: Value) -> Value:
    return math.ceil(_number(value, "ceil"))


def _fn_floor(value: Value) -> Value:
    return math.floor(_number(value, "floor"))


def _fn_abs(value: Value) -> Value:
    return abs(_number(value, "abs"))


def _fn_round(value: Value, digits: Value = 0) -> Value:
    places = _number(digits, "round")
    if not isinstance(places, int) or not 0 <= places <= 6:
        raise ExprEvalError("round: число знаков — целое от 0 до 6")
    result = round(_number(value, "round"), places)
    return int(result) if places == 0 else result


def _fn_len(value: Value) -> Value:
    if not isinstance(value, tuple | str):
        raise ExprEvalError(f"len: ожидается список или строка, получено «{value}»")
    return len(value)


def _fn_contains(container: Value, item: Value) -> Value:
    if isinstance(container, tuple):
        return item in container
    if isinstance(container, str) and isinstance(item, str):
        return item in container
    raise ExprEvalError(f"contains: ожидается список или строка, получено «{container}»")


FUNCTIONS: dict[str, tuple[Callable[..., Value], int, int]] = {
    # имя: (реализация, минимум аргументов, максимум аргументов)
    "min": (_fn_min, 1, 16),
    "max": (_fn_max, 1, 16),
    "ceil": (_fn_ceil, 1, 1),
    "floor": (_fn_floor, 1, 1),
    "abs": (_fn_abs, 1, 1),
    "round": (_fn_round, 1, 2),
    "len": (_fn_len, 1, 1),
    "contains": (_fn_contains, 2, 2),
}

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.UnaryOp,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.IfExp,
    ast.Call,
    ast.Name,
    ast.Attribute,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
)


def _dotted_path(node: ast.Attribute) -> str:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        raise ExprSyntaxError("путь факта должен состоять из имён через точку")
    parts.append(current.id)
    parts.reverse()
    if parts[0] not in NAMESPACES:
        raise ExprSyntaxError(
            f"неизвестное пространство имён «{parts[0]}» в пути {'.'.join(parts)}"
        )
    for part in parts:
        if not SEGMENT_PATTERN.match(part):
            raise ExprSyntaxError(f"недопустимая часть пути «{part}»")
    return ".".join(parts)


class _Validator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.paths: set[str] = set()
        self.nodes = 0

    def generic_visit(self, node: ast.AST) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ExprSyntaxError("выражение слишком сложное")
        if not isinstance(node, _ALLOWED_NODES):
            raise ExprSyntaxError(f"недопустимая конструкция: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.nodes += 1
        self.paths.add(_dotted_path(node))

    def visit_Name(self, node: ast.Name) -> None:
        self.nodes += 1
        if node.id not in CONSTANT_NAMES:
            raise ExprSyntaxError(f"неизвестное имя «{node.id}»")

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            name = node.func.id if isinstance(node.func, ast.Name) else "?"
            raise ExprSyntaxError(f"неизвестная функция «{name}»")
        if node.keywords or any(isinstance(arg, ast.Starred) for arg in node.args):
            raise ExprSyntaxError("именованные и распакованные аргументы запрещены")
        _, low, high = FUNCTIONS[node.func.id]
        if not low <= len(node.args) <= high:
            raise ExprSyntaxError(f"{node.func.id}: неверное число аргументов")
        self.nodes += 1
        for arg in node.args:
            self.visit(arg)

    def visit_Constant(self, node: ast.Constant) -> None:
        self.nodes += 1
        if not isinstance(node.value, str | int | float | bool):
            raise ExprSyntaxError(f"недопустимая константа {node.value!r}")


@dataclass(frozen=True, slots=True)
class Expression:
    """Скомпилированное выражение: исходный текст, дерево и пути фактов, которые оно читает."""

    source: str
    tree: ast.Expression
    paths: frozenset[str]

    def evaluate(self, resolve: Resolver) -> Value:
        """Вычисляет выражение; значения фактов берёт через `resolve(path)`."""
        return _Evaluator(resolve).eval(self.tree.body)


def compile_expr(source: str) -> Expression:
    """Разбирает и проверяет выражение; `ExprSyntaxError` с понятным сообщением при ошибке."""
    text = source.strip()
    if not text:
        raise ExprSyntaxError("пустое выражение")
    if len(text) > MAX_SOURCE_LENGTH:
        raise ExprSyntaxError(f"выражение длиннее {MAX_SOURCE_LENGTH} символов")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ExprSyntaxError(f"синтаксическая ошибка: {exc.msg}") from exc
    validator = _Validator()
    validator.visit(tree)
    return Expression(text, tree, frozenset(validator.paths))


class _Evaluator:
    def __init__(self, resolve: Resolver) -> None:
        self.resolve = resolve

    def eval(self, node: ast.expr) -> Value:
        match node:
            case ast.Constant(value=str() | int() | float() as value):
                return value
            case ast.Name(id=name):
                return CONSTANT_NAMES[name]
            case ast.Attribute():
                return self.resolve(_dotted_path(node))
            case ast.List(elts=items) | ast.Tuple(elts=items):
                return tuple(self._scalar(self.eval(item)) for item in items)
            case ast.BoolOp(op=op, values=values):
                return self._bool_op(op, values)
            case ast.UnaryOp(op=ast.Not(), operand=operand):
                return not self._truth(self.eval(operand))
            case ast.UnaryOp(op=op, operand=operand):
                number = _number(self.eval(operand), "унарный минус")
                return -number if isinstance(op, ast.USub) else number
            case ast.BinOp(left=left, op=op, right=right):
                return self._bin_op(op, self.eval(left), self.eval(right))
            case ast.Compare(left=left, ops=ops, comparators=comparators):
                return self._compare(left, ops, comparators)
            case ast.IfExp(test=test, body=body, orelse=orelse):
                return self.eval(body) if self._truth(self.eval(test)) else self.eval(orelse)
            case ast.Call(func=ast.Name(id=name), args=args):
                function = FUNCTIONS[name][0]
                return self._checked(function(*(self.eval(arg) for arg in args)))
        raise ExprEvalError(f"неподдерживаемый узел {type(node).__name__}")  # pragma: no cover

    @staticmethod
    def _scalar(value: Value) -> Scalar:
        if isinstance(value, tuple):
            raise ExprEvalError("вложенные списки не поддерживаются")
        return value

    @staticmethod
    def _truth(value: Value) -> bool:
        if not isinstance(value, bool):
            raise ExprEvalError(f"ожидается логическое значение, получено «{value}»")
        return value

    def _bool_op(self, op: ast.boolop, values: list[ast.expr]) -> bool:
        is_and = isinstance(op, ast.And)
        for item in values:
            if self._truth(self.eval(item)) != is_and:
                return not is_and
        return is_and

    @staticmethod
    def _checked(value: Value) -> Value:
        is_number = isinstance(value, int | float) and not isinstance(value, bool)
        if is_number and (math.isnan(value) or abs(value) > MAX_MAGNITUDE):  # type: ignore[arg-type]
            raise ExprEvalError("слишком большое число")
        return value

    def _bin_op(self, op: ast.operator, left: Value, right: Value) -> Value:
        a, b = _number(left, "арифметика"), _number(right, "арифметика")
        if isinstance(op, ast.Div | ast.FloorDiv | ast.Mod) and b == 0:
            raise ExprEvalError("деление на ноль")
        match op:
            case ast.Add():
                result = a + b
            case ast.Sub():
                result = a - b
            case ast.Mult():
                result = a * b
            case ast.Div():
                result = a / b
            case ast.FloorDiv():
                result = a // b
            case _:
                result = a % b
        return self._checked(result)

    def _compare(self, left: ast.expr, ops: list[ast.cmpop], comparators: list[ast.expr]) -> bool:
        current = self.eval(left)
        for op, node in zip(ops, comparators, strict=True):
            other = self.eval(node)
            if not compare_values(op, current, other):
                return False
            current = other
        return True


def compare_values(op: ast.cmpop, left: Value, right: Value) -> bool:
    """Сравнение с проверкой типов: упорядочиваются только числа с числами и строки со строками."""
    match op:
        case ast.Eq():
            return left == right
        case ast.NotEq():
            return left != right
        case ast.In() | ast.NotIn():
            if not isinstance(right, tuple | str):
                raise ExprEvalError(f"«in»: справа ожидается список, получено «{right}»")
            if isinstance(right, str) and not isinstance(left, str):
                raise ExprEvalError("«in» по строке: слева ожидается строка")
            found = left in right
            return found if isinstance(op, ast.In) else not found
    both_numbers = all(
        isinstance(v, int | float) and not isinstance(v, bool) for v in (left, right)
    )
    both_strings = isinstance(left, str) and isinstance(right, str)
    if not (both_numbers or both_strings):
        raise ExprEvalError(f"нельзя сравнить «{left}» и «{right}»")
    a, b = left, right
    match op:
        case ast.Lt():
            return a < b  # type: ignore[operator]
        case ast.LtE():
            return a <= b  # type: ignore[operator]
        case ast.Gt():
            return a > b  # type: ignore[operator]
        case _:
            return a >= b  # type: ignore[operator]


# --- Шаблоны объяснений: «БП {build.psu.wattage} Вт слабоват» -------------------------------

_PLACEHOLDER = re.compile(r"\{\{|\}\}|\{([^{}]+)\}")
MISSING_PLACEHOLDER = "?"


NBSP = "\u00a0"


def format_number(value: int) -> str:
    """Целое с неразрывным пробелом между разрядами: 170000 → «170 000», 5520 → «5 520».

    Разряды отделяются с тысячи — так же, как суммы в интерфейсе (Intl, ru-RU).
    """
    return f"{value:,}".replace(",", NBSP)


def format_value(value: Value) -> str:
    """Значение для текста: «да/нет», целые без «.0» и с разрядами, дроби с запятой, списки."""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, int):
        return format_number(value)
    if isinstance(value, float):
        if value.is_integer():
            return format_number(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    if isinstance(value, tuple):
        return ", ".join(format_value(item) for item in value)
    return str(value)


@dataclass(frozen=True, slots=True)
class Template:
    """Скомпилированный шаблон: чередование текста и выражений."""

    source: str
    parts: tuple[str | Expression, ...]

    @property
    def paths(self) -> frozenset[str]:
        """Пути фактов, которые читает шаблон."""
        return frozenset(
            p for part in self.parts if isinstance(part, Expression) for p in part.paths
        )

    def render(self, resolve: Resolver) -> str:
        """Подставляет значения; если факта нет или выражение не вычислилось — «?»."""
        chunks: list[str] = []
        for part in self.parts:
            if isinstance(part, str):
                chunks.append(part)
                continue
            try:
                chunks.append(format_value(part.evaluate(resolve)))
            except ExprEvalError:
                chunks.append(MISSING_PLACEHOLDER)
        return "".join(chunks)


def compile_template(source: str) -> Template:
    """Разбирает шаблон: `{выражение}` подставляется, `{{` и `}}` — литеральные скобки."""
    parts: list[str | Expression] = []
    position = 0
    for match in _PLACEHOLDER.finditer(source):
        text = source[position : match.start()]
        if "{" in text or "}" in text:
            raise ExprSyntaxError("непарная фигурная скобка в шаблоне")
        token = match.group(0)
        if token in ("{{", "}}"):
            parts.append(text + token[0])
        else:
            if text:
                parts.append(text)
            parts.append(compile_expr(match.group(1)))
        position = match.end()
    rest = source[position:]
    if "{" in rest or "}" in rest:
        raise ExprSyntaxError("непарная фигурная скобка в шаблоне")
    if rest:
        parts.append(rest)
    return Template(source, tuple(parts))
