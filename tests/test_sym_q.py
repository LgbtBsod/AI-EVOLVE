"""qa.py sym / q / ctx for Rust and Lua: spans, outlines, capped grouped output."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import file_toc  # noqa: E402
from qa_plugins import q, sym  # noqa: E402

RS = '#[pyclass]\npub struct Foo {\n    a: u8,\n}\n\nimpl Foo {\n    #[pyfunction]\n    pub fn go(&self) {\n        1;\n    }\n}\n'
LUA = 'local M = {\n  a = 1,\n}\nfunction M.run(x)\n  return x\nend\n'


def test_rust_outline_and_span():
    lines = file_toc.rust_outline(RS)
    assert any("struct Foo" in ln and "pyclass" in ln for ln in lines)
    assert any("fn go" in ln and "pyfunction" in ln for ln in lines)
    assert file_toc.symbol_span(RS, "rs", "Foo") == (1, 4)
    assert file_toc.symbol_span(RS, "rs", "go") == (7, 10)


def test_lua_outline_and_span():
    assert any("function M.run" in ln for ln in file_toc.lua_outline(LUA))
    assert file_toc.symbol_span(LUA, "lua", "M.run") == (4, 6)
    assert file_toc.symbol_span(LUA, "lua", "nope") is None


def test_sym_python_and_missing():
    out = sym.sym_lines("tools/file_toc.py:fit")
    assert out[0].startswith("tools/file_toc.py:") and "def fit" in out[1]
    assert "no function" in sym.sym_lines("tools/file_toc.py:nope_zzz")[0]


def test_q_groups_and_caps():
    queries = ["find:tools/qa_plugins/sym.py", "read:tools/file_toc.py:1-3", "bogus:x"]
    shown, full = q.render(queries, [q.run_query(x) for x in queries])
    assert shown[0] == "== find:tools/qa_plugins/sym.py" and "unknown query kind" in "\n".join(full)
    assert len(shown) <= sym.query_cfg()["total_lines"]
