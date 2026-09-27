"""qa.py ctxwatch - session context-bloat watch: snapshot enabled account plugins/skills (fed by the calling agent, not locally
queryable -- no local API for the Anthropic account's plugin/skill catalog) + this session's first_ctx (from the transcript,
via usage_ledger like `qa.py tokens --usage`), diff vs the last snapshot, flag new non-project plugins/skills inflating context.

    ListPlugins (+ ListSkills) -> qa.py ctxwatch snapshot [--file F]   # F/stdin: {"plugins": [...], "skills": [...]} (each
                                                                        # item a name, or {"name": ..., "enabled": true})
    qa.py ctxwatch                                                    # report: count + first_ctx vs the previous snapshot,
                                                                        # names added/gone (the likely cause of a jump)
    qa.py ctxwatch --json                                             # same, machine-readable

History: dev_probe_output/qa/ctxwatch_history.jsonl (git-ignored, last `ctxwatch.keep` kept). Thresholds: `ctxwatch` in lua_content/qa.lua.
Not a `qa.py check`: it needs fresh external input (the plugin/skill list) each time, which nothing local can fetch on its own.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

from probe_settings import qa_settings
from qa_report import QA_OUT, fmt_num

import usage_ledger as U
from qa_plugins.tokens import project_folder

CTXWATCH_HISTORY = QA_OUT / "ctxwatch_history.jsonl"


def cfg() -> dict:
    return dict(qa_settings()["ctxwatch"])


def _current_first_ctx() -> tuple[int | None, str]:
    """(first_ctx, session id) of the most recently touched MAIN transcript of this project, else (None, "")."""
    folder = project_folder()
    mains = [f for f in U.project_files(folder) if f["kind"] == "main"] if folder.is_dir() else []
    if not mains:
        return None, ""
    latest = max(mains, key=lambda f: f["path"].stat().st_mtime)
    rows, _ = U.rows_for([latest], QA_OUT / U.CACHE_NAME)
    stats = U.file_stats(rows[0]) if rows else None
    return (stats["first_ctx"] if stats else None), latest["session"]


def _names(items) -> list[str]:
    """A snapshot list item is a bare name, or {"name": ..., "enabled": ...} (only enabled counts when the key is present)."""
    out = [it for it in items or [] if isinstance(it, str)]
    out += [str(it["name"]) for it in items or [] if isinstance(it, dict) and it.get("name") and it.get("enabled", True)]
    return sorted(set(out))


def _load_history(path: Path = CTXWATCH_HISTORY) -> list[dict]:
    if not path.is_file():
        return []
    parsed = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        with contextlib.suppress(ValueError):
            parsed.append(json.loads(line))
    return parsed


def _append(rec: dict, keep: int, path: Path = CTXWATCH_HISTORY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > keep:
        path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")


def cmd_snapshot(args, path: Path = CTXWATCH_HISTORY) -> int:
    raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        print("ctxwatch snapshot: --file/stdin is not valid JSON "
              '(expected {"plugins": [...]} or {"plugins": [...], "skills": [...]}, items = name or {name, enabled})')
        return 2
    if isinstance(payload, list):                      # bare list = plugins, for a plain ListPlugins dump
        payload = {"plugins": payload}
    plugins, skills = _names(payload.get("plugins")), _names(payload.get("skills"))
    if not plugins and not skills:
        print("ctxwatch snapshot: no plugins/skills in the payload")
        return 2
    first_ctx, session = _current_first_ctx()
    rec = {"ts": int(time.time()), "session": session, "first_ctx": first_ctx, "plugins": plugins, "skills": skills}
    _append(rec, int(cfg()["keep"]), path)
    print(f"QA verdict=OK ctxwatch snapshot session={session or '-'} plugins={len(plugins)} skills={len(skills)} "
          f"first_ctx={fmt_num(first_ctx) if first_ctx else '-'}")
    return 0


def _named_delta(cur: list[str], prev: list[str]) -> tuple[list[str], list[str]]:
    cur_s, prev_s = set(cur), set(prev)
    return sorted(cur_s - prev_s), sorted(prev_s - cur_s)


def _diff(cur: dict, prev: dict | None) -> dict:
    """Everything comparative between `cur` and `prev` (prev=None: `cur` is the baseline, nothing is "new" yet)."""
    if not prev:
        return {"d_ctx": None, "d_plugins": None, "d_skills": None,
                "added_plugins": [], "removed_plugins": [], "added_skills": [], "removed_skills": []}
    added_p, removed_p = _named_delta(cur.get("plugins") or [], prev["plugins"])
    added_s, removed_s = _named_delta(cur.get("skills") or [], prev["skills"])
    d_ctx = cur["first_ctx"] - prev["first_ctx"] if cur.get("first_ctx") and prev.get("first_ctx") else None
    return {"d_ctx": d_ctx, "d_plugins": len(cur.get("plugins") or []) - len(prev["plugins"]),
            "d_skills": len(cur.get("skills") or []) - len(prev["skills"]),
            "added_plugins": added_p, "removed_plugins": removed_p, "added_skills": added_s, "removed_skills": removed_s}


def _report(path: Path = CTXWATCH_HISTORY) -> dict:
    hist = _load_history(path)
    if not hist:
        return {"ok": True, "empty": True}
    cur, prev = hist[-1], hist[-2] if len(hist) > 1 else None
    d = _diff(cur, prev)
    w = cfg()
    new_names = len(d["added_plugins"]) + len(d["added_skills"])
    bad = new_names >= int(w["warn_new"]) or (d["d_ctx"] is not None and d["d_ctx"] > int(w["warn_ctx_grow"]))
    return {"ok": not bad, "empty": False, "session": cur.get("session"), "first_ctx": cur.get("first_ctx"),
            "plugins": len(cur.get("plugins") or []), "skills": len(cur.get("skills") or []), **d}


def _fmt_count(label: str, cur: int, d: int | None) -> str:
    delta = f"({'+' if d > 0 else ''}{d})" if d else ""
    return f"{label}={cur}{delta}"


def _fmt_names(label: str, names: list[str], cap: int = 8) -> str:
    shown = ", ".join(names[:cap])
    return f"  {label}: {shown}" + (f" (+{len(names) - cap} more)" if len(names) > cap else "")


def _print_text_report(r: dict) -> None:
    if r.get("empty"):
        print("ctxwatch: no snapshot yet -- ListPlugins (+ optionally ListSkills), pipe to `qa.py ctxwatch snapshot` "
              "(no local tool can list the account's plugins/skills)")
        return
    ctx = f"first_ctx={fmt_num(r['first_ctx']) if r['first_ctx'] else '-'}" + (f"({'+' if r['d_ctx'] > 0 else ''}{r['d_ctx']})" if r["d_ctx"] else "")
    print(f"{'ok' if r['ok'] else 'warn':<5} ctxwatch {_fmt_count('plugins', r['plugins'], r['d_plugins'])} "
          f"{_fmt_count('skills', r['skills'], r['d_skills'])} {ctx}")
    for label, names in (("+ new plugin", r["added_plugins"]), ("- gone plugin", r["removed_plugins"]),
                          ("+ new skill", r["added_skills"]), ("- gone skill", r["removed_skills"])):
        if names:
            print(_fmt_names(label, names))


def cmd_ctxwatch(args, path: Path = CTXWATCH_HISTORY) -> int:
    r = _report(path)
    print(json.dumps(r)) if getattr(args, "json", False) else _print_text_report(r)
    return 0 if r.get("ok", True) else 1


def brief_line(path: Path = CTXWATCH_HISTORY) -> str:
    """One line for `qa.py brief`, or "" without a snapshot yet / on any error (brief never fails on a side line)."""
    try:
        r = _report(path)
        if r.get("empty"):
            return ""
        bits = [_fmt_count("plugins", r["plugins"], r["d_plugins"])]
        if r["skills"]:
            bits.append(_fmt_count("skills", r["skills"], r["d_skills"]))
        tag = " (non-project bloat?)" if not r["ok"] else ""
        return "ctxwatch: " + " ".join(bits) + tag + " | `qa.py ctxwatch`"
    except Exception:  # noqa: BLE001 - a side line on `brief` must never crash it
        return ""


def register(sub):
    p = sub.add_parser("ctxwatch", help="session context-bloat watch: snapshot enabled account plugins/skills (fed by the "
                        "calling agent) + first_ctx, diff vs the last snapshot, flag new non-project plugins/skills",
                        description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", nargs="?", choices=["snapshot"], help="snapshot = record a new one; omit = report vs last")
    p.add_argument("--file", help="snapshot: read the {plugins, skills} JSON from this file instead of stdin")
    p.add_argument("--json", action="store_true", help="report as one JSON object instead of text lines")
    p.set_defaults(func=lambda args: cmd_snapshot(args) if args.action == "snapshot" else cmd_ctxwatch(args))
