"""Parity: the one glob matcher (tools/glob_match.py) equals the retired regex translator on every real pattern."""
import glob
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import glob_match  # noqa: E402


def _old_re(g: str) -> str:
    """Verbatim copy of the retired qa_plugins/check.py `_glob_re` (kept here only as the parity reference)."""
    parts, out = g.split("/"), []
    for n, seg in enumerate(parts):
        last = n == len(parts) - 1
        if seg == "**":
            out.append(".+" if last else "(?:[^/]+/)*")
            continue
        out.append("".join("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in seg))
        out.append("" if last else "/")
    return "".join(out)


def _patterns() -> list:
    pats = set()
    for f in glob.glob(str(ROOT / "lua_content" / "*.lua")) + glob.glob(str(ROOT / "tools" / "qa_plugins" / "*.py")):
        for m in re.finditer(r'"([^"\s\()^$|]*[*?][^"\s\()^$|]*)"', Path(f).read_text(encoding="utf8")):
            pats.add(m.group(1))
    return sorted(pats)


def test_parity_with_old_translator_on_all_real_patterns():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    pats = _patterns()
    assert len(pats) > 30 and files
    bad = [(p, g) for p in files for g in pats if glob_match.gmatch(p, g) != (re.fullmatch(_old_re(g), p) is not None)]
    assert not bad, bad[:5]


def test_semantics():
    m = glob_match.matches
    assert m("src/a/b.py", ["src/**/*.py"]) and m("src/b.py", ["src/**/*.py"]) and not m("tools/a.py", ["src/**/*.py"])
    assert not m("tools/a/b.py", ["tools/*.py"]) and m("lua_content/qa.lua", ["x", "lua_content/**"])
