"""qa.py bisect - coordinator-only (git worktree; per docs/agent_context/slice.md subagents may not use it): does the
working-tree diff explain one scenario's behaviour change, and if so which dirty file(s)? Born from a real investigation
(2026-09-27, slice G2's `boss40` false alarm) that took ~20 manual steps: this automates that exact process.

Runs `tools/agent_play.py SCRIPT --seed N` once in a fresh worktree at --base (default HEAD) and once in the current tree,
compares their RESULT-line numbers. If they differ, binary-searches the dirty files (git_util.dirty) for the smallest subset
whose reversion alone reproduces the --base result. If reverting EVERY dirty file still does not reproduce it, the
divergence is NOT explained by this diff (environment/state, e.g. saves/ or an unseeded RNG -- see `qa.py determinism`)
and no file is blamed.

    qa.py bisect "spawn boss; wait 40" --seed 7
    qa.py bisect "spawn boss; wait 40" --seed 7 --files src/effects/manager.py,src/effects/ops.py   # test this subset only
    qa.py bisect "spawn boss; wait 40" --seed 7 --base origin/main
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from git_util import dirty, git, git_rc
from probe_settings import ROOT

_KV = re.compile(r"([A-Za-z_][\w.\-]*)=(\S+)")
_ENV = {"AI_EVOLVE_TACTICS_MEMORY": "off", "AI_EVOLVE_HERO_MIND": "off"}    # else runs in the same tree pollute each other
_NUMERIC_FIELDS = ("dealt", "taken", "hp", "kills", "t", "lvl", "xp")


def _to_num(s: str):
    try:
        return float(s)
    except ValueError:
        return s


def run_scenario(cwd: Path, script: str, seed: int) -> dict | None:
    """RESULT-line metrics of one agent_play run in `cwd`, or None if it produced no RESULT line."""
    cmd = [sys.executable, str(ROOT / "tools" / "agent_play.py"), "--seed", str(seed), "--render", "none", script]
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120, env={**os.environ, **_ENV}, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    line = next((ln for ln in reversed(res.stdout.splitlines()) if ln.startswith("RESULT ")), None)
    return {k: _to_num(v) for k, v in _KV.findall(line)} if line is not None else None


def _same(a: dict | None, b: dict | None) -> bool:
    if a is None or b is None:
        return False
    keys = [k for k in _NUMERIC_FIELDS if k in a and k in b]
    return bool(keys) and all(a[k] == b[k] for k in keys)


def make_worktree(base: str) -> Path | None:
    tmp = Path(tempfile.mkdtemp(prefix="qa_bisect_"))
    rc, _ = git_rc("worktree", "add", "--detach", str(tmp), base, root=ROOT)
    return tmp if rc == 0 else None


def remove_worktree(path: Path) -> None:
    git("worktree", "remove", str(path), "--force", root=ROOT)


class _Reverted:
    """Context manager: `paths` get their `base` git content in `root` for the duration (missing at base = removed), then restore."""

    def __init__(self, paths: list, base: str, root: Path):
        self.paths, self.base, self.root = paths, base, root
        self._backup: dict = {}

    def __enter__(self):
        for p in self.paths:
            full = self.root / p
            self._backup[p] = full.read_bytes() if full.is_file() else None
            rc, content = git_rc("show", f"{self.base}:{p}", root=self.root)
            if rc == 0:
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content, encoding="utf-8")
            elif full.is_file():
                full.unlink()                                          # did not exist at base: remove it for this test
        return self

    def __exit__(self, *exc):
        for p, data in self._backup.items():
            full = self.root / p
            if data is None:
                full.unlink(missing_ok=True)
            else:
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_bytes(data)
        return False


def _narrow(paths: list, base: str, script: str, seed: int, target: dict) -> list:
    """Smallest half-split of `paths` whose reversion alone reproduces `target`; best-effort (no full delta-debugging)."""
    if len(paths) <= 1:
        return paths
    mid = len(paths) // 2
    for half in (paths[:mid], paths[mid:]):
        with _Reverted(half, base, ROOT):
            if _same(run_scenario(ROOT, script, seed), target):
                return _narrow(half, base, script, seed, target)
    return paths                                                       # neither half alone suffices: report the whole set


def _diagnose(files: list, base: str, args, cur: dict, target: dict) -> int:
    """`cur` already known to differ from `target`, or not: print the verdict and return its exit code."""
    script, seed = args.script, args.seed
    if _same(cur, target):
        print(f"ok    bisect no divergence ({len(files)} dirty file(s), all innocent) result={target}")
        return 0
    with _Reverted(files, base, ROOT):
        full_revert = run_scenario(ROOT, script, seed)
    if not _same(full_revert, target):
        print(f"warn  bisect divergence NOT explained by these {len(files)} file(s) -- reverting all of them still "
              f"gives {full_revert}, not the {base} result {target}. Likely environment/state, not this diff "
              f"(check `qa.py determinism` for leaks: saves/, an unseeded RNG, ...).")
        return 1
    culprits = _narrow(files, base, script, seed, target)
    print(f"FAIL  bisect culprit(s): {', '.join(culprits)} (of {len(files)} dirty) | cur={cur} {base}={target}")
    return 1


def cmd_bisect(args) -> int:
    base = args.base or "HEAD"
    files = [f for f in (args.files.split(",") if args.files else dirty(root=ROOT)) if (ROOT / f).is_file()]
    if not files:
        print(f"bisect: nothing dirty vs {base} -- nothing to explain")
        return 0
    print(f"bisect: {len(files)} candidate file(s) vs {base}; running {args.script!r} seed={args.seed} ...")
    cur = run_scenario(ROOT, args.script, args.seed)
    if cur is None:
        print("bisect: the current tree produced no RESULT line")
        return 2
    wt = make_worktree(base)
    if wt is None:
        print(f"bisect: could not create a worktree at {base}")
        return 2
    try:
        target = run_scenario(wt, args.script, args.seed)
        if target is None:
            print(f"bisect: {base} produced no RESULT line")
            return 2
        return _diagnose(files, base, args, cur, target)
    finally:
        remove_worktree(wt)


def register(sub):
    p = sub.add_parser("bisect", help="coordinator-only: does the working-tree diff explain a scenario's behaviour "
                        "change, and if so which dirty file(s)", description=__doc__.strip().splitlines()[0],
                        epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("script", help="an agent_play.py script, e.g. 'spawn boss; wait 40'")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--base", default=None, help="ref to compare against (default: HEAD)")
    p.add_argument("--files", help="comma-separated subset to test instead of every dirty file")
    p.set_defaults(func=cmd_bisect)
