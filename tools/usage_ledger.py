"""REAL billed usage from Claude Code transcripts (stdlib + optional orjson), incremental cache keyed by (path, size, mtime).

billed = input + cache_creation + output; cache_read is reported separately (priced ~10x cheaper). One API message spans several JSONL lines
with the same `message.id`: the LAST usage per id counts. Layout: <proj>/<session>.jsonl (main), <session>/subagents/agent-*.jsonl (+ .meta.json),
<session>/subagents/workflows/<run>/agent-*.jsonl. Data/labels: `tokens.usage` in lua_content/qa.lua.
"""
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime
from pathlib import Path

try:
    import orjson
    _loads = orjson.loads
except ImportError:                       # pragma: no cover
    _loads = json.loads

CACHE_NAME = "usage_cache.json"
FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def _obj(raw: bytes) -> dict | None:
    if b'"usage"' not in raw or b'"assistant"' not in raw:
        return None
    try:
        return _loads(raw)
    except ValueError:
        return None


def _local_day(ts) -> str:
    """Transcript timestamps are UTC (`...Z`); a day is the LOCAL calendar day, so `usage today` matches the owner's clock."""
    s = str(ts or "")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except ValueError:
        return s[:10]


def _parse(raw: bytes) -> tuple | None:
    """(message key, row) of an assistant line that carries usage, else None; only candidate lines reach the json parser."""
    o = _obj(raw) or {}
    m = o.get("message") or {}
    u = m.get("usage")
    if o.get("type") != "assistant" or not isinstance(u, dict):
        return None
    return m.get("id") or o.get("uuid"), [_local_day(o.get("timestamp")), *(int(u.get(f) or 0) for f in FIELDS)]


def scan_file(path: Path) -> list[list]:
    """[[day, inp, cw, cr, out], ...] one row per message.id (last usage wins), in order."""
    seen: dict = {}
    with path.open("rb") as fh:
        for raw in fh:
            hit = _parse(raw)
            if hit:
                seen[hit[0] or len(seen)] = hit[1]
    return list(seen.values())


def _meta(path: Path) -> dict:
    p = path.with_suffix(".meta.json")
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def project_files(folder: Path) -> list[dict]:
    """Every transcript of one project folder: {path, kind main|agent, session, id, type, run, label}."""
    out = []
    for main in sorted(folder.glob("*.jsonl")):
        out.append({"path": main, "kind": "main", "session": main.stem[:8], "id": main.stem[:8], "type": "main", "run": "", "label": ""})
        for p in sorted((main.with_suffix("") / "subagents").rglob("agent-*.jsonl")):
            mj = _meta(p)
            run = p.parent.name if p.parent.name.startswith("wf_") else ""
            out.append({"path": p, "kind": "agent", "session": main.stem[:8], "id": p.stem[6:14], "type": str(mj.get("agentType") or ""),
                        "run": run, "label": str(mj.get("description") or mj.get("label") or "")})
    return out


def load_cache(cache: Path | None) -> dict:
    try:
        return json.loads(cache.read_text(encoding="utf-8")) if cache and cache.is_file() else {}
    except (OSError, ValueError):
        return {}


def rows_for(files: list[dict], cache: Path | None) -> tuple[list[dict], bool]:
    """Files + their message rows, using/refreshing the cache. Second value: True when anything was re-scanned."""
    old, new, dirty, res = load_cache(cache), {}, False, []
    for f in files:
        key = str(f["path"])
        try:
            st = f["path"].stat()
        except OSError:
            continue
        hit = old.get(key)
        if hit and hit["size"] == st.st_size and hit["mtime"] == st.st_mtime:
            recs = hit["recs"]
        else:
            recs, dirty = scan_file(f["path"]), True
        new[key] = {"size": st.st_size, "mtime": st.st_mtime, "recs": recs}
        res.append({**f, "recs": recs})
    if cache and (dirty or set(old) != set(new)):
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(new), encoding="utf-8")
    return res, dirty


def cache_age(cache: Path) -> float | None:
    return time.time() - cache.stat().st_mtime if cache.is_file() else None


def _sum(recs: list[list]) -> dict:
    inp, cw, cr, out = (sum(r[i] for r in recs) for i in (1, 2, 3, 4))
    return {"billed": inp + cw + out, "inp": inp, "cw": cw, "cr": cr, "out": out, "turns": len(recs)}


def file_stats(f: dict, day: str | None = None) -> dict | None:
    recs = [r for r in f["recs"] if not day or r[0] == day]
    if not recs:
        return None
    first = f["recs"][0]
    return {**_sum(recs), "first_ctx": first[1] + first[2] + first[3]}


def role_of(f: dict, untyped_types: tuple = ("workflow-subagent", "")) -> str:
    return "main" if f["kind"] == "main" else ("untyped" if f["type"] in untyped_types else f["type"])


def _parts(f: dict, by: str, day: str | None, ut: tuple) -> list[tuple]:
    """[(group name, rows)] one transcript contributes to."""
    if by == "day":
        return [(d, [r for r in f["recs"] if r[0] == d]) for d in sorted({r[0] for r in f["recs"]})]
    name = {"role": role_of(f, ut), "session": f["session"], "agent": f["id"] if f["kind"] == "agent" else "main:" + f["id"]}[by]
    return [(name, [r for r in f["recs"] if not day or r[0] == day])]


def _row(name: str, g: dict) -> dict:
    return {"name": name, **_sum(g["recs"]), "first_ctx": int(statistics.median(g["firsts"])), "n": len(g["firsts"]),
            "main_billed": _sum(g["main"])["billed"], "agent_billed": _sum(g["agent"])["billed"], "type": "/".join(sorted(g["types"]))}


def group(files: list[dict], by: str, day: str | None = None, untyped_types: tuple = ("workflow-subagent", "")) -> list[dict]:
    """Groups by day|role|agent|session; each: name, billed, inp, cw, cr, out, turns, first_ctx (median of its files), n."""
    acc: dict = {}
    for f in files:
        for name, recs in _parts(f, by, day, untyped_types):
            if not recs:
                continue
            g = acc.setdefault(name, {"recs": [], "firsts": [], "main": [], "agent": [], "types": set()})
            g["recs"] += recs
            g["main" if f["kind"] == "main" else "agent"] += recs
            g["firsts"].append(recs[0][1] + recs[0][2] + recs[0][3])
            g["types"].add(role_of(f, untyped_types))
    return sorted((_row(n, g) for n, g in acc.items()), key=lambda r: -r["billed"])


def agent_samples(files: list[dict], untyped_types: tuple = ("workflow-subagent", "")) -> list[dict]:
    """One sample per agent transcript: type, billed, turns, first_ctx, cr, run."""
    out = []
    for f in files:
        s = file_stats(f) if f["kind"] == "agent" else None
        if s:
            out.append({"type": role_of(f, untyped_types), "run": f["run"], "id": f["id"], **s})
    return out


def medians(samples: list[dict], min_n: int = 3) -> dict:
    """{type: {n, billed, turns, first_ctx, cr}} medians for types with >= min_n samples."""
    by: dict = {}
    for s in samples:
        by.setdefault(s["type"], []).append(s)
    return {t: {"n": len(v), **{k: int(statistics.median(x[k] for x in v)) for k in ("billed", "turns", "first_ctx", "cr")}}
            for t, v in by.items() if len(v) >= min_n}
