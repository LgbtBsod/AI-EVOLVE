"""file_toc - the table of contents of a source file in a few lines (stdlib only: behind `qa.py ctx` and the read guard hook).

    outline(path, ranges=False, methods=True)   # Python via ast: `L4 class A  # doc`, `  L6 .run(x)`, `L9 def f(y)` (ranges=True: `L4-9`)
    outline_for(path, data, cfg, max_lines)     # any file: Python -> ast (compact tiers), other languages -> the regexes of guards.lua `outline.by_ext`
"""
from __future__ import annotations

import ast
import os
import re


def _sig(fn) -> str:
    a = fn.args
    names = [x.arg for x in (*a.posonlyargs, *a.args)]
    if a.vararg:
        names.append("*" + a.vararg.arg)
    names += [x.arg for x in a.kwonlyargs]
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    return ", ".join(n for n in names if n not in ("self", "cls"))


def _doc1(node) -> str:
    d = (ast.get_docstring(node) or "").strip().splitlines()
    return f"  # {d[0][:70]}" if d else ""


def _span(node, ranges: bool) -> str:
    end = getattr(node, "end_lineno", None)
    return f"L{node.lineno}-{end}" if ranges and end and end != node.lineno else f"L{node.lineno}"


def _methods(node) -> list:
    """Public methods and __init__ (the other dunders are noise)."""
    funcs = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return [m for m in funcs if not (m.name.startswith("__") and m.name != "__init__")]


def _class_lines(node, ranges: bool, methods: bool) -> list[str]:
    shown = _methods(node)
    if not methods:
        return [f"{_span(node, ranges)} class {node.name}" + (f"  ({len(shown)} methods)" if shown else "")]
    return [f"{_span(node, ranges)} class {node.name}{_doc1(node)}",
            *(f"  {_span(m, ranges)} .{m.name}({_sig(m)}){_doc1(m)}" for m in shown)]


def _is_const(node) -> bool:
    return isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets)


def python_outline(source: str | ast.Module, ranges: bool = False, methods: bool = True, consts: bool = True) -> list[str]:
    """Classes/methods/functions with signatures and the first docstring line (+ UPPER_CASE constants). `source`: text or an already parsed module."""
    lines: list[str] = []
    for node in (ast.parse(source) if isinstance(source, str) else source).body:
        if isinstance(node, ast.ClassDef):
            lines += _class_lines(node, ranges, methods)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(f"{_span(node, ranges)} def {node.name}({_sig(node)}){_doc1(node)}")
        elif consts and _is_const(node):
            lines.append(f"L{node.lineno} {', '.join(t.id for t in node.targets)} = ...")
    return lines


def outline(path, ranges: bool = False, methods: bool = True) -> list[str]:
    """Оглавление файла: классы/методы/функции с сигнатурами и 1-й строкой docstring."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return python_outline(fh.read(), ranges, methods)


def regex_outline(text: str, patterns: list[str]) -> list[str]:
    """`Lnn name` for every line matching one of the patterns (group 1 = the name shown, else the whole match)."""
    rxs = [re.compile(p) for p in patterns]
    out: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        for rx in rxs:
            m = rx.search(line)
            if m:
                out.append(f"L{n} {(m.group(1) if m.groups() else m.group(0)).strip()[:90]}")
                break
    return out


def head_sample(text: str, n: int) -> list[str]:
    return [f"L{i} {ln[:110]}" for i, ln in enumerate(text.splitlines()[:n], 1)]


def fit(lines: list[str], max_lines: int) -> list[str]:
    """At most max_lines lines; the cut is announced by a last `... +N more` line."""
    if len(lines) <= max_lines:
        return lines
    return [*lines[:max_lines - 1], f"... +{len(lines) - max_lines + 1} more"]


def _python_tiers(text: str, max_lines: int) -> list[str]:
    tree = ast.parse(text)                                   # parsed once, then fewer details tier by tier
    for methods, consts in ((True, True), (True, False), (False, True), (False, False)):
        lines = python_outline(tree, True, methods, consts)
        if len(lines) <= max_lines:
            return lines
    return fit(lines, max_lines)


def outline_for(path: str, data: bytes | str, cfg: dict, max_lines: int) -> list[str]:
    """The outline that fits `max_lines`: Python via ast (fewer details tier by tier), others via cfg["by_ext"], else the first lines."""
    text = data if isinstance(data, str) else data.decode("utf-8", "replace")
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext == "py":
        try:
            return _python_tiers(text, max_lines)
        except SyntaxError:
            pass
    patterns = (cfg.get("by_ext") or {}).get(ext)
    lines = regex_outline(text, patterns) if patterns else []
    return fit(lines or head_sample(text, min(max_lines, int(cfg.get("head_lines", 12)))), max_lines)
