"""qa.py wf - lean Workflow scripts: a skeleton with the cheap defaults, a static cost estimate, a section assembler (data: lua_content/agent_kit.lua `wf`, `workflow_cost`).

    qa.py wf new NAME [--kind audit|map-write|review] [--out FILE]   # typed agents, explorers write their own file section, no verifier agent
    qa.py wf estimate SCRIPT|-                                       # agent() calls (fan-out where literal) x measured cost -> predicted billed tokens
    qa.py wf assemble DIR [--out FILE]                               # concatenate DIR/*.md, check that every `path:line` reference exists (the script step instead of a verifier agent)

Why: a default workflow agent cold-starts at ~67k context, re-read every turn; `agentType` explorer|implementer|verifier|reviewer starts at ~12k (measured, see `workflow_cost`).
The estimate is static: turns are the measured average, so it is good to about +-35% (a script with a big embedded prompt or many retries is under-counted).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import agent_kit
import guard_hook as G
import qa_report as R
from probe_settings import ROOT, qa_settings


def _line(status: str, metrics: dict, t0: float, detail=None) -> str:
    res = R.Result(status, metrics, detail or [], dur=time.time() - t0, name="wf")
    return R.format_line(res, 2, None, R.report_cfg(qa_settings()))


def skeleton(name: str, kind: str, kit: dict) -> str:
    wf = kit["wf"]
    text = "\n".join(wf["skeleton"]) + "\n"
    header = wf["header"].replace("\\", "\\\\").replace("'", "\\'")
    for k, v in (("<header>", header), ("<name>", name), ("<NAME>", name.upper()), ("<kind>", kind), ("<agent_type>", wf["agent_type"][kind])):
        text = text.replace(k, v)
    return text


def _fanout(script: str, pos: int, cost: dict) -> int:
    """Copies of the agent() call at `pos`: the literal size of the array of an enclosing `X.map(` (top-level `  {` items), else default_fanout; 1 outside a map."""
    m = None
    maps = list(re.finditer(r"([A-Za-z_]\w*)\s*\.map\s*\(", script[:pos]))
    m = maps[-1] if maps else None
    if not m or pos - m.start() > 600:
        return 1
    arr = re.search(r"\b" + re.escape(m.group(1)) + r"\s*=\s*\[(.*?)\n\]", script, re.DOTALL)
    return len(re.findall(r"^ {0,2}\{", arr.group(1), re.MULTILINE)) if arr else int(cost["default_fanout"])


def estimate(script: str, cost: dict) -> dict:
    """Static prediction: per agent() call `cold + turns * (growth + out)` billed tokens (constants of `workflow_cost`)."""
    calls = typed = agents = 0
    billed = 0
    for m in G.agent_calls(script):
        is_typed = "agentType" in G._call_args(script, m.end())
        n = _fanout(script, m.start(), cost)
        cold = cost["cold_typed"] if is_typed else cost["cold_default"]
        billed += n * (cold + cost["avg_turns"] * (cost["growth_per_turn"] + cost["out_per_turn"]))
        calls, agents, typed = calls + 1, agents + n, typed + n * is_typed
    return {"calls": calls, "agents": agents, "untyped": agents - typed, "billed": billed}


def cmd_estimate(args, kit: dict) -> int:
    t0 = time.time()
    script = sys.stdin.read() if args.script == "-" else Path(args.script).read_text(encoding="utf-8", errors="replace")
    e = estimate(script, kit["workflow_cost"])
    c = kit["workflow_cost"]
    detail = [f"use: agentType on every agent(): {e['untyped']} untyped agent(s) start at ~{c['cold_default'] // 1000}k instead of ~{c['cold_typed'] // 1000}k context, re-read every turn"] if e["untyped"] else []
    print(_line("warn" if e["untyped"] else "ok", {"agents": e["agents"], "calls": e["calls"], "untyped": e["untyped"], "predicted_billed": e["billed"]}, t0, detail))
    return 0


def _refs(text: str) -> list[str]:
    return re.findall(r"`((?:src|tools|tests|lua_content|rust_core|docs)/[\w./-]+?\.\w+)(?::\d+)?`", text)


def cmd_assemble(args) -> int:
    t0 = time.time()
    parts = sorted(Path(args.dir).glob("*.md"))
    body = "\n\n".join(p.read_text(encoding="utf-8") for p in parts)
    refs = sorted(set(_refs(body)))
    bad = [r for r in refs if not (ROOT / r).exists()]
    ok = bool(parts) and not bad
    if args.out and parts:
        Path(args.out).write_text(body + "\n", encoding="utf-8")
    print(_line("ok" if ok else "fail", {"sections": len(parts), "refs": len(refs), "refs_bad": len(bad), "lines": body.count("\n") + 1}, t0, [f"missing: {b}" for b in bad[:5]]))
    return 0 if ok else 1


def cmd_wf(args) -> int:
    kit = agent_kit.load()
    if args.action == "new":
        text = skeleton(args.arg, args.kind, kit)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wf: wrote {args.out} ({text.count(chr(10))} lines); next: qa.py wf estimate {args.out}")
        else:
            sys.stdout.write(text)
        return 0
    return cmd_estimate(argparse.Namespace(script=args.arg), kit) if args.action == "estimate" else cmd_assemble(argparse.Namespace(dir=args.arg, out=args.out))


def register(sub):
    p = sub.add_parser("wf", help="lean Workflow scripts: `new` skeleton (agentType everywhere), `estimate` predicted billed tokens, `assemble` section files",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["new", "estimate", "assemble"])
    p.add_argument("arg", help="new: NAME | estimate: SCRIPT or - | assemble: DIR")
    p.add_argument("--kind", default="audit", choices=["audit", "map-write", "review"], help="new: skeleton kind")
    p.add_argument("--out", help="new / assemble: write to FILE (default: stdout for new)")
    p.set_defaults(func=cmd_wf)
