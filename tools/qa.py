#!/usr/bin/env python3
"""QA front door: одна команда вместо чтения документации и сырого вывода.

    python tools/qa.py brief                 # 10 строк: окружение, изменения, что гонять, последние прогоны
    python tools/qa.py doctor                # чего не хватает в окружении + точная команда починки
    python tools/qa.py affected [FILES]      # какие тесты/скрипты задевает правка (граф импортов)
    python tools/qa.py test [--changed]      # pytest шардами параллельно; печатает только НОВЫЕ падения
    python tools/qa.py test --update-known   # текущие падения -> tests/qa_known_failures.json
    python tools/qa.py golden [--record]     # детерминированные сценарии игры vs эталон (lua_content/qa.lua)
    python tools/qa.py sweep "SCRIPT"        # Monte Carlo по seed: распределения + bootstrap CI (Rust)
    python tools/qa.py fuzz [--runs N]       # случайные действия игрока + инварианты -> минимальный repro
    python tools/qa.py ctx FILE              # оглавление файла + связи + тесты (вместо чтения целиком)
    python tools/qa.py dead [--list]         # модули, которые никто не импортирует
    python tools/qa.py docs                  # какие .md устарели (ссылки на несуществующее/мёртвое)
    python tools/qa.py perf "SCRIPT"         # горячие функции игры (cProfile, fast-режим)

Прогоны игры идут параллельно подпроцессами (tools/qa_pool.py, asyncio),
статистика и обход графа - в Rust (rust_core.QaKernels), настройки - Lua
(lua_content/qa.lua). Детали всегда на диске (dev_probe_output/qa/), в
консоль - только вывод.
"""
import argparse
import ast
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_kernels as kernels  # noqa: E402
import qa_graph  # noqa: E402
from probe_settings import ROOT, qa_settings  # noqa: E402
from qa_pool import Job, default_jobs, python_job, run_many  # noqa: E402

QA_OUT = ROOT / "dev_probe_output" / "qa"
GOLDEN_FILE = ROOT / "tests" / "golden" / "agent_scenarios.json"
DURATIONS = ROOT / "dev_probe_output" / ".qa_cache" / "test_durations.json"
AGENT_PLAY = ROOT / "tools" / "agent_play.py"


def out_dir(kind):
    QA_OUT.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{kind}_{time.strftime('%H%M%S')}_", dir=QA_OUT))


def relpath(p):
    p = Path(p)
    return p.relative_to(ROOT).as_posix() if p.is_absolute() and p.is_relative_to(ROOT) else str(p)


# ---------------------------------------------------------------- git / changes

def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def changed_files(base=None):
    """Изменения рабочего дерева + коммиты ветки относительно base (merge-base)."""
    base = base or qa_settings()["tests"]["base_ref"]
    files = set()
    mb = git("merge-base", "HEAD", base)
    if mb:
        files |= set(git("diff", "--name-only", mb, "HEAD").splitlines())
    files |= set(git("diff", "--name-only", "HEAD").splitlines())
    files |= set(git("ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(f for f in files if f and (ROOT / f).exists())


# ---------------------------------------------------------------- doctor / brief

def cmd_doctor(args):
    checks = []

    def check(name, ok, fix=""):
        checks.append((ok, name, fix))

    check(f"python {platform.python_version()} (project needs 3.14)", sys.version_info >= (3, 14),
          "uv python install 3.14 && uv venv -p 3.14 .venv && uv pip install -r requirements-dev.txt")
    for mod, fix in (("panda3d", "uv pip install -r requirements.txt"), ("lupa", "uv pip install lupa"),
                     ("sqlalchemy", "uv pip install -r requirements.txt"), ("pytest", "uv pip install pytest"),
                     ("PIL", "uv pip install -r tools/requirements-dev.txt (optional: screenshots analysis)")):
        try:
            __import__(mod)
            check(mod, True)
        except ImportError:
            check(mod, False, fix)
    try:
        import lupa.lua55  # noqa: F401
        check("Lua 5.5 (lupa.lua55)", True)
    except ImportError:
        check("Lua 5.5 (lupa.lua55)", False, "uv pip install 'lupa>=2.8'")
    check(f"rust_core kernels ({kernels.BACKEND})", kernels.BACKEND == "rust" and kernels._rust_qa is not None,
          "uv pip install ./rust_core   (needs cargo; tools fall back to Python, ~13-170x slower)")
    check("cargo (to build rust_core)", shutil.which("cargo") is not None, "https://rustup.rs")
    if sys.platform.startswith("linux"):
        check("xvfb-run (screenshots without a display)", shutil.which("xvfb-run") is not None,
              "sudo apt-get install -y xvfb libgl1-mesa-dri")
    for ok, name, fix in checks:
        print(f"{'ok  ' if ok else 'MISS'} {name}" + ("" if ok or not fix else f"  ->  {fix}"))
    return 0 if all(ok for ok, _, _ in checks) else 1


def cmd_brief(args):
    graph = qa_graph.build()
    status = qa_graph.liveness(graph)
    dead = [p for p, s in status.items() if s == "dead"]
    changed = changed_files()
    tests, scripts, _ = qa_graph.impacted(graph, changed)
    known = load_known()
    print(f"env: python {platform.python_version()}, kernels={kernels.BACKEND}, "
          f"branch={git('rev-parse', '--abbrev-ref', 'HEAD') or '?'}")
    print(f"changes vs {qa_settings()['tests']['base_ref']}: {len(changed)} file(s)"
          + (f" -> {len(tests)} test file(s), scripts: {', '.join(Path(s).name for s in scripts) or '-'}" if changed else ""))
    print(f"known failing tests: {len(known)} (tests/qa_known_failures.json)")
    print(f"code: {len(graph)} modules, {len(dead)} dead ({sum(graph[p]['loc'] for p in dead)} LOC) - `qa.py dead`")
    try:
        import probe_db
        con = probe_db.connect()
        rows = con.execute("SELECT run_id, kind, status, kills, died FROM runs ORDER BY created DESC LIMIT 3").fetchall()
        for r in rows:
            print(f"run {r[0]}: {r[1]} {r[2]} kills={r[3]} died={r[4]}")
        con.close()
    except Exception:
        pass
    if GOLDEN_FILE.exists():
        print(f"golden scenarios: {len(json.loads(GOLDEN_FILE.read_text(encoding='utf-8'))['scenarios'])} recorded - `qa.py golden`")
    print("next: `qa.py test --changed` | `qa.py golden` | `qa.py fuzz` | CLAUDE.md for the tool table")
    return 0


# ---------------------------------------------------------------- graph views

def cmd_affected(args):
    graph = qa_graph.build()
    files = args.files or changed_files(args.base)
    tests, scripts, touched = qa_graph.impacted(graph, files)
    always = qa_settings()["tests"]["always"]
    print(f"changed: {len(files)} file(s); python modules touched: {len(touched)}")
    print(f"tests ({len(tests)}): {' '.join(tests) or '-'}")
    print(f"scripts: {' '.join(sorted(set(scripts) | set(always))) or '-'}")
    return 0


def cmd_dead(args):
    graph = qa_graph.build()
    status = qa_graph.liveness(graph)
    dead = sorted(p for p, s in status.items() if s == "dead")
    by_dir = defaultdict(lambda: [0, 0])
    for p in dead:
        d = p.rsplit("/", 1)[0] if "/" in p else "."
        by_dir[d][0] += 1
        by_dir[d][1] += graph[p]["loc"]
    total = sum(v[1] for v in by_dir.values())
    counts = Counter(status.values())
    print(f"modules: game={counts['game']} tool={counts['tool']} test={counts['test']} dead={counts['dead']} "
          f"({total} LOC nobody imports; entry points: main.py, tools/* scripts, tests)")
    for d, (n, loc) in sorted(by_dir.items(), key=lambda kv: -kv[1][1])[:args.top]:
        print(f"  {loc:6d} LOC  {n:3d} file(s)  {d}/")
    if args.list:
        for p in dead:
            print(f"  {p}  ({graph[p]['loc']} LOC) {graph[p]['doc'][:60]}")
    return 0


def outline(path):
    """Оглавление файла: классы/методы/функции с сигнатурами и 1-й строкой docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    lines = []

    def sig(fn):
        a = fn.args
        names = [x.arg for x in (*a.posonlyargs, *a.args)]
        if a.vararg:
            names.append("*" + a.vararg.arg)
        names += [x.arg for x in a.kwonlyargs]
        if a.kwarg:
            names.append("**" + a.kwarg.arg)
        return ", ".join(n for n in names if n not in ("self", "cls"))

    def doc1(node):
        d = (ast.get_docstring(node) or "").strip().splitlines()
        return f"  # {d[0][:70]}" if d else ""

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            lines.append(f"L{node.lineno} class {node.name}{doc1(node)}")
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for m in methods:
                if m.name.startswith("__") and m.name != "__init__":
                    continue
                lines.append(f"  L{m.lineno} .{m.name}({sig(m)}){doc1(m)}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(f"L{node.lineno} def {node.name}({sig(node)}){doc1(node)}")
        elif isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets):
            lines.append(f"L{node.lineno} {', '.join(t.id for t in node.targets)} = ...")
    return lines


def cmd_ctx(args):
    path = (ROOT / args.file).resolve()
    rel = relpath(path)
    graph = qa_graph.build()
    node = graph.get(rel)
    if node is None:
        print(f"{rel}: not a project .py file")
        return 2
    status = qa_graph.liveness(graph)[rel]
    tests, scripts, _ = qa_graph.impacted(graph, [rel])
    print(f"{rel}: {node['loc']} lines, liveness={status}" + (f" - {node['doc']}" if node["doc"] else ""))
    print(f"imports (project): {', '.join(node['imports']) or '-'}")
    importers = qa_graph.importers(graph, rel)
    print(f"imported by ({len(importers)}): {', '.join(importers[:12]) or '-'}" + (" ..." if len(importers) > 12 else ""))
    print(f"covered by tests: {', '.join(tests) or '- (none!)'}")
    if scripts:
        print(f"exercised by scripts: {', '.join(scripts)}")
    print("outline:")
    for line in outline(path)[:args.limit]:
        print(f"  {line}")
    return 0


# ---------------------------------------------------------------- docs staleness

_REF_RE = re.compile(r"(?<![\w/.-])((?:[\w-]+/)*[\w-]+\.(?:py|lua|rs|json|toml|md))\b")


def cmd_docs(args):
    graph = qa_graph.build()
    status = qa_graph.liveness(graph)
    names = defaultdict(list)
    for p in graph:
        names[Path(p).name].append(p)
    rows = []
    for md in sorted(ROOT.rglob("*.md")):
        if any(part in qa_graph.SKIP_DIRS for part in md.relative_to(ROOT).parts):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        refs = set(_REF_RE.findall(text))
        missing, dead = [], []
        for ref in refs:
            cands = [ROOT / ref, md.parent / ref]
            hit = next((c for c in cands if c.exists()), None)
            if hit is None and "/" not in ref and names.get(ref):
                hit = ROOT / names[ref][0]
            if hit is None:
                missing.append(ref)
            elif hit.suffix == ".py" and status.get(relpath(hit.resolve())) == "dead":
                dead.append(ref)
        n = len(refs)
        verdict = ("NO-REFS" if n == 0 else
                   "STALE" if len(missing) + len(dead) > max(1, n // 3) else
                   "CHECK" if missing or dead else "OK")
        rows.append((verdict, relpath(md), n, missing, dead))
    order = {"STALE": 0, "CHECK": 1, "NO-REFS": 2, "OK": 3}
    rows.sort(key=lambda r: (order[r[0]], r[1]))
    print(f"{len(rows)} markdown files: " + ", ".join(f"{k}={v}" for k, v in Counter(r[0] for r in rows).items()))
    for verdict, md, n, missing, dead in rows[:args.top]:
        extra = []
        if missing:
            extra.append(f"missing: {', '.join(sorted(missing)[:4])}{' ...' if len(missing) > 4 else ''}")
        if dead:
            extra.append(f"dead code: {', '.join(sorted(dead)[:3])}{' ...' if len(dead) > 3 else ''}")
        print(f"{verdict:7s} {md} ({n} refs) {'; '.join(extra)}")
    return 0


# ---------------------------------------------------------------- tests

def known_path():
    return ROOT / qa_settings()["tests"]["known_failures"]


def load_known():
    p = known_path()
    return json.loads(p.read_text(encoding="utf-8")).get("failures", {}) if p.exists() else {}


def _test_files(paths):
    out = []
    for p in paths:
        p = ROOT / p
        if p.is_dir():
            out += sorted(str(f.relative_to(ROOT).as_posix()) for f in p.rglob("test_*.py")
                          if "__pycache__" not in f.parts)
        elif p.exists():
            out.append(relpath(p))
    return out


def _shards(files, n):
    """LPT: самые долгие файлы (по прошлым прогонам) - по разным шардам."""
    durations = json.loads(DURATIONS.read_text(encoding="utf-8")) if DURATIONS.exists() else {}
    shards = [[0.0, []] for _ in range(max(1, min(n, len(files))))]
    for f in sorted(files, key=lambda f: -durations.get(f, 1.0)):
        shard = min(shards, key=lambda s: s[0])
        shard[0] += durations.get(f, 1.0)
        shard[1].append(f)
    return [s[1] for s in shards if s[1]]


def cmd_test(args):
    if args.changed:
        graph = qa_graph.build()
        files = qa_graph.impacted(graph, changed_files(args.base))[0]
        if not files:
            print("no test file is affected by the current changes (qa.py affected to see why)")
            return 0
    else:
        files = _test_files(args.paths or ["tests"])
    shards = _shards(files, args.jobs or default_jobs())
    run_dir = out_dir("test")
    env = {"PYTHONPATH": os.pathsep.join([str(ROOT / "tools"), os.environ.get("PYTHONPATH", "")])}
    jobs = []
    for i, shard in enumerate(shards):
        out = run_dir / f"shard{i}.jsonl"
        jobs.append(Job(f"shard{i}", [sys.executable, "-m", "pytest", "-q", "-p", "qa_pytest_plugin",
                                      "-p", "no:cacheprovider", "--rootdir", str(ROOT), "--continue-on-collection-errors", *shard,
                                      *args.pytest_args],
                        env={**env, "QA_PYTEST_OUT": str(out)}, timeout=args.timeout))
    start = time.perf_counter()
    results = run_many(jobs, len(jobs))
    wall = time.perf_counter() - start
    recs = []
    for i, r in enumerate(results):
        (run_dir / f"shard{i}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        f = run_dir / f"shard{i}.jsonl"
        if f.exists():
            recs += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
        elif r.rc not in (0, 1, 5):
            recs.append({"id": f"<shard {i}>", "outcome": "error", "s": 0, "msg": (r.stderr or r.stdout)[-300:]})

    per_file = defaultdict(float)
    for rec in recs:
        per_file[rec["id"].split("::")[0]] += rec.get("s", 0)
    old = json.loads(DURATIONS.read_text(encoding="utf-8")) if DURATIONS.exists() else {}
    DURATIONS.parent.mkdir(parents=True, exist_ok=True)
    DURATIONS.write_text(json.dumps({**old, **{k: round(v, 2) for k, v in per_file.items()}}), encoding="utf-8")

    counts = Counter(r["outcome"] for r in recs)
    bad = [r for r in recs if r["outcome"] in ("failed", "error", "collect_error")]
    known = load_known()
    new = [r for r in bad if r["id"] not in known]
    flaky = _rerun_for_flakes([r["id"] for r in new if r["outcome"] == "failed"], run_dir, env, args) \
        if new and args.reruns else {}
    fixed = [k for k in known if k not in {r["id"] for r in bad} and k.split("::")[0] in per_file]
    serial = sum(per_file.values())
    real_new = [r for r in new if r["id"] not in flaky]
    print(f"tests: {counts['passed']} passed, {counts['skipped']} skipped, "
          f"{len(bad)} failing ({len(real_new)} NEW, {len(flaky)} flaky, {len(bad) - len(new)} known) "
          f"in {wall:.1f}s on {len(shards)} shard(s) (serial ~{serial:.0f}s)")
    for r in new[:args.show]:
        tag = f"FLAKY (passed {flaky[r['id']]})" if r["id"] in flaky else f"NEW {r['outcome']}"
        print(f"  {tag}: {r['id']} - {r.get('msg', '')}" + (f" [{r['at']}]" if r.get("at") else ""))
    if len(new) > args.show:
        print(f"  ... {len(new) - args.show} more NEW in {relpath(run_dir)}/shard*.jsonl")
    if fixed:
        print(f"  now passing (remove from known): {', '.join(fixed[:5])}")
    slow = sorted(per_file.items(), key=lambda kv: -kv[1])[:3]
    if slow and serial > 10:
        print("  slowest: " + ", ".join(f"{Path(f).name} {s:.0f}s" for f, s in slow))
    if args.update_known:
        payload = {"_comment": "Pre-existing failures: qa.py test reports them as known, not NEW. "
                               "Update with `python tools/qa.py test --update-known`.",
                   "failures": {r["id"]: kernels.log_template(r.get("msg", "")) for r in bad if r["id"] not in flaky}}
        known_path().parent.mkdir(parents=True, exist_ok=True)
        known_path().write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  recorded {len(payload['failures'])} known failure(s) -> {relpath(known_path())}")
    return 1 if real_new else 0


def _rerun_for_flakes(ids, run_dir, env, args):
    """Перезапускает упавшие тесты `reruns` раз параллельно. -> {id: "k/n"} для
    тех, что хоть раз прошли: флейки, а не регрессия (не чинить вслепую)."""
    if not ids:
        return {}
    jobs = []
    for k in range(args.reruns):
        out = run_dir / f"rerun{k}.jsonl"
        jobs.append(Job(f"rerun{k}", [sys.executable, "-m", "pytest", "-q", "-p", "qa_pytest_plugin",
                                      "-p", "no:cacheprovider", "--rootdir", str(ROOT), *ids],
                        env={**env, "QA_PYTEST_OUT": str(out)}, timeout=args.timeout, meta={"out": out}))
    passes = Counter()
    for r in run_many(jobs, len(jobs)):
        f = r.meta["out"]
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec["outcome"] == "passed":
                    passes[rec["id"]] += 1
    return {i: f"{passes[i]}/{args.reruns} reruns" for i in ids if passes[i]}


# ---------------------------------------------------------------- game runs

def play_job(name, script, seed, out, extra=(), timeout=300):
    return python_job(name, AGENT_PLAY, "--seed", seed, "--out", out, *extra, script,
                      timeout=timeout, meta={"out": Path(out), "script": script, "seed": seed})


def read_session(result):
    f = result.meta["out"] / "session.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def trajectory(result):
    f = result.meta["out"] / "state.jsonl"
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    ts = [json.loads(line)["t"] for line in lines]
    return ts, [f"{h:016x}" for h in kernels.lines_fingerprint(lines)]


def cmd_golden(args):
    cfg = qa_settings()
    scenarios = [s for s in cfg["scenarios"] if not args.only or s["name"] in args.only]
    fields = cfg["golden_fields"]
    base = out_dir("golden")
    results = run_many([play_job(s["name"], s["script"], s["seed"], base / s["name"]) for s in scenarios],
                       args.jobs)
    current = {}
    for s, r in zip(scenarios, results):
        sess = read_session(r)
        if sess is None:
            print(f"{s['name']}: run failed (rc={r.rc}): {(r.stderr or r.stdout).strip()[-200:]}")
            continue
        ts, fp = trajectory(r)
        current[s["name"]] = {"seed": s["seed"], "script": s["script"], "status": sess["status"],
                              "final": {k: sess["final"].get(k) for k in fields},
                              "invariants": sorted({v["id"] for v in sess.get("invariants", [])}),
                              "t": ts, "fingerprints": fp}
    platform_tag = f"{platform.system()}-{platform.machine()}-py{platform.python_version()}"
    if args.record:
        GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_FILE.write_text(json.dumps({"_comment": "qa.py golden --record; scenarios in lua_content/qa.lua",
                                           "platform": platform_tag, "scenarios": current}, indent=1) + "\n",
                               encoding="utf-8")
        print(f"recorded {len(current)} scenario(s) -> {relpath(GOLDEN_FILE)} ({platform_tag})")
        for name, c in current.items():
            print(f"  {name}: {c['status']} " + " ".join(f"{k}={c['final'][k]}" for k in ("t", "hp", "kills", "lvl"))
                  + (f" invariants={c['invariants']}" if c["invariants"] else ""))
        return 0
    if not GOLDEN_FILE.exists():
        print("no golden file yet: run `python tools/qa.py golden --record` on a known-good tree")
        return 2
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    if golden.get("platform") != platform_tag:
        print(f"(note: golden recorded on {golden.get('platform')}, this is {platform_tag}; "
              "libm differences can shift float-sensitive trajectories)")
    changed = 0
    for name, cur in current.items():
        ref = golden["scenarios"].get(name)
        if ref is None:
            print(f"{name}: NEW scenario (not in golden)")
            changed += 1
            continue
        if ref["script"] != cur["script"] or ref["seed"] != cur["seed"]:
            print(f"{name}: scenario definition changed - re-record")
            changed += 1
            continue
        diffs = [f"{k} {ref['final'].get(k)}->{cur['final'].get(k)}" for k in fields
                 if ref["final"].get(k) != cur["final"].get(k)]
        if ref["status"] != cur["status"]:
            diffs.insert(0, f"status {ref['status']}->{cur['status']}")
        if ref["invariants"] != cur["invariants"]:
            diffs.append(f"invariants {ref['invariants']}->{cur['invariants']}")
        first = next((i for i, (a, b) in enumerate(zip(ref["fingerprints"], cur["fingerprints"])) if a != b), None)
        if first is None and len(ref["fingerprints"]) != len(cur["fingerprints"]):
            first = min(len(ref["fingerprints"]), len(cur["fingerprints"]))
        if diffs or first is not None:
            changed += 1
            where = f"; trajectory diverges at t={cur['t'][first] if first < len(cur['t']) else '?'}" if first is not None else ""
            print(f"{name}: CHANGED {', '.join(diffs) or 'final state equal'}{where}")
    same = len(current) - changed
    print(f"golden: {same}/{len(current)} scenario(s) identical" + ("" if not changed else
          " - intended gameplay change? re-record with --record"))
    return 1 if changed else 0


def _fmt(v):
    return "-" if v is None or (isinstance(v, float) and v != v) else f"{v:.4g}"


def cmd_sweep(args):
    cfg = qa_settings()["sweep"]
    seeds = list(range(args.first_seed, args.first_seed + (args.seeds or cfg["seeds"])))
    base = out_dir("sweep")
    start = time.perf_counter()
    results = run_many([play_job(f"s{s}", args.script, s, base / f"seed{s}") for s in seeds], args.jobs or cfg["jobs"])
    sessions = [(r, read_session(r)) for r in results]
    ok = [s for _, s in sessions if s]
    if not ok:
        print("all runs failed; first stderr: " + (results[0].stderr[-300:] if results else ""))
        return 2
    metrics = args.metrics or cfg["metrics"]
    print(f"sweep: {len(ok)}/{len(seeds)} runs of `{args.script}` in {time.perf_counter() - start:.1f}s "
          f"(seeds {seeds[0]}..{seeds[-1]}, stats backend={'rust' if kernels._rust_qa else 'python'})")
    print(f"{'metric':8s} {'mean':>9s} {'sd':>8s} {'p5':>8s} {'p50':>8s} {'p95':>8s}  95% CI of mean")
    for m in metrics:
        vals = [float(s["final"][m]) for s in ok if isinstance(s["final"].get(m), (int, float))]
        d = kernels.describe(vals, cfg["bootstrap_resamples"], 12345)
        print(f"{m:8s} {_fmt(d['mean']):>9s} {_fmt(d['sd']):>8s} {_fmt(d['p5']):>8s} {_fmt(d['p50']):>8s} "
              f"{_fmt(d['p95']):>8s}  [{_fmt(d['ci_lo'])}, {_fmt(d['ci_hi'])}]")
    died = sum(1 for s in ok if not s["final"]["alive"])
    fails = Counter(s["status"] for s in ok)
    exp_total = sum(len(s["expects"]) for s in ok)
    exp_pass = sum(1 for s in ok for e in s["expects"] if e["passed"])
    inv = Counter(v["id"] for s in ok for v in s.get("invariants", []))
    print(f"hero died in {died}/{len(ok)} runs ({100 * died / len(ok):.0f}%); status {dict(fails)}"
          + (f"; expects passed {exp_pass}/{exp_total}" if exp_total else ""))
    if inv:
        print("invariant violations: " + ", ".join(f"{k} in {v} run(s)" for k, v in inv.most_common()))
    worst = [s for s in ok if s["status"] != "OK"][:1]
    if worst:
        print(f"example failing run: {worst[0]['repro']}")
    print(f"details: {relpath(base)}/seed*/session.json (each run is also in probe_db)")
    return 0


# ---------------------------------------------------------------- fuzz + shrink

def _signatures(sess, result):
    """Отдельные сигнатуры багов прогона: каждое нарушение инварианта, fatal,
    первая ERROR-строка (шаблоном). Один прогон может дать несколько багов."""
    if sess is None:
        return {f"CRASH rc={result.rc}"}
    sigs = {v["id"] for v in sess.get("invariants", [])}
    if sess.get("fatal"):
        sigs.add("FATAL:" + kernels.log_template(sess["fatal"])[:60])
    for e in sess.get("errors", [])[:1]:
        sigs.add("ERROR:" + kernels.log_template(e.split(": ", 1)[-1])[:60])
    return sigs


def _run_scripts(scripts, seed, base, jobs, tag):
    jl = [play_job(f"{tag}{i}", "; ".join(cmds), seed, base / f"{tag}{i}", timeout=120)
          for i, cmds in enumerate(scripts)]
    return [(cmds, r, read_session(r)) for cmds, r in zip(scripts, run_many(jl, jobs))]


def shrink(cmds, seed, signature, base, jobs, max_rounds=40):
    """ddmin (Zeller): минимальный поднабор команд, дающий ту же сигнатуру бага.
    Кандидаты одного раунда проверяются параллельно."""
    n = 2
    rounds = 0
    while len(cmds) >= 2 and rounds < max_rounds:
        rounds += 1
        size = max(1, len(cmds) // n)
        chunks = [cmds[i:i + size] for i in range(0, len(cmds), size)]
        candidates = chunks + [[c for j, ch in enumerate(chunks) if j != i for c in ch] for i in range(len(chunks))]
        candidates = [c for c in candidates if c and len(c) < len(cmds)]
        found = None
        for cand, r, sess in _run_scripts(candidates, seed, base, jobs, f"r{rounds}_"):
            if r.rc != 0 and signature in _signatures(sess, r):
                found = cand
                break
        if found is not None:
            cmds = found
            n = 2 if found in chunks else max(n - 1, 2)
        elif n >= len(cmds):
            break
        else:
            n = min(len(cmds), n * 2)
    return cmds


def cmd_fuzz(args):
    cfg = qa_settings()["fuzz"]
    rng = random.Random(args.seed)
    actions = [a for a, _ in cfg["actions"]]
    weights = [w for _, w in cfg["actions"]]
    runs, length, jobs = args.runs or cfg["runs"], args.length or cfg["length"], args.jobs or cfg["jobs"]
    base = out_dir("fuzz")
    cases = [(rng.randrange(1, 10**6), rng.choices(actions, weights, k=length)) for _ in range(runs)]
    start = time.perf_counter()
    results = run_many([play_job(f"f{i}", "; ".join(cmds), seed, base / f"f{i}", timeout=120)
                        for i, (seed, cmds) in enumerate(cases)], jobs)
    groups = defaultdict(list)
    for (seed, cmds), r in zip(cases, results):
        if r.rc != 0:
            for sig in _signatures(read_session(r), r):
                groups[sig].append((seed, cmds))
    print(f"fuzz: {runs} random player-action scripts x {length} cmds in {time.perf_counter() - start:.1f}s "
          f"({jobs} parallel): {sum(1 for r in results if r.rc != 0)} failing, {len(groups)} distinct bug signature(s)")
    for sig, cases_ in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        seed, cmds = min(cases_, key=lambda c: len(c[1]))
        small = cmds if args.no_shrink else shrink(cmds, seed, sig, base / "shrink", jobs)
        script = "; ".join(small)
        name = re.sub(r"[^A-Za-z0-9]+", "_", sig)[:50].strip("_") or "bug"
        (base / f"{name}.play").write_text(f"# {sig}\n# seed {seed}\n" + "\n".join(small) + "\n", encoding="utf-8")
        print(f"BUG {sig}: {len(cases_)}/{runs} runs; minimal repro ({len(cmds)} -> {len(small)} cmds):")
        print(f"  python tools/agent_play.py --seed {seed} '{script}'")
    if not groups:
        print("no invariant violations, crashes or errors found")
    print(f"details: {relpath(base)}")
    return 1 if groups else 0


# ---------------------------------------------------------------- perf

def cmd_perf(args):
    import pstats
    run_dir = out_dir("perf")
    prof = run_dir / "agent_play.prof"
    r = subprocess.run([sys.executable, "-m", "cProfile", "-o", str(prof), str(AGENT_PLAY), "--seed", str(args.seed),
                        "--out", str(run_dir / "run"), "--no-invariants", args.script],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if not prof.exists():
        print(f"profiling failed: {r.stderr[-400:]}")
        return 2
    stats = pstats.Stats(str(prof))
    total = stats.total_tt
    rows = []
    for (file, line, func), (cc, nc, tt, ct, _) in stats.stats.items():
        f = file.replace("\\", "/")
        if "/src/" in f or f.endswith("/main.py"):
            rows.append((tt, ct, nc, f"{f.split('/src/')[-1] if '/src/' in f else 'main.py'}:{line} {func}"))
    game_tt = sum(r[0] for r in rows)
    result_line = next((line for line in r.stdout.splitlines() if line.startswith("RESULT")), "")
    sim = re.search(r"t=([\d.]+)s", result_line)
    print(f"profile of `{args.script}`: {total:.2f}s CPU total, game code (src/, main.py) {game_tt:.2f}s "
          f"({100 * game_tt / max(total, 1e-9):.0f}%)" + (f", {sim.group(1)}s of game time" if sim else ""))
    print(f"{'self s':>7s} {'cum s':>7s} {'calls':>8s}  function")
    for tt, ct, nc, name in sorted(rows, reverse=True)[:args.top]:
        print(f"{tt:7.3f} {ct:7.3f} {nc:8d}  src/{name}" if not name.startswith("main.py") else
              f"{tt:7.3f} {ct:7.3f} {nc:8d}  {name}")
    print(f"full profile: {relpath(prof)} (python -m pstats)")
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("\n\n", 1)[1])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("brief")
    p = sub.add_parser("affected")
    p.add_argument("files", nargs="*")
    p.add_argument("--base", default=None)
    p = sub.add_parser("test")
    p.add_argument("paths", nargs="*", help="test files/dirs (default: tests/)")
    p.add_argument("--changed", action="store_true", help="only tests affected by the current changes")
    p.add_argument("--base", default=None)
    p.add_argument("--jobs", type=int, default=None)
    p.add_argument("--show", type=int, default=10)
    p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--update-known", action="store_true")
    p.add_argument("--reruns", type=int, default=3, help="rerun NEW failures to detect flaky tests (0 = off)")
    p.add_argument("--pytest-args", nargs=argparse.REMAINDER, default=[])
    p = sub.add_parser("golden")
    p.add_argument("--record", action="store_true")
    p.add_argument("--only", nargs="*")
    p.add_argument("--jobs", type=int, default=None)
    p = sub.add_parser("sweep")
    p.add_argument("script")
    p.add_argument("--seeds", type=int, default=None)
    p.add_argument("--first-seed", type=int, default=1)
    p.add_argument("--jobs", type=int, default=None)
    p.add_argument("--metrics", nargs="*")
    p = sub.add_parser("fuzz")
    p.add_argument("--runs", type=int, default=None)
    p.add_argument("--length", type=int, default=None)
    p.add_argument("--jobs", type=int, default=None)
    p.add_argument("--seed", type=int, default=1, help="fuzzer RNG seed (the campaign itself is reproducible)")
    p.add_argument("--no-shrink", action="store_true")
    p = sub.add_parser("ctx")
    p.add_argument("file")
    p.add_argument("--limit", type=int, default=60)
    p = sub.add_parser("dead")
    p.add_argument("--list", action="store_true")
    p.add_argument("--top", type=int, default=12)
    p = sub.add_parser("docs")
    p.add_argument("--top", type=int, default=40)
    p = sub.add_parser("perf")
    p.add_argument("script")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--top", type=int, default=15)
    args = parser.parse_args(argv)
    return globals()[f"cmd_{args.cmd}"](args)


if __name__ == "__main__":
    sys.exit(main())
