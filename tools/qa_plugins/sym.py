"""qa.py sym FILE:NAME [--callers] [--context N] - ONE function/class/struct/impl/Lua function with line numbers instead of reading the whole file.

    qa.py sym tools/qa_report.py:result_lines
    qa.py sym rust_core/src/ffi/mod.rs:LuaContent --callers      # + static callers (word grep on the name, capped)

Python via ast, Rust/Lua via the regex spans of tools/file_toc.py (indent-matched closing brace / `end`; not tree-sitter). Caps: the `q` table of lua_content/qa.lua.
"""
from __future__ import annotations

import argparse
import re
import subprocess

import file_toc
from probe_settings import ROOT, qa_settings

_q_caps = {"sym_lines": 60, "callers": 8, "max_line_chars": 160, "total_lines": 120, "per_query_lines": 30, "grep_files": 12, "grep_per_file": 3}
_DEF = re.compile(r"\s*(?:pub\s+)?(?:def|fn|class|struct|function)\s")


def query_cfg() -> dict:
    return {**_q_caps, **(qa_settings().get("q") or {})}


def tracked_files() -> list[str]:
    run = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return [ln for ln in run.stdout.splitlines() if ln]


def read_text(rel: str) -> str | None:
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def callers(name: str, limit: int) -> list[str]:
    """Static callers: `path:line text` of lines that use `name` as a word (definition lines excluded)."""
    rx = re.compile(r"(?<![\w])" + re.escape(name.split(".")[-1]) + r"\b")
    hits: list[str] = []
    for rel in tracked_files():
        if not rel.endswith((".py", ".rs", ".lua")):
            continue
        for n, line in enumerate((read_text(rel) or "").splitlines(), 1):
            if rx.search(line) and not _DEF.match(line):
                hits.append(f"{rel}:{n} {line.strip()[:110]}")
                if len(hits) >= limit:
                    return hits
    return hits


def sym_lines(spec: str, want_callers: bool = False, context: int = 0) -> list[str]:
    """The lines `qa.py sym` prints for FILE:NAME."""
    settings = query_cfg()
    rel, _, name = spec.rpartition(":")
    text = read_text(rel) if rel else None
    if text is None or not name:
        return [f"sym {spec}: expected FILE:NAME with an existing FILE"]
    span = file_toc.symbol_span(text, rel.rsplit(".", 1)[-1].lower(), name)
    if span is None:
        return [f"sym {spec}: no function/class/struct/impl named {name!r} (try `qa.py ctx {rel}`)"]
    lines = text.splitlines()
    first, last = max(1, span[0] - context), min(len(lines), span[1] + context)
    shown = min(last, first + int(settings["sym_lines"]) - 1)
    width = int(settings["max_line_chars"])
    out = [f"{rel}:{span[0]}-{span[1]} {name}" + (f"  (showing L{first}-{shown} of {last - first + 1} lines)" if shown < last else "")]
    out += [f"{n:>5} {lines[n - 1][:width]}" for n in range(first, shown + 1)]
    if want_callers:
        limit = int(settings["callers"])
        found = callers(name, limit)
        out += [f"callers(static, {len(found)}{'+' if len(found) >= limit else ''}):", *(f"  {h}" for h in found)]
    return out


def cmd_sym(args) -> int:
    lines = sym_lines(args.spec, args.callers, args.context)
    print("\n".join(lines))
    return 0 if len(lines) > 1 else 2


def register(sub):
    p = sub.add_parser("sym", help="one function/class/impl/Lua function of a file with line numbers (+ static callers)",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("spec", help="FILE:NAME")
    p.add_argument("--callers", action="store_true", help="also list static callers (word grep on the name)")
    p.add_argument("--context", type=int, default=0, help="extra lines before/after")
    p.set_defaults(func=cmd_sym)
