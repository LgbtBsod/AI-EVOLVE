"""qa.py route - which model, effort and tool-call budget a stage of a Workflow or an Agent call gets (data: lua_content/agent_kit.lua).

    qa.py route STAGE            # the row: model / effort / max_calls / escalate / why
    qa.py route --list           # every stage (cheap first) and every role
    qa.py route --check          # validate agent_kit.lua (roles have files, valid model names, budgets > 0, templates fit) and that .claude/agents/*.md is fresh
    qa.py route --write-agents   # (re)generate .claude/agents/<role>.md from agent_kit.lua, then check

A NEW `.claude/agents/` directory needs a harness restart before its agents appear; edits of existing files are picked up within seconds.
Cheap model + low effort for running tests, summarising logs and mechanical edits; the strongest model only for design, judging and adversarial review.
"""
from __future__ import annotations

import argparse
import difflib
import time

import agent_kit as AK
import qa_report as R


def _line(status: str, metrics: dict, detail: list | None, t0: float) -> str:
    return AK.status_line("route", status, metrics, detail, t0)


def _table(cfg: dict) -> list[str]:
    rows = [f"  {'stage':<19} {'role':<12} {'model':<7} {'effort':<7} {'calls':<6} {'escalate':<9} why"]
    rows += [f"  {r['stage']:<19} {r['role']:<12} {r['model']:<7} {r['effort']:<7} {int(r['max_calls']):<6} {r.get('escalate', '-'):<9} {R.one_line(r['why'], 58)}"
             for r in cfg["routes"]]
    rows += ["", f"  {'role':<19} {'file':<12} {'model':<7} {'effort':<7} {'calls':<6} {'writes':<9} tools"]
    rows += [f"  {r['name']:<19} {'.md':<12} {r['model']:<7} {r['effort']:<7} {int(r['max_calls']):<6} {'yes' if r['writes'] else 'no':<9} {r['tools']}" for r in cfg["roles"]]
    return rows


def _list(cfg: dict, t0: float) -> int:
    models = list(dict.fromkeys(r["model"] for r in cfg["routes"]))
    print(_line("ok", {"stages": len(cfg["routes"]), "roles": len(cfg["roles"]), "models": ",".join(models)}, None, t0))
    print("\n".join(_table(cfg)))
    return 0


def _show(cfg: dict, stage: str, t0: float) -> int:
    row = AK.routes(cfg).get(stage)
    if row is None:
        close = difflib.get_close_matches(stage, list(AK.routes(cfg)), n=3, cutoff=0.4)
        hint = f"unknown stage {stage!r}; " + (f"closest: {', '.join(close)}" if close else f"stages: {', '.join(AK.routes(cfg))}")
        print(_line("error", {}, [hint], t0))
        return 2
    metrics = {"stage": stage, "role": row["role"], "model": row["model"], "effort": row["effort"], "calls": int(row["max_calls"]), "escalate": row.get("escalate", "-")}
    print(_line("ok", metrics, None, t0))
    print(f"  why: {row['why']}")
    print(f"  agent: python tools/qa.py prompt {row['role']} --task \"...\"   workflow: agent(prompt, {{ model: '{row['model']}', effort: '{row['effort']}' }})   on FAIL retry with {row.get('escalate', '-')}")
    return 0


def _check(cfg: dict, t0: float, wrote: list | None = None, machine: bool = False) -> int:
    fails, warns = AK.validate(cfg, AK.ROOT)
    metrics = {"roles": len(cfg["roles"]), "routes": len(cfg["routes"]), "agents": len(cfg["roles"]), "fresh": "no" if any(f.startswith("stale:") for f in fails) else "yes"}
    if wrote is not None:
        metrics["written"] = len(wrote)
    status = "fail" if fails else ("warn" if warns else "ok")
    detail = [*fails, *warns]
    if machine:                                                             # what the `agent_kit` check of qa.lua parses
        print("\n".join(R.result_lines(R.Result(status, metrics, detail, repro="python tools/qa.py route --write-agents" if fails else None))))
    else:
        print(_line(status, metrics, detail or None, t0))
        print("\n".join(f"  {ln}" for ln in detail[1:]))                    # the first one is already on the line
    return 1 if fails else 0


def _write(cfg: dict, t0: float) -> int:
    existed = (AK.ROOT / cfg["agents_dir"]).is_dir()
    wrote = AK.write_agents(cfg, AK.ROOT)
    code = _check(cfg, t0, wrote)
    if wrote and not existed:
        print(f"  {cfg['agents_dir']}/ is new: restart the harness once so the agents appear (later edits are picked up within seconds)")
    return code


def cmd_route(args) -> int:
    t0 = time.perf_counter()
    try:
        cfg = AK.load()
        AK.roles(cfg), AK.routes(cfg)
    except Exception as exc:  # noqa: BLE001 - tool boundary: say why the Lua file did not load
        print(_line("error", {}, [f"{AK.LUA} did not load: {type(exc).__name__}: {exc}"], t0))
        return 2
    if args.write_agents:
        return _write(cfg, t0)
    if args.check or args.result:
        return _check(cfg, t0, machine=args.result)
    return _show(cfg, args.stage, t0) if args.stage else _list(cfg, t0)


def register(sub):
    p = sub.add_parser("route", help="model / effort / tool-call budget per stage of a Workflow or Agent call; --check validates agent_kit.lua, --write-agents generates .claude/agents/",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stage", nargs="?", help="a stage of `qa.py route --list`, e.g. run-tests, implement, adversarial-review")
    p.add_argument("--list", action="store_true", help="every stage and role (the default without STAGE)")
    p.add_argument("--check", action="store_true", help="validate lua_content/agent_kit.lua and the freshness of .claude/agents/*.md")
    p.add_argument("--write-agents", action="store_true", help="(re)generate .claude/agents/*.md from agent_kit.lua, then check")
    p.add_argument("--result", action="store_true", help="--check in the machine form for `qa.py check` (RESULT line)")
    p.set_defaults(func=cmd_route)
