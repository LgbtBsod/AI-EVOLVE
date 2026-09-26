#!/usr/bin/env python3
"""qa_report - ONE output format for every QA check (shared library, no CLI).

An agent should spend tokens on decisions, not on reading logs. Every check
(pytest shards, golden, agent_play scenarios, boot test, ...) is turned into a
`Result` and printed by ONE formatter:

    ok     combat_smoke  passed=53 failed=0 dur=0.6s
    FAIL   play:swarm    kills=6(-40%) dealt=484.2(-22%) dur=0.1s | FAIL expect alive at t=40 | repro: python tools/...
    cached tests         passed=292 new=0 known=1 dur=3.1s age=4m

    QA verdict=FAIL checks=3 ok=1 fail=1 warn=0 cached=1 dur=0.8s head=1d147e1 dirty=2 selected=3/12 by=diff

Statuses: ok | FAIL | warn | ERROR | skip | cached (fail = the code is wrong, error = the
check itself could not run/parse). Output is capped (`report.max_lines` in
lua_content/qa.lua): the overflow goes to a file and one `(+N more lines: PATH)` line
is printed. Metric deltas against the previous recorded run of the same check are
appended only when they exceed the thresholds in qa.lua (`dealt=484.2(-22%)`).
History: dev_probe_output/qa/history.jsonl. Exit code: 0 ok/cached/warn/skip, 1 any fail, 2 tool error.

A check is declared as DATA in lua_content/qa.lua (`checks = {...}`, no Python) or as a Python
file tools/qa_checks/<name>.py:

    from qa_report import check, Result
    @check("my_check", cost="low", watches=["src/x/**"], tags=["combat"])
    def my_check(ctx):
        return ctx.result(ctx.run("python tools/x.py"), parse="counts")   # or Result("ok", {"n": 3})

Parsers for the output formats the repo already has: result_line (`RESULT k=v ...`), pytest
(pytest / `qa.py test` summary), counts (`N passed, M failed`), regex (named groups), exit (rc only).
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QA_OUT = ROOT / "dev_probe_output" / "qa"
HISTORY = QA_OUT / "history.jsonl"

STATUSES = ("ok", "fail", "warn", "error", "skip", "cached")
WORD = {"ok": "ok", "fail": "FAIL", "warn": "warn", "error": "ERROR", "skip": "skip", "cached": "cached"}
ORDER = {"error": 0, "fail": 1, "warn": 2, "skip": 3, "ok": 4, "cached": 5}   # worst first: overflow cuts the good news
LINE_RE = re.compile(r"^(ok|FAIL|warn|ERROR|skip|cached) +\S+")
HEADER_RE = re.compile(r"^QA verdict=(OK|FAIL) checks=\d+ ok=\d+ fail=\d+ warn=\d+ cached=\d+ ")

# Same defaults as the `report` table of lua_content/qa.lua (used when Lua is unavailable).
DEFAULT_CFG = {
    "max_lines": 30, "detail_lines": 3, "line_width": 150,
    "delta_pct": 15, "delta_abs": 1, "delta": {}, "delta_ignore": ["dur", "wall", "t"],
    "history_keep": 400, "timeout": 600, "jobs": 4,
}


def report_cfg(qa_settings: dict | None = None) -> dict:
    cfg = {**DEFAULT_CFG, **((qa_settings or {}).get("report") or {})}
    return cfg


# ---------------------------------------------------------------- result + formatting

@dataclass
class Result:
    status: str                                        # ok | fail | warn | error | skip | cached
    metrics: dict = field(default_factory=dict)        # printed as k=v, compared with the previous run
    detail: list = field(default_factory=list)         # first line goes inline, fails print up to detail_lines
    repro: str | None = None                           # one command that reproduces a non-ok result
    dur: float = 0.0
    name: str = ""
    age: float | None = None                           # cached only: seconds since the original run
    variant: str = ""                                  # e.g. "diff": a subset run must not be compared with a full one

    @property
    def key(self) -> str:                              # history/delta identity
        return f"{self.name}@{self.variant}" if self.variant else self.name

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "metrics": self.metrics, "detail": self.detail,
                "repro": self.repro, "dur": round(self.dur, 3), "age": self.age}


_ANSI = re.compile(r"(?:\x1b|\^\[)\[[0-9;?]*[ -/]*[@-~]")      # real ESC, or the `^[` a log saved through `cat -A` shows


def clean(text: str) -> str:
    return _ANSI.sub("", text).replace("\r", "")


def one_line(text, width: int = 150) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= width else s[:max(1, width - 3)] + "..."


def fmt_num(v) -> str:
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.0f}" if abs(v) >= 1000 else (f"{v:.3f}".rstrip("0").rstrip(".") or "0")
    return "_".join(str(v).split())


def fmt_dur(s: float) -> str:
    if s >= 60:
        m, sec = divmod(round(s), 60)
        return f"{m}m{sec:02d}s"
    return f"{s:.1f}s" if s < 10 else f"{s:.0f}s"


def fmt_age(s: float) -> str:
    s = max(0, int(s))
    return f"{s}s" if s < 90 else f"{s // 60}m" if s < 5400 else f"{s // 3600}h" if s < 172800 else f"{s // 86400}d"


def delta_tokens(metrics: dict, prev: dict | None, cfg: dict) -> dict:
    """{metric: '(-22%)'} for numeric metrics that moved more than qa.lua `report.delta*` allows."""
    out = {}
    for k, v in metrics.items():
        p = (prev or {}).get(k)
        if k in cfg["delta_ignore"] or isinstance(v, bool) or isinstance(p, bool) \
                or not isinstance(v, (int, float)) or not isinstance(p, (int, float)):
            continue
        thr = cfg["delta"].get(k, {})
        diff = v - p
        if abs(diff) < thr.get("abs", cfg["delta_abs"]) or diff == 0:
            continue
        if p != 0:
            pct = diff / abs(p) * 100
            if abs(pct) < thr.get("pct", cfg["delta_pct"]):
                continue
            out[k] = f"({pct:+.0f}%)"
        else:
            out[k] = f"({diff:+g})"
    return out


def format_line(res: Result, name_w: int = 0, deltas: dict | None = None, cfg: dict | None = None) -> str:
    """The ONE line format: `STATUS NAME k=v ... dur=1.2s [age=3m] [| first detail] [| repro: CMD]`."""
    cfg = cfg or DEFAULT_CFG
    deltas = deltas or {}
    toks = [f"{k}={fmt_num(v)}{deltas.get(k, '')}" for k, v in res.metrics.items()]
    toks.append(f"dur={fmt_dur(res.dur)}")
    if res.status == "cached" and res.age is not None:
        toks.append(f"age={fmt_age(res.age)}")
    line = f"{WORD[res.status]:<6} {res.name:<{name_w}} " + " ".join(toks)
    if res.detail and res.status not in ("ok", "cached"):
        line += " | " + one_line(res.detail[0], cfg["line_width"])
    if res.repro and res.status in ("fail", "error", "warn"):
        line += f" | repro: {res.repro}"
    return line.rstrip()


def verdict(results) -> str:
    return "FAIL" if any(r.status in ("fail", "error") for r in results) else "OK"


def exit_code(results) -> int:
    if any(r.status == "fail" for r in results):
        return 1
    return 2 if any(r.status == "error" for r in results) else 0


def header_line(results, meta: dict) -> str:
    c = Counter(r.status for r in results)
    parts = [f"QA verdict={verdict(results)}", f"checks={len(results)}", f"ok={c['ok']}", f"fail={c['fail']}",
             f"warn={c['warn']}", f"cached={c['cached']}"]
    if c["skip"]:
        parts.append(f"skip={c['skip']}")
    if c["error"]:
        parts.append(f"error={c['error']}")
    parts += [f"dur={fmt_dur(meta.get('dur', 0.0))}", f"head={meta.get('head', '?')}", f"dirty={meta.get('dirty', '?')}",
              f"selected={meta.get('selected', len(results))}/{meta.get('total', len(results))}",
              f"by={meta.get('by', 'all')}"]
    return " ".join(parts)


def render(results, meta: dict, prev: dict | None = None, cfg: dict | None = None):
    """-> (printed_lines, full_lines). printed obeys the line budget (header included); full has every detail line.
    Worst results first, so an overflow only ever hides good news."""
    cfg = cfg or DEFAULT_CFG
    ordered = sorted(results, key=lambda r: ORDER[r.status])
    width = max((len(r.name) for r in ordered), default=0)
    width = min(width, 24)
    head = header_line(results, meta)
    short, full = [head], [head]
    for r in ordered:
        deltas = {} if r.status == "cached" else delta_tokens(r.metrics, (prev or {}).get(r.key), cfg)   # a replay has no news
        line = format_line(r, width, deltas, cfg)
        short.append(line)
        full.append(line)
        if r.status in ("fail", "error"):
            extra = [f"  | {one_line(d, cfg['line_width'])}" for d in r.detail[1:]]
            short += extra[:max(0, cfg["detail_lines"] - 1)]
            full += extra
    return short, full


def budgeted(short, full, cfg: dict | None = None, write_full: Callable[[list], str] | None = None):
    """Cut `short` to max_lines; if anything is hidden, dump `full` via write_full(lines)->path and add the pointer line."""
    cfg = cfg or DEFAULT_CFG
    hidden = len(full) - len(short)
    if len(short) > cfg["max_lines"]:
        short = short[:cfg["max_lines"] - 1]
        hidden = len(full) - len(short)
    if hidden > 0:
        path = write_full(full) if write_full else "-"
        short = short[:cfg["max_lines"] - 1] + [f"(+{hidden} more lines: {path})"]
    return short


def to_json(results, meta: dict) -> str:
    c = Counter(r.status for r in results)
    return json.dumps({"verdict": verdict(results), "counts": dict(c), "meta": meta,
                       "checks": [r.to_dict() for r in results]}, separators=(",", ":"), default=str)


def result_lines(res: Result) -> list:
    """Machine form of a Result for a Lua-declared check (`parse = "result_line"`): detail lines, `repro:`, one RESULT line.
    An error prints no RESULT line, so the runner reports ERROR (the check itself broke) instead of FAIL (the code got worse)."""
    lines = list(res.detail)
    if res.repro:
        lines.append(f"repro: {res.repro}")
    if res.status != "error":
        lines.append(f"RESULT status={res.status.upper()} " + " ".join(f"{k}={fmt_num(v)}" for k, v in res.metrics.items()))
    return lines


def write_full(lines: list, run_id: str | None = None) -> str:
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    d = QA_OUT / f"check_{run_id}"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "full.txt"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f.relative_to(ROOT).as_posix() if f.is_relative_to(ROOT) else f.as_posix()


# ---------------------------------------------------------------- history

def append_history(results, meta: dict, cfg: dict | None = None, path: Path | None = None) -> None:
    """One JSON line per fresh (non-cached, non-skipped) check run; trimmed to history_keep lines."""
    cfg = cfg or DEFAULT_CFG
    path = path or HISTORY
    rows = [{"ts": int(time.time()), "name": r.key, "status": r.status, "metrics": r.metrics,
             "dur": round(r.dur, 3), "head": meta.get("head"), "dirty": meta.get("dirty")}
            for r in results if r.status in ("ok", "fail", "warn")]
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.writelines(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > cfg["history_keep"] * 2:
        path.write_text("\n".join(lines[-cfg["history_keep"]:]) + "\n", encoding="utf-8")


def load_prev(names=None, path: Path | None = None) -> dict:
    """{name: metrics of its latest recorded run}."""
    path = path or HISTORY
    if not path.exists():
        return {}
    prev = {}
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        n = row.get("name")
        if n not in prev and (names is None or n in names):
            prev[n] = row.get("metrics") or {}
    return prev


# ---------------------------------------------------------------- parsers (output text -> status, metrics, detail)

def to_num(s):
    if isinstance(s, (int, float)):
        return s
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


_KV = re.compile(r"([A-Za-z_][\w.\-]*)=(\S+)")
DETAIL_RE = re.compile(r"^\s*(FAIL|FAILED|ERROR|Error|error:|Traceback|E {2,}|\(!\)|NEW |FLAKY|expect)")


def tail(text: str, n: int = 3) -> list:
    return [ln.strip() for ln in text.splitlines() if ln.strip()][-n:]


def detail_lines(text: str, spec: dict, n: int = 6) -> list:
    rx = re.compile(spec["detail"]) if spec.get("detail") else DETAIL_RE
    seen, out = set(), []
    for ln in text.splitlines():
        s = ln.strip()
        if s and rx.search(ln) and s not in seen:
            seen.add(s)
            out.append(s)
    return out[:n]


PARSERS: dict = {}


def parser(name):
    def deco(fn):
        PARSERS[name] = fn
        return fn
    return deco


@parser("exit")
def _p_exit(text, rc, spec):
    return "ok", {}, detail_lines(text, spec)


@parser("result_line")
def _p_result_line(text, rc, spec):
    line = next((ln for ln in reversed(text.splitlines()) if ln.startswith("RESULT ")), None)
    if line is None:
        return "error", {}, ["no RESULT line in output", *tail(text, 2)]
    metrics = {k: to_num(v) for k, v in _KV.findall(line)}
    st = str(metrics.pop("status", "OK")).upper()
    return {"OK": "ok", "WARN": "warn"}.get(st, "fail"), metrics, detail_lines(text, spec)


_QA_TEST = re.compile(r"^tests: (\d+) passed, (\d+) skipped, (\d+) failing \((\d+) NEW, (\d+) flaky, (\d+) known\)", re.MULTILINE)
_PYT_COUNT = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)")


@parser("pytest")
def _p_pytest(text, rc, spec):
    m = _QA_TEST.search(text)                       # `qa.py test` summary
    if m:
        passed, skipped, _failing, new, flaky, known = map(int, m.groups())
        detail = [ln.strip() for ln in text.splitlines() if re.match(r"\s+(NEW|FLAKY)", ln)]
        return ("fail" if new else "ok"), {"passed": passed, "skipped": skipped, "new": new, "known": known,
                                            "flaky": flaky}, detail[:6]
    if "no test file is affected" in text:
        return "ok", {"passed": 0}, []
    sums = [ln for ln in text.splitlines() if re.search(r"\bin \d+(\.\d+)?s\b", ln) and _PYT_COUNT.search(ln)]
    if not sums:
        if "no tests ran" in text:
            return "warn", {"passed": 0}, ["no tests ran"]
        return "error", {}, ["no pytest summary line in output", *tail(text, 2)]
    counts = Counter()
    for n, word in _PYT_COUNT.findall(sums[-1]):
        counts["error" if word.startswith("error") else word] += int(n)
    metrics = {"passed": counts["passed"], "failed": counts["failed"], "skipped": counts["skipped"],
               "error": counts["error"]}
    failed = [re.sub(r"^FAILED\s+", "", ln.strip()) for ln in text.splitlines() if re.match(r"(FAILED|ERROR) ", ln)]
    return ("fail" if counts["failed"] or counts["error"] else "ok"), metrics, list(dict.fromkeys(failed))[:5]


@parser("counts")
def _p_counts(text, rc, spec):
    m = re.search(r"(\d+) passed, (\d+) failed", text)
    if not m:
        return "error", {}, ["no 'N passed, M failed' line in output", *tail(text, 2)]
    passed, failed = int(m[1]), int(m[2])
    return ("fail" if failed else "ok"), {"passed": passed, "failed": failed}, detail_lines(text, spec)


@parser("regex")
def _p_regex(text, rc, spec):
    pats = spec.get("pattern") or []
    pats = [pats] if isinstance(pats, str) else list(pats)
    metrics = {}
    for p in pats:
        m = re.search(p, text, re.MULTILINE)
        if m:
            metrics.update({k: to_num(v) for k, v in m.groupdict().items() if v is not None})
    if pats and not metrics:
        return "warn", {}, [f"output did not match {pats[0][:60]!r}", *tail(text, 1)]
    return "ok", metrics, detail_lines(text, spec)


def interpret(text: str, rc: int, spec: dict, secs: float = 0.0, name: str = "") -> Result:
    """Command output -> Result. `spec` keys (all optional, from a Lua check table): parse, pattern, detail,
    keep, hide_zero, warn_over, soft, soft_if, soft_note, repro."""
    text = clean(text)
    if rc == 124 and "timeout after" in text[-400:]:
        return Result("error", {}, [tail(text, 1)[0]], spec.get("repro"), secs, name)
    status, metrics, detail = PARSERS[spec.get("parse", "exit")](text, rc, spec)
    if rc != 0 and status in ("ok", "warn"):
        status, detail = "fail", detail or [f"exit code {rc}", *tail(text, 2)]
    if status in ("fail", "error") and not detail:
        detail = tail(text, 3)
    if status == "fail":
        m = re.search(spec["soft_if"], text, re.MULTILINE) if spec.get("soft_if") else None
        if spec.get("soft") or m:
            note = m.group(0).strip() if m else spec.get("soft_note", "soft check (known problem)")
            status, detail = "warn", [f"soft: {note}", *detail]
    if status == "ok":
        for k, limit in (spec.get("warn_over") or {}).items():
            if isinstance(metrics.get(k), (int, float)) and metrics[k] > limit:
                status, detail = "warn", [f"{k}={fmt_num(metrics[k])} > limit {limit}"]
                break
    if spec.get("keep"):
        metrics = {k: metrics[k] for k in spec["keep"] if k in metrics}
    for k in spec.get("hide_zero") or ():
        if metrics.get(k) in (0, "0/0"):
            del metrics[k]
    repro = spec.get("repro")
    m = re.search(r"^repro:\s*(.+?)(?: \| |$)", text, re.MULTILINE)
    if m and status != "ok":
        repro = m.group(1).strip()
    return Result(status, metrics, detail, repro, secs, name)


# ---------------------------------------------------------------- check registry

@dataclass
class Check:
    name: str
    cost: str = "medium"                    # low <2 s | medium 2-15 s | high >15 s
    watches: tuple = ()                     # globs: the check is selected when a changed/affected file matches
    needs: tuple = ()                       # importable modules; missing -> status skip
    tags: tuple = ()
    what: str = ""
    fn: Callable | None = None              # Python check: fn(ctx) -> Result
    spec: dict = field(default_factory=dict)    # data check (lua_content/qa.lua): cmd, parse, ...
    always: bool = False                    # selected even when nothing it watches changed
    ci: bool = True                         # part of `qa.py check --ci`
    solo: bool = False                      # runs alone (it spawns its own worker pool)
    source: str = ""

    def definition(self) -> str:
        """Everything that defines what the check does: part of the cache key."""
        try:
            body = inspect.getsource(self.fn) if self.fn is not None else ""
        except (OSError, TypeError):            # source not available (REPL, frozen): fall back to the name
            body = getattr(self.fn, "__qualname__", "")
        return json.dumps([self.name, self.spec, list(self.watches), list(self.needs), body], sort_keys=True,
                          default=str)


_collector: list | None = None
_LOOSE: list = []


def check(name, cost="medium", watches=(), needs=(), tags=(), what="", always=False, ci=True, solo=False):
    """Decorator for a Python check: `fn(ctx) -> Result`. Auto-discovered from tools/qa_checks/*.py."""
    def deco(fn):
        chk = Check(name, cost, tuple(watches), tuple(needs), tuple(tags), what or (inspect.getdoc(fn) or "").split("\n")[0],
                    fn=fn, always=always, ci=ci, solo=solo, source=f"@check {getattr(fn, '__module__', '?')}")
        (_collector if _collector is not None else _LOOSE).append(chk)
        return fn
    return deco


def load_python_checks(directory: Path | None = None) -> list:
    """Import every tools/qa_checks/*.py (no __init__ needed) and return the checks they declare."""
    global _collector
    directory = Path(directory) if directory else ROOT / "tools" / "qa_checks"
    found: list = []
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        _collector = found
        try:
            spec = importlib.util.spec_from_file_location(f"qa_checks_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:  # noqa: BLE001  a broken check file must not break the others
            found.append(Check(path.stem, "low", fn=lambda ctx, e=exc: Result("error", detail=[f"{type(e).__name__}: {e}"]),
                               source=f"@check {path.name} (import failed)"))
        finally:
            _collector = None
    return found


@dataclass
class CmdOut:
    rc: int
    out: str
    secs: float
    cmd: str = ""                                 # what ran: the default `repro` of a failing result


class RunCtx:
    """What a Python check gets: run commands (through the qa_pool) and turn output into a Result."""

    def __init__(self, runner=None, changed=(), root: Path = ROOT):
        self.runner, self.changed, self.root = runner, list(changed), root

    def run(self, cmd, timeout: float = 600, env: dict | None = None) -> CmdOut:
        import shlex
        import sys

        import qa_pool
        argv = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
        if argv and argv[0] == "python":
            argv[0] = sys.executable
        (res,) = (self.runner or qa_pool.run_many)([qa_pool.Job("ctx", argv, env or {}, timeout)])
        return CmdOut(res.rc, res.stdout + ("\n" + res.stderr if res.stderr else ""), res.seconds,
                      cmd if isinstance(cmd, str) else " ".join(cmd))

    def result(self, out: CmdOut, **spec) -> Result:
        return interpret(out.out, out.rc, {"repro": out.cmd, **spec}, out.secs)
