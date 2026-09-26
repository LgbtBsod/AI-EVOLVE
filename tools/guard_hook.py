#!/usr/bin/env python3
"""guard_hook - Claude Code hook entry point that keeps big, raw and repeated reads out of an agent's context (stdlib only, fails OPEN).

Called by the hooks that `qa.py guard --install` writes to .claude/settings.json (PreToolUse: Read|Grep|Glob|Bash, and PreCompact):

    .venv/Scripts/python.exe -S -E tools/guard_hook.py          # the hook JSON arrives on stdin

    deny  = exit 2 + the answer on stderr (Claude Code hands it to the model: outline / digest command / one-line stub, all with the retry hint)
    nudge = exit 0 + {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "..."}}
    pass  = exit 0, no output. It never prints permissionDecision "allow": that would skip the user's permission prompts.

Rules (data: lua_content/guards.lua, compiled to dev_probe_output/qa/guards.json; management: `qa.py guard`):
    READ GUARD   unranged Read of a file over N lines / M bytes -> the outline (tools/file_toc.py) + how to retry
    REPEAT STUB  second Read of an UNCHANGED file in the same context -> one line (the state resets on PreCompact)
    RAW-LOG      Read (or `cat`) of state.jsonl / game.log / ci_*.log / dev_probe_output dumps -> the digest command + a small head/tail sample
    BATCH NUDGE  two single read-only calls in a row -> "put independent read-only calls into ONE message"
Soft mode: the SAME denied call repeated within `window_s` passes, so the guard can never dead-lock a session. AI_EVOLVE_GUARD=off disables it.
Any internal error, malformed JSON or missing config -> exit 0 without output (the guard must never block work by accident).

Start-up budget: the interpreter alone is ~55 ms on Windows; `json` + `re` would add ~25 ms more, so the module imports only os/sys/time/zlib
(JSON goes through the C scanner `_json` directly, globs are matched without `re`; `re`/`json` are imported lazily on the rare paths that need them).
"""
from __future__ import annotations

import os
import sys
import time
import zlib

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS_DIR)
STATE_VERSION = 1


class Decision:
    """action: allow | deny | nudge; rule: which rule spoke ("-" = nothing to log); chars: estimated context kept out (deny) / read anyway (forced retry)."""
    __slots__ = ("action", "chars", "key", "message", "path", "rule")

    def __init__(self, action="allow", rule="-", path="", message="", chars=0, key=""):  # noqa: PLR0913 - a plain record
        self.action, self.rule, self.path, self.message, self.chars, self.key = action, rule, path, message, chars, key

    def _replace(self, **kw) -> Decision:
        new = Decision(self.action, self.rule, self.path, self.message, self.chars, self.key)
        for name, value in kw.items():
            setattr(new, name, value)
        return new


class FileInfo:
    """What one scan of a file yields: size, line count, content checksum, the bytes (first 64 KB of a huge file), binary?, huge?"""
    __slots__ = ("binary", "crc", "data", "huge", "lines", "size")

    def __init__(self, size: int, lines: int, crc: str, data: bytes, binary: bool, huge: bool):  # noqa: PLR0913 - a plain record
        self.size, self.lines, self.crc, self.data, self.binary, self.huge = size, lines, crc, data, binary, huge


# ---------------------------------------------------------------- JSON without importing json (json.decoder pulls in `re`: ~25 ms)

class _ScanCtx:
    """The context object the C scanner of `json` expects (what json.decoder.JSONDecoder sets up)."""
    strict, object_hook, object_pairs_hook, parse_float, parse_int = True, None, None, float, int

    @staticmethod
    def parse_constant(_name):
        return None


try:
    from _json import encode_basestring_ascii as _enc_str, make_scanner as _make_scanner
    _SCAN = _make_scanner(_ScanCtx)
except ImportError:  # pragma: no cover - a Python without the C accelerator: fall back to the (slower) json module
    _enc_str = _SCAN = None


def loads(data):
    """JSON text/bytes -> object (ValueError when malformed)."""
    text = data.decode("utf-8") if isinstance(data, bytes | bytearray) else data
    if _SCAN is None:
        import json
        return json.loads(text.lstrip("﻿"))
    start = len(text) - len(text.lstrip("﻿ \t\r\n"))
    try:
        return _SCAN(text, start)[0]
    except StopIteration:
        raise ValueError("no JSON value") from None


def dumps(obj) -> str:
    """Compact JSON of str/int/float/bool/None/list/tuple/dict (what the state, the log and the hook answer contain)."""
    if _enc_str is None:
        import json
        return json.dumps(obj, separators=(",", ":"))
    if isinstance(obj, str):
        return _enc_str(obj)
    if isinstance(obj, dict):
        return "{" + ",".join(f"{_enc_str(str(k))}:{dumps(v)}" for k, v in obj.items()) + "}"
    if isinstance(obj, list | tuple):
        return "[" + ",".join(map(dumps, obj)) + "]"
    return _scalar(obj)


def _scalar(obj) -> str:
    if isinstance(obj, float):
        return repr(obj) if obj - obj == 0 else "null"          # nan / inf are not JSON
    if obj is None:
        return "null"
    return ("true" if obj else "false") if isinstance(obj, bool) else str(int(obj))


class Ctx:
    """Everything one hook call needs: config, state (loaded once, saved once when dirty), who is asking."""
    __slots__ = ("cfg", "cwd", "dirty", "dry", "now", "out", "owner", "payload", "root", "state")

    def __init__(self, payload: dict, cfg: dict, opts: dict):
        self.payload, self.cfg = payload, cfg
        self.root = opts.get("root", ROOT)
        self.out = opts.get("out") or out_dir(opts.get("env"), self.root)
        self.now = opts.get("now") or time.time()
        self.dry, self.dirty = bool(opts.get("dry")), False
        self.owner = str(payload.get("agent_id") or payload.get("session_id") or "?")[:24]   # a sub-agent has its own context
        self.cwd = payload.get("cwd") or self.root
        self.state = opts["state"] if opts.get("state") is not None else load_state(self.out)


# ---------------------------------------------------------------- files: config, state, log

def out_dir(env=None, root: str = ROOT) -> str:
    return (env if env is not None else os.environ).get("AI_EVOLVE_GUARD_OUT") or os.path.join(root, "dev_probe_output", "qa")


def read_json(path: str):
    try:
        with open(path, "rb") as fh:
            return loads(fh.read())
    except (OSError, ValueError):
        return None


def _write_json(path: str, obj) -> None:
    """Atomic write (tmp + replace); Windows may refuse the replace while another hook reads the file: retry briefly."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(dumps(obj))
    for _ in range(4):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.01)
    os.replace(tmp, path)


def crc_of(data: bytes) -> str:
    return f"{zlib.crc32(data):08x}:{len(data)}"


def default_loader(path: str) -> dict:
    """The only place that boots Lua: tools/lua_bridge (rust_core or lupa). Runs on `--compile` and when guards.lua changed."""
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)
    import lua_bridge
    return lua_bridge.load(path)


def compile_rules(root: str = ROOT, out: str | None = None, loader=None) -> dict:
    """lua_content/guards.lua -> dev_probe_output/qa/guards.json (with the source checksum, so a stale cache is detected)."""
    src = os.path.join(root, "lua_content", "guards.lua")
    with open(src, "rb") as fh:
        crc = crc_of(fh.read())
    cfg = dict((loader or default_loader)(src))
    cfg["_src"] = crc
    _write_json(os.path.join(out or out_dir(root=root), "guards.json"), cfg)
    return cfg


def load_cfg(root: str = ROOT, out: str | None = None, loader=None) -> dict | None:
    """The compiled rules; recompiled when guards.lua changed. None = no rules (the hook then passes everything)."""
    out = out or out_dir(root=root)
    try:
        with open(os.path.join(root, "lua_content", "guards.lua"), "rb") as fh:
            crc = crc_of(fh.read())
    except OSError:
        return None
    cached = read_json(os.path.join(out, "guards.json"))
    if isinstance(cached, dict) and cached.get("_src") == crc:
        return cached
    try:
        fresh = compile_rules(root, out, loader) if loader else _compile_in_child(root, out)
    except Exception:  # noqa: BLE001 - tool boundary: a broken Lua file must not block work; a stale cache still guards
        fresh = None
    if isinstance(fresh, dict) and fresh.get("_src") == crc:
        return fresh
    return cached if isinstance(cached, dict) else None


def _compile_in_child(root: str, out: str) -> dict | None:
    """The hook runs `python -S -E`: no site-packages, so no lupa / rust_core. A child interpreter with site does the (rare) recompile."""
    import subprocess
    subprocess.run([sys.executable, "-E", os.path.abspath(__file__), "--compile", root, out], capture_output=True, timeout=8, check=False)
    return read_json(os.path.join(out, "guards.json"))


def load_state(out: str) -> dict:
    st = read_json(os.path.join(out, "guard_state.json"))
    if not isinstance(st, dict) or st.get("v") != STATE_VERSION:
        st = {"v": STATE_VERSION}
    for name in ("reads", "denied", "nudge"):
        if not isinstance(st.get(name), dict):
            st[name] = {}
    return st


def save_state(ctx: Ctx) -> None:
    scfg = ctx.cfg.get("state") or {}
    ttl, cap = scfg.get("ttl_s", 21600), scfg.get("max_entries", 1500)
    for name in ("reads", "denied"):
        keep = {k: v for k, v in ctx.state[name].items() if ctx.now - v.get("t", 0) <= ttl}
        if len(keep) > cap:
            keep = dict(sorted(keep.items(), key=lambda kv: kv[1]["t"])[-cap:])
        ctx.state[name] = keep
    ctx.state["nudge"] = {k: t for k, t in ctx.state["nudge"].items() if ctx.now - t <= ttl}
    _write_json(os.path.join(ctx.out, scfg.get("path", "guard_state.json")), ctx.state)


def append_log(ctx: Ctx, d: Decision) -> None:
    """One JSON line per decision: ts, rule, act, path, chars (avoided for a deny, wasted for a forced retry), k (call key), o (owner)."""
    lcfg = ctx.cfg.get("log") or {}
    rec = {"ts": round(ctx.now, 1), "rule": d.rule, "act": d.action, "path": d.path, "chars": d.chars,
           "k": f"{zlib.crc32(d.key.encode()):08x}" if d.key else "", "o": ctx.owner[:8], "sub": 1 if ctx.payload.get("agent_id") else 0}
    path = os.path.join(ctx.out, lcfg.get("path", "guards.jsonl"))
    os.makedirs(ctx.out, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (dumps(rec) + "\n").encode("utf-8"))
        big = os.fstat(fd).st_size > lcfg.get("max_kb", 512) * 1024
    finally:
        os.close(fd)
    if big:
        _trim_log(path)


def _trim_log(path: str) -> None:
    with open(path, "rb") as fh:
        lines = fh.read().splitlines()
    with open(path, "wb") as fh:
        fh.write(b"\n".join(lines[len(lines) // 2:]) + b"\n")


# ---------------------------------------------------------------- small helpers

_RX: dict = {}


def _rx(pattern: str):
    """A compiled regex (`re` is imported on first use: only Bash commands and the batch nudge need one)."""
    if pattern not in _RX:
        import re
        _RX[pattern] = re.compile(pattern)
    return _RX[pattern]


def glob_match(pat: str, s: str) -> bool:
    """.gitignore-like glob on a lower-cased forward-slash path: `**/` any directories (or none), `**` anything, `*` inside a name, `?` one character."""
    if not pat:
        return not s
    if pat.startswith("**/"):
        return glob_match(pat[3:], s) or any(glob_match(pat[3:], s[i + 1:]) for i, c in enumerate(s) if c == "/")
    if pat.startswith("**"):
        return any(glob_match(pat[2:], s[i:]) for i in range(len(s) + 1))
    return _glob_star(pat[1:], s) if pat[0] == "*" else _glob_char(pat, s)


def _glob_star(rest: str, s: str) -> bool:
    """`*`: any run of characters that does not cross a `/`."""
    n = 0
    while not glob_match(rest, s[n:]):
        if n >= len(s) or s[n] == "/":
            return False
        n += 1
    return True


def _glob_char(pat: str, s: str) -> bool:
    return bool(s) and (pat[0] == s[0] or (pat[0] == "?" and s[0] != "/")) and glob_match(pat[1:], s[1:])


def _pkey(path: str) -> str:
    return path.replace("\\", "/").lower()


def _match_any(pk: str, patterns) -> bool:
    return any(glob_match(p.lower(), pk) for p in patterns)


def _rel(path: str, root: str) -> str:
    p, r = path.replace("\\", "/"), root.replace("\\", "/").rstrip("/") + "/"
    return p[len(r):] if p.lower().startswith(r.lower()) else p


def _abs(path: str, cwd: str) -> str:
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd, path))


def _int(value):
    try:
        return int(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _fmt(template: str, **kv) -> str:
    for k, v in kv.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def _k(chars: float, per_token: float) -> str:
    return str(max(1, round(chars / per_token / 1000)))


def _ago(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} s"
    return f"{seconds / 60:.0f} min" if seconds < 5400 else f"{seconds / 3600:.1f} h"


def scan_file(path: str, max_bytes: int) -> FileInfo:
    """size, line count, content checksum and the bytes (the first 64 KB only for a file over max_bytes: judged by size + mtime)."""
    st = os.stat(path)
    if st.st_size > max_bytes:
        with open(path, "rb") as fh:
            head = fh.read(65536)
        return FileInfo(st.st_size, 0, f"huge:{st.st_size}:{st.st_mtime_ns}", head, b"\0" in head[:8192], True)
    with open(path, "rb") as fh:
        data = fh.read()
    lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    return FileInfo(len(data), lines, crc_of(data), data, b"\0" in data[:8192], False)


def _range(ti: dict, fi: FileInfo, default_lines: int) -> tuple[int, int | None, int]:
    """(first line, limit or None, last line) of a Read call."""
    start, limit = max(1, _int(ti.get("offset")) or 1), _int(ti.get("limit"))
    if limit is not None and limit <= 0:
        limit = None
    last = start + (limit if limit is not None else default_lines) - 1
    return start, limit, min(last, fi.lines) if fi.lines else last


def _est_chars(fi: FileInfo, first: int, last: int) -> int:
    return fi.size if not fi.lines else int(fi.size * max(1, last - first + 1) / fi.lines)


# ---------------------------------------------------------------- rules: raw log, repeat, big

def _rule_raw(path: str, fi: FileInfo, rng, ctx: Ctx) -> Decision | None:
    raw, per = ctx.cfg["raw"], ctx.cfg.get("chars_per_token", 3.5)
    limit = rng[1]
    if fi.size <= raw["max_bytes"] or (limit is not None and limit <= raw["ranged_max_lines"]):
        return None
    pk = _pkey(path)
    rule = None if _match_any(pk, raw.get("skip", ())) else next((r for r in raw["rules"] if glob_match(r["glob"].lower(), pk)), None)
    if rule is None:
        return None
    rel = _rel(path, ctx.root)
    msg = _fmt(ctx.cfg["messages"]["read_raw"], rel=rel, kb=f"{fi.size / 1024:.0f}", tok=_k(fi.size, per), digest=rule["digest"],
               sample=_sample(path, fi, raw), window=round(ctx.cfg["window_s"] / 60))
    return Decision("deny", "read-raw", rel, msg, max(0, fi.size - len(msg)))


def _file_tail(path: str, size: int, n: int) -> list[bytes]:
    with open(path, "rb") as fh:
        fh.seek(max(0, size - 16384))
        return fh.read().splitlines()[1:][-n:]


def _sample(path: str, fi: FileInfo, raw: dict) -> str:
    """The first `head` and the last `tail` lines (a `...` row between them when lines are missing)."""
    cap, head, tail = raw["line_cap"], raw["head"], raw["tail"]
    lines = fi.data.splitlines()
    gap = fi.huge or len(lines) > head + tail
    if fi.huge:
        lines = lines[:head] + _file_tail(path, fi.size, tail)
    elif gap:
        lines = lines[:head] + lines[-tail:]
    shown = [b.decode("utf-8", "replace")[:cap] for b in lines]
    return "\n".join("  " + p for p in [*shown[:head], *["..."] * gap, *shown[head:]])


def _rule_repeat(path: str, fi: FileInfo, rng, ctx: Ctx) -> Decision | None:
    rp = ctx.cfg.get("repeat_read") or {}
    rec = ctx.state["reads"].get(f"{ctx.owner}|{_pkey(path)}")
    if not rp.get("enabled") or not rec or rec["h"] != fi.crc:
        return None
    first, _, last = rng
    if not any(a <= first and last <= b for a, b in rec["r"]):
        return None
    est = _est_chars(fi, first, last)
    if est < rp["min_chars"]:
        return None
    rel = _rel(path, ctx.root)
    msg = _fmt(ctx.cfg["messages"]["read_repeat"], rel=rel, age=_ago(ctx.now - rec["t"]), tok=_k(est, ctx.cfg.get("chars_per_token", 3.5)))
    return Decision("deny", "read-repeat", rel, msg, max(0, est - len(msg)))


def _rule_big(path: str, fi: FileInfo, rng, ctx: Ctx) -> Decision | None:
    rd, per = ctx.cfg["read"], ctx.cfg.get("chars_per_token", 3.5)
    first, limit, last = rng
    est = _est_chars(fi, first, last)
    over_lines = last - first + 1 > (rd["min_lines"] if limit is None else rd["ranged_max_lines"]) and (fi.lines > 0 or limit is not None)
    if not (over_lines or (limit is None and est > rd["min_bytes"])):
        return None
    rel = _rel(path, ctx.root)
    msg = _fmt(ctx.cfg["messages"]["read_big"], rel=rel, lines=fi.lines or "many", kb=f"{fi.size / 1024:.0f}", tok=_k(est, per),
               outline=_outline_text(path, fi, ctx), sym=_sym_hint(rel, ctx), window=round(ctx.cfg["window_s"] / 60))
    return Decision("deny", "read-big", rel, msg, max(0, est - len(msg)))


def _outline_text(path: str, fi: FileInfo, ctx: Ctx) -> str:
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)
    import file_toc
    lines = file_toc.outline_for(path, fi.data, ctx.cfg.get("outline") or {}, max(5, ctx.cfg["read"]["outline_lines"] - 4))
    return "\n".join("  " + ln for ln in lines)


def _sym_hint(rel: str, ctx: Ctx) -> str:
    sym = ctx.cfg["read"].get("sym_file")
    return f" (or `python tools/qa.py sym {rel}:FUNC`)" if sym and os.path.isfile(os.path.join(ctx.root, sym)) else ""


# ---------------------------------------------------------------- read flow (Read and `cat FILE`)

def _note_read(ctx: Ctx, path: str, fi: FileInfo, span: tuple[int, int]) -> None:
    key = f"{ctx.owner}|{_pkey(path)}"
    rec = ctx.state["reads"].get(key)
    if rec is None or rec["h"] != fi.crc:            # a changed file: what was read before is void
        rec = {"h": fi.crc, "t": ctx.now, "r": []}
    rec["t"] = ctx.now
    merged: list[list[int]] = []
    for a, b in sorted([*rec["r"], list(span)]):
        if merged and a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    rec["r"] = merged[-(ctx.cfg.get("repeat_read") or {}).get("max_ranges", 8):]
    ctx.state["reads"][key] = rec
    ctx.dirty = True


def _take_denied(ctx: Ctx, dkey: str) -> dict | None:
    """The same call denied a moment ago -> this is the retry: it passes (soft mode) and the entry is spent."""
    den = ctx.state["denied"].get(dkey)
    if not den or ctx.cfg.get("mode") != "soft" or ctx.now - den.get("t", 0) > ctx.cfg["window_s"]:
        return None
    del ctx.state["denied"][dkey]
    ctx.dirty = True
    return den


def _bypass(pk: str, rel: str, rd: dict) -> Decision | None:
    """Files the guard never judges: the allow-list (.claude/, memory, CLAUDE.md ...) and binary extensions."""
    if _match_any(pk, rd["allow"]):
        return Decision("allow", "read-allow", rel)
    return Decision("allow", "read-binary", rel) if pk.rsplit(".", 1)[-1] in rd["binary_ext"] else None


def read_flow(path: str, ti: dict, ctx: Ctx, rules) -> Decision:
    """One read through the rules: bypass -> (the retry of a denied call passes) -> the first rule that fires -> allow + remember."""
    rd, rel = ctx.cfg["read"], _rel(path, ctx.root)
    hit = _bypass(_pkey(path), rel, rd)
    if hit:
        return hit
    try:
        fi = scan_file(path, rd["max_scan_bytes"])
    except OSError:
        return Decision()                                   # missing / unreadable: the tool reports it
    return Decision("allow", "read-binary", rel) if fi.binary else _judge(path, fi, ti, ctx, rules)


def _judge(path: str, fi: FileInfo, ti: dict, ctx: Ctx, rules) -> Decision:
    """The file is known text: the retry of a denied call passes, else the first rule that fires denies, else allow + remember."""
    rng = _range(ti, fi, ctx.cfg["read"]["default_lines"])
    dkey = f"{ctx.owner}|{_pkey(path)}|{rng[0]}:{rng[1] or 0}"
    den = _take_denied(ctx, dkey)
    fired = None if den else next(filter(None, (rule(path, fi, rng, ctx) for rule in rules)), None)
    if fired:
        return fired._replace(key=dkey)
    _note_read(ctx, path, fi, (rng[0], rng[2]))
    return Decision("allow", "read-retry" if den else "read-pass", _rel(path, ctx.root), chars=(den or {}).get("c", 0), key=dkey)


def _read_call(ti: dict, ctx: Ctx) -> Decision:
    path = ti.get("file_path")
    if not isinstance(path, str) or not path:
        return Decision()
    return read_flow(_abs(path, ctx.cwd), ti, ctx, (_rule_raw, _rule_repeat, _rule_big))


def _bash_rule(cmd: str, ctx: Ctx) -> Decision:
    """The first bash rule (guards.lua `bash.rules`) the command breaks: deny once with the fix; the identical repeat passes; `# allow:ID` passes at once."""
    bcfg = ctx.cfg.get("bash") or {}
    if not bcfg.get("enabled") or not cmd:
        return Decision()
    for rule in bcfg.get("rules") or ():
        if ("allow:" + rule["id"]) in cmd or not _rx(rule["pattern"]).search(cmd):
            continue
        key = f"{ctx.owner}|bash|{rule['id']}|{crc_of(cmd.encode('utf-8', 'replace'))}"
        if _take_denied(ctx, key):
            return Decision("allow", "bash-retry", rule["id"], key=key)
        msg = _fmt(ctx.cfg["messages"]["bash"], id=rule["id"], say=rule["say"], window=round(ctx.cfg["window_s"] / 60))
        return Decision("deny", "bash-" + rule["id"], cmd[:80], msg, key=key)
    return Decision()


def _bash_call(ti: dict, ctx: Ctx) -> Decision:
    """Known-bad forms first (guard-bash); then `cat FILE` is an unranged Read: only the raw-log rule applies to it."""
    cmd = str(ti.get("command") or "")
    hit = _bash_rule(cmd, ctx)
    if hit.rule != "-":
        return hit
    m = _rx(ctx.cfg["raw"]["bash_cat"]).match(cmd)
    if not m:
        return Decision()
    d = read_flow(_abs(m.group("path").strip("\"'"), ctx.cwd), {}, ctx, (_rule_raw,))
    if d.action == "deny":
        return d._replace(rule="bash-raw")
    return d if d.rule == "read-retry" else Decision()      # a forced retry is logged: the statistics net it against the deny


# ---------------------------------------------------------------- batch nudge

def _is_readonly(name, inp, bcfg: dict) -> bool:
    if name in bcfg["readonly_tools"]:
        return True
    return name == "Bash" and bool(_rx(bcfg["readonly_bash"]).match(str((inp or {}).get("command") or "")))


def _transcript_for(payload: dict) -> str | None:
    tp, agent, sess = payload.get("transcript_path"), payload.get("agent_id"), payload.get("session_id")
    if not tp or not agent or os.path.basename(tp).startswith("agent-"):
        return tp
    folder = os.path.join(os.path.dirname(tp), sess or os.path.splitext(os.path.basename(tp))[0], "subagents")
    for name in dict.fromkeys((str(agent), str(agent).removeprefix("agent-"), str(agent).removeprefix("subagent-"))):
        cand = os.path.join(folder, f"agent-{name}.jsonl")
        if os.path.isfile(cand):
            return cand
    return None


def _tail_lines(path: str, nbytes: int) -> list[bytes]:
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        fh.seek(max(0, size - nbytes))
        lines = fh.read().split(b"\n")
    return lines[1:] if size > nbytes else lines


def _turn_groups(lines: list[bytes]) -> list[list[tuple]]:
    """Assistant turns (grouped by message id) as lists of (tool name, input, tool_use id)."""
    groups: dict = {}
    for ln in lines:
        parsed = _tool_calls(ln) if b'"tool_use"' in ln else None
        if parsed:
            groups.setdefault(parsed[0], []).extend(parsed[1])
    return list(groups.values())


def _tool_calls(line: bytes) -> tuple | None:
    """One transcript line -> (message id, [(tool name, input, tool_use id)]) for an assistant message with tool calls, else None."""
    try:
        d = loads(line)
    except ValueError:
        return None
    msg = d.get("message") if isinstance(d, dict) else None
    if not isinstance(msg, dict) or d.get("type") != "assistant" or not isinstance(msg.get("content"), list):
        return None
    return msg.get("id") or d.get("uuid"), [(b.get("name"), b.get("input"), b.get("id")) for b in msg["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]


def _prior_turns(payload: dict, bcfg: dict) -> list[list[tuple]] | None:
    """The turns before the current call; None when unknown or when the current turn already holds several calls (already batching)."""
    path = _transcript_for(payload)
    if not path or not os.path.isfile(path):
        return None
    groups = _turn_groups(_tail_lines(path, bcfg["lookback_bytes"]))
    cur = payload.get("tool_use_id")
    for i, g in enumerate(groups):
        if any(c[2] == cur for c in g) and cur:
            return None if len(g) > 1 else groups[:i]
    return groups


def _single_read_only_run(turns: list[list[tuple]] | None, bcfg: dict) -> bool:
    """The last `prior_turns` turns each hold exactly one call and it is read-only."""
    n = bcfg["prior_turns"]
    return turns is not None and len(turns) >= n and all(len(t) == 1 and _is_readonly(t[0][0], t[0][1], bcfg) for t in turns[-n:])


def _nudge(payload: dict, ctx: Ctx) -> Decision:
    b = ctx.cfg.get("batch") or {}
    ti = payload.get("tool_input") or {}
    if not b.get("enabled") or not _is_readonly(payload.get("tool_name"), ti, b):
        return Decision()
    if ctx.now - ctx.state["nudge"].get(ctx.owner, 0) < b["cooldown_s"]:
        return Decision()
    if not _single_read_only_run(_prior_turns(payload, b), b):
        return Decision()
    ctx.state["nudge"][ctx.owner] = ctx.now
    ctx.dirty = True
    return Decision("nudge", "batch", "", _fmt(ctx.cfg["messages"]["batch"], n=b["prior_turns"]))


# ---------------------------------------------------------------- decide / render / main

def _on_compact(ctx: Ctx) -> Decision:
    """After a compaction the model no longer holds what it read: forget this context's reads so no stub points at vanished text."""
    prefix = ctx.owner + "|"
    ctx.state["reads"] = {k: v for k, v in ctx.state["reads"].items() if not k.startswith(prefix)}
    ctx.dirty = True
    return Decision("allow", "compact-reset")


def evaluate(payload: dict, ctx: Ctx) -> Decision:
    event = payload.get("hook_event_name") or "PreToolUse"
    if event in ("PreCompact", "PostCompact"):
        return _on_compact(ctx)
    if event != "PreToolUse":
        return Decision()
    tool, ti = payload.get("tool_name"), payload.get("tool_input") or {}
    if tool not in ("Read", "Bash", "Grep", "Glob"):
        return Decision()
    d = _read_call(ti, ctx) if tool == "Read" else _bash_call(ti, ctx) if tool == "Bash" else Decision()
    if d.action == "deny":
        return d
    nudge = _nudge(payload, ctx)
    return nudge if nudge.action == "nudge" else d


def _finalize(d: Decision, ctx: Ctx) -> Decision:
    """log mode: a deny is only recorded (`would-...`); soft mode: remember the denied call so that its exact repeat passes."""
    if d.action != "deny":
        return d
    if ctx.cfg.get("mode") == "log":
        return d._replace(action="allow", rule="would-" + d.rule)
    ctx.state["denied"][d.key] = {"t": ctx.now, "c": d.chars}
    ctx.dirty = True
    return d


def _load(raw, opts: dict, env) -> tuple[dict, dict] | None:
    """(payload, rules) when there is something to judge: valid JSON object, compiled rules, mode soft|log."""
    payload, root = loads(raw), opts.get("root", ROOT)
    cfg = opts.get("cfg") or load_cfg(root, opts.get("out") or out_dir(env, root), opts.get("loader"))
    return (payload, cfg) if isinstance(payload, dict) and cfg and cfg.get("mode") in ("soft", "log") else None


def _persist(ctx: Ctx, d: Decision) -> None:
    """State (when changed) and one log line per decision; a dry run (`qa.py guard --simulate`) writes nothing."""
    if ctx.dry:
        return
    if ctx.dirty:
        save_state(ctx)
    if d.rule != "-":
        append_log(ctx, d)


def decide(raw, opts: dict | None = None) -> Decision:
    """hook JSON (bytes/str) -> Decision. NEVER raises: any failure is an allow. opts: root, out, env, cfg, now, dry, loader, state."""
    opts = opts or {}
    env = opts["env"] if opts.get("env") is not None else os.environ
    if (env.get("AI_EVOLVE_GUARD") or "").strip().lower() in ("off", "0", "false", "no"):
        return Decision()
    try:
        loaded = _load(raw, opts, env)
        if loaded is None:
            return Decision()
        ctx = Ctx(loaded[0], loaded[1], opts)
        d = _finalize(evaluate(loaded[0], ctx), ctx)
        _persist(ctx, d)
        return d
    except Exception:  # noqa: BLE001 - fail open: the guard must never block work because of its own bug
        return Decision()


def render(d: Decision) -> tuple[int, str, str]:
    """(exit code, stdout, stderr) of a decision."""
    if d.action == "deny":
        return 2, "", d.message + "\n"
    if d.action == "nudge":
        return 0, dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": d.message}}), ""
    return 0, "", ""


SESSION_CMDS = {"SessionStart": ["resume"], "Stop": ["ckpt", "--auto"], "SubagentStop": ["ckpt", "--auto"]}


def session_event(raw, env=None, root=ROOT, timeout: int = 8) -> str:
    """SessionStart -> the `qa.py resume` text as additionalContext (empty when clean); Stop/SubagentStop -> `qa.py ckpt --auto`. Never raises, '' = nothing to say."""
    env = os.environ if env is None else env
    if (env.get("AI_EVOLVE_GUARD") or "").strip().lower() in ("off", "0", "false", "no"):
        return ""
    try:
        payload = loads(raw)
        event = payload.get("hook_event_name") if isinstance(payload, dict) else None
        cmd = SESSION_CMDS.get(event)
        if cmd is None:
            return ""
        import subprocess
        run = subprocess.run([sys.executable, os.path.join(root, "tools", "qa.py"), *cmd], cwd=root, capture_output=True, timeout=timeout, check=False)
        text = run.stdout.decode("utf-8", "replace").strip()
        if event != "SessionStart" or not text:
            return ""
        return dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "Unfinished work (qa.py resume):\n" + text}})
    except Exception:  # noqa: BLE001 - fail open, like the read guard
        return ""


def _ruff_exe(root: str) -> str | None:
    for rel in (".venv/Scripts/ruff.exe", ".venv/bin/ruff"):
        cand = os.path.join(root, rel)
        if os.path.isfile(cand):
            return cand
    import shutil
    return shutil.which("ruff")


def _ruff_row(row: str, root: str) -> str:
    loc, msg = row.split(": ", 1)
    parts = loc.rsplit(":", 2)
    return f"{_rel(parts[0], root)}:{parts[1]} {msg}"


def _py_problems(path: str, cfg: dict, root: str) -> list[str]:
    """`file:line message` for a syntax error (ast, in-process) or, when ruff is found, an undefined name / redefinition (one ruff call, ~30 ms)."""
    import ast
    try:
        with open(path, "rb") as fh:
            src = fh.read()
        ast.parse(src, path)
    except SyntaxError as exc:
        return [f"{os.path.basename(path)}:{exc.lineno or 1} E999 {exc.msg}"]
    except (OSError, ValueError):
        return []
    ruff = _ruff_exe(root)
    if not ruff:
        return []
    import subprocess
    run = subprocess.run([ruff, "check", "--isolated", "--no-cache", "--select", cfg.get("select", "F821,E9"), "--output-format", "concise", path],
                         capture_output=True, timeout=cfg.get("timeout_s", 5), check=False, cwd=root)
    rows = [ln.strip() for ln in run.stdout.decode("utf-8", "replace").splitlines() if ln.strip() and ": " in ln]
    return [_ruff_row(r, root) for r in rows]


def _post_target(payload: dict, cfg: dict, env) -> str | None:
    """The edited file when the lint applies (enabled, mode not off, Edit/Write/NotebookEdit, a configured extension), else None."""
    pcfg = (cfg or {}).get("post_edit") or {}
    path = (payload.get("tool_input") or {}).get("file_path") if payload.get("tool_name") in ("Edit", "Write", "NotebookEdit") else None
    ok = pcfg.get("enabled") and cfg.get("mode") != "off" and isinstance(path, str) and path.rsplit(".", 1)[-1] in pcfg["exts"]
    return path if ok else None


def post_edit(raw, env=None, root=ROOT, cfg=None) -> str:
    """PostToolUse Edit|Write|NotebookEdit on a .py file -> additionalContext `file:line message` (empty when clean). Never raises, never blocks; Lua is not checked here (a
    lupa boot is far over the hook's latency budget): `qa.py static` covers it."""
    env = os.environ if env is None else env
    if (env.get("AI_EVOLVE_GUARD") or "").strip().lower() in ("off", "0", "false", "no") or b'"PostToolUse"' not in raw:
        return ""
    try:
        payload = loads(raw)
        cfg = cfg or load_cfg(root, out_dir(env, root))
        path = _post_target(payload, cfg, env)
        rows = _py_problems(_abs(path, payload.get("cwd") or root), cfg["post_edit"], str(root)) if path else []
        if not rows:
            return ""
        text = _fmt(cfg["messages"]["post_edit"], n=len(rows), lines=chr(10).join(rows[: cfg["post_edit"].get("max_lines", 6)]))
        return dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}})
    except Exception:  # noqa: BLE001 - fail open: a lint hook must never get in the way
        return ""


def main() -> int:
    if sys.argv[1:2] == ["--compile"]:                       # child of _compile_in_child: `--compile ROOT OUT`
        compile_rules(*sys.argv[2:4])
        return 0
    try:
        raw = sys.stdin.buffer.read()
    except OSError:
        return 0
    session = session_event(raw) or post_edit(raw)
    if session:
        sys.stdout.write(session)
        return 0
    code, out, err = render(decide(raw))
    try:
        if out:
            sys.stdout.buffer.write(out.encode("utf-8"))
            sys.stdout.buffer.flush()
        if err:
            sys.stderr.buffer.write(err.encode("utf-8"))
            sys.stderr.buffer.flush()
    except OSError:
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
