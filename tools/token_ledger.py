"""Transcript waste ledger (stdlib + optional orjson): parse Claude Code session JSONL into per-log metrics.

Schema quirk: every content block of an assistant message is a SEPARATE line, so tool_use blocks are grouped by `message.id`
into real turns. tool_result blocks live in user records (`message.content[]`, `tool_use_id`). Sizes are chars (tokens ~ chars/4).
Thresholds and patterns: `tokens` in lua_content/qa.lua (passed in as `cfg`). Counts are approximate (undocumented schema).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

try:
    import orjson
    _loads = orjson.loads
except ImportError:                       # pragma: no cover - the json fallback is the same schema, slower
    _loads = json.loads


class Log:
    """Raw facts of one transcript file: ordered turns, results by tool_use_id, assistant text."""

    def __init__(self, name: str):
        self.name = name
        self.turns: dict[str, list[dict]] = {}
        self.results: dict[str, dict] = {}
        self.text: list[str] = []


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _call(block: dict) -> dict:
    inp = block.get("input") or {}
    return {"id": block.get("id", ""), "tool": block.get("name", "?"), "input": inp,
            "in_chars": len(json.dumps(inp, ensure_ascii=False)),
            "path": inp.get("file_path") or inp.get("path") or inp.get("pattern") or (inp.get("command") or "")[:60]}


def _take_assistant(log: Log, rec: dict) -> None:
    msg = rec.get("message") or {}
    turn = log.turns.setdefault(msg.get("id") or rec.get("uuid", ""), [])
    for block in msg.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            turn.append(_call(block))
        elif block.get("type") == "text":
            log.text.append(block.get("text", ""))


def _take_user(log: Log, rec: dict) -> None:
    content = (rec.get("message") or {}).get("content")
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            body = _text_of(block.get("content"))
            log.results[block.get("tool_use_id", "")] = {"chars": len(body), "lines": body.count("\n") + 1,
                                                        "error": bool(block.get("is_error")), "head": body[:200]}


def parse_log(path: Path) -> Log:
    log = Log(path.stem)
    with open(path, "rb") as fh:
        for raw in fh:
            if b'"message"' not in raw:
                continue
            try:
                rec = _loads(raw)
            except ValueError:
                continue
            kind = rec.get("type")
            if kind == "assistant":
                _take_assistant(log, rec)
            elif kind == "user":
                _take_user(log, rec)
    return log


def is_readonly(call: dict, cfg: dict, writes: list[re.Pattern]) -> bool:
    if call["tool"] in cfg["readonly_tools"]:
        return True
    if call["tool"] not in cfg["shell_tools"]:
        return False
    cmd = re.sub(r"\d*>&\d|\d*>\s*/dev/null|\d*>\s*\$null", "", call["input"].get("command", ""))
    return not any(p.search(cmd) for p in writes)


def saveable_turns(flags: list[bool]) -> int:
    """Runs of >= 2 consecutive all-read-only turns: each run saves len-1 turns when batched."""
    saved = run = 0
    for ro in [*flags, False]:
        if ro:
            run += 1
        else:
            saved += max(0, run - 1)
            run = 0
    return saved


def _by_tool(calls: list[dict], log: Log, cpt: int) -> dict:
    tot: Counter = Counter()
    for c in calls:
        tot[c["tool"]] += log.results.get(c["id"], {}).get("chars", 0) // cpt
    return dict(tot.most_common())


def _reads(calls: list[dict], log: Log, min_lines: int) -> tuple[int, int, list]:
    paths = Counter(c["path"] for c in calls if c["tool"] == "Read")
    repeats = sum(n - 1 for n in paths.values())
    unbounded = [c["path"] for c in calls if c["tool"] == "Read" and "offset" not in c["input"] and "limit" not in c["input"]
                 and log.results.get(c["id"], {}).get("lines", 0) > min_lines]
    return repeats, len(unbounded), unbounded


def _writes(calls: list[dict], cpt: int) -> dict:
    out: Counter = Counter()
    for c in calls:
        tool, inp = c["tool"], c["input"]
        if tool == "Edit":
            out["edit"] += c["in_chars"]
            out["edit_old"] += len(inp.get("old_string", ""))
        elif tool == "Write":
            out["write"] += c["in_chars"]
        elif tool in ("Bash", "PowerShell") and "<<" in inp.get("command", ""):
            out["heredoc"] += c["in_chars"]
    return {k: v // cpt for k, v in out.items()}


def _retries(calls: list[dict], log: Log, prefix: int) -> int:
    heads = Counter(log.results[c["id"]]["head"][:prefix] for c in calls if log.results.get(c["id"], {}).get("error"))
    return sum(n - 1 for n in heads.values())


def turn_shape(turns: list[list[dict]], readonly: list[bool]) -> dict:
    n, calls = len(turns), sum(len(t) for t in turns)
    saved = saveable_turns(readonly)
    pct = (lambda k: round(100 * k / n)) if n else (lambda k: 0)
    return {"turns": n, "calls": calls, "cpt": round(calls / n, 2) if n else 0.0, "multi_pct": pct(sum(len(t) > 1 for t in turns)),
            "saveable": saved, "saveable_pct": pct(saved)}


_RELAY = re.compile(r"^RELAY:", re.M)


def readonly_flags(turns: list[list[dict]], cfg: dict, writes: list[re.Pattern]) -> list[bool]:
    return [all(is_readonly(c, cfg, writes) for c in t) for t in turns]


def _heavy(calls: list[dict], log: Log, cpt: int, top: int) -> list:
    rows = sorted(((log.results.get(c["id"], {}).get("chars", 0) // cpt, c["tool"], c["path"]) for c in calls), reverse=True)
    return [list(h) for h in rows[:top]]


def metrics(log: Log, cfg: dict) -> dict:
    """All ledger numbers of one log. A turn = one message id with >= 1 tool call."""
    cpt = int(cfg["chars_per_token"])
    writes = [re.compile(p) for p in cfg["write_patterns"]]
    turns = [t for t in log.turns.values() if t]
    calls = [c for t in turns for c in t]
    repeats, unbounded, unbounded_paths = _reads(calls, log, int(cfg["unbounded_lines"]))
    return {
        **turn_shape(turns, readonly_flags(turns, cfg, writes)),
        "result_tok": sum(r["chars"] for r in log.results.values()) // cpt, "by_tool": _by_tool(calls, log, cpt),
        "repeats": repeats, "unbounded": unbounded, "unbounded_paths": unbounded_paths[:5],
        "heavy": _heavy(calls, log, cpt, int(cfg["heavy_top"])),
        "writes": _writes(calls, cpt), "retries": _retries(calls, log, int(cfg["retry_prefix"])),
        "relays": sum(bool(_RELAY.search(t)) for t in log.text),
    }


def guard_stats(path: Path, cpt: int = 4) -> dict:
    """blocks / allows / tokens kept out of the context from dev_probe_output/qa/guards.jsonl ({} when absent)."""
    if not path.is_file():
        return {}
    acts: Counter = Counter()
    chars = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = _loads(line)
        except ValueError:
            continue
        acts[rec.get("act", "?")] += 1
        chars += rec.get("chars", 0) if rec.get("act") == "deny" else 0
    return {"blocks": acts.get("deny", 0), "allows": acts.get("allow", 0), "nudges": acts.get("nudge", 0), "avoided_tok": chars // cpt}


def session_files(main: Path) -> tuple[Path, list[Path]]:
    """(main transcript, sub-agent logs under <session>/subagents/** and <session>/workflows/**)."""
    root = main.with_suffix("")
    subs = sorted(p for d in ("subagents", "workflows") for p in (root / d).rglob("agent-*.jsonl")) if root.is_dir() else []
    return main, subs


def find_session(projects: Path, root: Path, which: str) -> Path | None:
    """`latest` (newest transcript of this project), a session id, or a PATH."""
    if which.endswith(".jsonl") and Path(which).is_file():
        return Path(which)
    folder = projects / re.sub(r"[^A-Za-z0-9]", "-", str(root))
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
    if which == "latest":
        return files[-1] if files else None
    return next((p for p in files if p.stem.startswith(which)), None)
