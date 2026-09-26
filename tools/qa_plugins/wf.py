"""qa.py wf - lean Workflow scripts: a skeleton with the cheap defaults, a static cost estimate, a section assembler (data: lua_content/agent_kit.lua `wf`, `workflow_cost`).

    qa.py wf new NAME [--kind audit|map-write|review] [--out FILE]   # typed agents, explorers write their own file section, no verifier agent
    qa.py wf estimate SCRIPT|-                                       # agent() calls (fan-out where literal) x measured cost -> predicted billed tokens
    qa.py wf assemble DIR [--out FILE]                               # concatenate DIR/*.md, check that every `path:line` reference exists (the script step instead of a verifier agent)

Why: a default workflow agent cold-starts at ~67k context, re-read every turn; `agentType` explorer|implementer|verifier|reviewer starts at ~12k (measured, see `workflow_cost`).
The estimate is static: turns are the measured average, so it is good to about +-35% (a script with a big embedded prompt or many retries is under-counted).
"""
from __future__ import annotations

import argparse
import json
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


def _agent_type(args: str) -> str:
    m = re.search(r"agentType\s*:\s*['\"]([\w-]+)['\"]", args)
    return m.group(1) if m else ("typed" if "agentType" in args else "untyped")


def _one_cost(kind: str, cost: dict, cal: dict) -> int:
    """Billed tokens of ONE agent: the calibrated median of its type (workflow agents first), else the constants of `workflow_cost`."""
    for scope in ("wf", "all"):
        hit = (cal.get(scope) or {}).get(kind)
        if hit:
            return int(hit["billed"])
    cold = cost["cold_default"] if kind == "untyped" else cost["cold_typed"]
    return cold + cost["avg_turns"] * (cost["growth_per_turn"] + cost["out_per_turn"])


def estimate(script: str, cost: dict, cal: dict | None = None) -> dict:
    """Static prediction: per agent() call the calibrated median billed of its agentType (`--recalibrate`), else `cold + turns * (growth + out)` (`workflow_cost`)."""
    calls = typed = agents = 0
    billed = 0
    for m in G.agent_calls(script):
        kind = _agent_type(G._call_args(script, m.end()))
        n = _fanout(script, m.start(), cost)
        billed += n * _one_cost(kind, cost, cal or {})
        calls, agents, typed = calls + 1, agents + n, typed + n * (kind != "untyped")
    return {"calls": calls, "agents": agents, "untyped": agents - typed, "billed": billed}


def calibration_path() -> Path:
    return R.QA_OUT / qa_settings()["tokens"]["usage"]["calibration_file"]


def recalibrate(min_n: int) -> dict:
    """Per-type medians from the usage ledger: `wf` = workflow-run agents, `all` = every recorded agent; written to wf_calibration.json."""
    from qa_plugins import tokens as T
    import usage_ledger as U
    files, _ = T.usage_files(None)
    ut = T.usage_cfg()["untyped_types"]
    samples = U.agent_samples(files, ut)
    cal = {"samples": len(samples), "wf": U.medians([s for s in samples if s["run"]], min_n), "all": U.medians(samples, min_n)}
    path = calibration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cal), encoding="utf-8")
    return cal


def load_calibration() -> dict:
    try:
        return json.loads(calibration_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _calibration(force: bool) -> dict:
    return load_calibration() if not force and load_calibration() else recalibrate(int(qa_settings()["tokens"]["usage"]["min_samples"]))


def measured_run(run: str) -> int | None:
    import token_ledger as L
    d = L.find_workflow(Path.home() / ".claude" / "projects", run)
    return sum(a["billed"] for a in L.workflow_agents(d)) if d else None


def _medians_text(cal: dict) -> str:
    med = {**(cal.get("all") or {}), **(cal.get("wf") or {})}
    return ",".join(f"{t}={v['billed'] // 1000}k" for t, v in sorted(med.items()))


def cmd_estimate(args, kit: dict) -> int:
    t0 = time.time()
    script = sys.stdin.read() if args.arg == "-" else Path(args.arg).read_text(encoding="utf-8", errors="replace")
    cal = _calibration(args.recalibrate)
    e = estimate(script, kit["workflow_cost"], cal)
    c = kit["workflow_cost"]
    detail = [f"use: agentType on every agent(): {e['untyped']} untyped agent(s) start at ~{c['cold_default'] // 1000}k instead of ~{c['cold_typed'] // 1000}k context, re-read every turn"] if e["untyped"] else []
    met = {"agents": e["agents"], "calls": e["calls"], "untyped": e["untyped"], "predicted_billed": e["billed"],
           "calibrated": "yes" if cal.get("wf") or cal.get("all") else "no", "n": cal.get("samples", 0)}
    got = measured_run(args.vs) if args.vs else None
    got and met.update(measured_billed=got, error_pct=round(100 * (e["billed"] - got) / got))
    met["medians"] = _medians_text(cal) or "-"
    print(_line("warn" if e["untyped"] else "ok", met, t0, detail))
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
    return cmd_estimate(args, kit) if args.action == "estimate" else cmd_assemble(argparse.Namespace(dir=args.arg, out=args.out))


def register(sub):
    p = sub.add_parser("wf", help="lean Workflow scripts: `new` skeleton (agentType everywhere), `estimate` predicted billed tokens, `assemble` section files",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["new", "estimate", "assemble"])
    p.add_argument("arg", help="new: NAME | estimate: SCRIPT or - | assemble: DIR")
    p.add_argument("--kind", default="audit", choices=["audit", "map-write", "review"], help="new: skeleton kind")
    p.add_argument("--out", help="new / assemble: write to FILE (default: stdout for new)")
    p.add_argument("--recalibrate", action="store_true", help="estimate: refresh per-agentType medians from the usage ledger (wf_calibration.json)")
    p.add_argument("--vs", metavar="RUN", help="estimate: also the error against the measured billed of workflow run RUN")
    p.set_defaults(func=cmd_wf)
