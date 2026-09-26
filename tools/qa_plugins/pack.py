"""qa.py pack "TASK" [--files a,b] [--max-tok 1500] [--json] - a ready context pack for an agent: ranked files with symbol ranges, importers/tests, tools, state, verify, do-not-read.

    qa.py pack "add a check for repo hygiene" --max-tok 1500
    qa.py pack "fix the flaky determinism test" --files tests/test_agent_tools.py

Ranking (weights in the `pack` table of lua_content/qa.lua): task words in path / symbol names / docstrings + import-graph proximity to --files + git churn.
Logic: tools/pack_builder.py. Fallback when a file looks wrong: `qa.py ctx FILE`.
"""
from __future__ import annotations

import argparse
import json
import time

import pack_builder as PB
from probe_settings import qa_settings


def render_lines(pack: dict, took: float, max_tok: int, per_tok: int) -> list:
    body = [f"file: {p}" for p in pack["files"]] or ["file: (no match - try `qa.py tools --find` or `qa.py ctx FILE`)"]
    if pack["importers"]:
        body.append("importers: " + ", ".join(pack["importers"]))
    if pack["tests"]:
        body.append("tests: " + ", ".join(pack["tests"]))
    body += [f"tool: {t}" for t in pack["tools"]]
    body += [f"state: {s}" for s in pack["state"]]
    body += [f"use instead: {a}" for a in pack["answers"]]
    body.append("do NOT read: " + " ".join(pack["skip"]))
    body.append("verify: " + pack["verify"])
    shown = PB.fit_tokens(body, max_tok, per_tok)
    head = f"PACK files={len(pack['top'])} tokens={sum(len(x) for x in shown) // per_tok}/{max_tok} dur={took:.1f}s"
    return [head, *shown]


def cmd_pack(args) -> int:
    cfg = (qa_settings().get("pack") or {})
    start = time.time()
    seeds = [f for f in (args.files or "").split(",") if f]
    pack = PB.build_pack(" ".join(args.task), seeds, cfg, qa_settings())
    if args.json:
        print(json.dumps(pack, ensure_ascii=False))
        return 0
    print("\n".join(render_lines(pack, time.time() - start, args.max_tok or int(cfg["max_tok"]), int(cfg["chars_per_token"]))))
    return 0


def register(sub):
    p = sub.add_parser("pack", help="ranked context pack for a task (top files + symbol ranges, importers/tests, tools, state, verify, do-not-read)",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task", nargs="+", help="the task in words")
    p.add_argument("--files", default="", help="comma list of files already known to matter (import-graph proximity boosts their neighbours)")
    p.add_argument("--max-tok", type=int, default=0, help="token cap (chars/4); default pack.max_tok")
    p.add_argument("--json", action="store_true", help="the raw pack as JSON")
    p.set_defaults(func=cmd_pack)
