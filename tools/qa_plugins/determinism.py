"""qa.py determinism - why do two same-seed runs differ? One command, no guessing.

    qa.py determinism "SCRIPT" [--pairs 6] [--seed 5] [--variants normal,aslr-off,hashseed0]
                               [--wrap "taskset -c 0"] [--out DIR] [--jobs N] [--no-leaks]
    qa.py determinism --diff TRACE_A TRACE_B         # analyse two existing traces, run nothing

Runs N pairs of `agent_play --trace-frames` (fresh processes, parallel) per variant and compares each
pair frame by frame. A trace line holds, for EVERY simulated frame, a hash of the bit-exact world state
(floats as float.hex()), hashes of the RNG streams (random, RNGManager, numpy) and the raw state, so the
first divergent FRAME, whether RNG or state moved first, and the exact FIELD with its ULP distance are known:

  float-level (<= 4 ULP)  -> libm/FMA/SIMD noise amplified by threshold logic
  RNG hash first          -> conditional/extra RNG draw or an unseeded generator
  order / only t / tick   -> set-of-objects order / real clock / 1 s timer boundary

Variants: normal | hashseed0 (PYTHONHASHSEED=0) | aslr-off (`setarch <arch> -R`, only where setarch exists).
Rules, thresholds and texts are DATA in lua_content/qa.lua (section `determinism`); the defaults below apply
when the key is absent. A leak recorder (AI_EVOLVE_LEAK_REPORT, tools/probe_runtime.py) adds where the game
touches clocks/entropy/threads the virtual clock does not cover. Details: dev_probe_output/qa/determinism_<id>/
(report.json, traces, repro_determinism.sh). Exit: 0 identical, 1 diverged, 2 tool/run error.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import re
import shlex
import shutil
import struct
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from probe_settings import ROOT, qa_settings
from qa_pool import Job, default_jobs, run_many

AGENT_PLAY = ROOT / "tools" / "agent_play.py"
QA_OUT = ROOT / "dev_probe_output" / "qa"
KNOWN_VARIANTS = ("normal", "aslr-off", "hashseed0")
RNG_PARTS = ("random", "rng_manager", "numpy")

# Python defaults: identical in meaning to lua_content/qa.lua `determinism` (tests keep them in sync).
DEFAULTS = {
    "pairs": 6, "seed": 5, "jobs": 4, "timeout": 300,
    "variants": ["normal", "aslr-off", "hashseed0"],
    "float_ulp": 4, "tick_seconds": 1.0, "max_fields": 4, "hypotheses_shown": 5, "top_leaks": 5, "max_lines": 25,
    "owners": [
        {"prefix": "hero.", "files": ["src/entities/character.py", "src/gameplay/hero_drive.py"]},
        {"prefix": "en[", "files": ["src/entities/enemy.py", "src/gameplay/enemy_ai.py", "src/gameplay/world.py"]},
        {"prefix": "t", "files": ["tools/probe_runtime.py", "src/core/game_core.py"]},
    ],
    "float_sites": r"math\.|numpy|\bnp\.|hypot|atan2|\bsqrt\(|\bsin\(|\bcos\(|\bpow\(|\*\* ?0?\.5",
    "leak_severity": [
        {"match": "random.", "weight": 90}, {"match": "os.urandom", "weight": 90},
        {"match": "uuid.", "weight": 80}, {"match": "secrets.", "weight": 80},
        {"match": "threading.", "weight": 70}, {"match": "datetime.", "weight": 60}, {"match": "date.", "weight": 60},
        {"match": "time.perf_counter (real", "weight": 40}, {"match": "time.time (real", "weight": 40},
        {"match": "time.monotonic (real", "weight": 40}, {"match": "time.", "weight": 50},
    ],
    "hypotheses": [
        {"id": "float_ulp", "when": "float_level", "severity": "high",
         "symptom": "first diff <= {ulp} ULP ({fields}), RNG hashes equal",
         "cause": "float non-determinism (libm/FMA/SIMD, numpy) amplified by a threshold",
         "look": "math.*/numpy in {sites}; compare cpu flags/libc across classes (report.json env)"},
        {"id": "rng_first", "when": "rng_first", "severity": "high",
         "symptom": "RNG hash ({rng_parts}) diverges at f{rng_frame}, state {state_lag}",
         "cause": "conditional/extra RNG draw, or an unseeded generator",
         "look": "leaks below (random.Random() unseeded); grep 'random|rng' in {owners}"},
        {"id": "order", "when": "order", "severity": "high",
         "symptom": "same enemies in a different order",
         "cause": "set / dict-of-objects iteration order (hash(obj), id())",
         "look": "sets or dicts keyed by objects feeding scene.enemies; sort by a stable key"},
        {"id": "only_t", "when": "only_t", "severity": "high",
         "symptom": "only the virtual time t differs",
         "cause": "real clock or a timer boundary not covered by the virtual clock",
         "look": "time.* leaks below; frame-time source in tools/probe_runtime.py"},
        {"id": "tick", "when": "tick", "severity": "medium",
         "symptom": "divergence at a whole-second boundary (t={t})",
         "cause": "1 s tick (periodic effects / spawn timers) firing one frame apart",
         "look": "periodic effects in src/effects/manager.py; spawn timers in src/gameplay/world.py"},
        {"id": "logic", "when": "logic_level", "severity": "medium",
         "symptom": "state differs beyond float noise ({fields}), RNG equal",
         "cause": "nondeterministic branch: iteration order, real clock, thread timing or untraced input",
         "look": "leaks below; owners {owners}; diff frames f{last_same}..f{frame} with the repro script"},
        {"id": "entity_set", "when": "entity_set", "severity": "medium",
         "symptom": "different enemies alive (count differs)",
         "cause": "spawn/despawn/kill decided at a different frame (timer, RNG or ordering)",
         "look": "spawn timers + KillTracker path in src/gameplay/world.py; 'en.count' in report.json"},
        {"id": "length", "when": "length", "severity": "medium",
         "symptom": "identical common prefix but the traces have different lengths ({len_a} vs {len_b})",
         "cause": "run ended at a different frame: an untraced metric (kills/dealt) or a condition flipped",
         "look": "the script's until/expect conditions; session.json final of both runs"},
        {"id": "hashseed_refuted", "when": "hashseed_refuted", "severity": "info",
         "symptom": "PYTHONHASHSEED=0 pairs still diverge ({hashseed_diverged}/{hashseed_pairs})",
         "cause": "string-hash randomisation is NOT the cause",
         "look": "other variants / float_ulp rule / leaks"},
        {"id": "hashseed_implicated", "when": "hashseed_implicated", "severity": "high",
         "symptom": "PYTHONHASHSEED=0 pairs are clean but other variants diverge",
         "cause": "str-hash randomisation reaches game logic (set/dict-of-str iteration order)",
         "look": "grep 'set(' / '.keys()' loops where the order picks an action; use sorted()"},
        {"id": "aslr_implicated", "when": "aslr_implicated", "severity": "medium",
         "symptom": "aslr-off diverges more often ({aslr_diverged}/{aslr_pairs}) than normal ({normal_diverged}/{normal_pairs})",
         "cause": "address-dependent behaviour (id()/hash(obj) ordering, native allocator) or a float path",
         "look": "sorted(..., key=id), sets of objects; also the float_ulp rule"},
        {"id": "multi_class", "when": "multi_class", "severity": "info",
         "symptom": "{runs} runs fall into {classes} recurring trajectory classes",
         "cause": "a few stable trajectories, picked by the environment (CPU/libm dispatch, memory layout)",
         "look": "which variant/pair lands in which class (report.json fp_a/fp_b); on CI diff the env fingerprints"},
    ],
}


def settings() -> dict:
    """DEFAULTS overridden key by key from lua_content/qa.lua `determinism` (lists are replaced whole)."""
    cfg = copy.deepcopy(DEFAULTS)
    try:
        lua = qa_settings().get("determinism") or {}
    except Exception:  # noqa: BLE001 - broken/missing Lua must not break the tool
        lua = {}
    for key, value in lua.items():
        if key in cfg and value is not None:
            cfg[key] = value
    return cfg


# ------------------------------------------------------------------ floats

_HEXF = re.compile(r"^[+-]?(?:0x[0-9a-fA-F]+\.?[0-9a-fA-F]*p[+-]?\d+|inf|nan)$")
_MISSING = "<missing>"


def as_float(v):
    """float.hex() strings and plain numbers -> float; anything else -> None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and _HEXF.match(v):
        return float.fromhex(v)
    return None


def _ordered(x: float) -> int:
    n = struct.unpack("<q", struct.pack("<d", x))[0]
    return n if n >= 0 else -(n & 0x7FFFFFFFFFFFFFFF)


def ulp_distance(a, b):
    """Number of representable doubles between a and b (0 = same value; +0.0/-0.0 = 0). None when either is
    not a number or exactly one is NaN. Accepts floats and float.hex() strings."""
    fa, fb = as_float(a), as_float(b)
    if fa is None or fb is None:
        return None
    if math.isnan(fa) or math.isnan(fb):
        return 0 if math.isnan(fa) and math.isnan(fb) else None
    return abs(_ordered(fa) - _ordered(fb))


def show(v) -> str:
    f = as_float(v) if isinstance(v, str) else None
    return repr(f) if f is not None else str(v)


# ------------------------------------------------------------------ traces

def load_trace(path) -> list[dict]:
    """JSONL trace -> records with the raw world carried forward (`s` is omitted while unchanged).
    A torn last line (killed run) ends the trace instead of failing the analysis."""
    records, state = [], None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                break
            if "s" in rec:
                state = rec["s"]
            rec["s"] = state
            records.append(rec)
    return records


def fingerprint(trace) -> str:
    """One id per trajectory: two runs share it iff every frame's state and RNG hashes are equal."""
    digest = hashlib.blake2b(digest_size=6)
    for rec in trace:
        digest.update(f"{rec['h']}{rec['r']}|".encode())
    return digest.hexdigest()


def flatten_state(state) -> dict:
    """World -> {"hero.x": ..., "en[0].x": ..., "en.count": n}. Enemies are compared by slot in scene order."""
    out = {}
    if not state:
        return out
    hero = state.get("hero")
    out["hero"] = "absent" if hero is None else "present"
    for key, value in (hero or {}).items():
        out[f"hero.{key}"] = value
    enemies = state.get("en") or []
    out["en.count"] = len(enemies)
    for i, enemy in enumerate(enemies):
        for key, value in enemy.items():
            out[f"en[{i}].{key}"] = value
    return out


_SLOT = re.compile(r"^en\[(\d+)\]\.(.*)$")


def _path_order(path):
    m = _SLOT.match(path)
    if m:
        return 2, int(m.group(1)), m.group(2)
    return (0 if path.startswith("hero") else 1), 0, path


@dataclass
class FieldDiff:
    path: str
    a: object
    b: object
    abs_diff: float | None
    ulp: int | None
    kind: str  # "float" (both numbers, <= max_ulp apart) | "logic"

    def to_dict(self):
        return {"path": self.path, "a": self.a, "b": self.b, "abs_diff": self.abs_diff, "ulp": self.ulp,
                "kind": self.kind}


def diff_states(sa, sb, max_ulp: int = 4, ta=None, tb=None) -> list[FieldDiff]:
    """Every differing field of two worlds (plus the virtual time `t` when given), in natural order."""
    fa, fb = flatten_state(sa), flatten_state(sb)
    if ta is not None or tb is not None:
        fa["t"], fb["t"] = ta, tb
    diffs = []
    for path in sorted(set(fa) | set(fb), key=_path_order):
        va, vb = fa.get(path, _MISSING), fb.get(path, _MISSING)
        if va == vb:
            continue
        x, y = as_float(va), as_float(vb)
        if x is not None and y is not None:
            ulp = ulp_distance(x, y)
            ad = abs(x - y) if not (math.isnan(x) or math.isnan(y)) else None
            kind = "float" if ulp is not None and ulp <= max_ulp else "logic"
            diffs.append(FieldDiff(path, va, vb, ad, ulp, kind))
        else:
            diffs.append(FieldDiff(path, va, vb, None, None, "logic"))
    return diffs


def _enemy_tuples(state):
    return [(e.get("ty"), e.get("x"), e.get("y"), e.get("hp")) for e in ((state or {}).get("en") or [])]


@dataclass
class Divergence:
    frame: int                      # first frame where anything differs (state hash or RNG hash)
    t: float | None
    last_same: int | None
    last_same_t: float | None
    channel: str                    # "rng" | "state"
    rng_first: int | None = None
    state_first: int | None = None
    rng_parts: list = field(default_factory=list)   # which RNG streams differ at rng_first
    fields: list = field(default_factory=list)      # FieldDiff at state_first
    float_level: bool = False
    only_t: bool = False
    order: bool = False
    entity_set: bool = False
    length: bool = False
    tick: bool = False
    len_a: int = 0
    len_b: int = 0

    @property
    def classification(self):
        return "float-level" if self.float_level else "logic-level"

    def to_dict(self):
        d = {k: v for k, v in self.__dict__.items() if k != "fields"}
        d["fields"] = [f.to_dict() for f in self.fields]
        d["classification"] = self.classification
        return d


def crossed_tick(t_prev, t, tick: float) -> bool:
    """True when a whole multiple of `tick` seconds lies in (t_prev, t]."""
    if t_prev is None or t is None or tick <= 0:
        return False
    eps = 1e-9
    return math.floor(t / tick + eps) > math.floor(t_prev / tick + eps)


def compare_traces(a, b, cfg=None):
    """First divergence of two traces, or None when they are identical (frame count included)."""
    cfg = cfg or DEFAULTS
    n = min(len(a), len(b))
    state_first = rng_first = None
    for i in range(n):
        if state_first is None and a[i]["h"] != b[i]["h"]:
            state_first = i
        if rng_first is None and a[i]["r"] != b[i]["r"]:
            rng_first = i
        if state_first is not None and rng_first is not None:
            break
    if state_first is None and rng_first is None:
        if len(a) == len(b):
            return None
        longer = a if len(a) > len(b) else b
        first = n
        t_prev = a[n - 1]["t"] if n else None
        return Divergence(frame=first, t=longer[first]["t"], last_same=n - 1 if n else None, last_same_t=t_prev,
                          channel="state", length=True, len_a=len(a), len_b=len(b),
                          tick=crossed_tick(t_prev, longer[first]["t"], cfg["tick_seconds"]))

    first = min(x for x in (state_first, rng_first) if x is not None)
    div = Divergence(frame=first, t=a[first]["t"], last_same=first - 1 if first else None,
                     last_same_t=a[first - 1]["t"] if first else None, channel="state",
                     rng_first=rng_first, state_first=state_first, len_a=len(a), len_b=len(b))
    if rng_first is not None:
        pa, pb = a[rng_first]["r"].split(":"), b[rng_first]["r"].split(":")
        div.rng_parts = [RNG_PARTS[i] if i < len(RNG_PARTS) else f"part{i}"
                         for i, (x, y) in enumerate(zip(pa, pb)) if x != y]
    if state_first is not None:
        ra, rb = a[state_first], b[state_first]
        div.fields = diff_states(ra["s"], rb["s"], int(cfg["float_ulp"]), ra["t"], rb["t"])
        world = [f for f in div.fields if f.path != "t"]
        div.only_t = not world
        div.float_level = bool(div.fields) and all(f.kind == "float" for f in div.fields)
        ea, eb = _enemy_tuples(ra["s"]), _enemy_tuples(rb["s"])
        div.order = ea != eb and sorted(map(repr, ea)) == sorted(map(repr, eb))
        div.entity_set = len(ea) != len(eb)
    if rng_first is not None and (state_first is None or rng_first < state_first):
        div.channel = "rng"
    elif rng_first is not None and rng_first == state_first and not div.float_level:
        div.channel = "rng"   # same frame and not float noise: the draw is the likelier cause
    if div.channel == "rng":
        div.float_level = False
    div.tick = crossed_tick(a[first - 1]["t"] if first else None, a[first]["t"], cfg["tick_seconds"])
    return div


# ------------------------------------------------------------------ hypotheses

PREDICATES = {
    "float_level": lambda c: c["div"].channel == "state" and c["div"].float_level,
    "rng_first": lambda c: c["div"].channel == "rng",
    "order": lambda c: c["div"].order,
    "only_t": lambda c: c["div"].only_t and not c["div"].length,
    "tick": lambda c: c["div"].tick,
    "logic_level": lambda c: (c["div"].channel == "state" and bool(c["div"].fields) and not c["div"].float_level
                              and not c["div"].only_t and not c["div"].order and not c["div"].entity_set),
    "entity_set": lambda c: c["div"].entity_set,
    "length": lambda c: c["div"].length,
    "hashseed_refuted": lambda c: c["v"].get("hashseed0", {}).get("diverged", 0) > 0,
    "hashseed_implicated": lambda c: (c["v"].get("hashseed0", {}).get("pairs", 0) > 0
                                      and c["v"]["hashseed0"]["diverged"] == 0
                                      and any(s["diverged"] for n, s in c["v"].items() if n != "hashseed0")),
    "aslr_implicated": lambda c: (c["v"].get("aslr-off", {}).get("diverged", 0) > 0
                                  and c["v"]["aslr-off"]["diverged"] / c["v"]["aslr-off"]["pairs"]
                                  > c["v"].get("normal", {}).get("diverged", 0) / max(1, c["v"].get("normal", {}).get("pairs", 0))),
    "multi_class": lambda c: 1 < c["classes"] < c["runs"],
}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}


class _Safe(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def owner_files(paths, cfg) -> list[str]:
    files: list[str] = []
    for path in paths or ["hero."]:
        for rule in cfg["owners"]:
            if path.startswith(rule["prefix"]):
                files += [f for f in rule["files"] if f not in files]
                break
    if not files:
        files = [f for rule in cfg["owners"] for f in rule["files"]][:3]
    return files


def float_sites(files, pattern, max_files=2, max_lines=4) -> str:
    """'src/x.py:L689,L954,L974,L1017 (+16)' for the float-heavy lines of the owning modules."""
    rx = re.compile(pattern)
    parts = []
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        hits = [i for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
                if rx.search(line) and not line.lstrip().startswith("#")]
        if hits:
            parts.append(f"{rel}:" + ",".join(f"L{i}" for i in hits[:max_lines])
                         + (f" (+{len(hits) - max_lines})" if len(hits) > max_lines else ""))
        if len(parts) >= max_files:
            break
    return "; ".join(parts) or "the modules that own the field"


def build_context(div: Divergence, cfg, variants=None, classes=1, runs=2) -> dict:
    variants = variants or {}
    paths = [f.path for f in div.fields]
    files = owner_files(paths, cfg)
    ctx = {"div": div, "v": variants, "classes": classes, "runs": runs}
    lag = ("still identical at the end of the trace" if div.state_first is None else
           "diverges the same frame" if div.state_first == div.rng_first else
           f"diverges {div.state_first - (div.rng_first or 0)} frame(s) later (f{div.state_first})")
    ctx["vars"] = _Safe({
        "ulp": int(cfg["float_ulp"]), "fields": ", ".join(paths[:4]) or "-", "owners": ", ".join(files),
        "sites": float_sites(files, cfg["float_sites"]) if div.float_level else ", ".join(files),
        "rng_parts": "+".join(div.rng_parts) or "?", "rng_frame": div.rng_first, "state_lag": lag,
        "t": f"{div.t:.4f}" if div.t is not None else "?", "last_same": div.last_same, "frame": div.frame,
        "len_a": div.len_a, "len_b": div.len_b, "classes": classes, "runs": runs,
        **{f"{key}_{what}": stats.get(what, 0)
           for name, key in (("hashseed0", "hashseed"), ("aslr-off", "aslr"), ("normal", "normal"))
           for stats in [variants.get(name, {})] for what in ("pairs", "diverged")},
    })
    return ctx


def evaluate_rules(ctx, cfg) -> list[dict]:
    """Rules whose `when` predicate holds, worst first, texts filled from the context."""
    found = []
    for order, rule in enumerate(cfg["hypotheses"]):
        pred = PREDICATES.get(rule.get("when"))
        try:
            hit = bool(pred and pred(ctx))
        except (KeyError, ZeroDivisionError, TypeError):
            hit = False
        if hit:
            fill = lambda key: str(rule.get(key, "")).format_map(ctx["vars"])  # noqa: E731
            found.append({"id": rule["id"], "severity": rule.get("severity", "medium"), "order": order,
                          "symptom": fill("symptom"), "cause": fill("cause"), "look": fill("look")})
    found.sort(key=lambda h: (_SEVERITY_ORDER.get(h["severity"], 1), h["order"]))
    return found


# ------------------------------------------------------------------ leaks

def leak_weight(kind: str, cfg) -> int:
    for rule in cfg["leak_severity"]:
        if kind.startswith(rule["match"]):
            return int(rule["weight"])
    return 10


def merge_leaks(paths) -> list[dict]:
    """Recorder reports of several runs -> findings (max count per site), most suspicious first."""
    merged: dict = {}
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for f in data.get("findings", []):
            key = (f["kind"], f["where"], f.get("detail", ""), f.get("via", ""))
            merged[key] = max(merged.get(key, 0), f["count"])
    return [{"kind": k, "where": w, "detail": d, "via": v, "count": n} for (k, w, d, v), n in merged.items()]


def rank_leaks(findings, cfg) -> list[dict]:
    return sorted(findings, key=lambda f: (-leak_weight(f["kind"], cfg), -f["count"], f["where"]))


def leak_text(f) -> str:
    kind = f["kind"].replace(" (real clock, bypasses the virtual one)", "[REAL]")
    text = f"{f['where']} {kind}" + (f"({f['detail']})" if f.get("detail") else "") + f" x{f['count']}"
    return text + (f" via {f['via']}" if f.get("via") else "")


# ------------------------------------------------------------------ environment

def env_fingerprint() -> dict:
    """What CI machines with different trajectory classes may differ in: CPU float paths, libc, python."""
    fp = {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
          "cpus": os.cpu_count(), "libc": "-".join(platform.libc_ver()).strip("-") or None}
    try:
        import importlib.metadata as md
        fp["numpy"] = md.version("numpy")
    except Exception:  # noqa: BLE001
        fp["numpy"] = None
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        model = re.search(r"model name\s*:\s*(.+)", text)
        flags = set((re.search(r"flags\s*:\s*(.+)", text) or [None, ""])[1].split())
        fp["cpu"] = model.group(1).strip() if model else None
        fp["cpu_flags"] = sorted(flags & {"fma", "avx", "avx2", "avx512f", "sse4_2", "bmi2"})
    except OSError:
        fp["cpu"] = platform.processor() or None
    return fp


# ------------------------------------------------------------------ running

@dataclass
class PairResult:
    variant: str
    pair: int
    dir_a: Path
    dir_b: Path
    error: str | None = None
    div: Divergence | None = None
    fp_a: str | None = None
    fp_b: str | None = None
    frames: int = 0


def variant_spec(name: str):
    """-> (command prefix, env, skip reason)."""
    if name == "normal":
        return [], {"PYTHONHASHSEED": "random"}, None
    if name == "hashseed0":
        return [], {"PYTHONHASHSEED": "0"}, None
    if name == "aslr-off":
        if shutil.which("setarch") is None:
            return [], {}, "setarch not found (Linux only)"
        return ["setarch", platform.machine() or "x86_64", "-R"], {"PYTHONHASHSEED": "random"}, None
    raise ValueError(f"unknown variant {name!r} (known: {', '.join(KNOWN_VARIANTS)})")


def agent_argv(python, seed, out, trace, script):
    return [python, "tools/agent_play.py", "--seed", str(seed), "--out", str(out), "--trace-frames", str(trace), script]


def run_dirs(base: Path, variant: str, pair: int):
    root = base / variant / f"pair{pair + 1}"
    return root / "a", root / "b"


def build_jobs(script, seed, pairs, variants, wrap, base, timeout, leaks=True) -> list[Job]:
    jobs = []
    for variant, (prefix, env, _skip) in variants.items():
        for k in range(pairs):
            for side, out in zip("ab", run_dirs(base, variant, k)):
                out.mkdir(parents=True, exist_ok=True)
                run_env = dict(env)
                if leaks and k == 0:
                    run_env["AI_EVOLVE_LEAK_REPORT"] = str(out / "leaks.json")
                argv = [*wrap, *prefix, *agent_argv(sys.executable, seed, out, out / "trace.jsonl", script)]
                jobs.append(Job(f"{variant}/pair{k + 1}/{side}", argv, run_env, timeout,
                                {"variant": variant, "pair": k, "side": side, "out": out}))
    return jobs


def run_ok(result) -> bool:
    out = result.meta["out"]
    return result.rc in (0, 1) and (out / "trace.jsonl").is_file() and (out / "session.json").is_file()


def analyse_pair(variant, k, res_a, res_b, cfg) -> PairResult:
    dir_a, dir_b = res_a.meta["out"], res_b.meta["out"]
    pr = PairResult(variant, k, dir_a, dir_b)
    bad = [r for r in (res_a, res_b) if not run_ok(r)]
    if bad:
        r = bad[0]
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]
        pr.error = f"{r.name}: rc={r.rc} {tail[0][:160]}"
        return pr
    ta, tb = load_trace(dir_a / "trace.jsonl"), load_trace(dir_b / "trace.jsonl")
    pr.frames = min(len(ta), len(tb))
    pr.fp_a, pr.fp_b = fingerprint(ta), fingerprint(tb)
    pr.div = compare_traces(ta, tb, cfg)
    return pr


# ------------------------------------------------------------------ output

def pair_lines(div: Divergence, cfg, hyps, indent="") -> list[str]:
    """Compact analysis of one divergent pair (no run info)."""
    t_last = f" t={div.last_same_t:.4f}" if div.last_same_t is not None else ""
    lines = [f"{indent}last identical frame: " + (f"f{div.last_same}{t_last}" if div.last_same is not None else "none")
             + f"; first divergent f{div.frame} t={div.t:.4f}" + f" ({div.len_a} vs {div.len_b} frames)"]
    if div.length:
        lines.append(f"{indent}channel: traces identical over {min(div.len_a, div.len_b)} frames, lengths differ")
    elif div.channel == "rng":
        lag = ("state still identical at the end" if div.state_first is None else
               f"state follows at f{div.state_first}")
        lines.append(f"{indent}channel: RNG diverged first at f{div.rng_first} ({'+'.join(div.rng_parts)}); {lag}")
    else:
        rng = ("RNG identical in every frame" if div.rng_first is None else
               f"RNG diverges later at f{div.rng_first} ({'+'.join(div.rng_parts)})")
        lines.append(f"{indent}channel: state diverged first at f{div.state_first}; {rng}")
    if div.fields:
        lines.append(f"{indent}differing fields ({len(div.fields)}): {div.classification}"
                     + (f" (<= {int(cfg['float_ulp'])} ULP)" if div.float_level else " (beyond float noise)"))
        for f in div.fields[:int(cfg["max_fields"])]:
            mag = ""
            if f.ulp is not None:
                mag = f"  |d|={f.abs_diff:.3g}  {f.ulp} ULP" if f.abs_diff is not None else f"  {f.ulp} ULP"
            lines.append(f"{indent}  {f.path:<12} {show(f.a)} vs {show(f.b)}{mag}")
        more = len(div.fields) - int(cfg["max_fields"])
        if more > 0:
            lines.append(f"{indent}  (+{more} more in report.json)")
    if hyps:
        lines.append(f"{indent}hypotheses (symptom -> likely cause -> where to look):")
        for i, h in enumerate(hyps[:int(cfg["hypotheses_shown"])], 1):
            lines.append(f"{indent} {i}. [{h['severity']}] {h['symptom']} -> {h['cause']} -> {h['look']}")
    return lines


def leak_lines(ranked, cfg) -> list[str]:
    if not ranked:
        return []
    top = ranked[:int(cfg["top_leaks"])]
    lines, cur = [f"leaks (top {len(top)} of {len(ranked)}; game code outside the virtual clock/seeds):"], ""
    for f in top:
        piece = leak_text(f)
        if cur and len(cur) + len(piece) > 150:
            lines.append("  " + cur)
            cur = ""
        cur = f"{cur}; {piece}" if cur else piece
    lines.append("  " + cur)
    return lines


def fit_lines(sections, limit):
    """Join sections in priority order. Over `limit`: drop lines from the back (leaks first, then the tail of
    the analysis: weakest hypotheses, then extra fields). The RESULT line, the variants line and the last
    section (repro) are never cut."""
    sections = [list(s) for s in sections]
    total = sum(len(s) for s in sections)
    for i in range(len(sections) - 2, 1, -1):
        while total > limit and sections[i]:
            sections[i].pop()
            total -= 1
    return [line for s in sections for line in s]


def write_repro(path: Path, script, seed, variant, wrap, prefix, env, division_line):
    """repro_determinism.sh: literal command lines of one pair + a loop until the traces differ + the diff helper."""
    envs = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
    lead = " ".join(filter(None, ["env " + envs if envs else "", *map(shlex.quote, wrap), *map(shlex.quote, prefix)]))
    cmds = []
    for side in "ab":
        argv = agent_argv('"$PY"', seed, f'"$OUT/{side}"', f'"$OUT/{side}/trace.jsonl"', shlex.quote(script))
        cmds.append(f"  {lead} " + " ".join(argv) + " >/dev/null 2>&1 || true")
    body = f"""#!/bin/sh
# qa.py determinism repro - {division_line}
# variant={variant} seed={seed}; every try uses FRESH processes. TRIES=20 sh repro_determinism.sh loops until the traces differ.
# PYTHON=/path/to/python overrides the interpreter. Traces go to ./repro_out next to this script.
cd {shlex.quote(ROOT.as_posix())} || exit 2
PY="${{PYTHON:-python}}"
OUT="$(cd "$(dirname "$0")" && pwd)/repro_out"
mkdir -p "$OUT/a" "$OUT/b"
i=0
while [ "$i" -lt "${{TRIES:-1}}" ]; do
  i=$((i+1))
{cmds[0]}
{cmds[1]}
  if ! cmp -s "$OUT/a/trace.jsonl" "$OUT/b/trace.jsonl"; then
    echo "diverged on try $i"
    "$PY" tools/qa.py determinism --diff "$OUT/a/trace.jsonl" "$OUT/b/trace.jsonl"
    exit 1
  fi
done
echo "identical after $i try(ies)"
# raw diff of the traces: diff "$OUT/a/trace.jsonl" "$OUT/b/trace.jsonl" | head
"""
    path.write_text(body, encoding="utf-8", newline="\n")


def rel(p) -> str:
    p = Path(p)
    return p.relative_to(ROOT).as_posix() if p.is_absolute() and p.is_relative_to(ROOT) else str(p)


# ------------------------------------------------------------------ commands

def cmd_diff(args, cfg) -> int:
    try:
        a, b = load_trace(args.diff[0]), load_trace(args.diff[1])
    except OSError as exc:
        print(f"cannot read trace: {exc}")
        return 2
    if not a or not b:
        print("empty trace (was agent_play run with --trace-frames?)")
        return 2
    div = compare_traces(a, b, cfg)
    if div is None:
        print(f"RESULT determinism-diff identical frames={len(a)} classes=1 first_frame=- t=- channel=none")
        return 0
    ctx = build_context(div, cfg, classes=1, runs=2)
    print(f"RESULT determinism-diff diverged first_frame={div.frame} t={div.t:.2f} channel={div.channel}")
    for line in pair_lines(div, cfg, evaluate_rules(ctx, cfg)):
        print(line)
    return 1


def _validate_args(args, cfg):
    """(specs, None) or (None, exit_code) after printing the reason."""
    if not args.script:
        print("give a SCRIPT (e.g. \"spawn enemy x2; wait 8\") or --diff TRACE_A TRACE_B")
        return None, 2
    names = [v.strip() for v in (args.variants or ",".join(cfg["variants"])).split(",") if v.strip()]
    try:
        specs = {n: variant_spec(n) for n in dict.fromkeys(names)}
    except ValueError as exc:
        print(exc)
        return None, 2
    try:
        from agent_play import ScriptError, parse_script
        parse_script(args.script)
    except ScriptError as exc:  # fail before booting 2N games
        print(f"script error: {exc}")
        return None, 2
    return specs, None


def _output_dir(out) -> Path:
    if out:
        base = Path(out).resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base
    QA_OUT.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"determinism_{time.strftime('%H%M%S')}_", dir=QA_OUT))


def _drop_unstartable(active, results, skipped) -> None:
    """A variant that cannot start at all (setarch without permission) is skipped, not an error."""
    for name in list(active):
        rs = [r for r in results.values() if r.meta["variant"] == name]
        if rs and not any(run_ok(r) for r in rs) and any(
                re.search(r"personality|setarch", r.stderr + r.stdout, re.I) for r in rs):
            skipped[name] = "setarch refused (container without personality permission?)"
            del active[name]


def _analyse_all(active, results, pairs, cfg):
    pair_results, errors = [], []
    for name in active:
        for k in range(pairs):
            pr = analyse_pair(name, k, results[f"{name}/pair{k + 1}/a"], results[f"{name}/pair{k + 1}/b"], cfg)
            (errors if pr.error else pair_results).append(pr)
    return pair_results, [e.error for e in errors]


@dataclass
class _Outcome:
    """Everything the report of one `qa.py determinism` run is rendered from."""
    args: object
    plan: tuple            # (seed, pairs, wrap)
    active: dict
    skipped: dict
    pair_results: list
    errors: list
    started: float = 0.0
    hyps: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def diverged(self) -> list:
        return [p for p in self.pair_results if p.div is not None]

    @property
    def first(self):
        return self.diverged[0] if self.diverged else None

    @property
    def classes(self) -> int:
        return len({fp for p in self.pair_results for fp in (p.fp_a, p.fp_b) if fp})


def _head_line(o) -> str:
    first = o.first
    where = (f"first_frame={first.div.frame} t={first.div.t:.2f} channel={first.div.channel}" if first
             else "first_frame=- t=- channel=none")
    return (f"RESULT determinism pairs={len(o.pair_results)} diverged={len(o.diverged)} classes={o.classes} "
            + where + (f" errors={len(o.errors)}" if o.errors else ""))


def _divergence_sections(o, cfg):
    first, diverged = o.first, o.diverged
    out = [[f"first divergent: {first.variant}/pair{first.pair + 1} (a vs b), classes across runs: {o.classes}"],
           pair_lines(first.div, cfg, o.hyps)]
    if len(diverged) > 1:
        others = sorted({p.div.frame for p in diverged})
        out.append([f"divergent frames over {len(diverged)} pairs: " + ", ".join(
            f"f{f} x{sum(1 for p in diverged if p.div.frame == f)}" for f in others[:6])])
    return out


def _summary_sections(o, cfg):
    var_bits = [f"{n} {s['pairs'] - s['diverged']}/{s['pairs']} identical" for n, s in o.stats.items()]
    var_bits += [f"{n} skipped ({why})" for n, why in o.skipped.items()]
    sections = [[_head_line(o)], ["variants: " + " | ".join(var_bits)]]
    if o.first is not None:
        sections += _divergence_sections(o, cfg)
    elif o.pair_results:
        p0 = o.pair_results[0]
        sections.append([f"all {len(o.pair_results)} pairs identical: {p0.frames} frames, RNG + state hashes equal "
                         f"(trajectory {p0.fp_a}); a flake needs more pairs or another variant/--wrap"])
    sections += [[f"run error: {e}"] for e in o.errors[:3]]
    return sections


def _variant_report(n, s, pair_results) -> dict:
    return {"env": s[1], "prefix": s[0], "pairs": [
        {"pair": p.pair + 1, "dir_a": rel(p.dir_a), "dir_b": rel(p.dir_b), "frames": p.frames,
         "fp_a": p.fp_a, "fp_b": p.fp_b, "diverged": p.div is not None,
         "divergence": p.div.to_dict() if p.div else None} for p in pair_results if p.variant == n]}


def _build_report(o, leaks) -> dict:
    seed, pairs, wrap = o.plan
    return {
        "schema": 1, "script": o.args.script, "seed": seed, "pairs_per_variant": pairs, "wrap": wrap,
        "variants": {n: _variant_report(n, s, o.pair_results) for n, s in o.active.items()},
        "skipped": o.skipped, "errors": o.errors, "classes": o.classes, "diverged": len(o.diverged),
        "hypotheses": o.hyps, "leaks": leaks, "env": env_fingerprint(),
        "seconds": round(time.perf_counter() - o.started, 1), "cmd": " ".join(map(shlex.quote, sys.argv)),
    }


def _repro_section(base, o):
    first = o.first
    target = first or (o.pair_results[0] if o.pair_results else None)
    if target is None:
        return None
    seed, _, wrap = o.plan
    prefix, env, _ = o.active[target.variant]
    what = (f"first divergent pair {target.variant}/pair{target.pair + 1}: f{target.div.frame} "
            f"t={target.div.t:.2f} channel={target.div.channel}" if first else
            f"no divergence observed - pair {target.variant}/pair{target.pair + 1} shown")
    write_repro(base / "repro_determinism.sh", o.args.script, seed, target.variant, wrap, prefix, env, what)
    return [f"repro: sh {rel(base / 'repro_determinism.sh')}  (TRIES=20 loops until it diverges) | "
            f"details: {rel(base / 'report.json')}"]


def _run_all(args, cfg, specs, base, plan):
    """Run every job; returns (active, skipped, results)."""
    seed, pairs, wrap = plan
    skipped = {n: s[2] for n, s in specs.items() if s[2]}
    active = {n: s for n, s in specs.items() if not s[2]}
    jobs = build_jobs(args.script, seed, pairs, active, wrap, base, float(cfg["timeout"]), not args.no_leaks)
    results = {r.name: r for r in run_many(jobs, args.jobs or int(cfg["jobs"]) or default_jobs())}
    _drop_unstartable(active, results, skipped)
    return active, skipped, results


def _variant_stats(active, pair_results, diverged) -> dict:
    return {n: {"pairs": sum(1 for p in pair_results if p.variant == n),
                "diverged": sum(1 for p in diverged if p.variant == n)} for n in active}


def _exit_code(diverged, errors, pair_results) -> int:
    if diverged:
        return 1
    return 2 if errors or not pair_results else 0


def _collect(args, cfg, specs, base):
    """Run the games and analyse the pairs -> _Outcome (hypotheses evaluated)."""
    plan = (int(cfg["seed"]) if args.seed is None else args.seed, args.pairs or int(cfg["pairs"]),
            shlex.split(args.wrap) if args.wrap else [])
    started = time.perf_counter()
    active, skipped, results = _run_all(args, cfg, specs, base, plan)
    pair_results, errors = _analyse_all(active, results, plan[1], cfg)
    o = _Outcome(args, plan, active, skipped, pair_results, errors, started)
    o.stats = _variant_stats(active, pair_results, o.diverged)
    if o.first is not None:
        o.hyps = evaluate_rules(build_context(o.first.div, cfg, o.stats, o.classes, 2 * len(pair_results)), cfg)
    return o


def cmd_determinism(args) -> int:
    cfg = settings()
    if args.diff:
        return cmd_diff(args, cfg)
    specs, code = _validate_args(args, cfg)
    if specs is None:
        return code
    base = _output_dir(args.out)
    o = _collect(args, cfg, specs, base)
    leaks = rank_leaks(merge_leaks([d / "leaks.json" for n in o.active for d in run_dirs(base, n, 0)]), cfg)
    sections = _summary_sections(o, cfg)
    sections.append(leak_lines(leaks, cfg))
    report = _build_report(o, leaks)
    (base / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    repro = _repro_section(base, o)
    if repro:
        sections.append(repro)
    for line in fit_lines(sections, int(cfg["max_lines"])):
        print(line)
    return _exit_code(o.diverged, o.errors, o.pair_results)


def register(sub) -> None:
    p = sub.add_parser("determinism", help="why do two same-seed runs differ: paired traced runs, first divergent frame",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("script", nargs="?", help="agent_play script, e.g. \"spawn enemy x2; wait 8\"")
    p.add_argument("--pairs", type=int, default=None, help="pairs per variant (default 6, lua_content/qa.lua)")
    p.add_argument("--seed", type=int, default=None, help="game seed (default 5)")
    p.add_argument("--variants", default=None, help="comma list of normal,aslr-off,hashseed0 (default: all)")
    p.add_argument("--wrap", default="", help="command prefix for every run, e.g. \"taskset -c 0\"")
    p.add_argument("--out", default=None, help="output dir (default dev_probe_output/qa/determinism_<id>)")
    p.add_argument("--jobs", type=int, default=None, help="parallel game processes (default 4)")
    p.add_argument("--no-leaks", action="store_true", help="skip the leak recorder (pair 1 of each variant)")
    p.add_argument("--diff", nargs=2, metavar=("TRACE_A", "TRACE_B"), help="analyse two existing traces only")
    p.set_defaults(func=cmd_determinism)
