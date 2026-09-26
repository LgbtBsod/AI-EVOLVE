"""qa.py static - undefined names, redefinitions, syntax errors in Python, Lua and GitHub workflows (the `static` check).

    qa.py static                 # the whole repo (tools/ src/ main.py, lua_content/**/*.lua, .github/workflows)
    qa.py static FILE [FILE]     # only these files (.py / .lua / .yml)
    qa.py static --result        # what the `static` check of qa.lua parses: detail lines, `repro:`, one RESULT line

Logic: tools/static_gate.py (ruff F821,F811,E9 + compile; LuaJIT 2.1 and Lua 5.5 compile-only via lupa; workflow structure lint).
"""
from __future__ import annotations

import argparse
import time

import qa_report as R
import static_gate as SG
from probe_settings import qa_settings


def cmd_static(args) -> int:
    t0 = time.perf_counter()
    res = SG.run(files=args.files or None)
    if args.result:
        print("\n".join(R.result_lines(res)))
        return R.exit_code([res])
    res.dur = time.perf_counter() - t0
    print(R.format_line(res, len(res.name), None, R.report_cfg(qa_settings())))
    print("\n".join(f"  {ln}" for ln in res.detail))
    return R.exit_code([res])


def register(sub):
    p = sub.add_parser("static", help="static gate: ruff F821/F811/E9, compile, Lua syntax (LuaJIT + 5.5), workflow lint",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*", help="only these files (default: the whole repo)")
    p.add_argument("--result", action="store_true", help="machine form for `qa.py check` (RESULT line)")
    p.set_defaults(func=cmd_static)
