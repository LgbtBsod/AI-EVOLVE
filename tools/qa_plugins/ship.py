"""qa.py ship - check, stage, commit, push and wait for CI of exactly that sha in ONE command (one turn instead of 3-5).

    qa.py ship "MESSAGE"                 # changed-aware check -> stage everything (minus ship.exclude) -> commit -> push -> ci --wait
    qa.py ship "MESSAGE" --paths a,b     # stage only these paths
    qa.py ship "MESSAGE" --all           # the full check, always --no-cache
    qa.py ship "MESSAGE" --no-ci         # stop after the push
    qa.py ship "MESSAGE" --dry-run       # print what would be staged/committed, run the check only

    SHIP verdict=OK sha=abc1234 files=3 check=OK(24/25 warn=1) ci=OK(6/6) dur=2m10s

Refuses (one line, nothing changed) when HEAD is detached, behind origin, or not on a branch of `ship.branches`. A failing check prints its
header + the failing lines and stages NOTHING. Never --no-verify, amend, force or stash. Data: `ship` table of lua_content/qa.lua.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import time

import qa_report as R
from git_util import git, git_rc
from probe_settings import ROOT, qa_settings
from repo_hygiene import ignored, scan

SHIP_DEFAULTS = {"branches": ["main"], "exclude": [], "trailer": "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>",
                 "ci_find_tries": 6, "ci_find_wait": 5}


def ship_cfg(settings: dict | None = None) -> dict:
    cfg = {**SHIP_DEFAULTS, **((settings or {}).get("ship") or {})}
    for key in ("branches", "exclude"):
        v = cfg[key]
        cfg[key] = [v] if isinstance(v, str) else list(v or [])
    return cfg


def preflight(root, cfg: dict) -> str | None:
    """One refusal line or None: detached HEAD, wrong branch, behind origin."""
    branch = git("rev-parse", "--abbrev-ref", "HEAD", root=root)
    if not branch or branch == "HEAD":
        return "detached HEAD: check out a branch first"
    if branch not in cfg["branches"]:
        return f"branch {branch!r} is not in ship.branches {cfg['branches']}"
    git_rc("fetch", "-q", "origin", root=root, timeout=120)
    behind = git("rev-list", "--count", f"HEAD..origin/{branch}", root=root)
    if behind not in ("", "0"):
        return f"HEAD is {behind} commit(s) behind origin/{branch}: `git pull --rebase` first"
    return None


def dirty_paths(root) -> list[str]:
    """Modified, added, deleted and untracked paths (renames as their new name)."""
    lines = git("status", "--porcelain", "-uall", root=root, raw=True).splitlines()
    return [ln[3:].split(" -> ")[-1].strip('"') for ln in lines if len(ln) > 3]


def _first_line(out: str, err: str, rc: int) -> str:
    text = (err or out).strip()
    return text.splitlines()[0] if text else f"gh exited {rc}"


def _split_paths(arg: str | None) -> list[str]:
    return [p.strip().replace("\\", "/") for p in (arg or "").split(",") if p.strip()]


def _under(path: str, wanted: list[str]) -> bool:
    return any(path == w or path.startswith(w.rstrip("/") + "/") for w in wanted)


def choose(paths_arg: str | None, dirty: list[str], exclude: list[str]) -> tuple[list[str], list[str]]:
    """-> (paths to stage, paths dropped by ship.exclude)."""
    wanted = _split_paths(paths_arg)
    pool = [d for d in dirty if _under(d, wanted)] if wanted else dirty
    keep = [p for p in pool if not ignored(p, exclude)]
    return keep, [p for p in pool if p not in keep]


def hygiene_refusal(root, paths: list[str]) -> str | None:
    """A staged file that hygiene forbids (virtualenv, build output, saves...) or that is over max_file_kb."""
    cfg = {k: v for k, v in (qa_settings().get("hygiene") or {}).items() if k != "required_ignore"}
    files = [(p, (root / p).stat().st_size if (root / p).is_file() else 0) for p in paths]
    bad = scan(files, "", cfg)
    return f"hygiene refuses {bad[0].subject}: {bad[0].why} (+{len(bad) - 1} more)" if bad else None


def run_check(all_checks: bool) -> tuple[int, list[str]]:
    """The in-process `qa.py check` -> (exit code, its printed lines)."""
    from qa_plugins.check import cmd_check
    ns = argparse.Namespace(changed=not all_checks, all=all_checks, fast=False, name=None, tag=None, ci=False, no_cache=all_checks,
                            json=False, explain=None, list=False, base=None, max_lines=None)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_check(ns)
    return rc, buf.getvalue().splitlines()


def check_summary(lines: list[str]) -> str:
    head = next((ln for ln in lines if ln.startswith("QA verdict=")), "")
    kv = dict(tok.split("=", 1) for tok in head.split() if "=" in tok)
    warn = f" warn={kv['warn']}" if kv.get("warn", "0") != "0" else ""
    return f"OK({kv.get('ok', '?')}/{kv.get('checks', '?')}{warn})"


def failing_lines(lines: list[str]) -> list[str]:
    """Header + the FAIL/ERROR lines (with their `| fix:` / `| repro:`)."""
    return [ln for ln in lines if ln.startswith(("QA verdict=", "FAIL", "ERROR"))]


def _find_run(ci, full: str, cfg: dict, sleep) -> tuple[str | None, str]:
    """-> (run id of exactly this sha, error). The run of a fresh push appears a few seconds late: retry."""
    err = ""
    for i in range(int(cfg["ci_find_tries"])):
        rc, out, err = ci.gh("run", "list", "--commit", full, "--limit", "5", "--json", ci.LIST_FIELDS)
        runs = [r for r in (ci._json(out) or []) if r.get("headSha") == full] if rc == 0 else []
        if runs:
            return str(runs[0]["databaseId"]), ""
        if rc != 0 and i:
            return None, _first_line(out, err, rc)
        sleep(float(cfg["ci_find_wait"]))
    return None, f"no CI run for {full[:7]} after {cfg['ci_find_tries']} tries"


def _finish(ci, run_id: str) -> tuple[str, list[str]]:
    state = ci.wait_finished(run_id)
    rc, out, err = ci.gh("run", "view", run_id, "--json", ci.RUN_FIELDS)
    run = ci._json(out) if rc == 0 else None
    if state != "done" or run is None:
        return f"ERROR run={run_id} {state if state != 'done' else err.strip()}", []
    verdict = ci.verdict_of(run)
    states = [ci.job_state(j) for j in run.get("jobs") or []]
    text = f"{verdict}({states.count('ok')}/{len(states)})"
    if verdict == "CANCELLED":
        text += " (superseded by a newer push: not a verdict for this sha)"
    return text, ([f"repro: python tools/qa.py ci --run {run_id}"] if verdict == "FAIL" else [])


def wait_ci(root, sha: str, cfg: dict, sleep=time.sleep) -> tuple[str, list[str]]:
    """CI of exactly `sha` -> ('OK(6/6)' | 'FAIL(...)' | 'ERROR ...', extra lines)."""
    from qa_plugins import ci
    full = git("rev-parse", sha, root=root) or sha
    run_id, err = _find_run(ci, full, cfg, sleep)
    return _finish(ci, run_id) if run_id else (f"ERROR {err}", [])


def _fail(msg: str, extra=()) -> int:
    print("\n".join([f"SHIP verdict=FAIL {msg}", *extra]))
    return 1


def cmd_ship(args, root=ROOT, check_fn=None, ci_fn=None) -> int:
    t0 = time.perf_counter()
    cfg = ship_cfg(qa_settings())
    if problem := preflight(root, cfg):
        return _fail(problem)
    rc, lines = (check_fn or run_check)(args.all)
    if rc != 0:
        return _fail(f"check exit={rc}", failing_lines(lines))
    paths, dropped = choose(args.paths, dirty_paths(root), cfg["exclude"])
    if not paths:
        return _fail("nothing to ship (clean tree or everything excluded)")
    if problem := hygiene_refusal(root, paths):
        return _fail(problem)
    shown = f"files={len(paths)} first={','.join(paths[:8])}" + (f" excluded={len(dropped)}" if dropped else "")
    if args.dry_run:
        print(f"SHIP verdict=DRY-RUN would stage {shown} check={check_summary(lines)}\nmessage: {args.message}\ntrailer: {cfg['trailer']}")
        return 0
    return _stage_commit_push(args, root, cfg, {"paths": paths, "shown": shown, "summary": check_summary(lines), "ci_fn": ci_fn or wait_ci}, t0)


def _commit(root, paths: list[str], message: str) -> str | None:
    for step in (("add", "-A", "--", *paths), ("commit", "-m", message)):
        rc, out = git_rc(*step, root=root)
        if rc != 0:
            return f"git {step[0]} failed: {out.splitlines()[0] if out else rc}"
    return None


def _report(plan: dict, ok: bool, tail: dict) -> str:
    """plan = paths/shown/summary; tail = sha/ci/extra/dur."""
    paths = plan["paths"]
    head = (f"SHIP verdict={'OK' if ok else 'FAIL'} sha={tail['sha']} {plan['shown'].split(' first=')[0]} check={plan['summary']} "
            f"ci={tail['ci']} dur={tail['dur']}")
    return "\n".join([head, "staged: " + ", ".join(paths[:8]) + (f" (+{len(paths) - 8})" if len(paths) > 8 else ""), *tail["extra"]])


def _stage_commit_push(args, root, cfg, plan, t0) -> int:
    paths = plan["paths"]
    pre = [p for p in git("diff", "--cached", "--name-only", root=root).splitlines() if p not in paths]
    if pre:
        return _fail(f"index already holds {len(pre)} other staged file(s) ({pre[0]}): unstage them first")
    if problem := _commit(root, paths, f"{args.message}\n\n{cfg['trailer']}"):
        return _fail(problem)
    sha = git("rev-parse", "--short=7", "HEAD", root=root)
    rc, out = git_rc("push", "origin", "HEAD", root=root)
    if rc != 0:
        return _fail(f"push failed (commit {sha} is local): {out.splitlines()[-1] if out else rc}")
    ci_txt, extra = ("skipped", []) if args.no_ci else plan["ci_fn"](root, sha, cfg)
    ok = args.no_ci or ci_txt.startswith("OK")
    print(_report(plan, ok, {"sha": sha, "ci": ci_txt, "extra": extra, "dur": R.fmt_dur(time.perf_counter() - t0)}))
    return 0 if ok else 1


def register(sub):
    p = sub.add_parser("ship", help="check -> stage -> commit -> push -> ci --wait for that sha, one command, one line",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("message", help="commit message (the ship.trailer is appended)")
    p.add_argument("--paths", help="comma-separated paths to stage (default: everything not excluded)")
    p.add_argument("--all", action="store_true", help="full check, --no-cache")
    p.add_argument("--no-ci", action="store_true", help="stop after the push")
    p.add_argument("--dry-run", action="store_true", help="print what would be shipped, run the check only")
    p.set_defaults(func=cmd_ship)
