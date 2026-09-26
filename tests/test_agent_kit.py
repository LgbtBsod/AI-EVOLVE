"""agent-kit (tools/agent_kit.py, `qa.py prompt`, `qa.py route`, lua_content/agent_kit.lua, docs/agent_context/*.md, .claude/agents/*.md).

Rendering (size cap, refusal, the report contract), validation of the data (bad model name, missing role file, zero budget, budget drift between the Lua row and the
role file, unknown placeholder / command), the generated agent files (stale detection), the Workflow snippet and the `qa.py pack` feature detection.
"""
import copy
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import agent_kit as AK
import lua_bridge
import qa

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

VALID_MODELS = {"sonnet", "opus", "haiku", "fable"}          # the `model` enum of the Agent tool / Workflow option / .claude/agents frontmatter
CHEAP_STAGES = {"run-tests", "summarise-log", "mechanical-edit", "grep-research"}
STRONG_STAGES = {"design", "judge", "adversarial-review"}
KNOWN = {"check", "test", "ctx", "tools", "brief", "prompt", "route", "changed", "lua", "item", "ci", "golden", "determinism", "quality", "guard", "ckpt", "resume", "sym", "q", "tokens", "pack", "static", "wf"}


@pytest.fixture(scope="module")
def real():
    return AK.load()


@pytest.fixture()
def cfg(real):
    return copy.deepcopy(real)


def run(capsys, *argv):
    code = qa.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


# ---------------------------------------------------------------- the data itself

def test_real_kit_is_valid_and_fresh(real):
    fails, warns = AK.validate(real)
    assert fails == [] and warns == []                     # includes: role files exist, budgets equal, templates fit, commands exist, .claude/agents fresh


def test_models_are_the_tool_enum_and_routes_follow_the_cost_rule(real):
    assert set(real["models"]) == VALID_MODELS
    by_stage = AK.routes(real)
    assert CHEAP_STAGES | STRONG_STAGES <= set(by_stage)
    assert all(by_stage[s]["model"] in {"haiku", "sonnet"} and by_stage[s]["effort"] == "low" for s in CHEAP_STAGES)
    assert all(by_stage[s]["model"] == "opus" and by_stage[s]["effort"] == "high" for s in STRONG_STAGES)
    assert all(by_stage[s]["model"] == "sonnet" and by_stage[s]["effort"] == "medium" for s in ("implement", "refactor", "rust-kernel"))


def test_role_budgets_match_the_spec(real):
    budgets = {name: int(r["max_calls"]) for name, r in AK.roles(real).items()}
    assert budgets == {"verifier": 15, "explorer": 25, "implementer": 45, "rust-kernel": 45, "stabilizer": 45, "reviewer": 25, "lua-content": 35}


def test_role_files_are_short_and_state_budget_hook_and_contract(real):
    for name, role in AK.roles(real).items():
        text = (ROOT / AK.role_file(real, name)).read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 35, name
        assert f"TURN BUDGET: {int(role['max_calls'])} tool calls" in text
        assert "RELAY: continue with qa.py resume" in text and "ckpt" in text
        assert all(re.search(rf"^{re.escape(ln)}", text, re.MULTILINE) for ln in AK.report_lines(real, role)), name


def test_every_command_named_in_the_agent_context_parses(real, capsys):
    used = set()
    for path in [ROOT / real["preamble"], *(ROOT / AK.role_file(real, n) for n in AK.roles(real))]:
        used |= set(AK.QA_CMD.findall(path.read_text(encoding="utf-8")))
    used -= set(real["planned"])
    assert {"check", "test", "ctx", "tools", "brief"} <= used
    for cmd in sorted(used):
        with pytest.raises(SystemExit) as exc:
            qa.main([cmd, "--help"])
        assert exc.value.code == 0, cmd
    capsys.readouterr()


# ---------------------------------------------------------------- validation catches the mistakes

def problems(cfg, root=ROOT):
    return AK.validate(cfg, root)[0]


def test_bad_model_name_is_reported(cfg):
    cfg["roles"][0]["model"] = "gpt-9"
    cfg["routes"][0]["escalate"] = "claude-nothing"
    text = "\n".join(problems(cfg))
    assert "role implementer: model 'gpt-9' is not one of" in text and "route run-tests: escalate 'claude-nothing'" in text


def test_bad_effort_and_zero_budget_are_reported(cfg):
    cfg["roles"][1]["max_calls"] = 0
    cfg["routes"][2]["max_calls"] = -3
    cfg["routes"][3]["effort"] = "ultra"
    text = "\n".join(problems(cfg))
    assert "role verifier: max_calls must be > 0" in text and "route mechanical-edit: max_calls must be > 0" in text and "route grep-research: effort 'ultra'" in text


def test_missing_role_file_is_reported(cfg, tmp_path):
    (tmp_path / "docs" / "agent_context").mkdir(parents=True)
    (tmp_path / cfg["preamble"]).write_text("preamble\n", encoding="utf-8")
    text = "\n".join(problems(cfg, tmp_path))
    assert "role implementer: docs/agent_context/implementer.md is missing" in text


def test_budget_in_the_role_file_must_equal_the_lua_row(cfg):
    cfg["roles"][0]["max_calls"] = 44
    text = "\n".join(problems(cfg))
    assert "`TURN BUDGET: N` must equal max_calls=44 (found 45)" in text


def test_role_file_over_the_line_limit_is_reported(cfg):
    cfg["max_role_lines"] = 20
    assert any("lines > max_role_lines=20" in p for p in problems(cfg))


def test_route_with_unknown_role_and_duplicates(cfg):
    cfg["routes"][0]["role"] = "ghost"
    cfg["routes"].append(dict(cfg["routes"][1]))
    text = "\n".join(problems(cfg))
    assert "role 'ghost' is not a role" in text and "stage 'summarise-log' is listed twice" in text


def test_multi_line_reason_is_rejected(cfg):
    cfg["routes"][0]["why"] = "line one\nline two"
    assert any("route run-tests: `why` must be one non-empty line" in p for p in problems(cfg))


def test_unknown_placeholder_and_oversize_template(cfg):
    bad = copy.deepcopy(cfg)
    bad["prompt"].append("NOTE: <nonsense>")
    assert any("unknown placeholder <nonsense>" in p for p in problems(bad))
    big = copy.deepcopy(cfg)
    big["prompt"].append("X" * 2000)
    assert any("prompt template alone is" in p for p in problems(big))


def test_unknown_command_fails_and_planned_command_that_exists_warns(cfg):
    fake = set(KNOWN) - {"pack"}
    cfg["planned"] = ["pack"]
    fails, warns = AK.command_problems(cfg, ROOT, known=fake)                      # `pack` is planned: no failure
    assert fails == [] and warns == []
    fails, _ = AK.command_problems(cfg, ROOT, known=fake - {"ci"})
    assert any("`qa.py ci` is named in the agent context" in f for f in fails)
    _, warns = AK.command_problems(cfg, ROOT, known=fake | {"pack"})
    assert any("`qa.py pack` exists now" in w for w in warns)


def test_malformed_data_is_a_problem_not_a_crash(cfg):
    del cfg["report"]
    fails, _ = AK.validate(cfg)
    assert fails and "is malformed" in fails[0]


# ---------------------------------------------------------------- rendering

def test_prompt_is_short_points_at_the_context_and_carries_the_contract(real):
    role = AK.roles(real)["implementer"]
    text = AK.render_prompt(real, role, "Implement roadmap step 2.", ["tools/a.py", "tests/test_a.py"], "the test passes")
    lines = text.splitlines()
    assert lines[0].startswith("Read docs/agent_context/preamble.md and docs/agent_context/implementer.md first")
    assert "TASK: Implement roadmap step 2." in lines and "SCOPE (files you may touch): tools/a.py, tests/test_a.py" in lines and "DONE WHEN: the test passes" in lines
    assert any(ln.startswith("BUDGET: 45 tool calls") and "ckpt" in ln for ln in lines)
    report = next(ln for ln in lines if ln.startswith("REPORT:"))
    assert "250 words" in report and "files:" in report and "results:" in report and "unfinished:" in report and "verbatim" in report
    assert AK.tokens(real, text) < 200 and len(text) < 900


def test_role_extras_scope_and_done_defaults(real):
    explorer = AK.render_prompt(real, AK.roles(real)["explorer"], "Where is X?")
    assert "SCOPE (files you may touch): read-only: edit nothing" in explorer and "answer:, files:, results:, unfinished:" in explorer
    reviewer = AK.render_prompt(real, AK.roles(real)["reviewer"], "Review.")
    assert "verdict:, files:, results:, unfinished:" in reviewer
    stabilizer = AK.render_prompt(real, AK.roles(real)["stabilizer"], "Fix main.")
    assert "only what the task needs" in stabilizer and "DONE WHEN: `qa.py check --all --no-cache` verdict is OK" in stabilizer


def test_task_text_is_not_scanned_for_placeholders(real):
    text = AK.render_prompt(real, AK.roles(real)["verifier"], "keep <role> and <max_calls> as typed")
    assert "TASK: keep <role> and <max_calls> as typed" in text


def test_prompt_command_prints_the_prompt_and_a_size_line(capsys):
    code, out, err = run(capsys, "prompt", "verifier", "--task", "Run qa.py check --all and report the header.")
    assert code == 0
    assert out.startswith("Read docs/agent_context/preamble.md and docs/agent_context/verifier.md first")
    assert re.match(r"ok\s+prompt role=verifier tok=\d+ max=400 chars=\d+ dur=", err)


def test_prompt_command_refuses_an_oversize_prompt_and_prints_the_count(capsys):
    code, out, err = run(capsys, "prompt", "implementer", "--task", "word " * 500)
    assert code == 1 and err == ""
    assert out.startswith("FAIL") and re.search(r"tok=\d{3,} max=400", out) and "shorten --task" in out
    assert "TASK:" not in out                                               # nothing to paste


def test_prompt_command_errors(capsys):
    code, out, _ = run(capsys, "prompt", "wizard", "--task", "x")
    assert code == 2 and out.startswith("ERROR") and "role 'wizard' is not one of: implementer, verifier" in out
    code, out, _ = run(capsys, "prompt", "verifier")
    assert code == 2 and "--task is required" in out


def test_files_and_done_flags(capsys):
    code, out, _ = run(capsys, "prompt", "implementer", "--task", "t", "--files", "a.py, b.py,,", "--done", "d is true")
    assert code == 0 and "SCOPE (files you may touch): a.py, b.py\n" in out and "DONE WHEN: d is true\n" in out


def test_workflow_snippet_is_three_lines_with_the_roles_routing(capsys):
    code, out, _ = run(capsys, "prompt", "--workflow", "verifier")
    lines = out.strip().splitlines()
    assert code == 0 and len(lines) == 3
    assert "docs/agent_context/preamble.md" in lines[1] and "docs/agent_context/verifier.md" in lines[1] and "Budget 15 tool calls" in lines[1]
    assert "model: 'haiku'" in lines[2] and "effort: 'low'" in lines[2] and "agentType: 'verifier'" in lines[2]
    assert "<" not in out.replace("<=", "")                                 # every placeholder was filled
    assert "\n" not in lines[1] and "CONTEXT" not in lines[1]               # no inlined context block: only the pointer


# ---------------------------------------------------------------- qa.py pack: feature detection

def fake_root(tmp_path, with_pack):
    (tmp_path / "tools" / "qa_plugins").mkdir(parents=True)
    if with_pack:
        (tmp_path / "tools" / "qa_plugins" / "pack.py").write_text("# pack\n", encoding="utf-8")
    return tmp_path


def test_pack_is_skipped_silently_when_the_tool_does_not_exist(tmp_path):
    calls = []
    root = fake_root(tmp_path, with_pack=False)
    assert not AK.pack_available(root)
    assert AK.pack_text("task", root, run=lambda *a, **k: calls.append(a)) == "" and calls == []


def test_pack_output_is_appended_when_the_tool_exists(tmp_path, real):
    root = fake_root(tmp_path, with_pack=True)
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="PACK: files a.py b.py\n", stderr="")

    pack = AK.pack_text("do the thing", root, run=fake_run)
    assert seen[0][-2:] == ["pack", "do the thing"] and pack.startswith("PACK:")
    text = AK.with_pack(real, "PROMPT", pack)
    assert text == f"PROMPT\n{real['pack_heading']}\nPACK: files a.py b.py"


@pytest.mark.parametrize("failure", ["rc", "oserror", "timeout"])
def test_a_failing_pack_never_breaks_the_prompt(tmp_path, failure):
    root = fake_root(tmp_path, with_pack=True)

    def fake_run(cmd, **kw):
        if failure == "oserror":
            raise OSError("no python")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(cmd, 1)
        return subprocess.CompletedProcess(cmd, 1, stdout="half an answer", stderr="boom")

    assert AK.pack_text("t", root, run=fake_run) == ""


def test_prompt_pack_flag_end_to_end(monkeypatch, capsys):
    monkeypatch.setattr(AK, "pack_text", lambda task, *a, **k: "PACK BODY")
    code, out, err = run(capsys, "prompt", "explorer", "--task", "where is X", "--pack")
    assert code == 0 and out.rstrip().endswith("PACK BODY") and "CONTEXT PACK" in out and "pack=9chars" in err
    monkeypatch.setattr(AK, "pack_text", lambda task, *a, **k: "")
    code, out, err = run(capsys, "prompt", "explorer", "--task", "where is X", "--pack")
    assert code == 0 and "CONTEXT PACK" not in out and "pack=none" in err     # requested, nothing to add: no error


# ---------------------------------------------------------------- generated .claude/agents/*.md

def frontmatter(text):
    head = text.split("---\n")[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


def test_generated_agent_files_have_the_documented_frontmatter(real):
    for path, text in AK.agent_files(real).items():
        fm = frontmatter(text)
        role = AK.roles(real)[path.stem]
        assert list(fm) == ["name", "description", "tools", "model", "effort", "maxTurns"]
        assert fm["name"] == role["name"] and fm["model"] in VALID_MODELS and fm["tools"] == role["tools"]
        assert fm["maxTurns"] == str(math.ceil(int(role["max_calls"]) * 1.2)) and fm["description"].startswith('"')
        body = text.split("---\n", 2)[2]
        assert AK.GENERATED in body and f"{role['name']}.md" in body and "\r" not in text
    assert (ROOT / ".claude" / "agents" / "verifier.md").read_text(encoding="utf-8") == AK.agent_text(real, AK.roles(real)["verifier"])


def test_stale_detection_and_rewrite(cfg, tmp_path):
    assert len(AK.stale_agents(cfg, tmp_path)) == 7                          # nothing written yet: seven missing files
    assert len(AK.write_agents(cfg, tmp_path)) == 7
    assert AK.stale_agents(cfg, tmp_path) == [] and AK.write_agents(cfg, tmp_path) == []      # idempotent
    agent = tmp_path / ".claude" / "agents" / "verifier.md"
    agent.write_text(agent.read_text(encoding="utf-8").replace("model: haiku", "model: opus"), encoding="utf-8", newline="\n")
    assert AK.stale_agents(cfg, tmp_path) == [".claude/agents/verifier.md differs from lua_content/agent_kit.lua"]
    agent.write_bytes(AK.agent_text(cfg, AK.roles(cfg)["verifier"]).replace("\n", "\r\n").encode())
    assert AK.stale_agents(cfg, tmp_path) == []                              # a CRLF checkout is not drift
    cfg["roles"][1]["model"] = "sonnet"                                      # the Lua data moved on
    assert AK.stale_agents(cfg, tmp_path) == [".claude/agents/verifier.md differs from lua_content/agent_kit.lua"]
    assert AK.write_agents(cfg, tmp_path) == [".claude/agents/verifier.md"]


def test_orphan_generated_file_is_stale_but_hand_written_ones_are_left_alone(cfg, tmp_path):
    AK.write_agents(cfg, tmp_path)
    folder = tmp_path / ".claude" / "agents"
    (folder / "mine.md").write_text("---\nname: mine\ndescription: hand-written\n---\nhello\n", encoding="utf-8")
    assert AK.stale_agents(cfg, tmp_path) == []
    (folder / "gone.md").write_text(f"---\nname: gone\ndescription: x\n---\n{AK.GENERATED} from ...\n", encoding="utf-8")
    assert AK.stale_agents(cfg, tmp_path) == [".claude/agents/gone.md was generated for a role that no longer exists"]


def test_route_check_fails_on_stale_agents_and_write_agents_repairs(cfg, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(AK, "ROOT", tmp_path)                               # the route command reads AK.ROOT at call time
    monkeypatch.setattr(AK, "load", lambda root=tmp_path: cfg)
    monkeypatch.setattr(AK, "known_commands", lambda root=tmp_path: set(KNOWN))
    (tmp_path / "docs" / "agent_context").mkdir(parents=True)
    for name in ("preamble.md", *(f"{n}.md" for n in AK.roles(cfg))):
        (tmp_path / "docs" / "agent_context" / name).write_text((ROOT / "docs" / "agent_context" / name).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    code, out, _ = run(capsys, "route", "--check")
    assert code == 1 and out.startswith("FAIL") and "fresh=no" in out and "stale: .claude/agents/" in out
    code, out, _ = run(capsys, "route", "--write-agents")
    assert code == 0 and out.startswith("ok") and "written=7" in out and "restart the harness" in out
    code, out, _ = run(capsys, "route", "--check")
    assert code == 0 and out.startswith("ok") and "fresh=yes" in out


# ---------------------------------------------------------------- qa.py route

def test_route_list_shows_every_stage_and_role(capsys, real):
    code, out, _ = run(capsys, "route", "--list")
    lines = out.splitlines()
    assert code == 0 and lines[0].startswith("ok     route stages=12 roles=7 models=haiku,sonnet,opus")
    for stage in AK.routes(real):
        assert any(ln.split()[:1] == [stage] for ln in lines), stage
    assert lines[1].split()[:3] == ["stage", "role", "model"] and len(lines) <= 30


def test_route_row_and_unknown_stage(capsys):
    code, out, _ = run(capsys, "route", "adversarial-review")
    assert code == 0 and "role=reviewer model=opus effort=high calls=25" in out and "why:" in out
    code, out, _ = run(capsys, "route", "implment")
    assert code == 2 and out.startswith("ERROR") and "closest: implement" in out


def test_route_check_passes_on_the_repo(capsys):
    code, out, _ = run(capsys, "route", "--check")
    assert code == 0 and out.startswith("ok     route roles=7 routes=12 agents=7 fresh=yes")


def test_route_check_result_is_the_machine_form_and_the_check_is_declared(capsys):
    code, out, _ = run(capsys, "route", "--check", "--result")
    assert code == 0 and out.strip().splitlines()[-1].startswith("RESULT status=OK roles=7 routes=12 agents=7 fresh=yes")
    from probe_settings import qa_settings
    check = next(c for c in qa_settings()["checks"] if c["name"] == "agent_kit")
    assert check["cmd"] == "python tools/qa.py route --check --result" and check["parse"] == "result_line"
    assert {"docs/agent_context/**", ".claude/agents/**", "lua_content/agent_kit.lua"} <= set(check["watches"])     # a Markdown-only edit selects the check
