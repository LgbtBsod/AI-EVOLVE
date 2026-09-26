"""qa.py trend - slow or flipping checks from dev_probe_output/qa/history.jsonl (also printed as `warn trend` lines by `qa.py check`).

    qa.py trend                    # every triggered check: duration vs the median of the last N runs, ok<->FAIL flips
    qa.py trend --check NAME       # one check, with its numbers even when nothing triggers
    qa.py trend --last 20          # window (default: trend.window in lua_content/qa.lua)

A duration is flagged only when the newest `confirm` runs ALL exceed median*(1+dur_pct/100) and median+dur_abs (CI noise); flips = status
changes between ok and FAIL in the window. Checks with fewer than `min_rows` rows are skipped. Thresholds: `trend` table of lua_content/qa.lua.
"""
from __future__ import annotations

import statistics
from collections import defaultdict

import qa_report as R
from jsonl_io import read_jsonl
from probe_settings import qa_settings

TREND_DEFAULTS = {"window": 20, "min_rows": 8, "dur_pct": 30, "dur_abs": 1.0, "confirm": 3, "flips": 3}


def trend_cfg(settings: dict | None = None, last: int | None = None) -> dict:
    cfg = {**TREND_DEFAULTS, **((settings or {}).get("trend") or {})}
    if last:
        cfg["window"] = last
    return cfg


def _flips(rows: list) -> int:
    seq = [r.get("status") for r in rows if r.get("status") in ("ok", "fail")]
    return sum(1 for a, b in zip(seq, seq[1:], strict=False) if a != b)


def analyze_check(rows: list, cfg: dict) -> dict | None:
    """Numbers of one check (rows oldest first) or None when the history is too short."""
    rows = rows[-cfg["window"]:]
    if len(rows) < cfg["min_rows"]:
        return None
    durs = [float(r.get("dur") or 0) for r in rows]
    med = statistics.median(durs[:-cfg["confirm"]] or durs)
    limit = max(med * (1 + cfg["dur_pct"] / 100), med + cfg["dur_abs"])
    recent = durs[-cfg["confirm"]:]
    slow = len(recent) == cfg["confirm"] and all(d > limit for d in recent)
    pct = (statistics.median(recent) / med - 1) * 100 if med else 0.0
    return {"n": len(rows), "median": med, "pct": pct, "slow": slow, "flips": _flips(rows)}


def analyze(rows: list, cfg: dict, only: str | None = None) -> dict:
    by = defaultdict(list)
    for r in rows:
        if r.get("name") and (only is None or r["name"] == only):
            by[r["name"]].append(r)
    return {n: a for n, rs in by.items() if (a := analyze_check(rs, cfg))}


def trend_lines(rows: list, cfg: dict, only: str | None = None, verbose: bool = False) -> list:
    """`warn   trend NAME ...` lines for the triggered checks (all checks with numbers when `verbose`)."""
    out = []
    for name, a in sorted(analyze(rows, cfg, only).items()):
        notes = []
        if a["slow"]:
            notes.append(f"dur={a['pct']:+.0f}% vs median({a['n']})")
        if a["flips"] >= cfg["flips"]:
            notes.append(f"flips={a['flips']} in last {a['n']}")
        if notes:
            out.append(f"warn   trend {name} " + " ".join(notes))
        elif verbose:
            out.append(f"ok     trend {name} dur={a['pct']:+.0f}% vs median({a['n']}) median={R.fmt_dur(a['median'])} flips={a['flips']}")
    return out


def cmd_trend(args) -> int:
    cfg = trend_cfg(qa_settings(), args.last)
    lines = trend_lines(read_jsonl(R.HISTORY) if R.HISTORY.exists() else [], cfg, args.check, verbose=bool(args.check))
    print("\n".join(lines) if lines else f"trend: nothing flagged (window={cfg['window']}, min_rows={cfg['min_rows']})")
    return 0


def register(sub):
    p = sub.add_parser("trend", help="slow (median of last N + 3-run confirm) or flipping (ok<->FAIL) checks from history.jsonl",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
    p.add_argument("--check", help="one check name (prints its numbers even when not flagged)")
    p.add_argument("--last", type=int, default=None, help="window of runs (trend.window)")
    p.set_defaults(func=cmd_trend)
