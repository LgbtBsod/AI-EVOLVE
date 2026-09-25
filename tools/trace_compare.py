"""Did the refactor change behaviour? Per-frame trace hashes of every play scenario, before vs after.

    python tools/trace_compare.py --record DIR            # run every scenario with agent_play --trace-frames into DIR
    python tools/trace_compare.py BEFORE_DIR [AFTER_DIR]  # compare; AFTER_DIR omitted -> record now into
                                                          #   dev_probe_output/qa/trace_after, then compare

Scenarios = `scenarios` + `plays` of lua_content/qa.lua plus two long ones (`swarm60`, `boss40`), each run with its own
seed. A trace has one line per simulated frame: `h` = hash of the bit-exact world state, `r` = hashes of the RNG streams
(tools/agent_play.py FrameTracer). Output: ONE line per scenario

    melee_three same frames=74
    swarm DIFF first_frame=118 field=h frames=1390/1390
    golem_guard new frames=740 (no BEFORE trace)            # a scenario added after the BEFORE run: not a diff

`field` is what diverged first (h state, r RNG, len = one trace is shorter); exit 0 all same, 1 any DIFF, 2 tool error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

# long scenarios that are not in qa.lua (name, seed, script)
EXTRA = (("swarm60", 1, "spawn enemy x10; wait 60"), ("boss40", 7, "spawn boss; wait 40"))


def scenarios() -> list[tuple[str, int, str]]:
    """(name, seed, script) of every play scenario declared in qa.lua + EXTRA."""
    from probe_settings import qa_settings
    cfg = qa_settings()
    out = [(s["name"], int(s.get("seed", 1)), s["script"]) for s in cfg.get("scenarios") or []]
    for p in cfg.get("plays") or []:
        script = p["script"] + (f"; expect {p['expects']}" if isinstance(p.get("expects"), str) else "")
        out.append((p["name"], int(p.get("seed", 1)), script))
    out.extend(EXTRA)
    return out


def record(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, seed, script in scenarios():
        trace = out_dir / f"{name}.jsonl"
        cmd = [sys.executable, str(ROOT / "tools" / "agent_play.py"), "--seed", str(seed),
               "--trace-frames", str(trace), script]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        (out_dir / f"{name}.out").write_text(res.stdout + res.stderr, encoding="utf-8")
        if res.returncode != 0 or not trace.exists():
            print(f"{name} ERROR rc={res.returncode} (see {out_dir / (name + '.out')})")
            bad += 1
    return bad


def load(path: Path) -> list[tuple[str, str]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            rows.append((rec["h"], rec["r"]))
    return rows


def compare_one(before: Path, after: Path) -> str:
    if after.exists() and not before.exists():        # a scenario added after the BEFORE run: nothing to compare with
        return f"new frames={len(load(after))} (no BEFORE trace)"
    if not before.exists() or not after.exists():
        return f"DIFF first_frame=-1 field=missing ({'before' if not before.exists() else 'after'} trace absent)"
    a, b = load(before), load(after)
    for i, (x, y) in enumerate(zip(a, b)):
        if x[0] != y[0]:
            return f"DIFF first_frame={i} field=h frames={len(a)}/{len(b)}"
        if x[1] != y[1]:
            return f"DIFF first_frame={i} field=r frames={len(a)}/{len(b)}"
    if len(a) != len(b):
        return f"DIFF first_frame={min(len(a), len(b))} field=len frames={len(a)}/{len(b)}"
    return f"same frames={len(a)}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("before", nargs="?", help="directory with the BEFORE traces (<scenario>.jsonl)")
    ap.add_argument("after", nargs="?", help="directory with the AFTER traces (default: record now)")
    ap.add_argument("--record", metavar="DIR", help="only run every scenario and write its trace into DIR")
    args = ap.parse_args(argv)
    if args.record:
        return 2 if record(Path(args.record)) else 0
    if not args.before:
        ap.error("BEFORE_DIR or --record DIR required")
    after = Path(args.after) if args.after else ROOT / "dev_probe_output" / "qa" / "trace_after"
    if not args.after and record(after):
        return 2
    diffs = 0
    for name, _seed, _script in scenarios():
        line = compare_one(Path(args.before) / f"{name}.jsonl", after / f"{name}.jsonl")
        diffs += line.startswith("DIFF")
        print(f"{name} {line}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
