"""tools/quality_metrics.py + the `quality` check: the code-quality RATCHET.

No real tool runs here (except one smoke test): ruff/radon/vulture/import-linter output comes from tiny canned fixtures in
tests/fixtures/quality/ through a fake qa_pool runner, so the parsers, the ratchet rules, the baseline update and the output
contract are tested independently of what the live code looks like today.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import lua_bridge  # noqa: E402
import qa_pool  # noqa: E402
import qa_report as R  # noqa: E402
import quality_metrics as QM  # noqa: E402
from probe_settings import qa_settings  # noqa: E402
from qa_plugins import check as C  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "quality"
needs_lua = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")
CFG = {"ruff": {"select": ["BLE", "F401", "PLR0913"], "groups": {"blind_except": ["BLE001", "E722"]}}, "cc": {"min": 11},
       "vulture": {"min_confidence": 80}, "layers": {"config": ".importlinter"}, "baseline": "tests/quality_baseline.json",
       "cc_hints": [{"over": 20, "hint": "CC>20: split by kind"}, {"over": 0, "hint": "CC>10: extract a helper"}],
       "srp_module": {"cc11": 2, "hint": "SRP: {n} complex functions"},
       "rules": {"BLE001": {"hint": "catch the specific exceptions", "what": "blind except", "fix": "name the exception"}}}
LAYER_ENTRIES = [f"src.a{i} -> src.b{i}" for i in range(10)]


def text(name):
    return (FIX / name).read_text(encoding="utf-8")


def measurement(**over) -> QM.Measurement:
    """A Measurement built by the real parsers from the canned tool output."""
    m = QM.Measurement(files=["src/core/a.py", "src/ui/b.py", "src/a.py", "src/b.py", "src/db/c.py"], loc=100, cc_min=11,
                       groups={"blind_except": ["BLE001", "E722"]})
    m.diags = QM.parse_ruff(text("ruff.json"), ROOT)
    m.functions = QM.parse_radon(text("radon.json"), 11, ROOT)
    m.unused = QM.parse_vulture(text("vulture.txt"), ROOT)
    m.dups = {"Shared": ["src/a.py", "src/b.py"]}
    m.layers = QM.parse_layers(text("layers_ok.txt"), LAYER_ENTRIES)
    for k, v in over.items():
        setattr(m, k, v)
    return m


def worse_copy(m, **over) -> QM.Measurement:
    m2 = copy.deepcopy(m)
    for k, v in over.items():
        setattr(m2, k, v)
    return m2


# ---------------------------------------------------------------- parsers

def test_parse_ruff_paths_codes_and_syntax_errors():
    diags = QM.parse_ruff(text("ruff.json"), ROOT)
    assert len(diags) == 5
    assert {d["file"] for d in diags} == {"src/core/a.py", "src/ui/b.py", "src/ui/broken.py"}     # backslashes normalised
    assert [d["code"] for d in diags].count("BLE001") == 2 and diags[-1]["code"] == "syntax-error"
    assert diags[0]["line"] == 10
    absolute = json.dumps([{"code": "F401", "filename": str(ROOT / "src" / "x.py"), "location": {"row": 2}, "message": "m"}])
    assert QM.parse_ruff(absolute, ROOT)[0]["file"] == "src/x.py"
    win_style = json.dumps([{"code": "F401", "filename": str(ROOT / "src" / "x.py").replace("/", "\\"), "location": {"row": 2}, "message": "m"}])
    assert QM.parse_ruff(win_style, ROOT)[0]["file"] == "src/x.py"
    with pytest.raises(QM.ToolError, match="not JSON"):
        QM.parse_ruff("error: invalid config", ROOT)


def test_parse_radon_functions_closures_and_duplicates():
    fns = QM.parse_radon(text("radon.json"), 11, ROOT)
    assert {k: v["cc"] for k, v in fns.items()} == {
        "src/a.py::big": 13, "src/a.py::Runner.run": 25, "src/a.py::Runner.run.inner": 11,   # small (CC 5) and the class entry are not functions >= 11
        "src/b.py::K.x": 11, "src/b.py::K.x#2": 12}
    assert fns["src/a.py::Runner.run"]["line"] == 90
    assert len(QM.parse_radon(text("radon.json"), 20, ROOT)) == 1                              # the threshold is a parameter
    with pytest.raises(QM.ToolError, match="invalid syntax"):
        QM.parse_radon(text("radon_error.json"), 11, ROOT)


def test_parse_vulture_text():
    found = QM.parse_vulture(text("vulture.txt"), ROOT)
    assert [(u["file"], u["line"], u["conf"]) for u in found] == [
        ("src/core/a.py", 300, 100), ("src/db/c.py", 18, 90), ("src/db/c.py", 192, 100), ("src/db/c.py", 50, 100)]
    assert found[1]["msg"] == "unused import 'Engine'"
    assert QM.parse_vulture("", ROOT) == []


def test_parse_layers_new_edges_stale_entries_and_wrapped_lines():
    rep = QM.parse_layers(text("layers_broken.txt"), LAYER_ENTRIES[:3])
    assert rep.new == [("src.core.entity_manager", "src.entities.base_entity"),       # every hop of every broken chain
                       ("src.entities.base_entity", "src.core.helper"),
                       ("src.entities.character", "src.gameplay.hero_drive"),
                       ("src.entities.character", "src.gameplay.progression")]
    assert rep.stale == ["src.entities.character -> src.gameplay.nonexistent"]           # the warning wrapped after `->`
    assert rep.entries == 3 and rep.total == 3 - 1 + 4
    ok = QM.parse_layers(text("layers_ok.txt"), LAYER_ENTRIES)
    assert (ok.new, ok.stale, ok.total) == ([], [], 10)
    with pytest.raises(QM.ToolError, match="no contract summary"):
        QM.parse_layers(text("layers_config_error.txt"), [])


def test_ignore_entries_skip_comments(tmp_path):
    cfg = tmp_path / ".importlinter"
    cfg.write_text("[importlinter]\nroot_packages =\n    src\n\n[importlinter:contract:layers]\nname = layers\ntype = layers\n"
                   "layers =\n    src.a\n    src.b\nignore_imports =\n    # baseline: reason\n    src.b.x -> src.a.y\n"
                   "    src.b.z  ->   src.a.w\n    ; another comment\n", encoding="utf-8")
    assert QM.ignore_entries(cfg) == ["src.b.x -> src.a.y", "src.b.z -> src.a.w"]
    with pytest.raises(QM.ToolError):
        QM.ignore_entries(tmp_path / "missing")


def test_chunks_keep_command_lines_short():
    files = [f"src/module_{i}.py" for i in range(50)]
    parts = QM.chunks(files, 200)
    assert sum(parts, []) == files and len(parts) > 1
    assert all(sum(len(f) + 1 for f in p) <= 200 for p in parts)
    assert QM.chunks([], 200) == []
    jobs = QM.build_jobs({**CFG, "budget": {"argv_chars": 200}}, files)
    assert [j.name for j in jobs if j.name.startswith("ruff")] == [f"ruff#{i}" for i in range(len(parts))]
    assert jobs[-1].name == "layers#0"


def test_build_jobs_carry_the_lua_data():
    jobs = {j.name: j.argv for j in QM.build_jobs(CFG, ["src/a.py"])}
    assert jobs["ruff#0"][jobs["ruff#0"].index("--select") + 1] == "BLE,F401,PLR0913" and "--isolated" not in jobs["ruff#0"]
    assert jobs["ruff#0"][jobs["ruff#0"].index("--output-format") + 1] == "json"
    assert jobs["radon#0"][jobs["radon#0"].index("-n") + 1] == "C" and "-j" in jobs["radon#0"]     # CC >= 11 = rank C
    assert jobs["vulture#0"][jobs["vulture#0"].index("--min-confidence") + 1] == "80"
    assert "--config" in jobs["layers#0"] and ".importlinter" in jobs["layers#0"]
    jobs20 = {j.name: j.argv for j in QM.build_jobs({**CFG, "cc": {"min": 21}}, ["src/a.py"])}
    assert jobs20["radon#0"][jobs20["radon#0"].index("-n") + 1] == "D"


# ---------------------------------------------------------------- duplicated definitions

def test_dup_defs_detector_on_a_mini_project(tmp_path):
    (tmp_path / "a.py").write_text('from typing import TypeVar\nT = TypeVar("T")\nclass Shared: pass\nclass OnlyA: pass\n'
                                   'LIMIT = 1\nMAX_HP: int = 5\n_private = 1\nsmall = 2\ndef f():\n    class Nested: pass\n', encoding="utf-8")
    (tmp_path / "b.py").write_text('T = 1\nclass Shared: pass\nLIMIT = 2\nMAX_HP = 9\nclass Nested: pass\nsmall = 3\n', encoding="utf-8")
    (tmp_path / "c.py").write_text("class Shared: pass\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    files = ["a.py", "b.py", "c.py", "bad.py", "missing.py"]
    dups = QM.find_dup_defs(tmp_path, files)
    assert dups == {"LIMIT": ["a.py", "b.py"], "MAX_HP": ["a.py", "b.py"], "Shared": ["a.py", "b.py", "c.py"]}   # T: 1 char, not a constant
    allowed = QM.find_dup_defs(tmp_path, files, {"allow": ["Shared", "LIMIT@b.py"]})
    assert allowed == {"MAX_HP": ["a.py", "b.py"]}                        # LIMIT@b.py leaves ONE definition: no duplicate any more
    assert QM.find_dup_defs(tmp_path, ["a.py"]) == {}


def test_scope_is_the_live_game_modules_computed_from_the_import_graph():
    import qa_graph
    graph = qa_graph.build()
    files = QM.live_files({"scope": {"liveness": "game", "exclude": ["setup.py"]}}, graph)
    assert len(files) > 60 and "main.py" in files and "setup.py" not in files
    assert not any(f.startswith(("tests/", "tools/")) for f in files)                         # tests and tools are other liveness classes
    assert set(files) == {p for p, k in qa_graph.liveness(graph).items() if k == "game"} - {"setup.py"}
    assert "setup.py" in QM.live_files({"scope": {}}, graph)                                    # no hard-coded list: the default keeps every game file


# ---------------------------------------------------------------- the ratchet

def test_same_numbers_is_ok_and_the_line_has_the_headline_metrics():
    m = measurement()
    res = QM.evaluate(CFG, m, QM.to_baseline(m))
    assert res.status == "ok" and res.detail == []
    assert list(res.metrics)[:7] == ["ruff", "blind_except", "cc11", "cc_max", "dup_defs", "layers_broken", "vulture"]
    assert res.metrics["ruff"] == 5 and res.metrics["blind_except"] == 2 and res.metrics["cc11"] == 5
    assert res.metrics["cc_max"] == 25 and res.metrics["dup_defs"] == 1 and res.metrics["layers_broken"] == 10
    assert res.metrics["vulture"] == 4 and res.metrics["worst"] == "a.py:Runner.run:CC25"
    assert "improved" not in res.metrics


def test_a_new_violation_in_a_file_fails_with_the_lines():
    m = measurement()
    base = QM.to_baseline(m)
    worse = worse_copy(m, diags=[*m.diags, {"file": "src/core/a.py", "line": 77, "code": "BLE001", "msg": "x"}])
    res = QM.evaluate(CFG, worse, base)
    assert res.status == "fail" and res.repro == QM.REPRO_WORST
    assert "src/core/a.py BLE001 2->3" in res.detail[0] and ":10,40,77" in res.detail[0]           # which lines to look at
    assert "ruff 5->6" in res.detail[1] and "blind_except 2->3" in res.detail[1]


def test_a_new_file_with_violations_fails_even_if_a_total_would_stay_flat():
    m = measurement()
    base = QM.to_baseline(m)
    moved = worse_copy(m, diags=[d for d in m.diags if d["file"] != "src/ui/b.py"] + [
        {"file": "src/ui/new.py", "line": 1, "code": "PLR0913", "msg": "moved"}])        # same total, another file
    worse, better = QM.compare(base, moved)
    assert any(f.kind == "file" and f.key == "src/ui/new.py PLR0913" for f in worse)
    assert any(f.kind == "file" and f.key == "src/ui/b.py PLR0913" for f in better)
    assert QM.evaluate(CFG, moved, base).status == "fail"


def test_a_metric_total_above_baseline_fails_even_when_no_file_moved():
    m = measurement()
    base = QM.to_baseline(m)
    base["totals"]["vulture"] -= 1
    res = QM.evaluate(CFG, m, base)
    assert res.status == "fail" and "vulture 3->4" in res.detail[1]


def test_improvement_is_a_warn_that_suggests_update_baseline():
    m = measurement()
    base = QM.to_baseline(m)
    better = worse_copy(m, diags=[d for d in m.diags if d["code"] != "F401"])
    res = QM.evaluate(CFG, better, base)
    assert res.status == "warn" and res.metrics["improved"] >= 3
    assert "ruff 5->4" in res.detail[0] and "--update-baseline" in res.detail[0] and res.repro == QM.REPRO_UPDATE
    assert res.metrics["ruff"] == 4


def test_function_ratchet_new_worse_and_fixed():
    m = measurement()
    base = QM.to_baseline(m)

    grown = worse_copy(m, functions={**m.functions, "src/a.py::big": {**m.functions["src/a.py::big"], "cc": 14}})
    res = QM.evaluate(CFG, grown, base)
    assert res.status == "fail" and "CC 13->14: src/a.py::big" in res.detail[0]

    new_fn = worse_copy(m, functions={**m.functions, "src/a.py::brand_new": {"cc": 11, "file": "src/a.py", "name": "brand_new", "line": 1}})
    res = QM.evaluate(CFG, new_fn, base)
    assert res.status == "fail" and "NEW function CC 11: src/a.py::brand_new" in res.detail[0]

    fixed = worse_copy(m, functions={k: v for k, v in m.functions.items() if k != "src/a.py::big"})
    res = QM.evaluate(CFG, fixed, base)
    assert res.status == "warn" and "cc11 5->4" in res.detail[0]


def test_duplicate_definition_and_layer_edge_ratchet():
    m = measurement()
    base = QM.to_baseline(m)
    res = QM.evaluate(CFG, worse_copy(m, dups={**m.dups, "Fresh": ["src/a.py", "src/b.py"]}), base)
    assert res.status == "fail" and "NEW duplicate definition Fresh" in res.detail[0]

    broken = QM.parse_layers(text("layers_broken.txt"), LAYER_ENTRIES)
    res = QM.evaluate(CFG, worse_copy(m, layers=broken), base)
    assert res.status == "fail" and "NEW import src.entities.character -> src.gameplay.hero_drive" in res.detail[0]

    stale = QM.LayerReport(new=[], stale=["src.a0 -> src.b0"], entries=10)                 # an ignored edge was fixed
    res = QM.evaluate(CFG, worse_copy(m, layers=stale), base)
    assert res.status == "warn" and res.metrics["layers_broken"] == 9 and "delete these lines" in res.detail[1]


def test_no_baseline_is_an_error_with_the_way_out():
    res = QM.evaluate(CFG, measurement(), None)
    assert res.status == "error" and "--update-baseline" in res.detail[0] and res.repro == QM.REPRO_UPDATE


# ---------------------------------------------------------------- update-baseline

def test_update_baseline_refuses_to_raise_without_force(tmp_path):
    path = tmp_path / "tests" / "quality_baseline.json"
    m = measurement()
    ok, lines = QM.update_baseline(path, m)                                # first run creates it
    assert ok and "baseline created" in lines[0]
    before = path.read_bytes()
    assert b"\r\n" not in before and before.endswith(b"}\n")             # LF on every OS

    raised = worse_copy(m, diags=[*m.diags, {"file": "src/ui/b.py", "line": 9, "code": "BLE001", "msg": "x"}])
    ok, lines = QM.update_baseline(path, raised)
    assert not ok and "refusing to RAISE" in lines[0] and "src/ui/b.py BLE001 0->1" in lines[1]
    assert path.read_bytes() == before                                     # untouched

    ok, lines = QM.update_baseline(path, raised, force=True)
    assert ok and "RAISED" in lines[0]
    assert json.loads(path.read_text(encoding="utf-8"))["rules"]["BLE001"] == 3


def test_update_baseline_lowers_numbers_and_is_deterministic(tmp_path):
    path = tmp_path / "b.json"
    m = measurement()
    QM.update_baseline(path, m)
    better = worse_copy(m, functions={k: v for k, v in m.functions.items() if k != "src/a.py::big"})
    ok, lines = QM.update_baseline(path, better)
    assert ok and "baseline updated" in lines[0] and "2 lowered" in lines[0]                # cc11 total + the function
    first = path.read_bytes()
    QM.update_baseline(path, better)
    assert path.read_bytes() == first                                      # same numbers -> byte-identical file
    data = json.loads(first)
    assert data["totals"]["cc11"] == 4 and "src/a.py::big" not in data["functions"]
    assert QM.evaluate(CFG, better, data).status == "ok"                   # after the update the improvement is the new normal


# ---------------------------------------------------------------- end to end through a fake qa_pool runner

def fake_runner(rc_by_tool=None, outputs=None):
    rc_by_tool = {"ruff": 1, "radon": 0, "vulture": 3, "layers": 0, **(rc_by_tool or {})}
    outputs = {"ruff": text("ruff.json"), "radon": text("radon.json"), "vulture": text("vulture.txt"), "layers": text("layers_ok.txt"),
               **(outputs or {})}
    seen: list = []

    def run(job_list, jobs=None, **kw):
        seen.extend(job_list)
        out = []
        for j in job_list:
            tool = j.name.split("#")[0]
            out.append(qa_pool.Result(j.name, rc_by_tool[tool], outputs[tool], "", 0.01, {}))
        return out
    run.seen = seen
    return run


@pytest.fixture
def mini(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("class Shared: pass\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("class Shared: pass\n", encoding="utf-8")
    (tmp_path / ".importlinter").write_text("[importlinter]\nroot_packages =\n    src\n\n[importlinter:contract:layers]\nname = layers\ntype = layers\n"
                                            "layers =\n    src.a\n    src.b\nignore_imports =\n" + "".join(f"    {e}\n" for e in LAYER_ENTRIES),
                                            encoding="utf-8")
    return tmp_path


def test_measure_end_to_end_with_canned_tool_output(mini):
    runner = fake_runner()
    m = QM.measure({**CFG, "dup_defs": {}}, mini, runner, files=["src/a.py", "src/b.py"])
    assert m.totals == {"ruff": 5, "blind_except": 2, "cc11": 5, "cc_max": 25, "dup_defs": 1, "layers_broken": 10, "vulture": 4}
    assert m.dups == {"Shared": ["src/a.py", "src/b.py"]} and m.loc == 4
    assert sorted(j.name for j in runner.seen) == ["layers#0", "radon#0", "ruff#0", "vulture#0"]
    assert m.per_file["src/core/a.py"] == {"BLE001": 2, "F401": 1, "vulture": 1}
    assert m.rules == {"BLE001": 2, "F401": 1, "PLR0913": 1, "syntax-error": 1}


def test_check_passes_fails_and_reports_tool_errors(mini, monkeypatch):
    cfg = {**CFG, "dup_defs": {}}
    settings = {"quality": cfg}
    files = ["src/a.py", "src/b.py"]
    m = QM.measure(cfg, mini, fake_runner(), files=files)
    QM.dump_baseline(QM.baseline_path(cfg, mini), QM.to_baseline(m))
    import qa_graph
    graph = {f: {"imports": [], "script": False, "doc": "", "loc": 1} for f in files}
    graph["main.py"] = {"imports": files, "script": True, "doc": "", "loc": 1}          # scope = what main.py reaches
    monkeypatch.setattr(qa_graph, "build", lambda *a, **k: graph)
    assert QM.check(fake_runner(), mini, settings).status == "ok"

    more = json.loads(text("ruff.json"))
    more.append({"code": "BLE001", "filename": "src/a.py", "location": {"row": 3}, "message": "x"})
    res = QM.check(fake_runner(outputs={"ruff": json.dumps(more)}), mini, settings)
    assert res.status == "fail" and "src/a.py BLE001 0->1" in res.detail[0]

    res = QM.check(fake_runner(rc_by_tool={"ruff": 2}, outputs={"ruff": ""}), mini, settings)          # ruff itself broke: ERROR, not FAIL
    assert res.status == "error" and "ruff exited 2" in res.detail[0]
    res = QM.check(fake_runner(outputs={"layers": text("layers_config_error.txt")}, rc_by_tool={"layers": 1}), mini, settings)
    assert res.status == "error" and "import-linter" in res.detail[0]
    assert QM.check(fake_runner(), mini, {}).status == "error"                                           # no `quality` table in qa.lua


# ---------------------------------------------------------------- the uniform output contract

def all_statuses():
    m = measurement()
    base = QM.to_baseline(m)
    fail = QM.evaluate(CFG, worse_copy(m, diags=[*m.diags, {"file": "src/x.py", "line": 1, "code": "F401", "msg": "x"}]), base)
    warn = QM.evaluate(CFG, worse_copy(m, unused=m.unused[:2]), base)
    return {"ok": QM.evaluate(CFG, m, base), "fail": fail, "warn": warn, "error": QM.evaluate(CFG, m, None)}


def test_every_result_is_one_line_in_the_status_vocabulary():
    for want, res in all_statuses().items():
        assert res.status == want and res.status in R.STATUSES
        res.name, res.dur = "quality", 1.2
        line = R.format_line(res, 7, cfg=R.DEFAULT_CFG)
        assert "\n" not in line and R.LINE_RE.match(line), line
        assert line.startswith(R.WORD[want])
        assert " dur=1.2s" in line and line.split()[2].startswith("ruff=")
        if want != "ok":
            assert "| repro: python tools/qa.py quality" in line
    results = list(all_statuses().values())
    for r in results:
        r.name, r.dur = "quality", 1.0
    lines, full = R.render(results, {"dur": 1.0, "head": "abc", "dirty": 0, "selected": 4, "total": 4, "by": "name"}, None, R.DEFAULT_CFG)
    assert R.HEADER_RE.match(lines[0]) and full  # header + one line per check (+ at most detail_lines-1 continuation lines of the fail)
    assert sum(1 for ln in lines if R.LINE_RE.match(ln)) == 4
    assert all(R.LINE_RE.match(ln) or ln.startswith(("QA verdict", "  | ")) for ln in lines)


def test_deltas_use_the_existing_machinery():
    cfg = {**R.DEFAULT_CFG, "delta": {"ruff": {"pct": 0, "abs": 1}, "cc11": {"pct": 0, "abs": 1}}}
    res = all_statuses()["warn"]
    prev = {"ruff": res.metrics["ruff"] + 3, "cc11": res.metrics["cc11"], "worst": "old.py:f:CC30"}
    tokens = R.delta_tokens(res.metrics, prev, cfg)
    assert set(tokens) == {"ruff"} and tokens["ruff"].startswith("(-")                 # only the metric that moved, strings ignored


def test_worst_and_explain_screens():
    m = measurement()
    lines = QM.worst_lines(CFG, m, 3)
    assert len(lines) < 30 and lines[0].startswith("quality worst 3: scope=5 live modules")
    fn_rows = [ln for ln in lines if ln.strip().startswith("CC ")]
    assert fn_rows[0].split()[1] == "25" and "CC>20: split by kind" in fn_rows[0] and "src/a.py:90 Runner.run" in fn_rows[0]
    assert "duplicated definitions: Shared(2)" in lines and any("layers_broken=10" in ln for ln in lines)
    rows = QM.file_rows(CFG, m)
    assert rows[0][1] in ("src/a.py", "src/b.py", "src/core/a.py") and rows[0][0] >= 3
    a = next(r for r in rows if r[1] == "src/a.py")
    assert "SRP: 3 complex functions" in a[3]                                          # srp_module hint: 3 functions >= 2

    ex = QM.explain_lines(CFG, "ble001", QM.to_baseline(m))
    assert ex[0].startswith("BLE001") and ex[1].startswith("what:") and ex[2].startswith("fix:")
    assert any(ln.startswith("baseline: 2 in 1 files, worst src/core/a.py (2)") for ln in ex) and len(ex) <= 8
    assert QM.explain_lines({**CFG, "rules": {"layers_broken": {"hint": "h", "what": "w", "fix": "f"}}}, "layers")[0].startswith("layers_broken")


# ---------------------------------------------------------------- registry, Lua data, the real repo

@needs_lua
def test_the_check_is_declared_in_qa_lua_and_not_part_of_ci_on_every_os():
    chk = C.load_registry(qa_settings())["quality"]
    assert chk.fn is None and chk.ci is False and chk.spec["parse"] == "result_line"        # data check: no Python check file needed
    assert chk.spec["argv"][1:] == ["tools/qa.py", "quality", "--scope", "game", "--result"] and set(chk.needs) == {"ruff", "radon", "vulture", "importlinter"}
    assert {"tests/quality_baseline.json", "lua_content/qa.lua", ".importlinter", "pyproject.toml", "tools/quality_metrics.py"} <= set(chk.watches)
    assert C.matches(chk, ["src/effects/runtime.py"]) and not C.matches(chk, ["docs/x.md"])
    assert "quality" not in [c.name for c in C.load_registry(qa_settings()).values() if c.ci]          # `check --ci` skips it; CI runs it on Linux


@needs_lua
def test_result_lines_round_trip_through_the_runner_parser():
    """`qa.py quality --result` output -> qa_report.interpret with the spec from qa.lua gives the same status, metrics and details."""
    spec = C.load_registry(qa_settings())["quality"].spec
    for want, res in all_statuses().items():
        out = "\n".join(QM.result_lines(res)) + "\n"
        rc = {"ok": 0, "warn": 0, "fail": 1, "error": 2}[want]
        back = R.interpret(out, rc, spec, 1.0, "quality")
        assert back.status == want, (want, out)
        if want == "error":
            assert any("no baseline" in d for d in back.detail)                              # the cause is shown, not swallowed
            continue
        assert back.metrics == res.metrics and (back.detail[:1] == res.detail[:1] or want == "ok")
        assert not any(d.startswith(("RESULT", "repro:")) for d in back.detail)
        if want != "ok":
            assert back.repro == res.repro and back.repro.startswith("python tools/qa.py quality")
    assert QM.result_lines(R.Result("ok", {"ruff": 1}))[-1] == "RESULT status=OK ruff=1"


@needs_lua
def test_qa_lua_quality_table_is_complete():
    cfg = qa_settings()["quality"]
    for key in ("baseline", "scope", "ruff", "cc", "vulture", "dup_defs", "layers", "budget", "cc_hints", "rules"):
        assert key in cfg, key
    base = json.loads((ROOT / cfg["baseline"]).read_text(encoding="utf-8"))
    assert base["version"] == QM.BASELINE_VERSION and f"cc{cfg['cc']['min']}" in base["totals"]
    missing = [c for c in base["rules"] if not (cfg["rules"].get(c) or {}).get("fix")]
    assert not missing, f"rules in the baseline without a `what/fix` entry in qa.lua quality.rules: {missing}"
    for name, info in cfg["rules"].items():
        assert info.get("what") and info.get("fix") and info.get("hint"), name
    assert [h["over"] for h in cfg["cc_hints"]] == sorted((h["over"] for h in cfg["cc_hints"]), reverse=True)
    for key in ("ruff", "blind_except", "cc11", "cc_max", "dup_defs", "layers_broken", "vulture", "improved"):
        assert key in qa_settings()["report"]["delta"], key                                    # a move of any headline count is printed
    assert "quality" in C.load_registry(qa_settings())


def test_importlinter_baseline_lists_every_broken_edge_with_a_comment():
    entries = QM.ignore_entries(ROOT / ".importlinter")
    assert len(entries) == len(set(entries)) >= 1 and all(" -> " in e for e in entries)
    raw = (ROOT / ".importlinter").read_text(encoding="utf-8")
    assert raw.count("# baseline") >= 1 and "unmatched_ignore_imports_alerting = warn" in raw
    assert "[tool.ruff" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def tools_installed():
    import importlib.util
    return all(importlib.util.find_spec(m) for m in ("ruff", "radon", "vulture", "importlinter"))


@needs_lua
@pytest.mark.skipif(not tools_installed(), reason="pip install -r requirements-dev.txt (ruff radon vulture import-linter)")
def test_real_tools_on_the_real_repo_smoke():
    """The whole pipeline once for real (~1.5 s). fail is a legitimate outcome (someone made the code worse), error is not."""
    res = QM.check()
    assert res.status in ("ok", "warn", "fail"), res.detail
    assert res.metrics["ruff"] > 0 and res.metrics["cc11"] > 0 and res.metrics["layers_broken"] >= 0
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "qa.py"), "quality", "--explain", "BLE001"], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and "what:" in out.stdout and "fix:" in out.stdout


@needs_lua
def test_tools_scope_has_own_baseline_and_no_layer_job():
    cfg = QM.load_cfg(qa_settings())
    tools = QM.scoped_cfg(cfg, "tools")
    assert QM.scoped_cfg(cfg, "game") is cfg and tools["baseline"] == "tests/quality_baseline_tools.json"
    assert tools["scope"]["liveness"] == "tool" and tools["ruff"] == cfg["ruff"]
    assert not any(j.name.startswith("layers") for j in QM.build_jobs(tools, ["tools/x.py"]))
    assert any(j.name.startswith("layers") for j in QM.build_jobs(cfg, ["src/x.py"]))
    assert QM.load_baseline(QM.baseline_path(tools)) is not None
    with pytest.raises(QM.ToolError):
        QM.scoped_cfg(cfg, "nope")
