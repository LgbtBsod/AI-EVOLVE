"""Предикаты схемы: Python-выражение -> Lua (транслятор по белому списку AST).

Язык условий один (sim.eval_pred): числа, ctx.<поле>, + - * / % **, сравнения
(в том числе цепочки), and/or, унарный минус, max/min/floor/ceil/abs. Раньше
lua_gen копировал выражение в Lua как есть - и работали только простые случаи:
`!=` в Lua синтаксическая ошибка, max/floor там не определены, а цепочка
`a < b < c` в Lua сравнивает boolean с числом и падает.

Правило, которое проверяет валидатор (check_boolean): операнды and/or и само
условие - сравнения (или and/or сравнений). В Lua 0 - истина, в Python - ложь,
поэтому числовой операнд в and/or дал бы разный результат в двух языках.

Обратный перевод не нужен: lua_gen пишет условие как pred("исходник", fn),
и загрузчик (tools/lua_bridge.py) отдаёт исходник как есть.
"""
from __future__ import annotations

import ast

_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%", ast.Pow: "^"}
_CMP = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "~="}
_FUNCS = {"max", "min", "floor", "ceil", "abs"}


class PredicateError(ValueError):
    pass


def _num(v) -> str:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise PredicateError(f"literal {v!r} not allowed")
    return repr(v) if isinstance(v, float) else str(v)


def _emit(node) -> str:
    if isinstance(node, ast.Expression):
        return _emit(node.body)
    if isinstance(node, ast.Constant):
        return _num(node.value)
    if isinstance(node, ast.Attribute):
        if not isinstance(node.value, ast.Name) or node.value.id != "ctx" or node.attr.startswith("_"):
            raise PredicateError("attribute access must be ctx.<field>")
        return f"ctx.{node.attr}"
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return f"({_emit(node.left)} {_BIN[type(node.op)]} {_emit(node.right)})"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _emit(node.operand)
        return inner if isinstance(node.op, ast.UAdd) else f"(-{inner})"
    if isinstance(node, ast.Compare):
        parts, left = [], node.left
        for op, right in zip(node.ops, node.comparators):
            if type(op) not in _CMP:
                raise PredicateError("comparison operator not allowed")
            parts.append(f"{_emit(left)} {_CMP[type(op)]} {_emit(right)}")
            left = right
        return parts[0] if len(parts) == 1 else "(" + " and ".join(parts) + ")"
    if isinstance(node, ast.BoolOp):
        word = " and " if isinstance(node.op, ast.And) else " or "
        return "(" + word.join(_emit(v) for v in node.values) + ")"
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS or node.keywords:
            raise PredicateError("call of non-whitelisted function")
        return f"math.{node.func.id}(" + ", ".join(_emit(a) for a in node.args) + ")"
    raise PredicateError(f"expression element not allowed: {type(node).__name__}")


def to_lua(expr: str) -> str:
    """Python-предикат -> Lua-выражение (без обёртки function)."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise PredicateError(f"invalid predicate {expr!r}: {exc}") from exc
    return _emit(tree)


def _is_boolean(node) -> bool:
    if isinstance(node, ast.Expression):
        return _is_boolean(node.body)
    if isinstance(node, ast.Compare):
        return True
    if isinstance(node, ast.BoolOp):
        return all(_is_boolean(v) for v in node.values)
    return False


def check_boolean(expr: str) -> list[str]:
    """Ошибки, если условие не булево (см. правило в docstring модуля)."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        to_lua(expr)
    except (SyntaxError, PredicateError) as exc:
        return [str(exc)]
    if not _is_boolean(tree):
        return [f"predicate {expr!r} must be a comparison or and/or of comparisons "
                "(0 is true in Lua but false in Python)"]
    return []
