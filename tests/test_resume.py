"""qa.py ckpt / resume: tmp git repos - orphans, broken files, verdicts, snapshots that never touch the tree, restore, prune, hooks, silence when clean."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import guard_hook as GH  # noqa: E402
from qa_plugins import ckpt as C  # noqa: E402
from qa_plugins import guard as GD  # noqa: E402
from qa_plugins import resume as R  # noqa: E402


def sh(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    sh(tmp_path, "init", "-q")
    sh(tmp_path, "config", "user.email", "t@t")
    sh(tmp_path, "config", "user.name", "t")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "used.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "tools" / "main.py").write_text("import used\n", encoding="utf-8")
    sh(tmp_path, "add", "-A")
    sh(tmp_path, "commit", "-qm", "init")
    return tmp_path


def status_of(root: Path) -> str:
    out = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=root, capture_output=True, text=True, check=True).stdout
    return "\n".join(ln for ln in out.splitlines() if "dev_probe_output" not in ln)      # the journal is git-ignored in the real repo


def test_clean_tree_is_silent_and_fast(repo, capsys):
    args = type("A", (), {"root": str(repo), "diff": None, "restore": None, "apply": False, "brief": False, "check": False})()
    t0 = time.perf_counter()
    assert R.cmd_resume(args) == 0
    assert capsys.readouterr().out == ""
    assert time.perf_counter() - t0 < 0.3


def test_orphan_and_imported_module(repo):
    (repo / "tools" / "orphan.py").write_text("Y = 2\n", encoding="utf-8")
    (repo / "tools" / "wired.py").write_text("Z = 3\n", encoding="utf-8")
    (repo / "tools" / "main.py").write_text("import used\nimport wired\n", encoding="utf-8")
    info = R.gather(repo)
    assert info["orphans"] == ["tools/orphan.py"]


def test_broken_file_and_verdicts(repo):
    (repo / "tools" / "used.py").write_text("X = = 1\n", encoding="utf-8")
    info = R.gather(repo)
    assert info["broken"] == ["tools/used.py"] and info["verdict"] == "BROKEN"
    (repo / "tools" / "used.py").write_text("X = 2\n", encoding="utf-8")
    assert R.gather(repo)["verdict"] == "RISKY"                     # dirty, no green check yet
    assert R.verdict_of([1], [], [], "ok") == "SAFE"
    assert R.verdict_of([1], [], ["a.py"], "ok") == "RISKY"
    assert R.verdict_of([1], [], [], "fail") == "BROKEN"


def test_snapshot_never_touches_tree_and_restore(repo, capsys):
    (repo / "tools" / "used.py").write_text("X = 99\n", encoding="utf-8")
    (repo / "tools" / "new.py").write_text("N = 1\n", encoding="utf-8")
    before = status_of(repo)
    row = C.save(repo, "half", "wire new.py", agent="t")
    assert row and row["n"] == 1 and len(row["dirty"]) == 2 and status_of(repo) == before
    assert json.loads((repo / "dev_probe_output/qa/journal.jsonl").read_text().splitlines()[-1])["next"] == "wire new.py"
    (repo / "tools" / "used.py").write_text("X = 0\n", encoding="utf-8")
    assert R.cmd_restore(repo, 1, False) == 0 and (repo / "tools" / "used.py").read_text() == "X = 0\n"
    assert R.cmd_restore(repo, 1, True) == 0 and (repo / "tools" / "used.py").read_text() == "X = 99\n"
    assert R.cmd_restore(repo, 7, False) == 1
    capsys.readouterr()


def test_auto_skips_clean_and_prune_keeps_last(repo, monkeypatch):
    assert C.save(repo, "", "", auto=True) is None
    monkeypatch.setattr(C, "cfg", lambda: {**C.DEFAULTS, "keep": 3})
    (repo / "tools" / "used.py").write_text("X = 5\n", encoding="utf-8")
    for i in range(5):
        C.save(repo, f"s{i}", "")
    refs = C.git(repo, "for-each-ref", "--format=%(refname)", C.REF).splitlines()
    assert sorted(r.rsplit("/", 1)[1] for r in refs) == ["3", "4", "5"]


def test_hooks_install_idempotent_and_session_event(repo, monkeypatch):
    once = GD.install({"permissions": {"x": 1}}, "py")
    twice = GD.install(once, "py")
    assert once == twice and {"SessionStart", "Stop", "SubagentStop"} <= set(GD.installed_events(once))
    assert GD.uninstall(once) == {"permissions": {"x": 1}}
    assert GH.session_event(b'{"hook_event_name":"PreToolUse"}') == ""
    assert GH.session_event(b'{"hook_event_name":"SessionStart"}', env={"AI_EVOLVE_GUARD": "off"}) == ""
    (repo / "tools" / "used.py").write_text("X = 8\n", encoding="utf-8")
    assert GH.session_event(b"not json", root=str(repo)) == ""
