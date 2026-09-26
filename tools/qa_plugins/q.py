"""qa.py q QUERY... - N read-only queries in parallel in ONE call, one grouped and capped output (replaces grep -> ctx -> read chains).

    qa.py q "grep:def result_lines@tools/*.py+ctx" "sym:tools/qa_report.py:result_lines" "ctx:tools/file_toc.py" "read:tools/qa.py:184-200" "find:tools/qa_plugins/*.py" "changed"

Queries: grep:PAT[@glob][+ctx] (+ctx = outline of the matching files) | sym:FILE:NAME | ctx:FILE | read:FILE:A-B | find:GLOB | changed.
Caps (lua_content/qa.lua `q`): per query and in total; the overflow goes to dev_probe_output/qa/q_last.txt. Not recorded in the guard journal (skipped: not cheap).
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import file_toc
from probe_settings import ROOT
from qa_plugins.sym import query_cfg, read_text, sym_lines, tracked_files


def _tool(*args: str) -> list[str]:
    run = subprocess.run([sys.executable, str(ROOT / "tools" / "qa.py"), *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return (run.stdout or run.stderr).splitlines()


def _outline(rel: str) -> list[str]:
    return [f"  {ln}" for ln in file_toc.outline_for(rel, read_text(rel) or "", {}, 25)]


def _grep_file(rel: str, rx) -> list[str]:
    return [f"{rel}:{n} {ln.strip()[:120]}" for n, ln in enumerate((read_text(rel) or "").splitlines(), 1) if rx.search(ln)]


def _grep(arg: str) -> list[str]:
    settings = query_cfg()
    per_file, max_files = int(settings["grep_per_file"]), int(settings["grep_files"])
    pat, _, glob = arg.removesuffix("+ctx").partition("@")
    rx = re.compile(pat)
    out: list[str] = []
    matched = 0
    for rel in (f for f in tracked_files() if not glob or fnmatch.fnmatch(f, glob)):
        hits = _grep_file(rel, rx)
        matched += bool(hits)
        if hits and matched <= max_files:
            out += hits[:per_file] + ([f"  ... +{len(hits) - per_file} more in {rel}"] if len(hits) > per_file else [])
            out += _outline(rel) if arg.endswith("+ctx") else []
    return [f"{matched} file(s) match", *out]


def _read_range(arg: str) -> list[str]:
    rel, _, span = arg.rpartition(":")
    a, _, b = span.partition("-")
    lines = (read_text(rel) or "").splitlines()
    lo, hi = int(a), int(b or a)
    return [f"{n:>5} {lines[n - 1][:160]}" for n in range(max(1, lo), min(len(lines), hi) + 1)]


def _find(glob: str) -> list[str]:
    hits = [f for f in tracked_files() if fnmatch.fnmatch(f, glob) or fnmatch.fnmatch(f.rsplit("/", 1)[-1], glob)]
    return [f"{len(hits)} file(s)", *hits[:40]]


def run_query(query: str) -> list[str]:
    kind, _, arg = query.partition(":")
    handlers = {"grep": _grep, "sym": sym_lines, "read": _read_range, "find": _find,
                "ctx": lambda a: _tool("ctx", a), "changed": lambda a: _tool("changed")}
    if kind not in handlers:
        return [f"unknown query kind {kind!r} (grep|sym|ctx|read|find|changed)"]
    try:
        return handlers[kind](arg)
    except (ValueError, re.error, OSError) as exc:
        return [f"query error: {exc}"]


def render(queries: list[str], results: list[list[str]]) -> tuple[list[str], list[str]]:
    """(shown lines capped per query and in total, the full text lines)."""
    settings = query_cfg()
    shown: list[str] = []
    full: list[str] = []
    for query, lines in zip(queries, results, strict=True):
        full += [f"== {query}", *lines]
        shown += [f"== {query}", *file_toc.fit(lines, int(settings["per_query_lines"]))]
    return file_toc.fit(shown, int(settings["total_lines"])), full


def cmd_q(args) -> int:
    with ThreadPoolExecutor(max_workers=min(8, len(args.queries))) as pool:
        results = list(pool.map(run_query, args.queries))
    shown, full = render(args.queries, results)
    if len(shown) < len(full):
        path = ROOT / "dev_probe_output" / "qa" / "q_last.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(full) + "\n", encoding="utf-8", newline="\n")
        shown[-1] += f"  (full: {path.relative_to(ROOT).as_posix()})"
    print("\n".join(shown))
    return 0


def register(sub):
    p = sub.add_parser("q", help="N read-only queries (grep/sym/ctx/read/find/changed) in parallel, one grouped capped output",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("queries", nargs="+", help='e.g. "grep:PAT@glob+ctx" "sym:FILE:NAME" "ctx:FILE" "read:FILE:A-B" "find:GLOB" "changed"')
    p.set_defaults(func=cmd_q)
