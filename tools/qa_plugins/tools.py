"""qa.py tools - the registry of every tool: what exists, what it replaces, and whether the same tool is about to be built twice.

    qa.py tools --find "words"   # <= 8 matching tools (name, command, purpose): run it BEFORE writing any new tool or script
    qa.py tools                  # the report: tools / documented / undocumented / dup_suspects / stale / drift, details only for failures
    qa.py tools --write          # regenerate docs/TOOLS.md from the harvest (then the report)
    qa.py tools --result         # what the `tools` check of qa.lua parses

Logic: tools/tool_registry.py. Data: the `tools` table of lua_content/qa.lua. A new tool needs a purpose line: `help=` of its subparser, a module
docstring, a check's `what`, a Rust `///` doc, or a row in `tools.rows`; `TOOL = {...}` (below) overrides the harvested fields of a plugin.
"""
from __future__ import annotations

import argparse
import time

import qa_report as R
import tool_registry as TR
from probe_settings import ROOT, qa_settings

TOOL = {"purpose": "the tools registry: find an existing tool before writing one, regenerate docs/TOOLS.md, detect undocumented / duplicate / stale tools",
        "when": "before writing any new tool, script or plugin", "replaces": "grepping tools/ and reading the CLAUDE.md tool table",
        "output": "--find: name | command | purpose lines; report: one qa_report line", "cost": "low", "group": "read"}


def cmd_find(args, settings: dict) -> int:
    tcfg = settings.get("tools") or {}
    hits = TR.find(TR.build(ROOT, settings), " ".join(args.find), tcfg)
    if not hits:
        print(f"no tool matches {' '.join(args.find)!r}: nothing like it exists - write it, give it a purpose line, run `qa.py tools --write`")
        return 0
    print("\n".join(f"{t.id} | {t.command or '-'} | {t.purpose}" for t in hits))
    return 0


def cmd_tools(args) -> int:
    settings = qa_settings()
    if args.find:
        return cmd_find(args, settings)
    t0 = time.perf_counter()
    if args.write:
        TR.write(ROOT, settings)
    res = TR.report(ROOT, settings)
    res.name, res.dur = "tools", time.perf_counter() - t0
    if args.result:
        print("\n".join(R.result_lines(res)))
    else:
        print(R.format_line(res, len(res.name), None, R.report_cfg(settings)))
        if res.status != "ok":
            print("\n".join(f"  {ln}" for ln in res.detail))
    return R.exit_code([res])


def register(sub):
    p = sub.add_parser("tools", help="tools registry: --find WORDS before writing a tool, --write docs/TOOLS.md, report undocumented/duplicate/stale tools",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--find", nargs="+", metavar="WORD", help="the 'does this already exist?' query (<= 8 matches)")
    p.add_argument("--write", action="store_true", help="regenerate docs/TOOLS.md, then report")
    p.add_argument("--check", action="store_true", help="the report (default; kept for symmetry with --write)")
    p.add_argument("--result", action="store_true", help="machine form for `qa.py check` (RESULT line)")
    p.set_defaults(func=cmd_tools)
