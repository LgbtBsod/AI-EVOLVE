#!/usr/bin/env python3
"""quality_metrics - the code-quality RATCHET behind `qa.py check --name quality` and `qa.py quality` (shared library).

SOLID/DRY/SRP/SSOT violations cannot GROW: what exists today is the baseline (tests/quality_baseline.json: counts per metric, per file,
per function with CC >= 11); a NEW violation fails, an improvement is reported (`improved=N`) and ratcheted down with
`qa.py quality --update-baseline` (which refuses to raise any number unless `--force`).

Ready-made tools measure, nothing is re-implemented: ruff (blind except, unused code, too many args/branches, SIM, PERF...), radon
(cyclomatic complexity per function), vulture (dead code), import-linter (layering, `.importlinter`; its `ignore_imports` IS the
layering baseline). One ~20-line `ast` detector finds classes/UPPER_CONSTANTS defined in two live modules (DRY/SSOT).
Scope = live game modules (`qa_graph.liveness == 'game'`, recomputed each run). Thresholds, scope, rule selection, hints: `quality` in
lua_content/qa.lua (data); ruff's numeric limits: pyproject.toml.

    measure(cfg)            -> Measurement   (4 tool jobs in parallel through qa_pool + the ast detector; ~1-2 s)
    compare(base, m)        -> (worse, better) lists of Finding
    evaluate(cfg, m, base)  -> qa_report.Result   (ok | warn = improved | fail = worse | error)
    check()                 -> Result   (what `qa.py quality` and the `quality` check run; result_lines() = its RESULT-line form)
"""
from __future__ import annotations

import ast
import configparser
import fnmatch
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import qa_pool
import qa_report as R

ROOT = Path(__file__).resolve().parent.parent
BASELINE_VERSION = 1
RANKS = ((41, "F"), (31, "E"), (21, "D"), (11, "C"), (6, "B"), (1, "A"))       # radon rank <- lowest CC of the rank
LINT_IMPORTS = "import sys; from importlinter.cli import lint_imports_command as main; sys.exit(main())"
INSTALL = "python -m pip install -r requirements-dev.txt"


class ToolError(RuntimeError):
    """A tool (or the config) is broken: the check reports ERROR, never FAIL (fail = the code got worse)."""


def seq(x) -> list:
    """Lua turns {} into {} and {"a"} into ["a"]; accept both (and a bare string)."""
    return [x] if isinstance(x, str) else list(x.values()) if isinstance(x, dict) else list(x or [])


def load_cfg(settings: dict | None = None) -> dict:
    """The `quality` table of lua_content/qa.lua."""
    if settings is None:
        from probe_settings import qa_settings
        settings = qa_settings()
    cfg = settings.get("quality")
    if not cfg or not (cfg.get("ruff") or {}).get("select"):
        raise ToolError(f"no `quality` table in lua_content/qa.lua ({settings.get('_source', '?')}: is a Lua backend installed? "
                        "python tools/qa.py doctor)")
    return cfg


# ---------------------------------------------------------------- scope

def live_files(cfg: dict, graph: dict | None = None) -> list:
    """Live game modules: files whose qa_graph.liveness is `scope.liveness` (default 'game'), minus `scope.exclude` globs."""
    import qa_graph
    live = qa_graph.liveness(graph or qa_graph.build())
    scope = cfg.get("scope") or {}
    kind, skip = scope.get("liveness", "game"), seq(scope.get("exclude"))
    return sorted(p for p, k in live.items() if k == kind and not any(fnmatch.fnmatch(p, g) for g in skip))


def rel_path(name, root: Path = ROOT) -> str:
    """Tool output path (absolute or relative, either slash) -> repo-relative posix path."""
    s = str(name).replace("\\", "/")
    prefix = Path(root).resolve().as_posix().rstrip("/") + "/"
    if s.lower().startswith(prefix.lower()):
        s = s[len(prefix):]
    return s[2:] if s.startswith("./") else s


def chunks(files: list, limit: int) -> list:
    """Split a file list so one command line stays under `limit` chars (Windows: 32k)."""
    out, cur, size = [], [], 0
    for f in files:
        if cur and size + len(f) + 1 > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append(f)
        size += len(f) + 1
    return out + ([cur] if cur else [])


# ---------------------------------------------------------------- parsers (tool output -> plain data)

def parse_ruff(text: str, root: Path = ROOT) -> list:
    """`ruff check --output-format json` -> [{file, line, code, msg}]."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ToolError(f"ruff: output is not JSON ({exc}): {R.one_line(text, 80)}") from exc
    return [{"file": rel_path(d.get("filename", ""), root), "line": (d.get("location") or {}).get("row", 0),
             "code": d.get("code") or "syntax-error", "msg": d.get("message", "")} for d in data]


def _radon_walk(path: str, item: dict, parent: str, minimum: int, out: dict) -> None:
    cls = item.get("classname")
    qual = f"{parent}.{item['name']}" if parent else (f"{cls}.{item['name']}" if cls else item["name"])
    if item.get("type") != "class" and item.get("complexity", 0) >= minimum:
        key, n = f"{path}::{qual}", 2
        while key in out:                                   # same qualified name twice (property setter, overload): stable suffix
            key, n = f"{path}::{qual}#{n}", n + 1
        out[key] = {"cc": item["complexity"], "file": path, "name": qual, "line": item.get("lineno", 0)}
    for inner in [*item.get("closures", []), *item.get("methods", [])]:
        _radon_walk(path, inner, qual if item.get("type") != "class" else "", minimum, out)


def parse_radon(text: str, minimum: int, root: Path = ROOT) -> dict:
    """`radon cc -j` -> {"path::Class.func": {cc, file, name, line}} for every function with CC >= minimum."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ToolError(f"radon: output is not JSON ({exc}): {R.one_line(text, 80)}") from exc
    out: dict = {}
    for path, items in data.items():
        if isinstance(items, dict):                          # {"error": "..."}: a file radon could not parse
            raise ToolError(f"radon: {rel_path(path, root)}: {items.get('error', items)}")
        for item in items:
            _radon_walk(rel_path(path, root), item, "", minimum, out)
    return out


_VULTURE = re.compile(r"^(?P<file>.+?):(?P<line>\d+): (?P<msg>.+) \((?P<conf>\d+)% confidence\)\s*$", re.MULTILINE)


def parse_vulture(text: str, root: Path = ROOT) -> list:
    """vulture text (`path:line: unused variable 'x' (100% confidence)`, it has no JSON mode) -> [{file, line, msg, conf}]."""
    return [{"file": rel_path(m["file"], root), "line": int(m["line"]), "msg": m["msg"], "conf": int(m["conf"])}
            for m in _VULTURE.finditer(text)]


@dataclass
class LayerReport:
    new: list = field(default_factory=list)        # (importer, imported) edges NOT covered by `ignore_imports`: the contract is broken by them
    stale: list = field(default_factory=list)      # "a -> b" ignore entries that no longer match an import (fixed: delete the line)
    entries: int = 0                               # ignore_imports entries in the config (= the layering baseline)

    @property
    def total(self) -> int:                        # layers_broken: baselined edges that still exist + new ones
        return self.entries - len(self.stale) + len(self.new)


_LAYERS_SUMMARY = re.compile(r"Contracts: (\d+) kept, (\d+) broken")
_LAYERS_EDGE = re.compile(r"([\w.]+) -> ([\w.]+) \(l\.\d+\)")
_LAYERS_STALE = re.compile(r"No matches for ignored import ([\w.]+) -> ([\w.]+)")


def parse_layers(text: str, entries: list | None = None) -> LayerReport:
    """import-linter text -> LayerReport. Output wraps long lines, so whitespace is normalised first."""
    flat = " ".join(R.clean(text).split())
    if not _LAYERS_SUMMARY.search(flat):
        raise ToolError(f"import-linter: no contract summary: {R.one_line(text.strip()[-200:], 120)}")
    section = flat.split("Broken contracts", 1)[1] if "Broken contracts" in flat else ""
    new = sorted(dict.fromkeys(m.groups() for m in _LAYERS_EDGE.finditer(section)))
    stale = sorted({f"{a} -> {b.rstrip('.')}" for a, b in _LAYERS_STALE.findall(flat)})
    return LayerReport(new, stale, len(entries or []))


def ignore_entries(config: Path) -> list:
    """`ignore_imports` lines of every contract of an .importlinter (configparser: full-line `#` comments are skipped)."""
    if not config.is_file():
        raise ToolError(f"import-linter config {config.name} not found")
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(config, encoding="utf-8")
    lines = (ln for sec in cp.sections() if sec.startswith("importlinter:contract:")
             for ln in cp.get(sec, "ignore_imports", fallback="").splitlines())
    return sorted({" ".join(ln.split()) for ln in lines if ln.strip() and not ln.strip().startswith(("#", ";"))})


# ---------------------------------------------------------------- duplicated definitions (the only detector we own)

def find_dup_defs(root: Path, files: list, cfg: dict | None = None) -> dict:
    """{name: [files]} for top-level classes and UPPER_CONSTANTS defined in >= 2 modules (a TypeVar `T` is not a constant:
    const_pattern wants 2+ characters). `allow` (qa.lua) = names, or "Name@path", that are duplicated on purpose."""
    cfg = cfg or {}
    pattern = re.compile(cfg.get("const_pattern") or r"^[A-Z][A-Z0-9_]+$")
    allow = set(seq(cfg.get("allow")))
    where: dict = defaultdict(set)
    for f in files:
        try:
            tree = ast.parse((Path(root) / f).read_text(encoding="utf-8"), filename=f)
        except (OSError, SyntaxError, ValueError):
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name) and pattern.match(t.id)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and pattern.match(node.target.id):
                names = [node.target.id]
            else:
                continue
            for n in names:
                if n not in allow and f"{n}@{f}" not in allow:
                    where[n].add(f)
    return {n: sorted(fs) for n, fs in sorted(where.items()) if len(fs) > 1}


# ---------------------------------------------------------------- measurement

@dataclass
class Measurement:
    files: list = field(default_factory=list)          # the scope
    loc: int = 0
    diags: list = field(default_factory=list)          # ruff: {file, line, code, msg}
    unused: list = field(default_factory=list)         # vulture: {file, line, msg, conf}
    functions: dict = field(default_factory=dict)      # radon: "path::Class.func" -> {cc, file, name, line}
    dups: dict = field(default_factory=dict)           # name -> [files]
    layers: LayerReport = field(default_factory=LayerReport)
    cc_min: int = 11
    groups: dict = field(default_factory=dict)         # derived ruff metrics: name -> [codes]

    @property
    def rules(self) -> dict:
        out: dict = defaultdict(int)
        for d in self.diags:
            out[d["code"]] += 1
        return dict(sorted(out.items()))

    @property
    def per_file(self) -> dict:
        """{file: {rule code | 'vulture' | 'dup_defs': count}}: what "this file got worse" is compared on."""
        out: dict = defaultdict(lambda: defaultdict(int))
        for d in self.diags:
            out[d["file"]][d["code"]] += 1
        for u in self.unused:
            out[u["file"]]["vulture"] += 1
        for files in self.dups.values():
            for f in files:
                out[f]["dup_defs"] += 1
        return {f: dict(sorted(v.items())) for f, v in sorted(out.items())}

    @property
    def totals(self) -> dict:
        rules = self.rules
        cc = [f["cc"] for f in self.functions.values()]
        out = {"ruff": sum(rules.values())}
        out.update({g: sum(rules.get(c, 0) for c in codes) for g, codes in self.groups.items()})
        out.update({f"cc{self.cc_min}": len(cc), "cc_max": max(cc, default=0), "dup_defs": len(self.dups),
                    "layers_broken": self.layers.total, "vulture": len(self.unused)})
        return out

    def worst_function(self):
        return max(self.functions.values(), key=lambda f: (f["cc"], f["file"], f["name"]), default=None)


def build_jobs(cfg: dict, files: list) -> list:
    """One job per tool (per chunk of the file list): they run in parallel."""
    limit = int((cfg.get("budget") or {}).get("argv_chars", 24000))
    cc_min = int((cfg.get("cc") or {}).get("min", 11))
    rank = next(letter for low, letter in RANKS if cc_min >= low)
    select = ",".join(seq(cfg["ruff"]["select"]))
    conf = str((cfg.get("vulture") or {}).get("min_confidence", 80))
    layers_cfg = (cfg.get("layers") or {}).get("config", ".importlinter")
    jobs = []
    for i, part in enumerate(chunks(files, limit)):
        jobs += [qa_pool.Job(f"ruff#{i}", [sys.executable, "-m", "ruff", "check", "--select", select, "--output-format", "json",
                                           "--no-cache", *part]),
                 qa_pool.Job(f"radon#{i}", [sys.executable, "-m", "radon", "cc", "-n", rank, "-j", *part]),
                 qa_pool.Job(f"vulture#{i}", [sys.executable, "-m", "vulture", "--min-confidence", conf, *part])]
    jobs.append(qa_pool.Job("layers#0", [sys.executable, "-c", LINT_IMPORTS, "--config", layers_cfg, "--no-cache"]))
    return jobs


def _outputs(results) -> dict:
    by: dict = defaultdict(list)
    for r in results:
        by[r.name.split("#")[0]].append(r)
    return by


def _stdout(tool: str, results: list, ok_rc: tuple) -> list:
    out = []
    for r in results:
        if r.rc not in ok_rc:
            raise ToolError(f"{tool} exited {r.rc}: {R.one_line((r.stderr or r.stdout).strip()[-300:], 140)}  [{INSTALL}]")
        out.append(r.stdout)
    return out


def measure(cfg: dict, root: Path = ROOT, runner=None, files: list | None = None) -> Measurement:
    """Run the tools on the live scope. `runner(jobs, jobs=N)` defaults to qa_pool.run_many (tests pass a fake)."""
    files = live_files(cfg) if files is None else files
    if not files:
        raise ToolError("empty scope: no file has liveness 'game' (qa_graph cannot see main.py?)")
    cc_min = int((cfg.get("cc") or {}).get("min", 11))
    config = root / (cfg.get("layers") or {}).get("config", ".importlinter")
    entries = ignore_entries(config)
    by = _outputs((runner or qa_pool.run_many)(build_jobs(cfg, files), jobs=4))
    m = Measurement(files=list(files), cc_min=cc_min, groups={k: seq(v) for k, v in ((cfg["ruff"].get("groups")) or {}).items()})
    for text in _stdout("ruff", by["ruff"], (0, 1)):
        m.diags += parse_ruff(text, root)
    for text in _stdout("radon", by["radon"], (0,)):
        m.functions.update(parse_radon(text, cc_min, root))
    for text in _stdout("vulture", by["vulture"], (0, 3)):
        m.unused += parse_vulture(text, root)
    (layers,) = by["layers"]
    if layers.rc not in (0, 1):
        raise ToolError(f"import-linter exited {layers.rc}: {R.one_line(layers.stderr.strip()[-200:], 120)}  [{INSTALL}]")
    m.layers = parse_layers(layers.stdout + "\n" + layers.stderr, entries)
    m.dups = find_dup_defs(root, files, cfg.get("dup_defs"))
    m.loc = sum(_loc(root / f) for f in files)
    return m


def _loc(path: Path) -> int:
    """Lines of a file, counted like qa_graph (`qa.py brief`: ... LOC)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
    except OSError:
        return 0


# ---------------------------------------------------------------- baseline + ratchet

def to_baseline(m: Measurement) -> dict:
    return {"version": BASELINE_VERSION, "totals": m.totals, "rules": m.rules, "files": m.per_file,
            "functions": {k: v["cc"] for k, v in sorted(m.functions.items())}, "dup_defs": dict(sorted(m.dups.items()))}


def load_baseline(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def dump_baseline(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:              # LF on every OS (.gitattributes: eol=lf)
        fh.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class Finding:
    kind: str          # edge | function | dup | file | total | rule
    key: str
    base: int          # 0 = not in the baseline
    cur: int           # 0 = gone now

    def text(self) -> str:
        arrow = f"{self.base}->{self.cur}"
        if self.kind == "edge":
            return f"{'NEW' if self.cur else 'fixed'} import {self.key}"
        if self.kind == "function":
            return (f"NEW function CC {self.cur}: {self.key}" if not self.base else
                    f"CC {arrow}: {self.key}" if self.cur else f"CC {self.base}->below threshold: {self.key}")
        if self.kind == "dup":
            return f"NEW duplicate definition {self.key} ({self.cur} modules)" if self.cur else f"duplicate gone: {self.key}"
        return f"{self.key} {arrow}"

    def where(self, m: Measurement) -> str:
        """Line numbers for a file/rule finding (ruff tells which lines: the ones to look at)."""
        if self.kind == "file":
            path, _, code = self.key.partition(" ")
            lines = [d["line"] for d in m.diags if d["file"] == path and d["code"] == code]
            lines += [u["line"] for u in m.unused if u["file"] == path and code == "vulture"]
            return f":{','.join(map(str, sorted(lines)[:6]))}" if lines else ""
        return ""


_ORDER = {"edge": 0, "function": 1, "dup": 2, "file": 3, "total": 4, "rule": 5}


def compare(base: dict, m: Measurement) -> tuple:
    """(worse, better): every number that went up / down against the baseline, most actionable kinds first."""
    worse: list = []
    better: list = []

    def diff(kind, key, b, c):
        if c != b:
            (worse if c > b else better).append(Finding(kind, key, b, c))

    cur_total, base_total = m.totals, base.get("totals") or {}
    for k in {*cur_total, *base_total}:
        diff("total", k, base_total.get(k, 0), cur_total.get(k, 0))
    cur_rules, base_rules = m.rules, base.get("rules") or {}
    for k in {*cur_rules, *base_rules}:
        diff("rule", k, base_rules.get(k, 0), cur_rules.get(k, 0))
    cur_files, base_files = m.per_file, base.get("files") or {}
    for f in {*cur_files, *base_files}:
        cf, bf = cur_files.get(f, {}), base_files.get(f, {})
        for k in {*cf, *bf}:
            diff("file", f"{f} {k}", bf.get(k, 0), cf.get(k, 0))
    cur_fn, base_fn = {k: v["cc"] for k, v in m.functions.items()}, base.get("functions") or {}
    for k in {*cur_fn, *base_fn}:
        diff("function", k, base_fn.get(k, 0), cur_fn.get(k, 0))
    cur_dup, base_dup = m.dups, base.get("dup_defs") or {}
    for k in {*cur_dup, *base_dup}:
        if (k in cur_dup) != (k in base_dup):
            diff("dup", k, len(base_dup.get(k, ())), len(cur_dup.get(k, ())))
    for a, b in m.layers.new:
        worse.append(Finding("edge", f"{a} -> {b}", 0, 1))
    for entry in m.layers.stale:
        better.append(Finding("edge", entry, 1, 0))
    def order(f):
        return _ORDER[f.kind], -abs(f.cur - f.base), f.key
    return sorted(worse, key=order), sorted(better, key=order)


def _short(findings: list, n: int, m: Measurement | None = None) -> str:
    """One line: the most actionable findings (totals/rules are implied by them and only come last)."""
    parts = [f.text() + (f.where(m) if m else "") for f in findings if f.kind not in ("total", "rule")][:n]
    return "; ".join(parts) or "; ".join(f.text() for f in findings[:n])


def _totals(findings: list) -> str:
    return " ".join(f"{f.key} {f.base}->{f.cur}" for f in findings if f.kind == "total")


REPRO_WORST = "python tools/qa.py quality --worst 10"
REPRO_UPDATE = "python tools/qa.py quality --update-baseline"


def result_metrics(m: Measurement, n_improved: int = 0) -> dict:
    metrics = dict(m.totals)
    w = m.worst_function()
    if w:
        metrics["worst"] = f"{Path(w['file']).name}:{w['name']}:CC{w['cc']}"
    if n_improved:
        metrics["improved"] = n_improved
    return metrics


def evaluate(cfg: dict, m: Measurement, base: dict | None) -> R.Result:
    """Measurement + baseline -> Result: fail = something got worse, warn = only improvements (ratchet the baseline down), ok = same."""
    if base is None:
        return R.Result("error", result_metrics(m), [f"no baseline ({(cfg.get('baseline') or 'tests/quality_baseline.json')}): "
                                                      f"create it once with `{REPRO_UPDATE}`"], REPRO_UPDATE)
    worse, better = compare(base, m)
    shown = int((cfg.get("budget") or {}).get("findings", 6))
    if worse:
        detail = [_short(worse, shown, m), f"worse: {_totals(worse) or str(len(worse)) + ' finding(s)'}",
                  "fix the new ones (`qa.py quality --explain RULE`); never raise the baseline to hide them"]
        return R.Result("fail", result_metrics(m, len(better)), detail, REPRO_WORST)
    if better:
        stale = [f.key for f in better if f.kind == "edge"]
        detail = [f"improved: {_totals(better) or _short(better, shown)}; ratchet down with `{REPRO_UPDATE}`"]
        if stale:
            detail.append(f"stale ignore_imports in .importlinter (delete these lines): {'; '.join(stale)}")
        return R.Result("warn", result_metrics(m, len(better)), detail, REPRO_UPDATE)
    return R.Result("ok", result_metrics(m))


def update_baseline(path: Path, m: Measurement, force: bool = False) -> tuple:
    """(ok, lines). Writes the baseline when nothing got worse (or with force); otherwise refuses and lists what is worse."""
    old = load_baseline(path)
    worse, better = compare(old, m) if old is not None else ([], [])
    if worse and not force:
        return False, [f"quality: refusing to RAISE the baseline ({len(worse)} number(s) got worse); fix them, or --force if intended:",
                       *[f"  {f.text()}{f.where(m)}" for f in worse[:12]]]
    dump_baseline(path, to_baseline(m))
    rel = rel_path(path)
    if old is None:
        return True, [f"quality: baseline created: {rel} ({len(m.files)} files, {len(m.functions)} functions with CC>={m.cc_min})"]
    lines = [f"quality: baseline updated: {rel} ({len(better)} lowered" + (f", {len(worse)} RAISED (--force)" if worse else "") + ")"]
    lines += [f"  {f.text()}" for f in worse[:12]]
    stale = [f.key for f in better if f.kind == "edge"]
    if stale:
        lines.append("  delete from .importlinter ignore_imports: " + "; ".join(stale))
    return True, lines


def baseline_path(cfg: dict, root: Path = ROOT) -> Path:
    return root / (cfg.get("baseline") or "tests/quality_baseline.json")


def result_lines(res: R.Result) -> list:
    """Machine form of a Result for the Lua-declared check (`parse = "result_line"`): detail lines, `repro:`, one RESULT line.
    An error prints no RESULT line, so the runner reports ERROR (the check itself broke) instead of FAIL (the code got worse)."""
    lines = list(res.detail)
    if res.repro:
        lines.append(f"repro: {res.repro}")
    if res.status != "error":
        lines.append(f"RESULT status={res.status.upper()} " + " ".join(f"{k}={R.fmt_num(v)}" for k, v in res.metrics.items()))
    return lines


def check(runner=None, root: Path = ROOT, settings: dict | None = None) -> R.Result:
    """What the `quality` check runs: measure, compare with the baseline, one Result."""
    try:
        cfg = load_cfg(settings)
        return evaluate(cfg, measure(cfg, root, runner), load_baseline(baseline_path(cfg, root)))
    except ToolError as exc:
        return R.Result("error", {}, [str(exc)], "python tools/qa.py doctor")


# ---------------------------------------------------------------- reports: --worst, --explain

def cc_hint(cfg: dict, cc: int) -> str:
    rows = sorted((h for h in seq(cfg.get("cc_hints")) if isinstance(h, dict)), key=lambda h: -h.get("over", 0))
    return next((h["hint"] for h in rows if cc > h.get("over", 0)), "")


def file_rows(cfg: dict, m: Measurement) -> list:
    """[(total violations, file, 'BLE001:9 F401:3', hint)] worst first; a complex function counts as one violation."""
    per_fn: dict = defaultdict(int)
    for f in m.functions.values():
        per_fn[f["file"]] += 1
    srp = cfg.get("srp_module") or {}
    rules = cfg.get("rules") or {}
    rows = []
    for f in {*m.per_file, *per_fn}:
        counts = dict(m.per_file.get(f, {}))
        if per_fn.get(f):
            counts[f"cc{m.cc_min}"] = per_fn[f]
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        hint = (srp.get("hint", "").format(n=per_fn[f]) if srp and per_fn.get(f, 0) >= srp.get("cc11", 3)
                else (rules.get(top[0][0]) or {}).get("hint", ""))
        rows.append((sum(counts.values()), f, " ".join(f"{k}:{v}" for k, v in top[:4]), hint))
    return sorted(rows, key=lambda r: (-r[0], r[1]))


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[:max(1, width - 3)] + "..."


def worst_lines(cfg: dict, m: Measurement, n: int, width: int = 150) -> list:
    """Top offenders in one screen: functions by CC, files by total violations, each with a one-line hint from qa.lua."""
    fns = sorted(m.functions.values(), key=lambda f: (-f["cc"], f["file"], f["name"]))
    rows = file_rows(cfg, m)
    lines = [f"quality worst {n}: scope={len(m.files)} live modules / {m.loc} LOC | " + " ".join(f"{k}={v}" for k, v in m.totals.items()),
             f"functions by cyclomatic complexity ({min(n, len(fns))} of {len(fns)} with CC>={m.cc_min}):"]
    lines += [_clip(f"  CC {f['cc']:>3}  {f['file']}:{f['line']} {f['name']}  | {cc_hint(cfg, f['cc'])}", width) for f in fns[:n]]
    lines.append(f"files by violations ({min(n, len(rows))} of {len(rows)}):")
    lines += [_clip(f"  {total:>3}  {f}  {mix}" + (f"  | {hint}" if hint else ""), width) for total, f, mix, hint in rows[:n]]
    if m.dups:
        lines.append(_clip("duplicated definitions: " + " ".join(f"{k}({len(v)})" for k, v in m.dups.items()), width))
    if m.layers.total:
        lines.append(f"layers_broken={m.layers.total}: baselined edges in .importlinter ignore_imports"
                     + (f", {len(m.layers.new)} NEW" if m.layers.new else ""))
    return lines


def explain_lines(cfg: dict, name: str, base: dict | None = None) -> list:
    """One screen about a rule/metric: what it means, the usual fix, the baseline numbers; unknown ruff codes fall back to `ruff rule`."""
    rules = cfg.get("rules") or {}
    key = next((k for k in rules if k.lower() == name.lower()), None)
    if key is None and name.lower() in ("layers", "layers_broken", "import-linter"):
        key = "layers_broken"
    if key is None:
        proc = subprocess.run([sys.executable, "-m", "ruff", "rule", name.upper()], capture_output=True, text=True, cwd=ROOT)
        if proc.returncode != 0:
            return [f"unknown rule {name!r}; described in qa.lua: {' '.join(sorted(rules))}"]
        return [f"{name.upper()}: not in quality.rules (qa.lua), ruff says:", *proc.stdout.splitlines()[:22]]
    info = rules[key]
    lines = [f"{key}  {info.get('hint', '')}", f"what: {info.get('what', '-')}", f"fix:  {info.get('fix', '-')}"]
    if base:
        total = (base.get("totals") or {}).get(key, (base.get("rules") or {}).get(key))
        files = sorted(((bf.get(key, 0), f) for f, bf in (base.get("files") or {}).items() if bf.get(key)), reverse=True)
        if total is not None:
            lines.append(f"baseline: {total}" + (f" in {len(files)} files, worst {', '.join(f'{f} ({n})' for n, f in files[:3])}" if files else ""))
    lines.append(f"more: python -m ruff rule {key}" if re.fullmatch(r"[A-Z]+\d+", key) else "look:  python tools/qa.py quality --worst 10")
    return lines
