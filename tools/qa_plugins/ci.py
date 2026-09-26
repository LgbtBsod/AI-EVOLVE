"""qa.py ci - read a GitHub Actions run through the `gh` CLI and print ONLY what an agent needs.

    qa.py ci                       # latest run of the current branch (--latest) | --run ID | --sha SHA | --workflow NAME
    qa.py ci --wait                # poll quietly until the run finishes, then print the final block once
    qa.py ci --lines 12            # lines per failed-step block (default 8)

    CI verdict=FAIL run=35988866453 wf=Determinism_probe sha=16aa2e7 jobs=3 ok=2 fail=1 dur=2m35s
    FAIL rust_core (windows-latest) > Lua bridge parity (mlua vs lupa)  [python -m pytest -q tests/test_lua_bridge.py] exit=1
      FAILED tests/test_lua_bridge.py::test_export_lua_is_shared_between_backends - assert '-- ...' == '-- ...'
      E assert ...
      at tests\\test_lua_bridge.py:105: AssertionError
    full log: dev_probe_output/qa/ci_35988866453.log

Per failed step: the step + command, pytest `FAILED id - message` (<= 5), the assertion and <= 3 diff lines (pytest
'Full diff' noise dropped), the last Python traceback frame + exception, cargo `error[E....] file:line`, `ERROR:` lines,
and the `RESULT` / `QA verdict` / check lines our own tools printed. Same failure on several jobs = one block.
Timestamps, ANSI codes and the `job<TAB>step<TAB>` prefix are stripped; the whole cleaned log goes to a file.
Exit code: 0 ok, 1 failed/cancelled, 2 tool error (no gh, no run), 3 still running.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone

import qa_report as R
from git_util import git as _git
from probe_settings import ROOT, qa_settings

GH_HINT = "gh CLI not found - install https://cli.github.com/ then run `gh auth login`"
RUN_FIELDS = "databaseId,status,conclusion,headSha,workflowName,displayTitle,event,headBranch,createdAt,startedAt,updatedAt,url,jobs"
LIST_FIELDS = "databaseId,status,conclusion,headSha,workflowName,createdAt,updatedAt,headBranch,event"
OK_CONCLUSIONS = ("success", "skipped", "neutral")


def gh(*args, timeout: float = 120):
    """-> (rc, stdout, stderr). Tests replace this function; nothing else in this module touches the network."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                           timeout=timeout, cwd=ROOT)
    except FileNotFoundError:
        return 127, "", GH_HINT
    except subprocess.TimeoutExpired:
        return 124, "", f"gh timed out after {timeout}s"
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------- log cleaning

_TS = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ?")
BOM = chr(0xFEFF)                  # `gh` puts a byte-order mark in front of the first line of a log


def clean_log(raw: str) -> list:
    """`gh run view --log(-failed)` text -> [(job, step, line)]: BOM, ANSI, timestamps and the tab prefix removed."""
    entries = []
    for line in raw.replace("\r", "").split("\n"):
        parts = line.split("\t", 2)
        job, step, text = (parts[0], parts[1], parts[2]) if len(parts) == 3 else ("", "", line)
        text = _TS.sub("", R.clean(text).replace(BOM, ""))
        entries.append((job.replace(BOM, ""), step, text.rstrip()))
    while entries and not entries[-1][2]:
        entries.pop()
    return entries


def group_steps(entries) -> dict:
    steps: dict = {}
    for job, step, text in entries:
        steps.setdefault((job, step), []).append(text)
    return steps


# ---------------------------------------------------------------- extraction (pure functions: fixtures test these)

_PYT_COUNT = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected|warnings?)")
_WORKSPACE = re.compile(r"^(?:.*?[/\\]work[/\\][^/\\]+[/\\][^/\\]+[/\\]|[A-Za-z]:\\a\\[^\\]+\\[^\\]+\\)")


def _short(text: str, width: int = 130) -> str:
    return R.one_line(text, width)


def _rel(path: str) -> str:
    return _WORKSPACE.sub("", path)


def command_of(lines) -> str | None:
    for ln in lines:
        m = re.match(r"##\[group\]Run (.+)", ln)
        if m:
            return None if m.group(1).startswith("actions/") else m.group(1).strip()
    return None


def exit_code_of(lines) -> str | None:
    for ln in reversed(lines):
        m = re.search(r"Process completed with exit code (\d+)", ln)
        if m:
            return m.group(1)
    return None


def essentials(lines) -> list:
    """Failed step's log lines -> [(kind, text)] in priority order (the caller cuts to its line budget)."""
    out: list = []

    failed, seen = [], set()
    for ln in lines:
        m = re.match(r"FAILED (\S+?)(?: - (.*))?$", ln)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            failed.append(f"FAILED {m.group(1)}" + (f" - {_short(m.group(2), 110)}" if m.group(2) else ""))
    out += [("failed", f) for f in failed[:5]]
    if len(failed) > 5:
        out.append(("failed", f"(+{len(failed) - 5} more FAILED)"))

    block: list = []
    for ln in lines:                                   # first pytest `E ` block: assertion, then diff lines
        if re.match(r"^E(\s|$)", ln):
            block.append(ln[1:].strip())
        elif block:
            break
    texts = [t for t in block if t]
    if texts:
        out.append(("assert", "E " + _short(texts[0], 120)))
        rest = texts[1:]
        for i, t in enumerate(rest):
            if t.startswith("Full diff"):
                rest = rest[:i]                        # pytest repeats the whole object here: pure noise
                break
        out += [("diff", "  " + _short(t, 110)) for t in rest if not t.startswith("?")][:3]
    for ln in lines:
        m = re.match(r"^(\S+\.py):(\d+): (\w+)", ln)
        if m and block:
            out.append(("where", f"at {m.group(1)}:{m.group(2)}: {m.group(3)}"))
            break

    tb = max((i for i, ln in enumerate(lines) if ln.strip() == "Traceback (most recent call last):"), default=None)
    if tb is not None:
        frame, exc = None, None
        for ln in lines[tb + 1:]:
            m = re.match(r'\s+File "(.+)", line (\d+), in (.+)$', ln)
            if m:
                frame = f"{_rel(m.group(1))}:{m.group(2)} in {m.group(3)}"
            elif ln and not ln.startswith((" ", "\t")):
                exc = ln
                break
        if frame or exc:
            out.append(("traceback", "Traceback " + " -> ".join(x for x in (frame, _short(exc or "", 110)) if x)))

    cargo = []
    for i, ln in enumerate(lines):
        m = re.match(r"^error(?:\[(E\d+)\])?: (.+)$", ln)
        if not m:
            continue
        if m.group(1):
            loc = next((re.search(r"--> (\S+?):(\d+)", x) for x in lines[i + 1:i + 4] if "-->" in x), None)
            cargo.append(f"error[{m.group(1)}] " + (f"{loc.group(1)}:{loc.group(2)} " if loc else "") + _short(m.group(2), 90))
        elif "could not compile" in m.group(2):
            cargo.append("error: " + _short(m.group(2), 100))
    out += [("cargo", c) for c in cargo[:4]]
    for i, ln in enumerate(lines):
        m = re.match(r"^thread '(.+?)' panicked at (\S+?):(\d+)", ln)
        if m:
            out.append(("panic", f"panic {m.group(2)}:{m.group(3)} " + _short(lines[i + 1] if i + 1 < len(lines) else "", 90)))
            break
    out += [("cargo", f"test {m.group(1)} ... FAILED") for m in
            (re.match(r"^test (\S+) \.\.\. FAILED", ln) for ln in lines) if m][:3]

    errs, seen = [], set()
    for ln in lines:
        m = re.match(r"^(?:##\[error\])?(?:ERROR|Error|FATAL|fatal): ?(.+)", ln) or \
            re.match(r"^##\[error\](?!Process completed)(.+)", ln)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            errs.append(_short(ln.replace("##[error]", "").strip(), 130))
    out += [("error", e) for e in errs[:3]]

    ours = [_short(ln, 170) for ln in lines
            if re.match(r"^(RESULT |QA verdict|(FAIL|ERROR) +\S+ .*dur=)", ln)]
    out += [("tool", t) for t in list(dict.fromkeys(ours))[:4]]

    sums = [ln for ln in lines if re.search(r"\bin \d+(\.\d+)?s\b", ln) and _PYT_COUNT.search(ln)
            and re.match(r"^(=+ )?\d+ ", ln)]
    if sums:
        out.append(("summary", sums[-1].strip("= ").strip()))
    if not out:
        out = [("tail", t) for t in [ln for ln in lines if ln.strip() and not ln.startswith("##[")][-4:]]
    return out


def make_blocks(steps: dict, per_block: int = 8) -> list:
    """{(job, step): lines} of the failed steps -> [{jobs, step, cmd, exit, lines}] (same failure on N jobs = 1 block)."""
    blocks: dict = {}
    for (job, step), lines in steps.items():
        ess = [t for _k, t in essentials(lines)]
        key = (step, tuple(ess))
        blk = blocks.setdefault(key, {"jobs": [], "step": step, "cmd": command_of(lines), "exit": exit_code_of(lines),
                                      "lines": ess[:max(1, per_block - 1)]})
        blk["jobs"].append(job)
    return list(blocks.values())


def block_lines(blk: dict) -> list:
    """`FAIL jobs > step  [command] exit=N` + the essentials, indented."""
    cmd, step = blk["cmd"], blk["step"]
    jobs = ", ".join(j for j in blk["jobs"] if j) or "?"
    if cmd and step in (cmd, f"Run {cmd}"):
        head = f"FAIL {jobs} > {_short(cmd, 90)}"
    else:
        head = f"FAIL {jobs} > {_short(step, 70)}" + (f"  [{_short(cmd, 90)}]" if cmd else "")
    if blk["exit"]:
        head += f" exit={blk['exit']}"
    return [head] + [f"  {t}" for t in blk["lines"]]


# ---------------------------------------------------------------- run summary

def _t(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def run_duration(run: dict) -> float | None:
    a, b = _t(run.get("startedAt") or run.get("createdAt")), _t(run.get("updatedAt"))
    if run.get("status") != "completed":
        b = datetime.now(timezone.utc)
    return (b - a).total_seconds() if a and b else None


def job_state(job: dict) -> str:
    if job.get("status") != "completed":
        return "running"
    if job.get("conclusion") == "cancelled":
        return "cancelled"
    return "ok" if job.get("conclusion") in OK_CONCLUSIONS else "fail"


def verdict_of(run: dict) -> str:
    states = [job_state(j) for j in run.get("jobs") or []]
    if run.get("status") != "completed":
        return "RUNNING"
    if "fail" in states:
        return "FAIL"
    if "cancelled" in states:
        return "CANCELLED"
    c =(run.get("conclusion") or "").lower()
    return {"success": "OK", "failure": "FAIL", "timed_out": "FAIL", "cancelled": "CANCELLED", "skipped": "SKIPPED",
            "neutral": "OK"}.get(c, c.upper() or "UNKNOWN")


def header(run: dict) -> str:
    states = [job_state(j) for j in run.get("jobs") or []]
    parts = [f"CI verdict={verdict_of(run)}", f"run={run.get('databaseId')}",
             f"wf={'_'.join(str(run.get('workflowName') or '?').split())}", f"sha={str(run.get('headSha') or '?')[:7]}",
             f"jobs={len(states)}", f"ok={states.count('ok')}", f"fail={states.count('fail')}"]
    if states.count("cancelled"):
        parts.append(f"cancelled={states.count('cancelled')}")
    if states.count("running"):
        parts.append(f"running={states.count('running')}")
    d = run_duration(run)
    parts.append(f"dur={R.fmt_dur(d) if d is not None else '?'}")
    return " ".join(parts)


def failed_step_names(run: dict) -> list:
    return [(j.get("name", "?"), s.get("name", "?")) for j in run.get("jobs") or [] if job_state(j) == "fail"
            for s in j.get("steps") or [] if s.get("conclusion") == "failure"]


def build_report(run: dict, log_text: str | None, per_block: int = 8, max_lines: int = 30, log_path: str | None = None,
                 siblings=()) -> list:
    """Pure: run JSON (+ `--log-failed` text) -> the lines to print."""
    lines = [header(run)]
    others = [f"{'_'.join(str(s.get('workflowName')).split())}={'RUNNING' if s.get('status') != 'completed' else str(s.get('conclusion')).upper()}"
              f"({s.get('databaseId')})" for s in siblings if s.get("status") != "completed" or s.get("conclusion") != "success"]
    if others:
        lines.append("also: " + " ".join(others))
    if verdict_of(run) == "FAIL":
        blocks = make_blocks(group_steps(clean_log(log_text)), per_block) if log_text and log_text.strip() else []
        if not blocks:                                  # logs expired / not downloadable: names from the run JSON
            blocks = [{"jobs": [j], "step": s, "cmd": None, "exit": None, "lines": ["(no log text: gh run view "
                                                                                     f"{run.get('databaseId')} --log-failed)"]}
                      for j, s in failed_step_names(run)]
        budget = max_lines - len(lines) - (1 if log_path else 0)
        used = 0
        for i, blk in enumerate(blocks):
            bl = block_lines(blk)
            if used and used + len(bl) > budget - 1:      # keep one line for the "(+N more)" pointer
                lines.append(f"(+{len(blocks) - i} more failed step(s): see {log_path or 'the log'})")
                break
            lines += bl[:max(1, budget - used)]
            used += len(bl)
    if log_path:
        lines.append(f"full log: {log_path}")
    return lines


# ---------------------------------------------------------------- gh plumbing

def _json(out: str):
    try:
        return json.loads(out)
    except ValueError:
        return None


def resolve_run(args):
    """-> (run_id, siblings, error)."""
    if args.run:
        return str(args.run), [], None
    q = ["run", "list", "--limit", "10", "--json", LIST_FIELDS]
    if args.workflow:
        q += ["--workflow", args.workflow]
    branch = None
    if args.sha:
        q += ["--commit", _git("rev-parse", args.sha) or args.sha]
    else:
        branch = args.branch or _git("rev-parse", "--abbrev-ref", "HEAD")
        if branch and branch != "HEAD":
            q += ["--branch", branch]
    rc, out, err = gh(*q)
    runs = _json(out) if rc == 0 else None
    if rc != 0:
        return None, [], (err or out).strip().splitlines()[0] if (err or out).strip() else f"gh exited {rc}"
    if not runs and "--branch" in q and not args.branch:      # unpushed branch: fall back to the newest run anywhere
        i = q.index("--branch")
        rc, out, err = gh(*(q[:i] + q[i + 2:]))
        runs = _json(out) if rc == 0 else None
    if not runs:
        return None, [], "no workflow runs found" + (f" for {args.sha}" if args.sha else "")
    first = runs[0]
    return str(first["databaseId"]), [r for r in runs[1:] if r.get("headSha") == first.get("headSha")], None


def wait_finished(run_id: str, poll: float = 15.0, timeout: float = 1800.0, sleep=None) -> str:
    """Quiet polling. -> 'done' | 'timeout' | error text."""
    waited = 0.0
    while True:
        rc, out, err = gh("run", "view", run_id, "--json", "status,conclusion")
        if rc != 0:
            return (err or out).strip().splitlines()[0] if (err or out).strip() else f"gh exited {rc}"
        data = _json(out) or {}
        if data.get("status") == "completed":
            return "done"
        if waited >= timeout:
            return "timeout"
        (sleep or time.sleep)(poll)
        waited += poll


def cmd_ci(args) -> int:
    cfg = R.report_cfg(qa_settings())
    run_id, siblings, err = resolve_run(args)
    if err:
        print(f"CI verdict=ERROR {err}")
        return 2
    if args.wait:
        state = wait_finished(run_id, args.poll, args.timeout)
        if state == "timeout":
            print(f"CI verdict=TIMEOUT run={run_id} waited={R.fmt_dur(args.timeout)} (still running)")
            return 2
        if state != "done":
            print(f"CI verdict=ERROR {state}")
            return 2
    rc, out, err = gh("run", "view", run_id, "--json", RUN_FIELDS)
    run = _json(out) if rc == 0 else None
    if run is None:
        msg = (err or out).strip().splitlines()[0] if (err or out).strip() else f"gh exited {rc}"
        print(f"CI verdict=ERROR run={run_id} {msg}")
        return 2
    log_text = log_path = None
    if verdict_of(run) == "FAIL":
        rc, log_text, err = gh("run", "view", run_id, "--log-failed", timeout=300)
        if rc != 0:
            log_text = None
        if log_text:
            path = R.QA_OUT / f"ci_{run_id}.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(dump_log(clean_log(log_text)), encoding="utf-8")
            log_path = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
    print("\n".join(build_report(run, log_text, args.lines, cfg["max_lines"], log_path, siblings)))
    v = verdict_of(run)
    return 0 if v in ("OK", "SKIPPED") else 3 if v == "RUNNING" else 1


def dump_log(entries) -> str:
    """The whole cleaned log, grouped: `=== job > step ===` then its lines."""
    out, last = [], None
    for job, step, text in entries:
        if (job, step) != last:
            out.append(f"=== {job} > {step} ===" if job or step else "===")
            last = (job, step)
        out.append(text)
    return "\n".join(out) + "\n"


def register(sub):
    p = sub.add_parser("ci", help="GitHub Actions run via gh: verdict + only the essentials of failed steps",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--latest", action="store_true", help="newest run of the current branch (default)")
    g.add_argument("--run", type=int, help="run id")
    g.add_argument("--sha", help="newest run of this commit (HEAD, a short or a full sha)")
    p.add_argument("--branch", help="branch for --latest (default: current)")
    p.add_argument("--workflow", help="workflow name/file, e.g. CI")
    p.add_argument("--wait", action="store_true", help="poll quietly until the run completes")
    p.add_argument("--poll", type=float, default=15.0, help="seconds between polls with --wait")
    p.add_argument("--timeout", type=float, default=1800.0, help="give up waiting after N seconds")
    p.add_argument("--lines", type=int, default=8, help="max lines per failed-step block")
    p.set_defaults(func=cmd_ci)
