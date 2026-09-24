"""tools/qa_report.py + qa.py check / changed: one output format, budget, deltas, cache, registry, selection.

Nothing here runs a real check: commands go through a fake qa_pool runner. One test at the end runs the real
`lua` check through the CLI (0.4 s) to prove the whole path.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import lua_bridge  # noqa: E402
import qa  # noqa: E402
import qa_graph  # noqa: E402
import qa_pool  # noqa: E402
import qa_report as R  # noqa: E402
from probe_settings import qa_settings  # noqa: E402
from qa_plugins import changed as CH  # noqa: E402
from qa_plugins import check as C  # noqa: E402

needs_lua = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

CFG = {**R.DEFAULT_CFG, "delta": {"dealt": {"pct": 10, "abs": 5}, "kills": {"pct": 0, "abs": 1}}}
META = {"dur": 1.5, "head": "abc1234", "dirty": 3, "selected": 3, "total": 12, "by": "diff"}
ALLOWED = re.compile(r"^(?:(?:ok|FAIL|warn|ERROR|skip|cached) +\S+.*|QA verdict=.*|  \| .*|\(\+\d+ more lines: .+\))$")


def res(status="ok", name="x", metrics=None, detail=None, repro=None, dur=0.5, **kw):
    return R.Result(status, metrics or {}, detail or [], repro, dur, name, **kw)


# ---------------------------------------------------------------- the one line format

def test_line_format_for_every_status():
    lines = {
        "ok": R.format_line(res("ok", "combat_smoke", {"passed": 53, "failed": 0}, dur=0.6), 12, cfg=CFG),
        "fail": R.format_line(res("fail", "golden", {"identical": 1}, ["CHANGED hp 1->2"], "python tools/qa.py golden", 5.5), 12, cfg=CFG),
        "warn": R.format_line(res("warn", "dead", {"dead": 120}, ["dead=120 > limit 100"], "cmd"), 12, cfg=CFG),
        "error": R.format_line(res("error", "boot", {}, ["no RESULT line"], "cmd"), 12, cfg=CFG),
        "skip": R.format_line(res("skip", "boot", {}, ["no display"], "cmd"), 12, cfg=CFG),
        "cached": R.format_line(res("cached", "tests", {"passed": 9}, [], None, 0.0, age=240), 12, cfg=CFG),
    }
    assert lines["ok"] == "ok     combat_smoke passed=53 failed=0 dur=0.6s"
    assert lines["fail"].startswith("FAIL   golden       identical=1 dur=5.5s | CHANGED hp 1->2 | repro: python tools/qa.py golden")
    assert lines["cached"] == "cached tests        passed=9 dur=0.0s age=4m"
    assert lines["skip"].endswith("| no display") and "repro" not in lines["skip"]      # repro only for fail/error/warn
    assert lines["error"].startswith("ERROR ") and lines["warn"].startswith("warn   ")
    for line in lines.values():
        assert R.LINE_RE.match(line), line
    # status column is padded: the name always starts at the same offset
    assert {ln.index(name) for ln, name in [(lines["ok"], "combat_smoke"), (lines["fail"], "golden"), (lines["cached"], "tests")]} == {7}


def test_number_and_duration_formatting():
    assert R.fmt_num(178.0) == "178" and R.fmt_num(484.2) == "484.2" and R.fmt_num(0.33333) == "0.333"
    assert R.fmt_num(12345.678) == "12346" and R.fmt_num("108.5/140.0") == "108.5/140.0" and R.fmt_num("a b") == "a_b"
    assert R.fmt_dur(1.234) == "1.2s" and R.fmt_dur(42.4) == "42s" and R.fmt_dur(125) == "2m05s"
    assert R.fmt_age(30) == "30s" and R.fmt_age(600) == "10m" and R.fmt_age(7200) == "2h" and R.fmt_age(4 * 86400) == "4d"


def test_header_line_and_verdict():
    rs = [res("ok", "a"), res("fail", "b"), res("warn", "c"), res("cached", "d"), res("skip", "e")]
    head = R.header_line(rs, META)
    assert R.HEADER_RE.match(head)
    assert head == ("QA verdict=FAIL checks=5 ok=1 fail=1 warn=1 cached=1 skip=1 dur=1.5s head=abc1234 dirty=3 "
                    "selected=3/12 by=diff")
    assert R.verdict([res("ok"), res("warn"), res("skip"), res("cached")]) == "OK"
    assert R.verdict([res("ok"), res("error")]) == "FAIL"
    assert R.header_line([res("ok")], META).startswith("QA verdict=OK checks=1 ok=1 fail=0 warn=0 cached=0 dur=")


def test_exit_codes():
    assert R.exit_code([res("ok"), res("warn"), res("cached"), res("skip")]) == 0
    assert R.exit_code([res("ok"), res("fail")]) == 1
    assert R.exit_code([res("error")]) == 2
    assert R.exit_code([res("fail"), res("error")]) == 1


def test_json_form_is_machine_readable():
    data = json.loads(R.to_json([res("ok", "a", {"n": 1}), res("fail", "b", detail=["boom"], repro="cmd")], META))
    assert data["verdict"] == "FAIL" and data["counts"] == {"ok": 1, "fail": 1}
    assert [c["name"] for c in data["checks"]] == ["a", "b"] and data["checks"][1]["repro"] == "cmd"
    assert data["meta"]["by"] == "diff"


# ---------------------------------------------------------------- deltas

def test_deltas_only_above_thresholds():
    prev = {"dealt": 620.2, "kills": 10, "hp": 100.0, "note": "x", "t": 5, "zero": 0}
    cur = {"dealt": 484.2, "kills": 6, "hp": 101.0, "note": "y", "t": 50, "zero": 3}
    d = R.delta_tokens(cur, prev, CFG)
    assert d["dealt"] == "(-22%)" and d["kills"] == "(-40%)"
    assert "hp" not in d                      # +1%: below delta_pct
    assert "note" not in d and "t" not in d   # non numeric / ignored metric
    assert d["zero"] == "(+3)"                # previous value 0: absolute change
    assert R.delta_tokens({"dealt": 620.0}, {"dealt": 620.2}, CFG) == {}      # no change worth printing
    assert R.delta_tokens({"dealt": 500}, {"dealt": 496}, CFG) == {}          # +0.8% and < abs 5
    assert R.delta_tokens({"a": 1}, None, CFG) == {}


def test_delta_is_appended_in_the_rendered_line():
    short, _ = R.render([res("ok", "play:swarm", {"kills": 6, "dealt": 484.2})], META,
                        {"play:swarm": {"kills": 10, "dealt": 620.2}}, CFG)
    assert "dealt=484.2(-22%)" in short[1] and "kills=6(-40%)" in short[1]
    short, _ = R.render([res("cached", "play:swarm", {"kills": 6, "dealt": 484.2}, age=5)], META,
                        {"play:swarm": {"kills": 10, "dealt": 620.2}}, CFG)
    assert "(-" not in short[1]                                # a cached replay is not a new measurement


def test_history_roundtrip_and_previous_values(tmp_path):
    hist = tmp_path / "h" / "history.jsonl"
    R.append_history([res("ok", "a", {"n": 1}), res("cached", "b", {"n": 9}), res("skip", "c")], META, CFG, hist)
    R.append_history([res("ok", "a", {"n": 2}), res("fail", "d", {"n": 5})], META, CFG, hist)
    prev = R.load_prev(path=hist)
    assert prev == {"a": {"n": 2}, "d": {"n": 5}}         # cached/skipped runs are not runs; the latest wins
    assert R.load_prev(path=tmp_path / "missing.jsonl") == {}
    cfg = {**CFG, "history_keep": 5}
    for i in range(20):
        R.append_history([res("ok", "a", {"n": i})], META, cfg, hist)
    assert len(hist.read_text(encoding="utf-8").splitlines()) <= 10 and R.load_prev(path=hist)["a"] == {"n": 19}


def test_variant_keeps_subset_runs_out_of_the_full_history(tmp_path):
    hist = tmp_path / "history.jsonl"
    R.append_history([res("ok", "tests", {"passed": 831})], META, CFG, hist)
    diff_run = res("ok", "tests", {"passed": 107}, variant="diff")
    R.append_history([diff_run], META, CFG, hist)
    prev = R.load_prev(path=hist)
    assert prev["tests"] == {"passed": 831} and prev["tests@diff"] == {"passed": 107}
    short, _ = R.render([diff_run], META, prev, CFG)
    assert "passed=107 " in short[1]                       # no bogus "(-87%)" against the full run


# ---------------------------------------------------------------- budget

def test_budget_overflow_goes_to_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "QA_OUT", tmp_path / "qa")
    results = [res("ok", f"ok{i}", {"n": i}) for i in range(45)]
    results += [res("fail", f"bad{i}", {"n": 0}, [f"detail {i}.{j}" for j in range(8)], "cmd") for i in range(3)]
    short, full = R.render(results, META, None, CFG)
    lines = R.budgeted(short, full, CFG, R.write_full)
    assert len(lines) <= CFG["max_lines"] == 30
    assert lines[0].startswith("QA verdict=FAIL checks=48")
    assert lines[1].startswith("FAIL") and "bad0" in lines[1]              # worst first, so good news is what overflows
    assert [ln for ln in lines if ln.startswith("FAIL")].__len__() == 3
    m = re.fullmatch(r"\(\+(\d+) more lines: (.+)\)", lines[-1])
    assert m, lines[-1]
    dumped = Path(m.group(2)).read_text(encoding="utf-8").splitlines()
    assert len(dumped) == len(full) and int(m.group(1)) == len(full) - (len(lines) - 1)
    assert "  | detail 0.7" in dumped                                       # the file has every detail line
    assert all(ALLOWED.match(ln) for ln in lines), [ln for ln in lines if not ALLOWED.match(ln)]


def test_failed_check_prints_at_most_three_detail_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "QA_OUT", tmp_path / "qa")
    short, full = R.render([res("fail", "g", {}, [f"d{i}" for i in range(6)], "cmd")], META, None, CFG)
    assert short[1].count("| d0") == 1 and short[2:] == ["  | d1", "  | d2"]   # first inline + 2 = 3 detail lines
    lines = R.budgeted(short, full, CFG, R.write_full)
    assert len(lines) == 5 and re.fullmatch(r"\(\+3 more lines: .+\)", lines[-1])   # d3..d5 in the file


def test_no_pointer_line_when_everything_fits():
    short, full = R.render([res("ok", "a"), res("warn", "b", {}, ["x"])], META, None, CFG)
    assert R.budgeted(short, full, CFG, None) == short


# ---------------------------------------------------------------- parsers for the formats the repo already prints

AGENT_PLAY = ("HP \u2588\u2587\n"
              "RESULT status=OK t=2.47s hp=108.5/140.0 alive=True lvl=1 kills=3 dealt=178.0 taken=13.8 expects=1/1 errors=0 invariants=0 wall=0.08s\n"
              "details: dev_probe_output/play_x/session.json | python tools/probe_db.py stats play_x\n")
AGENT_PLAY_FAIL = ("FAIL expect kills>=99 at t=3.4 (kills=3)\n"
                   "RESULT status=FAIL t=3.4s hp=104.9/140.0 alive=True lvl=1 kills=3 dealt=182.4 taken=18.2 expects=0/1 errors=0 invariants=0 wall=0.08s\n"
                   "repro: python tools/agent_play.py --seed 1 --render none 'spawn enemy x3; expect kills>=99'\n")
QA_TEST = "tests: 831 passed, 0 skipped, 1 failing (0 NEW, 0 flaky, 1 known) in 3.5s on 8 shard(s) (serial ~20s)\n"


def parse(text, rc=0, **spec):
    return R.interpret(text, rc, spec, 1.0, "n")


def test_parser_result_line():
    r = parse(AGENT_PLAY, parse="result_line", keep=["kills", "dealt", "hp", "expects", "errors"], hide_zero=["errors"])
    assert r.status == "ok" and r.metrics == {"kills": 3, "dealt": 178.0, "hp": "108.5/140.0", "expects": "1/1"}
    r = parse(AGENT_PLAY_FAIL, 1, parse="result_line", keep=["kills"], cmd="python tools/agent_play.py")
    assert r.status == "fail" and r.detail[0] == "FAIL expect kills>=99 at t=3.4 (kills=3)"
    assert r.repro.startswith("python tools/agent_play.py --seed 1")            # the tool's own repro line wins
    # determinism prints a bare word after RESULT and no status=
    r = parse("RESULT determinism pairs=4 diverged=0 classes=1 first_frame=- t=- channel=none\n", parse="result_line")
    assert r.status == "ok" and r.metrics["pairs"] == 4 and r.metrics["first_frame"] == "-"
    r = parse("boom\nTraceback\n", 1, parse="result_line")
    assert r.status == "error" and r.detail[0] == "no RESULT line in output"


def test_parser_pytest_both_formats():
    r = parse(QA_TEST, parse="pytest", hide_zero=["skipped", "flaky"])
    assert r.status == "ok" and r.metrics == {"passed": 831, "new": 0, "known": 1}
    bad = "tests: 10 passed, 0 skipped, 2 failing (2 NEW, 0 flaky, 0 known) in 1.0s on 1 shard(s)\n  NEW failed: tests/a.py::t - assert 1 == 2 [tests/a.py:5]\n"
    r = parse(bad, 1, parse="pytest")
    assert r.status == "fail" and r.metrics["new"] == 2 and r.detail == ["NEW failed: tests/a.py::t - assert 1 == 2 [tests/a.py:5]"]
    raw = "..F\n=== short test summary info ===\nFAILED tests/a.py::t - assert 1 == 2\n1 failed, 2 passed, 1 skipped in 0.10s\n"
    r = parse(raw, 1, parse="pytest")
    assert r.status == "fail" and r.metrics == {"passed": 2, "failed": 1, "skipped": 1, "error": 0}
    assert r.detail == ["tests/a.py::t - assert 1 == 2"]
    r = parse("292 passed in 1.85s\n", parse="pytest")
    assert r.status == "ok" and r.metrics["passed"] == 292
    assert parse("no test file is affected by the current changes\n", parse="pytest").metrics == {"passed": 0}
    assert parse("garbage\n", parse="pytest").status == "error"


def test_parser_counts_combat_smoke():
    r = parse("OK   a\nFAIL b\n\n52 passed, 1 failed: ['b']\nStatus: FAILED\n", 1, parse="counts")
    assert r.status == "fail" and r.metrics == {"passed": 52, "failed": 1} and r.detail == ["FAIL b"]
    assert parse("53 passed, 0 failed\nStatus: OK\n", parse="counts").status == "ok"


def test_parser_regex_with_several_patterns_and_no_match():
    text = "79 markdown files: STALE=20, CHECK=20, NO-REFS=28, OK=11\n"
    r = parse(text, parse="regex", pattern=[r"(?P<md>\d+) markdown files", r"STALE=(?P<stale>\d+)", r"NOPE=(?P<x>\d+)"])
    assert r.status == "ok" and r.metrics == {"md": 79, "stale": 20}
    r = parse("something else\n", parse="regex", pattern=r"lua: (?P<n>\d+)/")
    assert r.status == "warn" and "did not match" in r.detail[0]      # the tool's format drifted: not a silent pass


def test_return_code_soft_failures_limits_and_timeouts():
    assert parse("all fine\n", 3, parse="exit").status == "fail"
    assert parse("golden: 1/5 scenario(s) identical\nCHANGED a\n", 1, parse="regex", pattern=r"golden: (?P<same>\d+)/", detail="CHANGED").detail == ["CHANGED a"]
    text = "(note: golden recorded on Linux-x86_64-py3.14.7, this is Windows-AMD64-py3.14.5; libm differs)\ngolden: 1/5 scenario(s) identical\n"
    r = parse(text, 1, parse="regex", pattern=r"golden: (?P<same>\d+)/", soft_if=r"golden recorded on [\w.-]+, this is [\w.-]+")
    assert r.status == "warn" and r.detail[0] == "soft: golden recorded on Linux-x86_64-py3.14.7, this is Windows-AMD64-py3.14.5"
    r = parse("RESULT pairs=2 diverged=1\n", 1, parse="result_line", soft=True, soft_note="known xfail")
    assert r.status == "warn" and r.detail[0] == "soft: known xfail"
    r = parse("dead=120 (900 LOC x\n", parse="regex", pattern=r"dead=(?P<dead>\d+)", warn_over={"dead": 100})
    assert r.status == "warn" and r.detail == ["dead=120 > limit 100"]
    r = parse("started\n[qa_pool] timeout after 60.0s", 124, parse="pytest")
    assert r.status == "error" and "timeout after 60.0s" in r.detail[0]
    r = parse("\x1b[31mFAIL\x1b[0m x\n52 passed, 1 failed\n", 1, parse="counts")
    assert r.detail == ["FAIL x"]                                          # ANSI stripped


# ---------------------------------------------------------------- registry: Lua data, scenarios, Python files

@needs_lua
def test_lua_declared_checks_and_scenarios_are_registered():
    cfg = qa_settings()
    reg = C.load_registry(cfg)
    expected = {"combat_smoke", "tests", "golden", "lua", "items", "pathfinding", "boot_smoke", "determinism-quick",
                "dead-code", "docs-stale"}
    assert expected <= set(reg), expected - set(reg)
    scenarios = [s["name"] for s in [*cfg["scenarios"], *cfg["plays"]]]
    assert {f"play:{n}" for n in scenarios} <= set(reg) and len(scenarios) >= 6      # every scenario is a check
    t = reg["tests"]
    assert t.spec["argv_diff"][-1] == "--changed" and t.solo and not t.ci
    assert reg["boot_smoke"].spec["requires"] == "display" and reg["determinism-quick"].spec["soft"] is True
    for chk in reg.values():
        assert chk.cost in ("low", "medium", "high") and chk.what, chk.name


def test_from_lua_spec_and_scenario_conversion():
    chk = C.from_lua({"name": "x", "cmd": 'python tools/qa.py determinism "wait 5" --pairs 2', "cmd_diff": "python t.py --changed",
                      "parse": "regex", "pattern": "a(?P<n>\\d)", "watches": ["src/**"], "cost": "low", "tags": ["a", "b"],
                      "keep": {}, "always": True, "ci": False})
    assert chk.spec["argv"] == ["python", "tools/qa.py", "determinism", "wait 5", "--pairs", "2"]
    assert chk.spec["argv_diff"] == ["python", "t.py", "--changed"] and chk.spec["pattern"] == ["a(?P<n>\\d)"]
    assert chk.watches == ("src/**",) and chk.tags == ("a", "b") and chk.always and not chk.ci and chk.spec["keep"] == []
    sc = C.from_scenario({"name": "boss", "seed": 7, "script": "spawn boss; wait 30", "expects": ["alive", "kills>=1"]},
                         {"keep": ["kills"], "watches": ["src/**"], "tags": ["play"]})
    assert sc.name == "play:boss" and sc.watches == ("src/**",) and sc.tags == ("play",)
    assert sc.spec["argv"][:4] == ["python", "tools/agent_play.py", "--seed", "7"]
    assert sc.spec["argv"][-1] == "spawn boss; wait 30; expect alive; expect kills>=1"
    assert sc.spec["parse"] == "result_line" and sc.spec["keep"] == ["kills"]


def test_duplicate_check_names_are_refused():
    cfg = {"checks": [{"name": "a", "cmd": "python x"}], "scenarios": [], "plays": []}
    assert set(C.load_registry(cfg, tmp_dir_without_checks())) == {"a"}
    cfg["checks"].append({"name": "a", "cmd": "python y"})
    with pytest.raises(ValueError, match="duplicate check name 'a'"):
        C.load_registry(cfg, tmp_dir_without_checks())


def tmp_dir_without_checks():
    return ROOT / "tests" / "__no_such_qa_checks_dir__"


PY_CHECK = '''
from qa_report import check, Result

@check("demo", cost="low", watches=["src/x/**"], needs=["json"], tags=["t1", "t2"])
def demo(ctx):
    """Demo check: counts things."""
    return ctx.result(ctx.run("python tools/x.py"), parse="counts")

@check("pure")
def pure(ctx):
    return Result("warn", {"n": 3}, ["careful"])

@check("bad")
def bad(ctx):
    return "not a Result"
'''


def fake_pool(out="5 passed, 0 failed\n", rc=0, seen=None):
    def runner(job_list, jobs=None):
        if seen is not None:
            seen.append([j.name for j in job_list])
        return [qa_pool.Result(j.name, rc, out, "", 0.4, j.meta) for j in job_list]
    return runner


def test_python_checks_are_discovered_from_a_directory(tmp_path):
    (tmp_path / "demo.py").write_text(PY_CHECK, encoding="utf-8")
    (tmp_path / "broken.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    (tmp_path / "_private.py").write_text("raise SystemExit\n", encoding="utf-8")
    found = {c.name: c for c in R.load_python_checks(tmp_path)}
    assert {"demo", "pure", "bad", "broken"} == set(found)                       # _private.py is ignored
    d = found["demo"]
    assert (d.cost, d.watches, d.needs, d.tags, d.what) == ("low", ("src/x/**",), ("json",), ("t1", "t2"), "Demo check: counts things.")
    out = C.run_checks(list(found.values()), "all", CFG, fake_pool())
    assert out["demo"].status == "ok" and out["demo"].metrics == {"passed": 5, "failed": 0} and out["demo"].name == "demo"
    assert out["pure"].status == "warn" and out["pure"].detail == ["careful"]
    assert out["bad"].status == "error" and "not Result" in out["bad"].detail[0]
    assert out["broken"].status == "error" and "boom" in out["broken"].detail[0]      # a broken file breaks only itself
    assert R.load_python_checks(tmp_path / "nope") == []
    bad = C.run_checks([found["demo"]], "all", CFG, fake_pool("FAIL x\n1 passed, 1 failed\n", rc=1))["demo"]
    assert bad.status == "fail" and bad.detail == ["FAIL x"] and bad.repro == "python tools/x.py"      # the command is the default repro


def test_missing_module_or_display_is_a_skip_not_a_failure():
    assert "needs no_such_module_xyz" in C.skip_reason(R.Check("n", needs=("no_such_module_xyz",)))
    assert C.skip_reason(R.Check("n", needs=("json",))) is None
    chk = R.Check("boot", spec={"requires": "display", "argv": ["python", "x"]})
    if not C.display_ok():
        assert "no display" in C.skip_reason(chk)
    else:
        assert C.skip_reason(chk) is None


# ---------------------------------------------------------------- selection

def fake_registry():
    mk = lambda n, w, **k: R.Check(n, k.pop("cost", "medium"), tuple(w), spec={"argv": ["python", n], "cmd": f"python {n}"}, **k)  # noqa: E731
    return {c.name: c for c in [
        mk("smoke", ["src/**/*.py"], cost="low", always=True, tags=("unit",)),
        mk("lua", ["lua_content/**/*.lua"], cost="low", tags=("lua",)),
        mk("agent", ["tools/agent_play.py"], tags=("play",)),
        mk("play:a", ["src/**/*.py"], cost="low", tags=("play",)),
        mk("play:b", ["src/**/*.py"], tags=("play",)),
        mk("noci", ["docs/**"], ci=False),
        mk("wide", []),
    ]}


def ns(**kw):
    base = dict(name=None, tag=None, ci=False, all=False, fast=False, changed=False)
    return argparse.Namespace(**{**base, **kw})


def fake_graph():
    node = lambda imports, script=False: {"imports": imports, "script": script, "doc": "", "loc": 1}  # noqa: E731
    return {"tools/qa_pool.py": node([]), "tools/agent_play.py": node(["tools/qa_pool.py"], True),
            "tests/test_qa_tools.py": node(["tools/qa_pool.py"])}


def names(sel):
    return [c.name for c in sel[0]]


def test_selection_by_diff_uses_watches_and_the_import_graph():
    reg, g = fake_registry(), fake_graph()
    assert names(C.select(reg, ns(), ["lua_content/x.lua"], g)) == ["smoke", "lua", "wide"]        # always + watched (+ empty watches = all)
    assert names(C.select(reg, ns(), ["src/x.py"], g)) == ["smoke", "play:a", "play:b", "wide"]
    assert names(C.select(reg, ns(), ["tools/qa_pool.py"], g)) == ["smoke", "agent", "wide"]       # `agent` imports the changed module
    assert names(C.select(reg, ns(), [], g)) == ["smoke"]                                          # nothing changed: only `always`
    assert C.select(reg, ns(), ["src/x.py"], g)[1] == "diff"


def test_selection_modes():
    reg, g = fake_registry(), fake_graph()
    assert names(C.select(reg, ns(all=True), [], g)) == list(reg) and C.select(reg, ns(all=True), [], g)[1] == "all"
    assert names(C.select(reg, ns(fast=True), [], g)) == ["smoke", "lua", "play:a"] and C.select(reg, ns(fast=True), [], g)[1] == "fast"
    assert names(C.select(reg, ns(name="lua,play:*"), [], g)) == ["lua", "play:a", "play:b"] and C.select(reg, ns(name="lua"), [], g)[1] == "name"
    assert names(C.select(reg, ns(tag="play"), [], g)) == ["agent", "play:a", "play:b"] and C.select(reg, ns(tag="play"), [], g)[1] == "tag"
    assert "noci" not in names(C.select(reg, ns(ci=True), [], g)) and C.select(reg, ns(ci=True), [], g)[1] == "all"
    assert names(C.select(reg, ns(changed=True, fast=True), ["src/x.py"], g)) == ["smoke", "play:a"]   # --changed --fast
    with pytest.raises(KeyError, match="unknown check 'nope'"):
        C.select(reg, ns(name="lua,nope"), [], g)


def test_glob_matching_semantics():
    assert C.gmatch("src/a/b.py", "src/**/*.py") and C.gmatch("src/a.py", "src/**/*.py") and not C.gmatch("tools/a.py", "src/**/*.py")
    assert C.gmatch("x.py", "**/*.py") and C.gmatch("lua_content/qa.lua", "lua_content/**") and not C.gmatch("tools/a/b.py", "tools/*.py")


def test_selection_on_the_real_registry():
    reg, graph = C.load_registry(), qa_graph.build()

    def sel(*files):
        return {c.name for c in C.select(reg, ns(), list(files), graph)[0]}
    assert sel() == {"combat_smoke"}
    assert {"pathfinding", "tests", "combat_smoke"} <= sel("src/gameplay/pathfinding.py")
    assert {"lua", "items", "tests"} <= sel("lua_content/items/game_items.lua")
    assert {"play:melee_three", "play:swarm", "golden"} <= sel("tools/agent_play.py")
    assert {"tests"} <= sel("tests/test_brand_new_file.py")                                   # a new test file is picked up automatically
    assert {"combat_smoke", "docs-stale"} <= sel("docs/LANGUAGE_SPLIT.md") and "pathfinding" not in sel("docs/LANGUAGE_SPLIT.md")


# ---------------------------------------------------------------- result cache

def test_cache_key_follows_watched_file_content(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("unwatched\n", encoding="utf-8")
    chk = R.Check("c", watches=("*.py",), spec={"argv": ["python", "x"]})
    h = C.Hasher(tmp_path / "h.json")

    def key(c=chk, argv=("python", "x"), files=("a.py", "b.txt")):
        return C.cache_key(c, list(argv), list(files), {}, h)
    k1 = key()
    assert key() == k1
    (tmp_path / "b.txt").write_text("changed but not watched\n", encoding="utf-8")
    assert key() == k1
    (tmp_path / "a.py").write_text("x = 22\n", encoding="utf-8")
    k2 = key()
    assert k2 != k1
    (tmp_path / "a.py").write_text("x = 33\n", encoding="utf-8")
    os.utime(tmp_path / "a.py", ns=(1, 2 ** 40))                     # same size, only mtime moved: still detected
    assert key() != k2
    assert key(argv=("python", "y")) != key()                        # a different command is a different check
    assert key(R.Check("c", watches=("*.py",), spec={"argv": ["python", "x"], "parse": "counts"})) != key()   # definition changed
    monkeypatch.setenv("AI_EVOLVE_HERO_MIND", "off")
    k_env = key()
    monkeypatch.setenv("AI_EVOLVE_HERO_MIND", "on")
    assert key() != k_env                                             # AI_EVOLVE_* knobs are part of the key


def test_cache_key_follows_the_import_closure(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    (tmp_path / "tool.py").write_text("import lib\n", encoding="utf-8")
    (tmp_path / "lib.py").write_text("v = 1\n", encoding="utf-8")
    graph = {"tool.py": {"imports": ["lib.py"], "script": True, "doc": "", "loc": 1}, "lib.py": {"imports": [], "script": False, "doc": "", "loc": 1}}
    chk = R.Check("c", watches=("tool.py",), spec={"argv": ["python", "tool.py"]})
    h = C.Hasher(tmp_path / "h.json")
    k1 = C.cache_key(chk, ["python"], ["tool.py", "lib.py"], graph, h)
    (tmp_path / "lib.py").write_text("v = 222\n", encoding="utf-8")            # not in `watches`, but imported by a watched file
    assert C.cache_key(chk, ["python"], ["tool.py", "lib.py"], graph, h) != k1


def test_second_run_is_cached_until_a_watched_file_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "repo_files", lambda: ["a.txt"])
    monkeypatch.setattr(C.qa_graph, "build", lambda *a, **k: {})
    (tmp_path / "a.txt").write_text("v1\n", encoding="utf-8")
    reg = {"demo": R.Check("demo", watches=("a.txt",), spec={"argv": ["python", "x"], "parse": "counts", "cmd": "python x"})}
    seen = []

    def run(**kw):
        cache = C.ResultCache(tmp_path / "cache.json", **kw)
        return C.execute(reg, [reg["demo"]], "all", CFG, argparse.Namespace(no_cache=False), runner=fake_pool(seen=seen),
                         cache=cache, hasher=C.Hasher(tmp_path / "h.json"))[0]
    first = run()
    assert first.status == "ok" and len(seen) == 1
    second = run()
    assert second.status == "cached" and second.metrics == first.metrics and second.age is not None and len(seen) == 1
    (tmp_path / "a.txt").write_text("v2 is longer\n", encoding="utf-8")
    third = run()
    assert third.status == "ok" and len(seen) == 2                                # edit a watched file -> miss
    assert run(enabled=False).status == "ok" and len(seen) == 3                   # --no-cache always runs
    assert run(max_age=0).status == "ok" and len(seen) == 4                       # expired entries are ignored


def test_only_clean_passes_are_cached(tmp_path):
    cache = C.ResultCache(tmp_path / "c.json")
    cache.put("bad", "k", res("fail", "bad", {"n": 1}))
    cache.put("warn", "k", res("warn", "warn"))
    cache.put("good", "k", res("ok", "good", {"n": 2}))
    cache.save()
    again = C.ResultCache(tmp_path / "c.json")
    assert again.get("bad", "k") is None and again.get("warn", "k") is None
    hit = again.get("good", "k")
    assert hit.status == "cached" and hit.metrics == {"n": 2} and again.get("good", "other-key") is None


# ---------------------------------------------------------------- the contract: every registered check prints ONE format

CANNED = {
    "golden": "golden: 5/5 scenario(s) identical\n",
    "lua": "lua: 19/19 files ok with rust, lupa\n",
    "items": "items: 26/26 pass\n",
    "dead-code": "modules: game=74 tool=77 test=99 dead=73 (18532 LOC nobody imports; entry points: main.py)\n",
    "docs-stale": "79 markdown files: STALE=20, CHECK=20, NO-REFS=28, OK=11\n",
}
CANNED_OK = {"result_line": AGENT_PLAY, "pytest": QA_TEST + "292 passed in 1.85s\n", "counts": "53 passed, 0 failed\nStatus: OK\n"}
CANNED_BAD = "\n".join(["FAIL first problem", "FAIL second problem", "FAIL third", "FAILED tests/a.py::t - assert 1 == 2", "E   assert boom",
                        "ERROR fourth", "Traceback (most recent call last):", "RESULT status=FAIL kills=0 dealt=0.0",
                        "tests: 1 passed, 0 skipped, 3 failing (3 NEW, 0 flaky, 0 known) in 1.0s on 1 shard(s)",
                        "1 passed, 4 failed", "3 failed, 1 passed in 0.10s", "golden: 0/5 scenario(s) identical",
                        "repro: python tools/agent_play.py --seed 1 'wait 5'"]) + "\n"


def canned_runner(reg, ok=True):
    def runner(job_list, jobs=None):
        out = []
        for j in job_list:
            spec = reg[j.name].spec
            text = CANNED.get(j.name) or CANNED_OK[spec["parse"]] if ok else CANNED_BAD
            out.append(qa_pool.Result(j.name, 0 if ok else 1, text, "", 0.25, {}))
        return out
    return runner


@needs_lua
@pytest.mark.parametrize("ok", [True, False], ids=["passing", "failing"])
def test_every_registered_check_prints_the_one_format(ok, tmp_path, monkeypatch):
    monkeypatch.setattr(R, "QA_OUT", tmp_path / "qa")
    monkeypatch.setattr(C, "repo_files", lambda: [])
    monkeypatch.setattr(C.qa_graph, "build", lambda *a, **k: {})
    cfg = R.report_cfg(qa_settings())
    reg = C.load_registry()
    results = C.execute(reg, list(reg.values()), "all", cfg, argparse.Namespace(no_cache=True), runner=canned_runner(reg, ok),
                        cache=C.ResultCache(tmp_path / "c.json", enabled=False), hasher=C.Hasher(tmp_path / "h.json"))
    assert [r.name for r in results] == list(reg) and len(results) >= 16
    assert {r.status for r in results} <= set(R.STATUSES)
    meta = {**META, "selected": len(results), "total": len(reg), "by": "all"}
    short, full = R.render(results, meta, None, cfg)
    lines = R.budgeted(short, full, cfg, R.write_full)
    assert len(lines) <= cfg["max_lines"]
    assert R.HEADER_RE.match(lines[0])
    for line in lines:
        assert ALLOWED.match(line), line
    body = [ln for ln in lines if R.LINE_RE.match(ln)]
    assert all(R.format_line(r, 0, cfg=cfg).split()[0] == R.WORD[r.status] for r in results)
    if ok:
        assert lines[0].startswith("QA verdict=OK") and R.exit_code(results) == 0
        assert all(ln.split()[0] in ("ok", "skip", "warn") for ln in body)
    else:
        assert lines[0].startswith("QA verdict=FAIL") and R.exit_code(results) == 1
        assert all(ln.split()[0] in ("FAIL", "warn", "ERROR", "skip") for ln in body)
        assert lines[-1].startswith("(+") and Path(re.search(r": (.+)\)$", lines[-1]).group(1)).is_file()   # overflow -> file


# ---------------------------------------------------------------- CLI

def test_explain_is_one_screen():
    reg = fake_registry()
    reg["smoke"].what = "smoke things"
    lines = C.explain(reg["smoke"])
    assert len(lines) <= 10 and lines[0].startswith("smoke  cost=low") and "watches: src/**/*.py" in lines[2]
    assert any("python tools/qa.py check --name smoke --no-cache" in ln for ln in lines) and "How to add a check" in lines[-1]


@needs_lua
def test_cli_list_explain_and_unknown_names(capsys):
    assert qa.main(["check", "--list"]) == 0
    listing = capsys.readouterr().out.splitlines()
    assert len(listing) >= 16 and any(ln.startswith("combat_smoke") for ln in listing)
    assert qa.main(["check", "--explain", "golden"]) == 0
    out = capsys.readouterr().out
    assert "parse:   regex" in out and "alone:   python tools/qa.py check --name golden --no-cache" in out
    assert qa.main(["check", "--explain", "nope"]) == 2 and "unknown check" in capsys.readouterr().out
    assert qa.main(["check", "--name", "nope"]) == 2 and capsys.readouterr().out.startswith("QA verdict=ERROR unknown check 'nope'")


@needs_lua
def test_cli_runs_a_real_check_end_to_end(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(R, "HISTORY", tmp_path / "history.jsonl")
    code = qa.main(["check", "--name", "lua", "--no-cache"])
    out = capsys.readouterr().out.splitlines()
    assert code == 0 and R.HEADER_RE.match(out[0]) and "selected=1/" in out[0] and "by=name" in out[0]
    assert re.match(r"ok +lua +loaded=\d+ files=\d+ dur=[\d.]+s$", out[1]), out[1]
    assert len(out) == 2
    code = qa.main(["check", "--name", "lua", "--no-cache", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0 and data["checks"][0]["name"] == "lua" and data["verdict"] == "OK"
    assert (tmp_path / "history.jsonl").read_text(encoding="utf-8").count('"name":"lua"') == 2


# ---------------------------------------------------------------- qa.py changed

PY_OLD = "def keep(a):\n    return a\n\ndef gone():\n    pass\n\nclass K:\n    def m(self):\n        return 1\n    def n(self):\n        return 2\n"
PY_NEW = "def keep(a):\n    return a + 1\n\ndef fresh():\n    pass\n\nclass K:\n    def m(self):\n        return 1\n    def n(self):\n        return 3\n"


def test_symbol_diff_python_rust_lua():
    a, r, c = CH.sym_diff(CH.py_symbols(PY_OLD), CH.py_symbols(PY_NEW))
    assert (a, r, c) == (["fresh"], ["gone"], ["K.n", "keep"])
    assert CH.py_symbols("def broken(:\n") is None
    rs_old = "pub struct A { x: i32 }\nimpl A {\n    pub fn one(&self) -> i32 { 1 }\n    fn two(&self) {}\n}\nfn free() {}\n"
    rs_new = "pub struct A { x: i32 }\nimpl A {\n    pub fn one(&self) -> i32 { 2 }\n    fn two(&self) {}\n    pub fn three(&self) {}\n}\nfn free() {}\n"
    a, r, c = CH.sym_diff(CH.rs_symbols(rs_old), CH.rs_symbols(rs_new))
    assert a == ["A::three"] and r == [] and c == ["A::one"]
    lua_old = "return {\n  a = 1,\n  b = {\n    x = 1,\n  },\n}\nfunction helper() return 1 end\n"
    lua_new = "return {\n  a = 1,\n  b = {\n    x = 2,\n  },\n  c = 3,\n}\nfunction helper() return 1 end\n"
    a, r, c = CH.sym_diff(CH.lua_symbols(lua_old), CH.lua_symbols(lua_new))
    assert a == ["c"] and c == ["b"] and r == []


def test_risk_flags():
    assert CH.risk_flags([".github/workflows/ci.yml", "main.py", "src/core/x.py", "lua_content/a.lua"], True) == \
        ["ci-workflow", "boot-path", "lua-content", "rust-ffi"]
    assert CH.risk_flags(["tests/test_a.py", "tests/x/test_b.py"]) == ["tests-only"]
    assert CH.risk_flags(["src/gameplay/x.py"]) == [] and CH.risk_flags([]) == []


def test_summary_is_at_most_thirty_lines_and_compact():
    rows = [("M", f"src/mod{i}/file{i}.py", i + 1, 1) for i in range(60)] + [("A", f"tests/fixtures/ci/f{i}.log", 10, 0) for i in range(9)]
    lines, paths, flags = CH.summarize(rows, lambda p: PY_OLD, lambda p: PY_NEW if p.endswith(".py") else None, "HEAD~3", max_lines=30)
    assert len(lines) + 1 <= 30 and len(paths) == 69                          # +1: the `check:` line the CLI appends
    assert lines[0].startswith("CHANGED vs HEAD~3: 69 files +") and "symbols +60 -60 ~120" in lines[0]
    assert any(re.match(r"A tests/fixtures/ci/\(9 files\) +\+90/-0", ln) for ln in lines)     # 9 plain files = 1 line
    assert lines[-3].startswith("(+") and lines[-2].startswith("areas:") and lines[-1].startswith("RISK: none")
    one, _, _ = CH.summarize([("M", "a.py", 3, 1)], lambda p: PY_OLD, lambda p: PY_NEW, "origin/main")
    assert one[1] == "M a.py +3/-1  +fresh -gone ~K.n ~keep"


def test_compact_names_collapse_families():
    reg = fake_registry()
    chosen = [reg[n] for n in ("smoke", "play:a", "play:b")]
    assert CH.compact_names(chosen, reg) == ["smoke", "play:*"]
    assert CH.compact_names(chosen[:2], reg) == ["smoke", "play:a"]


def test_changed_cli_on_a_real_revision(capsys):
    assert qa.main(["changed", "HEAD"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("CHANGED vs HEAD:") and len(out) <= 30
    assert qa.main(["changed", "no-such-rev-xyz"]) == 2
