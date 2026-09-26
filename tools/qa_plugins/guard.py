"""qa.py guard - the tool-call guard: what keeps big, raw and repeated reads out of an agent's context (Claude Code hooks, rules in lua_content/guards.lua).

    qa.py guard                        # status: hooks installed?, mode, rules fresh?, block statistics
    qa.py guard --explain              # the rules, thresholds and how to disable them
    qa.py guard --stats                # guards.jsonl: blocks / allows / nudges / forced retries, estimated tokens kept out of the context, per rule
    qa.py guard --compile              # guards.lua -> dev_probe_output/qa/guards.json (the hook recompiles it by itself when stale)
    qa.py guard --simulate FILE.json   # a sample hook payload through the rules (no state, no log): the decision, the exit code, the message
    qa.py guard --install              # add OUR hook entries to .claude/settings.json (soft mode; other settings untouched); --uninstall removes them

Hook entry point: tools/guard_hook.py (stdlib only, fails open). Off switch for one shell: AI_EVOLVE_GUARD=off. Data: lua_content/guards.lua.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import guard_hook as G
import qa_report as R
from probe_settings import ROOT, qa_settings

HOOK_FILE = "guard_hook.py"
EVENTS = {"PreToolUse": "Read|Grep|Glob|Bash|Workflow", "PostToolUse": "Edit|Write|NotebookEdit", "PreCompact": None, "SessionStart": None, "Stop": None, "SubagentStop": None}     # event -> matcher (None: no matcher)
SETTINGS = ROOT / ".claude" / "settings.json"


# ---------------------------------------------------------------- .claude/settings.json: only OUR entries

def venv_python(root: Path = ROOT) -> str:
    """The project interpreter as the hook should call it (relative to ${CLAUDE_PROJECT_DIR}, forward slashes)."""
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        if (root / rel).is_file():
            return "${CLAUDE_PROJECT_DIR}/" + rel
    return "${CLAUDE_PROJECT_DIR}/.venv/Scripts/python.exe"


def hook_entry(python: str) -> dict:
    """Exec form (no shell: about 60 ms less per call on Windows than Git Bash); -S -E = no site-packages, no PYTHON* env vars (a stale guards.json is rebuilt by a child interpreter that has them)."""
    return {"type": "command", "command": python, "args": ["-S", "-E", "${CLAUDE_PROJECT_DIR}/tools/" + HOOK_FILE], "timeout": 10}


def is_ours(hook: dict) -> bool:
    return HOOK_FILE in json.dumps(hook)


def _without_ours(groups: list) -> list:
    kept = []
    for group in groups:
        hooks = [h for h in group.get("hooks", []) if not is_ours(h)]
        if hooks:
            kept.append({**group, "hooks": hooks})
    return kept


def install(settings: dict, python: str) -> dict:
    """settings with our hooks added (an earlier copy of them is replaced, everything else stays byte for byte)."""
    hooks = dict(settings.get("hooks") or {})
    for event, matcher in EVENTS.items():
        group = {"hooks": [hook_entry(python)]}
        hooks[event] = [*_without_ours(hooks.get(event) or []), {"matcher": matcher, **group} if matcher else group]
    return {**settings, "hooks": hooks}


def uninstall(settings: dict) -> dict:
    hooks = {}
    for event, groups in (settings.get("hooks") or {}).items():
        kept = _without_ours(groups)
        if kept:
            hooks[event] = kept
    out = {k: v for k, v in settings.items() if k != "hooks"}
    return {**out, "hooks": hooks} if hooks else out


def installed_events(settings: dict) -> list[str]:
    return [e for e, groups in (settings.get("hooks") or {}).items() if any(is_ours(h) for g in groups for h in g.get("hooks", []))]


def read_settings(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def write_settings(path: Path, data: dict) -> None:
    if not data:                                    # nothing left: the file only ever held our entries
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- statistics

def load_log(path: Path) -> list[dict]:
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def summarize(rows: list[dict], chars_per_token: float = 3.5) -> dict:
    """blocks / allows / nudges / forced retries and the net tokens kept out of the context (denied chars minus what the forced retries read anyway)."""
    by_rule: dict[str, dict] = {}
    for r in rows:
        agg = by_rule.setdefault(r.get("rule", "?"), {"n": 0, "chars": 0})
        agg["n"] += 1
        agg["chars"] += int(r.get("chars") or 0)
    denied = sum(a["chars"] for k, a in by_rule.items() if k.startswith(("read-big", "read-raw", "read-repeat", "bash-raw")))
    wasted = by_rule.get("read-retry", {}).get("chars", 0)
    acts = Counter(r.get("act") for r in rows)
    return {"blocks": acts["deny"], "allows": acts["allow"], "nudges": acts["nudge"], "forced": by_rule.get("read-retry", {}).get("n", 0),
            "avoided_tok": max(0, int((denied - wasted) / chars_per_token)), "by_rule": by_rule}


def _log_path(cfg: dict) -> Path:
    return Path(G.out_dir(root=str(ROOT))) / ((cfg.get("log") or {}).get("path") or "guards.jsonl")


def _rules_state(cfg_cached: dict | None) -> str:
    src = ROOT / "lua_content" / "guards.lua"
    if not src.is_file():
        return "missing"
    crc = G.crc_of(src.read_bytes())
    return "fresh" if cfg_cached and cfg_cached.get("_src") == crc else "stale"


# ---------------------------------------------------------------- commands

def _line(name: str, status: str, metrics: dict, dur: float, detail=None) -> str:
    res = R.Result(status, metrics, detail or [], dur=dur, name=name)
    return R.format_line(res, len(name), None, R.report_cfg(qa_settings()))


def cmd_compile(t0: float) -> int:
    try:
        cfg = G.compile_rules()
    except Exception as exc:  # noqa: BLE001 - tool boundary: say why the Lua file did not compile
        print(_line("guard", "error", {}, time.perf_counter() - t0, [f"compile failed: {type(exc).__name__}: {exc}"]))
        return 2
    print(_line("guard", "ok", {"compile": 1, "mode": cfg.get("mode"), "raw_rules": len((cfg.get("raw") or {}).get("rules", [])),
                                 "src": cfg.get("_src")}, time.perf_counter() - t0))
    return 0


def cmd_explain(_args, cfg: dict, _t0: float) -> int:
    rd, raw, rp, b = cfg["read"], cfg["raw"], cfg["repeat_read"], cfg["batch"]
    print("\n".join([
        f"guard mode={cfg['mode']} (soft: the SAME denied call repeated within {round(cfg['window_s'] / 60)} min passes; log: only records; off: passes everything)",
        (f"READ    unranged Read of a file over {rd['min_lines']} lines or {rd['min_bytes'] // 1000} KB -> deny + outline (<= {rd['outline_lines']} lines); "
         f"limit <= {rd['ranged_max_lines']} passes; always passes: {', '.join(rd['allow'])}, binary files"),
        f"REPEAT  second Read of an UNCHANGED file (content checksum) in the same context, >= {rp['min_chars']} chars -> one-line stub; forgotten on PreCompact",
        (f"RAW     Read/`cat` of {len(raw['rules'])} raw-dump patterns (state.jsonl, game.log, ci_*.log, dev_probe_output/**, *.jsonl ...) over {raw['max_bytes']} bytes "
         f"-> the digest command + {raw['head']}+{raw['tail']} sample lines"),
        f"BASH    {len((cfg.get('bash') or {}).get('rules', []))} rules ({', '.join(r['id'] for r in (cfg.get('bash') or {}).get('rules', []))}) -> deny once with the replacement command; `# allow:ID` or the identical repeat passes",
        "LINT    PostToolUse on .py after Edit/Write: syntax + undefined name (ruff) as additionalContext, never blocks",
        f"BATCH   {b['prior_turns']} single read-only calls in a row -> additionalContext 'put independent read-only calls into ONE message' (at most every {b['cooldown_s']} s)",
        "off     AI_EVOLVE_GUARD=off (this shell) | mode = \"off\" in lua_content/guards.lua (everyone) | `qa.py guard --uninstall` (removes the hooks)",
        "data    lua_content/guards.lua -> dev_probe_output/qa/guards.json; log dev_probe_output/qa/guards.jsonl; state dev_probe_output/qa/guard_state.json",
    ]))
    return 0


def cmd_stats(_args, cfg: dict, t0: float) -> int:
    rows = load_log(_log_path(cfg))
    s = summarize(rows, cfg.get("chars_per_token", 3.5))
    detail = [f"{rule:<14} n={a['n']:<5} chars={a['chars']}" for rule, a in sorted(s["by_rule"].items(), key=lambda kv: -kv[1]["n"])]
    print(_line("guard", "ok", {k: v for k, v in s.items() if k != "by_rule"}, time.perf_counter() - t0))
    print("\n".join(f"  {ln}" for ln in detail) if detail else "  (no decisions logged yet: the hook writes dev_probe_output/qa/guards.jsonl)")
    return 0


def cmd_simulate(args, cfg: dict, t0: float) -> int:
    raw = sys.stdin.buffer.read() if args.simulate == "-" else Path(args.simulate).read_bytes()
    post = G.post_edit(raw, cfg=cfg)
    if post:                                        # PostToolUse payload: the lint answer, not a Pre decision
        print(_line("guard", "ok", {"simulate": 1, "action": "lint", "rule": "post-edit"}, time.perf_counter() - t0))
        print("\n".join(f"  {ln}" for ln in json.loads(post)["hookSpecificOutput"]["additionalContext"].splitlines()))
        return 0
    d = G.decide(raw, {"dry": True, "cfg": cfg})
    code, out, err = G.render(d)
    print(_line("guard", "ok", {"simulate": 1, "action": d.action, "rule": d.rule, "exit": code, "chars": d.chars}, time.perf_counter() - t0))
    print("\n".join(f"  {ln}" for ln in (err or out or "(no output: the call passes)").splitlines()))
    return 0


def cmd_install(args, cfg: dict, t0: float) -> int:
    path = Path(args.settings) if args.settings else SETTINGS
    try:
        before = read_settings(path)
    except ValueError as exc:
        print(_line("guard", "error", {}, time.perf_counter() - t0, [f"{path}: not valid JSON ({exc}); nothing written"]))
        return 2
    after = uninstall(before) if args.uninstall else install(before, venv_python())
    write_settings(path, after)
    verb = "removed from" if args.uninstall else "installed in"
    rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    events = ",".join(installed_events(after)) or "none"
    print(_line("guard", "ok", {"hooks": events, "mode": cfg.get("mode")}, time.perf_counter() - t0))
    print(f"  {verb} {rel}: PreToolUse (Read|Grep|Glob|Bash|Workflow: read guard + bash rules + untyped-workflow deny) + PostToolUse (Edit|Write|NotebookEdit: python lint) + PreCompact + SessionStart (resume brief) + Stop/SubagentStop (auto ckpt) ->tools/{HOOK_FILE}. "
          + ("Restart the session (or review /hooks) so it stops." if args.uninstall else
             f"Mode={cfg.get('mode')}; restart the session or review /hooks to activate; off: AI_EVOLVE_GUARD=off | qa.py guard --uninstall"))
    return 0


def cmd_status(_args, cfg: dict, t0: float) -> int:
    try:
        events = installed_events(read_settings(SETTINGS))
    except ValueError:
        events = []
    cached = G.read_json(os.path.join(G.out_dir(root=str(ROOT)), "guards.json"))
    s = summarize(load_log(_log_path(cfg)), cfg.get("chars_per_token", 3.5))
    status = "ok" if events else "warn"
    metrics = {"mode": cfg.get("mode"), "hooks": ",".join(events) or "none", "rules": _rules_state(cached), "blocks": s["blocks"], "allows": s["allows"],
               "nudges": s["nudges"], "avoided_tok": s["avoided_tok"]}
    print(_line("guard", status, metrics, time.perf_counter() - t0, [] if events else ["hooks not installed"]) + ("" if events else " | fix: python tools/qa.py guard --install"))
    return 0


COMMANDS = (("explain", cmd_explain), ("stats", cmd_stats), ("simulate", cmd_simulate), ("install", cmd_install), ("uninstall", cmd_install))


def cmd_guard(args) -> int:
    t0 = time.perf_counter()
    if args.compile:
        return cmd_compile(t0)
    cfg = G.load_cfg()
    if not cfg:
        print(_line("guard", "error", {}, time.perf_counter() - t0, ["lua_content/guards.lua did not load: `qa.py guard --compile` shows why"]))
        return 2
    handler = next((fn for flag, fn in COMMANDS if getattr(args, flag)), cmd_status)
    return handler(args, cfg, t0)


def register(sub):
    p = sub.add_parser("guard", help="tool-call guard (Claude Code hooks): outline instead of big reads, stub for repeat reads, raw-log digests; --install / --stats / --simulate",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--explain", action="store_true", help="rules, thresholds, how to disable")
    p.add_argument("--stats", action="store_true", help="blocks, allows, nudges, forced retries, tokens kept out of the context")
    p.add_argument("--compile", action="store_true", help="lua_content/guards.lua -> dev_probe_output/qa/guards.json")
    p.add_argument("--simulate", metavar="FILE.json", help="run a hook payload through the rules ('-' = stdin); no state, no log")
    p.add_argument("--install", action="store_true", help="add our hooks to .claude/settings.json (soft mode)")
    p.add_argument("--uninstall", action="store_true", help="remove our hooks from .claude/settings.json")
    p.add_argument("--settings", metavar="PATH", help="settings file for --install/--uninstall (default .claude/settings.json)")
    p.set_defaults(func=cmd_guard)
