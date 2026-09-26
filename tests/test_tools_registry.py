"""Tools registry (tools/tool_registry.py, `qa.py tools`, the `tools` check of lua_content/qa.lua, generated docs/TOOLS.md).

The harvest, the render, the gaps (undocumented / stale / near-duplicate / drift) and `--find` run on a tiny throw-away repository built in
tmp_path; the last tests pin the real repository (docs/TOOLS.md fresh, every tool documented, the CLI answers).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import tool_registry as TR  # noqa: E402
from probe_settings import qa_settings  # noqa: E402

QA_PY = '''"""QA front door.

    python tools/qa.py alpha --now      # first alpha does one thing
    python tools/qa.py alpha --other    # never used: the FIRST mention wins
    python tools/qa.py beta             # beta reads logs
"""
def main():
    sub = parser.add_subparsers()
    sub.add_parser("alpha")
    sub.add_parser("beta", help="beta help text wins over the header")
'''
PLUGIN = '''"""qa.py gamma - the docstring line.

More text.
"""
TOOL = {"replaces": "raw gamma work", "cost": "low"}


def register(sub):
    sub.add_parser("gamma", help="gamma help line")
    sub.add_parser("noise")           # a second command without help: its purpose is the docstring line
'''
RUST = '''/// Fast thing. It also does more.
/// Second line of the same sentence group.
#[pyclass]
struct PyThing { inner: u8 }

/// Find the path over a grid.
#[pyfunction]
#[pyo3(name = "find_path", signature = (a, b))]
fn py_find_path(a: i32) {}

#[pyclass]
struct PyBare;
'''


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path):
    write(tmp_path, "tools/qa.py", QA_PY)
    write(tmp_path, "tools/qa_plugins/__init__.py", '"""plugins"""\n')
    write(tmp_path, "tools/qa_plugins/gamma.py", PLUGIN)
    write(tmp_path, "tools/qa_plugins/_private.py", "def register(sub):\n    sub.add_parser('hidden', help='x')\n")
    write(tmp_path, "tools/script_one.py", '"""Runs the one thing.\n\nlong text\n"""\nif __name__ == "__main__":\n    pass\n')
    write(tmp_path, "tools/lib_two.py", '"""Shared helper for scripts."""\n')
    write(tmp_path, "tools/exit_script.py", '"""Ends with sys.exit."""\nimport sys\nsys.exit(0)\n')
    write(tmp_path, "tools/pkg/__init__.py", '"""A package of things."""\n')
    write(tmp_path, "tools/_skipped.py", '"""private"""\n')
    write(tmp_path, "tools/qa_checks/mine.py",
          'from qa_report import check\n\n\n@check("mine", cost="low")\ndef mine(ctx):\n    """The Python check line."""\n')
    write(tmp_path, "rust_core/src/ffi/mod.rs", RUST)
    write(tmp_path, "lua_content/a.lua", "-- lua_content/a.lua\n-- tool: settings of alpha\n-- tool.replaces: constants in code\nreturn {}\n")
    write(tmp_path, "lua_content/b.lua", "-- just content\nreturn {}\n")
    return tmp_path


def cfg_of(**tools) -> dict:
    base = {"checks": [{"name": "c1", "what": "the first check", "cmd": "python tools/qa.py alpha --x", "cost": "low"}],
            "scenarios": [{"name": "s1", "script": "wait 1"}], "plays": [{"name": "s2", "script": "wait 2"}],
            "scenario_check": {"cost": "low"},
            "tools": {"required": ["purpose"], "dup_threshold": 0.6, "skip_dirs": ["qa_plugins", "qa_checks"], "max_lines": 500,
                      "stopwords": ["the", "and", "for", "with", "python", "tools", "tool", "file"],
                      "groups": [{"id": "verify", "title": "verify"}, {"id": "analyse", "title": "analyse"}, {"id": "kernels", "title": "kernels"},
                                 {"id": "content", "title": "content"}, {"id": "libs", "title": "libs"}]}}
    base["tools"].update(tools)
    return base


def by_id(reg: TR.Registry) -> dict:
    return {t.id: t for t in reg.tools}


# ---------------------------------------------------------------- harvest

def test_harvest_finds_every_kind_of_tool(repo):
    ids = set(by_id(TR.build(repo, cfg_of())))
    assert ids == {"alpha", "beta", "gamma", "noise", "script_one", "exit_script", "lib_two", "pkg", "check:c1", "check:play:*", "check:mine",
                   "rust:Thing", "rust:find_path", "rust:Bare", "lua:a.lua"}
    assert "hidden" not in ids and "_skipped" not in ids and "qa_plugins" not in ids and "lua:b.lua" not in ids


def test_harvest_reads_purpose_where_the_code_states_it(repo):
    t = by_id(TR.build(repo, cfg_of()))
    assert t["alpha"].purpose == "first alpha does one thing"                     # header of qa.py: first mention wins
    assert t["beta"].purpose == "beta help text wins over the header"             # help= beats the header
    assert t["gamma"].purpose == "gamma help line"                                # plugin help= beats its docstring
    assert t["noise"].purpose.startswith("qa.py gamma - the docstring")           # no help=: the module docstring line
    assert t["script_one"].purpose == "Runs the one thing."                       # module docstring, first line
    assert t["pkg"].purpose == "A package of things."                             # __init__ docstring
    assert t["check:c1"].purpose == "the first check"                             # Lua `what`
    assert t["check:mine"].purpose == "The Python check line."                    # @check docstring
    assert t["rust:Thing"].purpose == "Fast thing."                               # first sentence of the /// docs
    assert t["rust:find_path"].purpose == "Find the path over a grid."
    assert t["rust:Bare"].purpose == ""                                           # no docs: reported as undocumented
    assert t["lua:a.lua"].purpose == "settings of alpha" and t["lua:a.lua"].replaces == "constants in code"


def test_harvest_kinds_commands_and_owners(repo):
    t = by_id(TR.build(repo, cfg_of()))
    assert (t["alpha"].kind, t["alpha"].command, t["alpha"].owner) == ("qa", "python tools/qa.py alpha", "tools/qa.py")
    assert t["gamma"].owner == "tools/qa_plugins/gamma.py"
    assert (t["script_one"].kind, t["script_one"].command) == ("script", "python tools/script_one.py")
    assert t["exit_script"].kind == "script"                                       # top-level sys.exit = runnable
    assert (t["lib_two"].kind, t["lib_two"].command) == ("lib", "import lib_two")
    assert t["rust:Thing"].command == "rust_core.Thing" and t["rust:find_path"].command == "rust_core.find_path"
    assert t["check:c1"].command == "python tools/qa.py check --name c1" and t["check:c1"].wraps == "python tools/qa.py alpha --x"
    play = t["check:play:*"]
    assert "2 gameplay checks" in play.purpose and "s1, s2" in play.purpose      # scenarios + plays: ONE row
    assert t["lua:a.lua"].group == "content" and t["rust:Thing"].group == "kernels" and t["lib_two"].group == "libs"


def test_plugin_tool_dict_overrides_harvest_and_row_overrides_both(repo):
    plain = by_id(TR.build(repo, cfg_of()))
    assert plain["gamma"].replaces == "raw gamma work" and plain["gamma"].cost == "low"     # TOOL = {...} in the plugin
    rows = [{"id": "gamma", "replaces": "the row wins", "purpose": "purpose from qa.lua"}]
    row = by_id(TR.build(repo, cfg_of(rows=rows)))["gamma"]
    assert (row.replaces, row.purpose, row.cost) == ("the row wins", "purpose from qa.lua", "low")   # untouched keys survive


def test_manual_row_adds_a_tool_and_an_orphan_row_is_drift(repo):
    rows = [{"id": "itemcheck", "manual": True, "command": "python -m x.itemcheck", "purpose": "checks one item", "group": "content"},
            {"id": "gone", "purpose": "the tool of this row was renamed"}]
    reg = TR.build(repo, cfg_of(rows=rows))
    assert by_id(reg)["itemcheck"].kind == "manual" and by_id(reg)["itemcheck"].group == "content"
    assert [k for k, _ in reg.problems] == ["drift"] and "'gone'" in reg.problems[0][1]


def test_same_name_twice_is_reported(repo):
    write(repo, "tools/alpha.py", '"""A script named like a qa.py command."""\nif __name__ == "__main__":\n    pass\n')
    reg = TR.build(repo, cfg_of())
    assert [k for k, _ in reg.problems] == ["dup"] and "'alpha'" in reg.problems[0][1]


# ---------------------------------------------------------------- render

def test_render_is_deterministic_sorted_and_free_of_timestamps(repo):
    cfg = cfg_of()
    first = TR.render(TR.build(repo, cfg), cfg)
    reversed_cfg = cfg_of()
    reversed_cfg["checks"] = list(reversed(reversed_cfg["checks"]))
    assert first == TR.render(TR.build(repo, reversed_cfg), reversed_cfg)
    assert first == TR.render(TR.build(repo, cfg), cfg) and first.endswith("\n") and "\r" not in first
    rows = [ln for ln in first.splitlines() if ln.startswith("| `")]
    assert len(rows) == len(TR.build(repo, cfg).tools)
    assert first.index("### verify") < first.index("### analyse") < first.index("### kernels") < first.index("### libs")   # group order = qa.lua
    assert all(ln.count("|") >= 7 for ln in rows)


def test_render_escapes_pipes_and_clips_long_cells(repo):
    rows = [{"id": "alpha", "command": "python tools/qa.py alpha a|b", "purpose": "word " * 60}]
    cfg = cfg_of(rows=rows, cell_width=40)
    line = next(ln for ln in TR.render(TR.build(repo, cfg), cfg).splitlines() if ln.startswith("| `alpha`"))
    assert "a\\|b" in line and "..." in line and len(line) < 200


# ---------------------------------------------------------------- gaps

def test_report_ok_when_everything_is_documented_and_fresh(repo):
    cfg = cfg_of(rows=[{"id": "rust:Bare", "purpose": "bare struct, documented by a row"}])
    TR.write(repo, cfg)
    res = TR.report(repo, cfg)
    assert res.status == "ok" and res.detail == [] and res.repro is None
    assert res.metrics["undocumented"] == 0 and res.metrics["stale"] == 0 and res.metrics["documented"] == res.metrics["tools"]


def test_missing_purpose_fails_with_the_tool_named(repo):
    cfg = cfg_of()                                  # rust:Bare has no docs, tools/qa_checks etc. are fine
    TR.write(repo, cfg)
    res = TR.report(repo, cfg)
    assert res.status == "fail" and res.metrics["undocumented"] == 1 and res.metrics["stale"] == 0
    assert res.detail[0].startswith("undocumented: rust:Bare") and res.repro == TR.REPRO
    short = cfg_of(rows=[{"id": "rust:Bare", "purpose": "tiny"}])                # under 8 characters is no purpose
    assert TR.undocumented(TR.build(repo, short).tools, short["tools"])[0][0].id == "rust:Bare"


def test_stale_doc_and_missing_doc_fail(repo):
    cfg = cfg_of(rows=[{"id": "rust:Bare", "purpose": "bare struct, documented by a row"}])
    assert "missing" in TR.doc_state(repo, TR.build(repo, cfg), cfg)
    assert TR.report(repo, cfg).metrics["stale"] == 1
    TR.write(repo, cfg)
    assert TR.report(repo, cfg).metrics["stale"] == 0
    write(repo, "tools/late_script.py", '"""A tool added after the doc was generated."""\nif __name__ == "__main__":\n    pass\n')
    res = TR.report(repo, cfg)
    assert res.status == "fail" and res.metrics["stale"] == 1 and res.detail[0].startswith("stale: docs/TOOLS.md differs")
    TR.write(repo, cfg)
    assert TR.report(repo, cfg).status == "ok"
    (repo / TR.DOC).write_bytes((repo / TR.DOC).read_bytes().replace(b"\n", b"\r\n"))       # a CRLF checkout is not stale
    assert TR.report(repo, cfg).metrics["stale"] == 0


def test_near_duplicate_is_flagged_and_the_allowlist_silences_it(repo):
    write(repo, "tools/log_reader.py", '"""Reads the game logs and summarises errors per minute."""\nif __name__ == "__main__":\n    pass\n')
    write(repo, "tools/log_summary.py", '"""Reads the game logs and summarises errors per minute."""\nif __name__ == "__main__":\n    pass\n')
    cfg = cfg_of(rows=[{"id": "rust:Bare", "purpose": "bare struct, documented by a row"}])
    tools = TR.build(repo, cfg).tools
    (score, a, b), = TR.dup_suspects(tools, cfg["tools"])
    assert {a.id, b.id} == {"log_reader", "log_summary"} and score >= 0.6
    TR.write(repo, cfg)
    res = TR.report(repo, cfg)
    assert res.status == "fail" and res.metrics["dup_suspects"] == 1 and "log_reader ~ log_summary" in res.detail[0]
    assert '"log_reader~log_summary"' in res.detail[0]                                          # the fix is in the message
    allowed = cfg_of(rows=cfg["tools"]["rows"], dup_allow=["log_reader~log_summary"])
    assert TR.dup_suspects(tools, allowed["tools"]) == []


def test_a_check_and_the_tool_it_runs_are_not_duplicates(repo):
    write(repo, "tools/qa_plugins/delta.py",
          '"""d"""\ndef register(sub):\n    sub.add_parser("delta", help="the first check of the second alpha tool")\n')
    cfg = cfg_of()
    cfg["checks"] = [{"name": "delta", "what": "the first check of the second alpha tool", "cmd": "python tools/qa.py delta --result"}]
    tools = TR.build(repo, cfg).tools
    assert TR.dup_suspects(tools, cfg["tools"]) == []                    # same words, but the check wraps the command
    cfg["checks"][0]["cmd"] = "python tools/other.py"
    assert len(TR.dup_suspects(TR.build(repo, cfg).tools, cfg["tools"])) == 1


def test_claude_md_command_that_is_not_a_subcommand_is_drift(repo):
    write(repo, "CLAUDE.md", "Run `python tools/qa.py alpha` then `qa.py nope --x` and `tools/qa.py beta`.\n")
    cfg = cfg_of(rows=[{"id": "rust:Bare", "purpose": "bare struct, documented by a row"}])
    TR.write(repo, cfg)
    res = TR.report(repo, cfg)
    assert res.status == "fail" and res.metrics["drift"] == 1 and "`qa.py nope`" in res.detail[0]
    assert TR.report(repo, cfg_of(rows=cfg["tools"]["rows"], drift_ignore=["nope"])).metrics["drift"] == 0


def test_detail_is_capped(repo):
    for i in range(6):
        write(repo, f"tools/bare{i}.py", "if __name__ == '__main__':\n    pass\n")
    cfg = cfg_of(max_detail=3)
    res = TR.report(repo, cfg)
    assert res.status == "fail" and len(res.detail) == 4 and res.detail[-1].startswith("(+")


# ---------------------------------------------------------------- --find

def test_find_ranks_name_hits_above_purpose_hits_and_limits(repo):
    reg = TR.build(repo, cfg_of(rows=[{"id": "beta", "when": "reading logs of a run", "replaces": "cat game.log"}]))
    tcfg = cfg_of()["tools"]
    assert TR.find(reg, "beta", tcfg)[0].id == "beta"
    assert TR.find(reg, "logs", tcfg)[0].id == "beta"                   # found through `when`
    assert TR.find(reg, "game.log", tcfg)[0].id == "beta"               # ... and through `replaces`
    assert TR.find(reg, "path grid", tcfg)[0].id == "rust:find_path"
    assert TR.find(reg, "spreadsheet translation", tcfg) == []
    assert len(TR.find(reg, "the", tcfg)) == 0                          # stop words alone match nothing
    assert len(TR.find(reg, "alpha beta gamma script check rust", tcfg, limit=3)) == 3
    many = cfg_of(max_find=2)["tools"]
    assert len(TR.find(reg, "alpha beta gamma script check rust", many)) == 2


def test_find_prefix_match_finds_word_forms(repo):
    reg = TR.build(repo, cfg_of())
    assert TR.find(reg, "helpers", cfg_of()["tools"])[0].id == "lib_two"      # helper ~ helpers (plural stripped)
    assert [t.id for t in TR.find(reg, "shar", cfg_of()["tools"])] == ["lib_two"]   # a word start still finds `shared`


# ---------------------------------------------------------------- the real repository

@pytest.fixture(scope="module")
def real():
    cfg = qa_settings()
    return cfg, TR.build(ROOT, cfg)


def test_real_repository_registry_is_documented_fresh_and_free_of_duplicates(real):
    cfg, reg = real
    res = TR.report(ROOT, cfg)
    assert res.status in ("ok", "warn"), res.detail
    assert res.metrics["undocumented"] == 0 and res.metrics["dup_suspects"] == 0 and res.metrics["stale"] == 0 and res.metrics["drift"] == 0
    assert res.metrics["tools"] >= 60
    pointers = [ln for ln in (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines() if "docs/TOOLS.md" in ln]
    assert len(pointers) == 1 and "tools --find" in pointers[0]                # exactly ONE pointer line in CLAUDE.md


def test_real_repository_every_qa_command_and_check_is_registered(real):
    cfg, reg = real
    ids = {t.id for t in reg.tools}
    assert {"ctx", "check", "tools", "test", "lua", "check:tools", "check:tests", "check:play:*", "rust:QaKernels", "agent_play"} <= ids
    assert {c["name"] for c in cfg["checks"]} <= {i.split(":", 1)[1] for i in ids if i.startswith("check:")}


def test_doc_size_stays_near_the_budget(real):
    cfg, reg = real
    assert TR.render(reg, cfg).count("\n") <= cfg["tools"]["max_lines"]


def test_cli_find_prints_at_most_eight_matches(capsys):
    import qa
    assert qa.main(["tools", "--find", "outline", "of", "a", "file"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert 1 <= len(lines) <= 8 and lines[0].startswith("ctx | python tools/qa.py ctx")
    assert qa.main(["tools", "--find", "zzzqqq"]) == 0
    assert capsys.readouterr().out.startswith("no tool matches")


def test_cli_report_line_and_machine_form(capsys):
    import qa
    assert qa.main(["tools", "--check"]) == 0
    line = capsys.readouterr().out.splitlines()[0]
    assert line.startswith("ok") and " tools tools=" in line and "undocumented=0" in line and "dup_suspects=0" in line and "stale=0" in line
    assert qa.main(["tools", "--result"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("RESULT status=OK tools=")


def test_the_check_is_declared_always_on_low_cost_and_in_ci():
    chk = {c["name"]: c for c in qa_settings()["checks"]}["tools"]
    assert chk["always"] is True and chk["cost"] == "low" and chk.get("ci", True) is True and chk["parse"] == "result_line"
    assert chk["cmd"] == "python tools/qa.py tools --result"
