"""
Lua -> JSON парсер для Effect Schema v1 (round-trip с lua_gen).

Реализован рекурсивным descent-парсером подмножества Lua-table синтаксиса,
которое генерирует lua_gen: таблицы, строки, числа, булевы, комментарии,
`function(ctx) return <expr> end` (сохраняется как предикат-строка),
`PRED["name"](ctx)` (сохраняется как "name").

API:
    parse_lua(text) -> object (dict/list/scalar)
    load_item_file(path) -> {"item": {...}, "effects": [...]}
"""

from __future__ import annotations

import re
from pathlib import Path


class LuaParseError(Exception):
    pass


_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>--\[\[[\s\S]*?\]\]|--[^\n]*)
  | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<func>function\s*\(\s*\w*\s*\))
  | (?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|-?\.\d+)
  | (?P<name>[A-Za-z_][\w:.]*)
  | (?P<punct>[{}()\[\],;=<>/+\-*%.]+)
""", re.VERBOSE)


_MULTI_OPS = {"..=", "...", "==", "~=", "<=", ">=", "//"}


def _split_punct(val: str):
    """Разбивает punct-токен на атомарные операторы (`},` -> `}`, `,`)."""
    out, i = [], 0
    while i < len(val):
        for op in _MULTI_OPS:  # длинные раньше коротких
            if val.startswith(op, i):
                out.append(op)
                i += len(op)
                break
        else:
            out.append(val[i])
            i += 1
    return out


def _normalize_expr(expr: str) -> str:
    """Канонизация строки-выражения после токенизации (round-trip стабильность).

    Токенизатор вставляет пробелы между токенами; убираем их вокруг
    скобок/точек, чтобы `ctx.hp_pct < 40` не превращалось в `ctx . hp_pct ...`.
    """
    expr = re.sub(r"\s*([().,])\s*", r"\1", expr)
    expr = re.sub(r"(?<!:)/(?!=)", " / ", expr)   # деление != путь
    expr = re.sub(r"(?<![<>=~])=(?!=|>)", " = ", expr)
    expr = re.sub(r"<(?!=)", " <", expr)
    expr = re.sub(r">(?!=)", " >", expr)
    expr = expr.replace(" < =", " <=").replace(" > =", " >=").replace(" = =", " ==")
    expr = expr.replace(" !", "!").replace("~ ", "~")
    expr = re.sub(r" {2,}", " ", expr)
    return expr.strip()


def _tokenize(src: str):
    toks = []
    i = 0
    while i < len(src):
        m = _TOKEN_RE.match(src, i)
        if not m:
            raise LuaParseError(f"unexpected char {src[i]!r} at {i}")
        i = m.end()
        kind = m.lastgroup
        if kind in ("ws", "comment"):
            continue
        if kind == "punct":
            toks.extend(("punct", p) for p in _split_punct(m.group()))
        else:
            toks.append((kind, m.group()))
    return toks


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.pos = 0

    def peek(self, k=0):
        return self.toks[self.pos + k] if self.pos + k < len(self.toks) else (None, None)

    def next(self):
        t = self.peek()
        self.pos += 1
        return t

    def expect_punct(self, s):
        kind, val = self.next()
        if kind != "punct" or val != s:
            raise LuaParseError(f"expected {s!r}, got {val!r}")

    # --- values -----------------------------------------------------
    def parse_value(self):
        kind, val = self.peek()
        if kind == "punct" and val == "{":
            return self.parse_table()
        if kind == "string":
            self.next()
            return _unquote(val)
        if kind == "num":
            self.next()
            f = float(val)
            return int(f) if f.is_integer() and "." not in val and "e" not in val.lower() else f
        if kind == "name":
            if val in ("true", "false", "nil"):
                self.next()
                return {"true": True, "false": False, "nil": None}[val]
            # вызов: name [ ... ] ( ... )  -> схлопнуть в строку-выражение
            if self.peek(1)[0] == "punct" and self.peek(1)[1] in ("[", "("):
                return self.parse_call_expr()
            self.next()
            return val
        if kind == "func":
            return self.parse_function_pred()
        raise LuaParseError(f"unexpected token {val!r}")

    def parse_call_expr(self):
        """PRED["name"](ctx) и т.п. -> строка; PRED["x"] распознаётся в имя."""
        parts = []
        depth_brackets = depth_parens = 0
        while True:
            kind, val = self.peek()
            if kind is None:
                break
            if kind == "punct":
                if "[" in val:
                    depth_brackets += val.count("[")
                if "]" in val:
                    depth_brackets -= val.count("]")
                if "(" in val:
                    depth_parens += val.count("(")
                if ")" in val:
                    depth_parens -= val.count(")")
                if depth_brackets <= 0 and depth_parens <= 0 and \
                        not any(c in val for c in "[]()"):
                    break
            parts.append(self.next()[1])
        expr = " ".join(parts)
        expr = re.sub(r"\s+", " ", expr).strip()
        expr = _normalize_expr(expr)
        m = re.fullmatch(r'PRED \[ "(.*?)" \] \( ctx \)', expr)
        if m:
            return m.group(1)
        return expr

    def parse_function_pred(self):
        """function(ctx) return <expr-text> end -> предикат-строка."""
        self.next()  # func token
        expr_parts = []
        depth = 0
        # collect until matching `end`
        while True:
            kind, val = self.next()
            if kind is None:
                raise LuaParseError("unterminated function")
            if kind == "name" and val == "function":
                depth += 1
            if kind == "name" and val == "end":
                if depth == 0:
                    break
                depth -= 1
            if kind == "name" and val == "return" and not expr_parts:
                continue
            expr_parts.append(val)
        expr = " ".join(expr_parts)
        expr = re.sub(r"\s+", " ", expr).strip()
        expr = _normalize_expr(expr)
        # PRED [ "name" ] ( ctx ) -> name
        m = re.fullmatch(r'PRED \[ "(.*?)" \] \( ctx \)', expr)
        if m:
            return m.group(1)
        # ( expr ) unwrap
        if expr.startswith("(") and expr.endswith(")"):
            inner = expr[1:-1]
            if inner.count("(") == inner.count(")"):
                expr = inner
        return expr

    def parse_table(self):
        self.expect_punct("{")
        result = {}
        arr = []
        is_array = True
        while True:
            kind, val = self.peek()
            if kind == "punct" and val == "}":
                self.next()
                break
            if kind is None:
                raise LuaParseError("unterminated table")
            # key = value  or  value
            if (kind == "name" and self.peek(1)[0] == "punct"
                    and self.peek(1)[1].startswith("=")
                    and not self.peek(1)[1].startswith("==")):
                key = self.next()[1]
                self.next()  # '='
                v = self.parse_value()
                is_array = False
                result[key] = v
            elif kind == "punct" and val == "[":
                self.next()
                k = self.parse_value()
                self.expect_punct("]")
                self.expect_punct("=")
                result[str(k)] = self.parse_value()
                is_array = False
            else:
                v = self.parse_value()
                arr.append(v)
            kind, val = self.peek()
            if kind == "punct" and val.startswith(",") or (kind == "punct" and val == ";"):
                self.next()
        if is_array and not result:
            return arr
        if not is_array and arr:
            result.setdefault("_list", arr)
        return result


def _unquote(s: str) -> str:
    body = s[1:-1]
    return body.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")


def parse_lua(text: str):
    # strip leading comments, then `return` (префикс `--...` совпадал с
    # регэкспом из-за того, что `.` матчит и `-`)
    text = text.strip()
    while text.startswith("--"):
        nl = text.find("\n")
        if nl == -1:
            return None
        text = text[nl + 1:].lstrip()
    m = re.match(r"^return\s+", text)
    if m:
        text = text[m.end():]
    toks = _tokenize(text)
    p = _Parser(toks)
    val = p.parse_value()
    return val


def load_item_file(path) -> dict:
    data = parse_lua(Path(path).read_text(encoding="utf-8"))
    effects = data.pop("effects", []) if isinstance(data, dict) else []
    return {"item": data, "effects": effects}
