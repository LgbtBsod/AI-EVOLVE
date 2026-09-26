"""qa.py ci: the log/JSON parser on trimmed real CI logs (tests/fixtures/ci). No network: `ci.gh` is replaced."""
import argparse
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import qa  # noqa: E402
import qa_report as R  # noqa: E402
from qa_plugins import ci  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "ci"


def log(name):
    return (FIX / f"{name}.log").read_text(encoding="utf-8")


def run_json(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def blocks(name, per_block=8):
    return ci.make_blocks(ci.group_steps(ci.clean_log(log(name))), per_block)


def one_block(name):
    (blk,) = blocks(name)
    return blk, ci.block_lines(blk)


# ---------------------------------------------------------------- cleaning

def test_clean_log_strips_prefix_timestamp_ansi_and_bom():
    entries = ci.clean_log(log("windows_lua_crlf"))
    job, step, first = entries[0]
    assert (job, step) == ("rust_core (windows-latest)", "Lua bridge parity (mlua vs lupa)")
    assert first == "##[group]Run python -m pytest -q tests/test_lua_bridge.py"      # no BOM, no timestamp
    assert entries[1][2] == "python -m pytest -q tests/test_lua_bridge.py"           # ANSI colour codes gone
    text = "\n".join(t for _j, _s, t in entries)
    assert "\x1b" not in text and chr(0xFEFF) not in text and not re.search(r"^\d{4}-\d\d-\d\dT", text, re.MULTILINE)
    assert ci.clean_log("plain line\r\nsecond\r\n") == [("", "", "plain line"), ("", "", "second")]     # raw (non gh) text too


def test_group_steps_keeps_order_and_separates_jobs():
    steps = ci.group_steps(ci.clean_log(log("linux_pytest_diff") + log("windows_lua_crlf")))
    assert list(steps) == [("Game (ubuntu-latest)", "Agent + QA tools (agent_play / dev_probe --render none --fast / probe_db / qa.py)"),
                           ("rust_core (windows-latest)", "Lua bridge parity (mlua vs lupa)")]


# ---------------------------------------------------------------- extraction on the real failures

def test_linux_pytest_assertion_diff_without_the_full_diff_noise():
    blk, lines = one_block("linux_pytest_diff")
    assert lines[0] == ("FAIL Game (ubuntu-latest) > Agent + QA tools (agent_play / dev_probe --render none --fast / pro..."
                        "  [python -m pytest -q tests/test_agent_tools.py tests/test_qa_tools.py] exit=1")
    assert lines[1].startswith("  FAILED tests/test_agent_tools.py::TestRealGame::test_agent_play_is_deterministic - AssertionError")
    assert lines[2].startswith("  E AssertionError: assert ({'t': 8.07")
    assert lines[3].startswith("    At index 0 diff: {'t': 8.07, 'hp': 116.1")
    assert lines[4] == "  at tests/test_agent_tools.py:232: AssertionError"
    assert lines[5] == "  1 failed, 44 passed, 3 skipped in 9.02s"
    assert len(lines) <= 8
    joined = "\n".join(lines)
    assert "Full diff" not in joined and "'nearest': 31.9" not in joined and "'pos': [" not in joined     # pytest's object dump is dropped
    assert "##[error]" not in joined and "Process completed" not in joined


def test_windows_lua_crlf_mismatch():
    blk, lines = one_block("windows_lua_crlf")
    assert lines[0] == "FAIL rust_core (windows-latest) > Lua bridge parity (mlua vs lupa)  [python -m pytest -q tests/test_lua_bridge.py] exit=1"
    assert lines[1].startswith("  FAILED tests/test_lua_bridge.py::test_export_lua_is_shared_between_backends - assert '-- ")
    assert lines[2].startswith("  E assert '-- ") and re.search(r"\\+r\\+n'", lines[1] + lines[2])     # the visible CRLF-vs-LF clue is kept
    diff = [ln for ln in lines if ln.startswith("    ")]
    assert len(diff) == 3 and diff[0].strip() == "Skipping 62 identical leading characters in diff, use -v to show"
    assert not any(ln.strip().startswith("?") for ln in lines)                                # pytest's `?` marker lines are dropped
    assert lines[-2] == "  at tests\\test_lua_bridge.py:105: AssertionError" and lines[-1] == "  1 failed, 44 passed in 0.32s"
    assert len(lines) <= 8


def test_cargo_errors_with_file_and_line():
    blk, lines = one_block("cargo_error")
    assert lines == ["FAIL rust_core (ubuntu-latest) > cargo test exit=101",
                     "  error[E0432] src/simulation/pathfinding.rs:14 unresolved import `crate::simulation::flowfield`",
                     "  error[E0308] src/analytics/mod.rs:88 mismatched types",
                     "  error: could not compile `rust_core` (lib) due to 2 previous errors"]


def test_python_traceback_last_frame_and_exception_plus_tool_result_line():
    blk, lines = one_block("traceback")
    assert lines[0] == "FAIL Game (macos-latest) > Boot test (GameCore -> menu/world -> plugins, offscreen)  [python tools/boot_smoke_test.py] exit=1"
    assert lines[1] == "  Traceback src/core/game_core.py:204 in boot -> KeyError: 'game_world'"      # runner workspace prefix removed
    assert lines[2] == "  RESULT status=FAIL scene=None enemies=0->0 errors=1"


def test_our_own_qa_lines_are_extracted_from_a_failed_check_step():
    blk, lines = one_block("qa_check_fail")
    assert lines[1].startswith("  QA verdict=FAIL checks=8 ok=7 fail=1")
    assert lines[2].startswith("  FAIL play:melee_three hp=0.0/140.0") and len(lines) <= 8
    assert not any(ln.strip().startswith("ok ") for ln in lines)                                    # passing check lines are not repeated


def test_result_lines_from_the_real_determinism_run():
    blk, lines = one_block("determinism_failed")
    assert lines[1] == "  RESULT determinism pairs=80 diverged=2 classes=2 first_frame=0 t=0.03 channel=rng"
    assert "exit=1" in lines[0] and "[python tools/qa.py determinism" in lines[0]


def test_errors_lines_are_deduplicated_and_capped():
    text = "\n".join(["##[group]Run pip install x", "ERROR: Could not find a version", "ERROR: Could not find a version",
                      "Error: second problem", "ERROR: third", "ERROR: fourth", "##[error]Process completed with exit code 1."])
    kinds = ci.essentials(text.splitlines())
    assert [t for k, t in kinds if k == "error"] == ["ERROR: Could not find a version", "Error: second problem", "ERROR: third"]
    assert ci.exit_code_of(text.splitlines()) == "1" and ci.command_of(text.splitlines()) == "pip install x"


def test_more_than_five_failed_tests_are_summarised():
    lines = [f"FAILED tests/t.py::test_{i} - assert {i}" for i in range(8)]
    failed = [t for k, t in ci.essentials(lines) if k == "failed"]
    assert len(failed) == 6 and failed[-1] == "(+3 more FAILED)"


def test_unrecognised_failure_falls_back_to_the_last_lines():
    lines = ["##[group]Run ./deploy.sh", "starting", "step one", "step two", "step three", "step four", "boom happened", "##[error]Process completed with exit code 2."]
    assert [t for _k, t in ci.essentials(lines)] == ["step two", "step three", "step four", "boom happened"]


def test_the_same_failure_on_several_jobs_is_one_block_and_the_line_budget_is_kept():
    base = log("linux_pytest_diff")
    other = base.replace("Game (ubuntu-latest)", "Game (macos-latest)")
    bl = ci.make_blocks(ci.group_steps(ci.clean_log(base + other)))
    assert len(bl) == 1 and bl[0]["jobs"] == ["Game (ubuntu-latest)", "Game (macos-latest)"]
    assert ci.block_lines(bl[0])[0].startswith("FAIL Game (ubuntu-latest), Game (macos-latest) > ")
    assert len(ci.block_lines(ci.make_blocks(ci.group_steps(ci.clean_log(log("windows_lua_crlf"))), per_block=4)[0])) == 4     # --lines 4


# ---------------------------------------------------------------- the run header and the whole report

def test_header_for_a_green_and_a_red_run():
    assert ci.header(run_json("run_ok")) == "CI verdict=OK run=35990063693 wf=CI sha=1d147e1 jobs=6 ok=6 fail=0 dur=3m49s"
    red = ci.header(run_json("run_failed"))
    assert red == "CI verdict=FAIL run=35988866453 wf=Determinism_probe sha=16aa2e7 jobs=3 ok=2 fail=1 dur=2m35s"
    running = {**run_json("run_ok"), "status": "in_progress", "conclusion": None,
               "jobs": [{"name": "a", "status": "in_progress", "conclusion": None}, {"name": "b", "status": "completed", "conclusion": "success"}]}
    assert ci.header(running).startswith("CI verdict=RUNNING run=35990063693 wf=CI sha=1d147e1 jobs=2 ok=1 fail=0 running=1 dur=")
    assert ci.verdict_of({**run_json("run_ok"), "conclusion": "cancelled", "jobs": []}) == "CANCELLED"


def test_a_cancelled_job_is_not_a_failure():
    run = run_json("run_ok")
    jobs = [dict(j) for j in run["jobs"]]
    jobs[0]["conclusion"] = "cancelled"
    run = {**run, "conclusion": "cancelled", "jobs": jobs}
    assert ci.verdict_of(run) == "CANCELLED"
    assert "cancelled=1" in ci.header(run) and "fail=0" in ci.header(run)


def test_report_for_a_failed_run_is_short_and_points_at_the_full_log():
    lines = ci.build_report(run_json("run_failed"), log("determinism_failed"), 8, 30, "dev_probe_output/qa/ci_35988866453.log")
    assert lines[0].startswith("CI verdict=FAIL run=35988866453")
    assert lines[1].startswith("FAIL determinism (windows-latest) > Same-seed pairs")
    assert lines[-1] == "full log: dev_probe_output/qa/ci_35988866453.log" and len(lines) <= 30
    assert ci.build_report(run_json("run_ok"), None) == [ci.header(run_json("run_ok"))]            # green run: exactly one line


def test_report_without_log_text_still_names_the_failed_step():
    lines = ci.build_report(run_json("run_failed"), None, log_path=None)
    assert lines[1] == "FAIL determinism (windows-latest) > Same-seed pairs (normal, ASLR off where available, hash seed 0)"
    assert lines[2].startswith("  (no log text: gh run view 35988866453 --log-failed)")


def test_many_failed_jobs_are_cut_with_a_pointer():
    log_text = "".join(
        f"job{i}\tstep{i}\t2026-09-24T09:50:00.0000000Z FAILED tests/t.py::test_{i} - assert {i}\n"
        f"job{i}\tstep{i}\t2026-09-24T09:50:00.0000000Z E   assert {i}\n" * 1 for i in range(12))
    run = {**run_json("run_failed"), "jobs": [{"name": f"job{i}", "status": "completed", "conclusion": "failure", "steps": []} for i in range(12)]}
    lines = ci.build_report(run, log_text, 8, 12, "dev_probe_output/qa/ci_1.log")
    assert len(lines) <= 12 and lines[-2].startswith("(+") and "more failed step(s)" in lines[-2]


def test_dump_log_groups_by_step():
    text = ci.dump_log(ci.clean_log(log("cargo_error")))
    assert text.startswith("=== rust_core (ubuntu-latest) > cargo test ===\n##[group]Run cargo test\n") and "\x1b" not in text


# ---------------------------------------------------------------- the command, with `gh` replaced by fixtures

class FakeGh:
    def __init__(self, runs=None, run=None, log_text=None, statuses=()):
        self.runs, self.run, self.log_text, self.calls = runs, run, log_text, []
        self.statuses = list(statuses)

    def __call__(self, *args, timeout=120):
        self.calls.append(args)
        if args[:2] == ("run", "list"):
            return 0, json.dumps(self.runs), ""
        if args[:2] == ("run", "view") and "--log-failed" in args:
            return (0, self.log_text, "") if self.log_text is not None else (1, "", "log expired")
        if args[:2] == ("run", "view") and args[3:] == ("--json", "status,conclusion"):
            st = self.statuses.pop(0) if self.statuses else "completed"
            return 0, json.dumps({"status": st, "conclusion": "failure" if st == "completed" else None}), ""
        if args[:2] == ("run", "view"):
            return 0, json.dumps(self.run), ""
        raise AssertionError(args)


@pytest.fixture
def qa_out(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "QA_OUT", tmp_path / "qa")
    return tmp_path / "qa"


def run_ci(capsys, *argv):
    code = qa.main(["ci", *argv])
    return code, capsys.readouterr().out.splitlines()


def test_latest_run_ok(monkeypatch, capsys, qa_out):
    fake = FakeGh(runs=json.loads((FIX / "runs_list.json").read_text(encoding="utf-8")), run=run_json("run_ok"))
    monkeypatch.setattr(ci, "gh", fake)
    code, out = run_ci(capsys, "--latest")
    assert code == 0 and out == ["CI verdict=OK run=35990063693 wf=CI sha=1d147e1 jobs=6 ok=6 fail=0 dur=3m49s"]
    assert fake.calls[0][:3] == ("run", "list", "--limit") and not any("--log-failed" in c for c in fake.calls)   # no log fetched for a green run


def test_failed_run_prints_blocks_and_saves_the_cleaned_log(monkeypatch, capsys, qa_out):
    fake = FakeGh(run=run_json("run_failed"), log_text=log("determinism_failed"))
    monkeypatch.setattr(ci, "gh", fake)
    code, out = run_ci(capsys, "--run", "35988866453")
    assert code == 1 and out[0].startswith("CI verdict=FAIL run=35988866453") and len(out) <= 30
    saved = qa_out / "ci_35988866453.log"
    assert out[-1] == f"full log: {saved.as_posix()}" and saved.is_file()
    text = saved.read_text(encoding="utf-8")
    assert "RESULT determinism pairs=80 diverged=2" in text and "\x1b" not in text and "Z RESULT" not in text


def test_sha_lookup_reports_failing_sibling_workflows(monkeypatch, capsys, qa_out):
    runs = json.loads((FIX / "runs_list.json").read_text(encoding="utf-8"))
    sib = {**runs[0], "databaseId": 99, "workflowName": "Determinism probe", "conclusion": "failure"}
    fake = FakeGh(runs=[runs[0], sib], run=run_json("run_ok"))
    monkeypatch.setattr(ci, "gh", fake)
    code, out = run_ci(capsys, "--sha", "1d147e1")
    assert out[1] == "also: Determinism_probe=FAILURE(99)" and "--commit" in fake.calls[0]


def test_wait_polls_quietly_and_prints_the_final_block_once(monkeypatch, capsys, qa_out):
    fake = FakeGh(run=run_json("run_failed"), log_text=log("determinism_failed"), statuses=["queued", "in_progress", "in_progress", "completed"])
    slept = []
    monkeypatch.setattr(ci, "gh", fake)
    monkeypatch.setattr(ci.time, "sleep", lambda s: slept.append(s))
    code, out = run_ci(capsys, "--run", "35988866453", "--wait", "--poll", "7")
    polls = [c for c in fake.calls if c[3:] == ("--json", "status,conclusion")]
    assert len(polls) == 4 and slept == [7.0, 7.0, 7.0]
    assert code == 1 and sum(1 for ln in out if ln.startswith("CI verdict=")) == 1        # nothing printed while waiting


def test_wait_gives_up_after_the_timeout(monkeypatch, capsys, qa_out):
    fake = FakeGh(run=run_json("run_ok"), statuses=["in_progress"] * 50)
    monkeypatch.setattr(ci, "gh", fake)
    monkeypatch.setattr(ci.time, "sleep", lambda s: None)
    code, out = run_ci(capsys, "--run", "1", "--wait", "--poll", "10", "--timeout", "30")
    assert code == 2 and out == ["CI verdict=TIMEOUT run=1 waited=30s (still running)"]


def test_running_run_has_its_own_exit_code(monkeypatch, capsys, qa_out):
    running = {**run_json("run_ok"), "status": "in_progress", "conclusion": None}
    monkeypatch.setattr(ci, "gh", FakeGh(run=running))
    code, out = run_ci(capsys, "--run", "1")
    assert code == 3 and out[0].startswith("CI verdict=RUNNING")


def test_missing_gh_is_one_helpful_line(monkeypatch, capsys):
    real_run = ci.subprocess.run

    def no_gh(cmd, *a, **k):
        if cmd[0] == "gh":
            raise FileNotFoundError("gh")
        return real_run(cmd, *a, **k)
    monkeypatch.setattr(ci.subprocess, "run", no_gh)
    code, out = run_ci(capsys, "--latest")
    assert code == 2 and out == ["CI verdict=ERROR gh CLI not found - install https://cli.github.com/ then run `gh auth login`"]


def test_gh_errors_and_empty_history_are_one_line(monkeypatch, capsys):
    monkeypatch.setattr(ci, "gh", lambda *a, **k: (1, "", "To get started with GitHub CLI, please run:  gh auth login\nmore text"))
    code, out = run_ci(capsys, "--latest")
    assert code == 2 and out == ["CI verdict=ERROR To get started with GitHub CLI, please run:  gh auth login"]
    monkeypatch.setattr(ci, "gh", lambda *a, **k: (0, "[]", ""))
    code, out = run_ci(capsys, "--sha", "abc")
    assert code == 2 and out == ["CI verdict=ERROR no workflow runs found for abc"]


def test_expired_logs_degrade_to_step_names(monkeypatch, capsys, qa_out):
    monkeypatch.setattr(ci, "gh", FakeGh(run=run_json("run_failed"), log_text=None))
    code, out = run_ci(capsys, "--run", "35988866453")
    assert code == 1 and out[1].startswith("FAIL determinism (windows-latest) > Same-seed pairs") and "no log text" in out[2]
    assert not any(ln.startswith("full log:") for ln in out)


def test_parser_arguments():
    p = argparse.ArgumentParser()
    ci.register(p.add_subparsers())
    a = p.parse_args(["ci", "--sha", "HEAD", "--wait", "--lines", "12", "--workflow", "CI"])
    assert (a.sha, a.wait, a.lines, a.workflow, a.run) == ("HEAD", True, 12, "CI", None)
