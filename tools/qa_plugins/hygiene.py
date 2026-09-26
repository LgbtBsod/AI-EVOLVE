"""qa.py hygiene - tracked junk (virtualenv, build output, saves, probe output, big files) and a .gitignore that lost its patterns.

    qa.py hygiene                # the report: one line per finding group + counts
    qa.py hygiene --result       # what the `hygiene` check of qa.lua parses: detail lines, `repro:`, one RESULT line
    qa.py hygiene --root DIR     # another repository (default: this one)

Logic: tools/repo_hygiene.py. Data: the `hygiene` table of lua_content/qa.lua.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import qa_report as R
import repo_hygiene as RH
from probe_settings import ROOT, qa_settings


def cmd_hygiene(args) -> int:
    settings = qa_settings()
    t0 = time.perf_counter()
    res = RH.check(Path(args.root) if args.root else ROOT, settings.get("hygiene") or {})
    if args.result:
        print("\n".join(RH.result_lines(res)))
        return R.exit_code([res])
    res.name, res.dur = "hygiene", time.perf_counter() - t0
    rcfg = R.report_cfg(settings)
    print(R.format_line(res, len(res.name), None, rcfg))
    if res.status != "ok":
        print("\n".join(f"  {ln}" for ln in res.detail))
    return R.exit_code([res])


def register(sub):
    p = sub.add_parser("hygiene", help="repo hygiene: no tracked virtualenv/build output/saves/big files, .gitignore keeps its patterns",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--result", action="store_true", help="machine form for `qa.py check` (RESULT line)")
    p.add_argument("--root", help="repository to scan (default: this one)")
    p.set_defaults(func=cmd_hygiene)
