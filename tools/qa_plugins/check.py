"""qa.py check - every verification in ONE command and ONE output format (tools/qa_report.py).

    qa.py check                       # checks affected by your diff (git diff vs origin/main + working tree)
    qa.py check --all | --fast        # everything | only cost=low checks
    qa.py check --name a,play:*       # by name (globs ok) | --tag play
    qa.py check --ci                  # what CI runs: --all minus checks with ci=false, no cache
    qa.py check --explain NAME        # what it checks, what it watches, how to run/add one (also --list)
    qa.py check --json | --no-cache

Checks are DATA in lua_content/qa.lua (`checks = {...}`; every `scenarios`/`plays` entry is a check too) or
Python files tools/qa_checks/<name>.py with `@check(...)` (see tools/qa_report.py). Results are cached by the
content of everything a check watches (+ its import closure, its definition and AI_EVOLVE_* env).
"""
from __future__ import annotations

import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

import qa_graph
import qa_pool
import qa_report as R
from probe_settings import ROOT, qa_settings

CACHE_DIR = ROOT / "dev_probe_output" / ".qa_cache"
CACHE_FILE = CACHE_DIR / "checks.json"
HASH_FILE = CACHE_DIR / "filehash.json"


def _qa():
    import qa  # tools/qa.py as a module: reuse its git helpers instead of copying them
    return qa


def _list(x) -> list:
    """Lua turns {} into {} and {"a"} into ["a"]; accept both (and a bare string)."""
    return [x] if isinstance(x, str) else list(x.values()) if isinstance(x, dict) else list(x or [])


# ---------------------------------------------------------------- registry: Lua data + scenarios + Python files

def from_lua(d: dict, source: str = "lua_content/qa.lua") -> R.Check:
    spec = {k: v for k, v in d.items() if k not in ("name", "cost", "watches", "needs", "tags", "what", "always", "ci", "solo", "cmd", "cmd_diff")}
    spec["argv"] = shlex.split(d["cmd"])
    spec["cmd"] = d["cmd"]
    if d.get("cmd_diff"):
        spec["argv_diff"] = shlex.split(d["cmd_diff"])
    for k in ("keep", "hide_zero", "pattern"):
        if k in spec:
            spec[k] = _list(spec[k])
    return R.Check(d["name"], d.get("cost", "medium"), tuple(_list(d.get("watches"))), tuple(_list(d.get("needs"))),
                   tuple(_list(d.get("tags"))), d.get("what", ""), spec=spec, always=bool(d.get("always", False)),
                   ci=bool(d.get("ci", True)), solo=bool(d.get("solo", False)), source=source)


def from_scenario(s: dict, base: dict) -> R.Check:
    """agent_play scenario (script + seed [+ expects]) -> check `play:NAME`; one Lua table entry = one gameplay test."""
    script = s["script"]
    for e in _list(s.get("expects")):
        script += f"; expect {e}"
    out = f"dev_probe_output/qa/check_play/{s['name']}"
    argv = ["python", "tools/agent_play.py", "--seed", str(s.get("seed", 1)), "--out", out, script]
    spec = {"argv": argv, "cmd": shlex.join(argv), "parse": "result_line", "keep": _list(base.get("keep")),
            "hide_zero": _list(base.get("hide_zero")), "timeout": base.get("timeout", 120)}
    return R.Check(f"play:{s['name']}", s.get("cost", base.get("cost", "low")),
                   tuple(_list(s.get("watches") or base.get("watches"))), (), tuple(_list(base.get("tags"))) + tuple(_list(s.get("tags"))),
                   s.get("what") or f"agent_play: {s['script']}", spec=spec, ci=bool(s.get("ci", True)),
                   source="lua_content/qa.lua scenarios")


def load_registry(cfg: dict | None = None, python_dir: Path | None = None) -> dict:
    cfg = cfg or qa_settings()
    reg: dict = {}

    def add(chk):
        if chk.name in reg:
            raise ValueError(f"duplicate check name {chk.name!r} ({reg[chk.name].source} and {chk.source})")
        reg[chk.name] = chk

    for d in _list(cfg.get("checks")):
        add(from_lua(d))
    for s in [*_list(cfg.get("scenarios")), *_list(cfg.get("plays"))]:
        add(from_scenario(s, cfg.get("scenario_check") or {}))
    for chk in R.load_python_checks(python_dir):
        add(chk)
    return reg


# ---------------------------------------------------------------- files, selection

def _glob_re(glob: str) -> str:
    """Translate a watch glob to a regex with `PurePosixPath.full_match` semantics (works on any Python): a `**`
    segment matches zero or more directories (as the LAST segment: everything below), `*` / `?` never cross a `/`."""
    parts, out = glob.split("/"), []
    for n, seg in enumerate(parts):
        last = n == len(parts) - 1
        if seg == "**":
            out.append(".+" if last else "(?:[^/]+/)*")          # the optional directories carry their own "/"
            continue
        out.append("".join("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in seg))
        out.append("" if last else "/")
    return "".join(out)


def gmatch(path: str, glob: str) -> bool:
    return re.fullmatch(_glob_re(glob), path) is not None


def watches_of(chk: R.Check) -> tuple:
    return chk.watches or ("**",)        # no declared inputs = the whole repo


def matches(chk: R.Check, files) -> bool:
    return any(gmatch(f, g) for f in files for g in watches_of(chk))


def repo_files() -> list:
    qa = _qa()
    out = qa.git("-c", "core.quotepath=false", "ls-files", "--cached", "--others", "--exclude-standard")
    return sorted(f for f in set(out.splitlines()) if f and (ROOT / f).is_file())


def affected_files(changed, graph) -> set:
    """Changed files + every python module that (transitively) imports a changed module."""
    _tests, _scripts, touched = qa_graph.impacted(graph, changed)
    return set(changed) | qa_graph.dependents(graph, touched)


def select(reg: dict, args, changed=(), graph=None):
    """-> (checks, by). by = name | tag | all | fast | diff."""
    every = list(reg.values())
    if args.name:
        pats = [p for p in args.name.split(",") if p]
        unknown = [p for p in pats if not any(fnmatch.fnmatch(c.name, p) for c in every)]
        if unknown:
            raise KeyError(f"unknown check {unknown[0]!r}; known: {' '.join(reg)}")
        chosen, by = [c for c in every if any(fnmatch.fnmatch(c.name, p) for p in pats)], "name"
    elif args.tag:
        chosen, by = [c for c in every if args.tag in c.tags], "tag"
    elif args.ci:
        chosen, by = [c for c in every if c.ci], "all"
    elif args.all or (args.fast and not args.changed):
        chosen, by = every, "all" if args.all else "fast"
    else:
        graph = graph if graph is not None else qa_graph.build()
        files = affected_files(list(changed), graph) if changed else set()
        chosen, by = [c for c in every if c.always or (files and matches(c, files))], "diff"
    if args.fast:
        chosen = [c for c in chosen if c.cost == "low"]
    return chosen, by


# ---------------------------------------------------------------- cache

class Hasher:
    """sha1 of file contents, remembered by (mtime, size) so unchanged files are not re-read."""

    def __init__(self, path: Path = HASH_FILE):
        self.path, self.dirty = path, False
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def digest(self, rel: str) -> str:
        p = ROOT / rel
        st = p.stat()
        hit = self.data.get(rel)
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
        h = hashlib.sha1(p.read_bytes()).hexdigest()
        self.data[rel], self.dirty = [st.st_mtime_ns, st.st_size, h], True
        return h

    def save(self):
        if self.dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")


def cache_key(chk: R.Check, argv, files, graph, hasher: Hasher) -> str:
    """sha256(check name + definition + used command + contents of watched files and their import closure + AI_EVOLVE_* env)."""
    watched = {f for f in files if any(gmatch(f, g) for g in watches_of(chk))}
    py = [f for f in watched if f.endswith(".py") and f in graph]
    inputs = sorted(watched | (qa_graph.reachable(graph, py) if py else set()))
    h = hashlib.sha256()
    h.update(chk.definition().encode())
    h.update(json.dumps(argv).encode())
    h.update(json.dumps(sorted((k, v) for k, v in os.environ.items() if k.startswith("AI_EVOLVE_"))).encode())
    h.update(f"py{sys.version_info[0]}.{sys.version_info[1]}".encode())
    for f in inputs:
        if (ROOT / f).is_file():
            h.update(f.encode())
            h.update(hasher.digest(f).encode())
    return h.hexdigest()


class ResultCache:
    def __init__(self, path: Path = CACHE_FILE, enabled: bool = True, max_age: float = 24 * 3600):
        self.path, self.enabled, self.max_age = path, enabled, max_age
        try:
            self.data = json.loads(path.read_text(encoding="utf-8")) if enabled else {}
        except (OSError, ValueError):
            self.data = {}

    def get(self, name: str, key: str):
        e = self.data.get(name)
        if not self.enabled or not e or e.get("key") != key or time.time() - e["ts"] > self.max_age:
            return None
        r = e["result"]
        return R.Result("cached", r["metrics"], [], r.get("repro"), 0.0, name, age=time.time() - e["ts"])

    def put(self, name: str, key: str, res: R.Result):
        if res.status == "ok":            # only clean passes are worth remembering; everything else reruns
            self.data[name] = {"key": key, "ts": time.time(), "result": res.to_dict()}

    def save(self):
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")


# ---------------------------------------------------------------- running

def display_ok() -> bool:
    return not sys.platform.startswith("linux") or bool(os.environ.get("DISPLAY") or shutil.which("xvfb-run"))


def skip_reason(chk: R.Check) -> str | None:
    for mod in chk.needs:
        if importlib.util.find_spec(mod) is None:
            return f"needs {mod}: python -m pip install {mod}"
    if chk.spec.get("requires") == "display" and not display_ok():
        return "no display: install xvfb (sudo apt-get install -y xvfb libgl1-mesa-dri) or set DISPLAY"
    return None


def argv_for(chk: R.Check, by: str) -> list:
    argv = list(chk.spec.get("argv_diff") if by == "diff" and chk.spec.get("argv_diff") else chk.spec.get("argv", []))
    if chk.spec.get("requires") == "display" and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        argv = ["xvfb-run", "-a", *argv]
    if argv and argv[0] == "python":
        argv[0] = sys.executable
    return argv


def _job(chk, by, cfg):
    spec = chk.spec
    return qa_pool.Job(chk.name, argv_for(chk, by), spec.get("env") or {}, float(spec.get("timeout") or cfg["timeout"]))


def _finish(chk: R.Check, res) -> R.Result:
    """qa_pool result -> Result of the check (parsed, named, with a default repro)."""
    text = res.stdout + ("\n" + res.stderr if res.stderr else "")
    out = R.interpret(text, res.rc, chk.spec, res.seconds, chk.name)
    if out.status in ("fail", "error", "warn") and not out.repro:
        out.repro = chk.spec.get("cmd")
    return out


def run_checks(todo, by: str, cfg: dict, runner=None, changed=()) -> dict:
    """Run checks (data checks in parallel through qa_pool; `solo` ones alone after them; Python checks last)."""
    runner = runner or qa_pool.run_many
    out: dict = {}
    data = [c for c in todo if c.fn is None]
    for wave in ([c for c in data if not c.solo], [c for c in data if c.solo]):
        if not wave:
            continue
        results = runner([_job(c, by, cfg) for c in wave], jobs=1 if wave[0].solo else cfg["jobs"])
        for c, res in zip(wave, results):
            out[c.name] = _finish(c, res)
    ctx = R.RunCtx(runner, changed)
    for c in (c for c in todo if c.fn is not None):
        t0 = time.perf_counter()
        try:
            res = c.fn(ctx)
        except Exception as exc:  # noqa: BLE001
            res = R.Result("error", {}, [f"{type(exc).__name__}: {exc}"])
        if not isinstance(res, R.Result):
            res = R.Result("error", {}, [f"check returned {type(res).__name__}, not Result"])
        res.name, res.dur = c.name, res.dur or time.perf_counter() - t0
        if res.status not in R.STATUSES:
            res = R.Result("error", {}, [f"invalid status {res.status!r}"], None, res.dur, c.name)
        out[c.name] = res
    return out


def execute(reg: dict, selected, by: str, cfg: dict, args, changed=(), runner=None, cache=None, hasher=None) -> list:
    """Skip / cache / run -> Results in selection order."""
    files = repo_files()
    graph = qa_graph.build()
    hasher = hasher or Hasher()
    cache = cache or ResultCache(enabled=not args.no_cache, max_age=cfg.get("cache_hours", 24) * 3600)
    results: dict = {}
    todo, keys = [], {}
    for c in selected:
        why = skip_reason(c)
        if why:
            results[c.name] = R.Result("skip", {}, [why], None, 0.0, c.name)
            continue
        keys[c.name] = cache_key(c, argv_for(c, by) if c.fn is None else [], files, graph, hasher)
        hit = cache.get(c.name, keys[c.name])
        if hit:
            results[c.name] = hit
        else:
            todo.append(c)
    hasher.save()
    fresh = run_checks(todo, by, cfg, runner, changed)
    for name, res in fresh.items():
        cache.put(name, keys[name], res)
        if by == "diff" and reg[name].spec.get("argv_diff"):
            res.variant = "diff"      # a subset run has its own history (no delta against a full run)
    results.update(fresh)
    cache.save()
    return [results[c.name] for c in selected]


# ---------------------------------------------------------------- CLI

def explain(chk: R.Check) -> list:
    spec = chk.spec
    how = spec.get("cmd") or f"python function {chk.fn.__module__}.{chk.fn.__name__}"
    lines = [f"{chk.name}  cost={chk.cost}  tags={','.join(chk.tags) or '-'}  always={str(chk.always).lower()}  ci={str(chk.ci).lower()}  source={chk.source}",
             f"what:    {chk.what or '-'}",
             f"watches: {' '.join(chk.watches) or '** (whole repo)'}   (selected by `qa.py check` when your diff touches one, or an importer of it)",
             f"runs:    {how}" + (f"   [diff mode: {spec['cmd_diff']}]" if spec.get("cmd_diff") else ""),
             f"parse:   {spec.get('parse', 'exit')}" + (f"  keep={','.join(spec['keep'])}" if spec.get("keep") else "")
             + (f"  soft_if=/{spec['soft_if']}/" if spec.get("soft_if") else "") + ("  soft=true" if spec.get("soft") else ""),
             f"alone:   python tools/qa.py check --name {chk.name} --no-cache",
             "add one: CLAUDE.md 'How to add a check' (tests/ file = auto | one table in lua_content/qa.lua | tools/qa_checks/x.py @check)"]
    return lines


def cmd_check(args) -> int:
    t0 = time.perf_counter()
    cfg_all = qa_settings()
    cfg = R.report_cfg(cfg_all)
    if args.max_lines:
        cfg["max_lines"] = args.max_lines
    try:
        reg = load_registry(cfg_all)
    except (ValueError, KeyError, RuntimeError) as exc:
        print(f"QA verdict=ERROR {exc}")
        return 2
    if not reg:
        print(f"QA verdict=ERROR no checks registered ({cfg_all.get('_source', '?')}: is a Lua backend installed? python tools/qa.py doctor)")
        return 2
    if args.list:
        w = max(len(n) for n in reg)
        for n, c in reg.items():
            print(f"{n:<{w}} {c.cost:<6} {','.join(c.tags) or '-':<12} {one(c.what)}")
        return 0
    if args.explain:
        if args.explain not in reg:
            print(f"unknown check {args.explain!r}; known: {' '.join(reg)}")
            return 2
        print("\n".join(explain(reg[args.explain])))
        return 0
    if args.ci:
        args.no_cache = True
    diff_mode = not (args.name or args.tag or args.ci or args.all or (args.fast and not args.changed))
    changed = _qa().changed_files(args.base) if diff_mode else []
    try:
        selected, by = select(reg, args, changed)
    except KeyError as exc:
        print(f"QA verdict=ERROR {exc.args[0]}")
        return 2
    results = execute(reg, selected, by, cfg, args, changed) if selected else []
    qa = _qa()
    meta = {"dur": time.perf_counter() - t0, "head": qa.git("rev-parse", "--short=7", "HEAD") or "?",
            "dirty": len(qa.git("status", "--porcelain").splitlines()), "selected": len(selected), "total": len(reg), "by": by}
    prev = R.load_prev()
    if args.json:
        print(R.to_json(results, meta))
    else:
        short, full = R.render(results, meta, prev, cfg)
        if not selected:
            note = f"(no check watches your {len(changed)} changed file(s); `qa.py check --all` runs all {len(reg)}, `--list` names them)"
            short, full = short + [note], full + [note]
        lines = R.budgeted(short, full, cfg, R.write_full)
        print("\n".join(lines))
        if args.ci and os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write("```\n" + "\n".join(lines) + "\n```\n")
    R.append_history(results, meta, cfg)
    return R.exit_code(results)


def one(text: str) -> str:
    return R.one_line(text, 90)


def register(sub):
    p = sub.add_parser("check", help="every verification, one command, one output format",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
    p.add_argument("--changed", action="store_true", help="checks affected by the diff (default)")
    p.add_argument("--all", action="store_true", help="every check")
    p.add_argument("--fast", action="store_true", help="only cost=low checks")
    p.add_argument("--name", help="comma-separated names/globs, e.g. golden,play:*")
    p.add_argument("--tag", help="checks with this tag")
    p.add_argument("--ci", action="store_true", help="what CI runs: all checks with ci=true, no cache")
    p.add_argument("--no-cache", action="store_true", help="ignore and do not update the result cache")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--explain", metavar="NAME", help="one screen about a check")
    p.add_argument("--list", action="store_true", help="one line per registered check")
    p.add_argument("--base", default=None, help="git ref for the diff (default origin/main)")
    p.add_argument("--max-lines", type=int, default=None, help="output line budget (qa.lua report.max_lines)")
    p.set_defaults(func=cmd_check)
