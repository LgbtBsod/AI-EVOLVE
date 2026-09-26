"""qa.py prompt - a SHORT prompt for an Agent or Workflow stage: the shared context lives in docs/agent_context/, the prompt only points at it.

    qa.py prompt ROLE --task "..." [--files a,b] [--done "..."] [--pack]   # <= ~400 tokens (chars/4) or refused; paste the output as the Agent prompt
    qa.py prompt --workflow ROLE                                            # the 3 lines a Workflow script embeds instead of an inlined CONTEXT block
    qa.py route --list                                                      # roles and stage routing: model / effort / call budget

The prompt goes to stdout (nothing else), the one qa_report size line to stderr. `--pack` appends `qa.py pack` when that tool exists (skipped silently before).
Roles, budgets, templates and the report contract: lua_content/agent_kit.lua; logic: tools/agent_kit.py.
"""
from __future__ import annotations

import argparse
import sys
import time

import agent_kit as AK


def _error(detail: str, t0: float) -> int:
    print(AK.status_line("prompt", "error", {}, [detail], t0))
    return 2


def _too_long(cfg: dict, role: dict, text: str, t0: float) -> int:
    metrics = {"role": role["name"], "tok": AK.tokens(cfg, text), "max": cfg["max_prompt_tokens"], "chars": len(text)}
    hint = "too long: shared context belongs in a repo file (docs/agent_context/); only TASK / SCOPE / DONE WHEN are typed here - shorten --task"
    print(AK.status_line("prompt", "fail", metrics, [hint], t0))
    return 1


def _render(args, cfg: dict, role: dict, t0: float) -> int:
    files = [f.strip() for f in (args.files or "").split(",") if f.strip()]
    text = AK.render_prompt(cfg, role, args.task, files, args.done or "")
    if AK.tokens(cfg, text) > cfg["max_prompt_tokens"]:
        return _too_long(cfg, role, text, t0)
    pack = AK.pack_text(args.task) if args.pack else ""
    print(AK.with_pack(cfg, text, pack))
    metrics = {"role": role["name"], "tok": AK.tokens(cfg, text), "max": cfg["max_prompt_tokens"], "chars": len(text)}
    if args.pack:
        metrics["pack"] = f"{len(pack)}chars" if pack.strip() else "none"
    print(AK.status_line("prompt", "ok", metrics, None, t0), file=sys.stderr)
    return 0


def cmd_prompt(args) -> int:
    t0 = time.perf_counter()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # a task text may hold any character; a cp1251 pipe must not crash on it
    try:
        cfg = AK.load()
        roles = AK.roles(cfg)
    except Exception as exc:  # noqa: BLE001 - tool boundary: say why the Lua file did not load
        return _error(f"{AK.LUA} did not load: {type(exc).__name__}: {exc}", t0)
    name = args.workflow or args.role or ""
    if name not in roles:
        return _error(f"role {name!r} is not one of: {', '.join(roles)}", t0)
    if args.workflow:
        print(AK.render_workflow(cfg, roles[name]))
        return 0
    if not (args.task or "").strip():
        return _error("--task is required (what the agent must do, in a few sentences)", t0)
    return _render(args, cfg, roles[name], t0)


def register(sub):
    p = sub.add_parser("prompt", help="a SHORT prompt (<= 400 tokens) for an Agent / Workflow stage: the shared context is in docs/agent_context/, roles + budgets in agent_kit.lua",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("role", nargs="?", help="implementer | verifier | explorer | rust-kernel | lua-content | stabilizer | reviewer (see `qa.py route --list`)")
    p.add_argument("--task", help="what the agent must do (a few sentences: the only free text in the prompt)")
    p.add_argument("--files", help="comma-separated SCOPE: the files the agent may touch")
    p.add_argument("--done", help="DONE WHEN (default: the role's own)")
    p.add_argument("--pack", action="store_true", help="append `qa.py pack TASK` when that tool exists (skipped silently before)")
    p.add_argument("--workflow", metavar="ROLE", help="print the 3-line snippet a Workflow script embeds instead of an inlined CONTEXT block")
    p.set_defaults(func=cmd_prompt)
