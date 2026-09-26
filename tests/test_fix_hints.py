"""Fix hints: lua_content/fixes.lua rules set Result.fix, the line shows `| fix:` before `| repro:`; hint only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import qa_report as R  # noqa: E402

RULES = R.load_fixes()


def one(name, status, metrics=None, detail=None):
    res = R.Result(status, metrics or {}, detail or [], repro="python x")
    res.name = name
    R.apply_fixes([res], RULES)
    return res


def test_rules_load():
    assert len(RULES) >= 8


def test_line_order_and_cap():
    res = one("tools", "fail", {"undocumented": 2}, ["undocumented tool"])
    line = R.format_line(res)
    assert line.index("| undocumented") < line.index("| fix: use: add a one-line purpose docstring") < line.index("| repro:")


def test_seeded_cases():
    assert one("lua", "fail", detail=["CRLF vs LF drift"]).fix == "git add --renormalize ."
    assert one("quality", "warn", {"improved": 3}).fix.endswith("--update-baseline")
    assert one("golden", "fail", detail=["golden differs at t=3"]).fix == "python tools/qa.py golden --record"
    assert "ci" in one("golden", "warn", detail=["soft: golden recorded on Linux"]).fix
    assert "F821" and one("static", "fail", detail=["a.py:3 F821 undefined name"]).fix.startswith("use:")
    assert one("hygiene", "fail", {"tracked": 4}).fix == "git rm -r --cached PATH"
    assert one("x", "error", detail=["ModuleNotFoundError: no module named ruff"]).fix.endswith("doctor")


def test_ok_gets_no_hint_and_explain_lists_rules():
    assert one("tools", "ok", {"undocumented": 2}).fix is None
    assert R.fixes_for("quality_tools", RULES)
