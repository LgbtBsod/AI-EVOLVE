"""qa.py bisect: _Reverted's file swap/restore, and _narrow's binary search, in isolation (no real agent_play run)."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("qa_plugin_bisect", Path(__file__).resolve().parents[1] / "tools" / "qa_plugins" / "bisect.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)


def _git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    return repo


def test_same_compares_only_shared_numeric_fields():
    assert B._same({"dealt": 1.0, "taken": 2.0}, {"dealt": 1.0, "taken": 2.0, "extra": "x"})
    assert not B._same({"dealt": 1.0}, {"dealt": 2.0})
    assert not B._same({"status": "OK"}, {"status": "OK"})           # no shared NUMERIC field -> not comparable
    assert not B._same(None, {"dealt": 1.0})


def test_reverted_restores_modified_and_new_files(tmp_path):
    repo = _git_repo(tmp_path)
    f = repo / "f.txt"
    f.write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    f.write_text("changed", encoding="utf-8")
    new = repo / "new.txt"
    new.write_text("brand new", encoding="utf-8")

    with B._Reverted(["f.txt", "new.txt"], "HEAD", repo):
        assert f.read_text(encoding="utf-8") == "base"
        assert not new.is_file()                                    # did not exist at HEAD -> removed for the test
    assert f.read_text(encoding="utf-8") == "changed"
    assert new.read_text(encoding="utf-8") == "brand new"


def test_narrow_isolates_the_single_culprit_file(monkeypatch):
    culprit = "b.py"
    files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
    target = {"dealt": 100.0}
    reverted_now = []

    class FakeReverted:
        def __init__(self, paths, base, root):
            self.paths = paths

        def __enter__(self):
            reverted_now[:] = self.paths
            return self

        def __exit__(self, *exc):
            reverted_now.clear()
            return False

    def fake_run(cwd, script, seed):
        return target if culprit in reverted_now else {"dealt": 999.0}

    monkeypatch.setattr(B, "_Reverted", FakeReverted)
    monkeypatch.setattr(B, "run_scenario", fake_run)
    assert B._narrow(files, "HEAD", "script", 1, target) == [culprit]


def test_narrow_gives_up_cleanly_when_only_the_full_set_works(monkeypatch):
    files = ["a.py", "b.py", "c.py", "d.py"]
    target = {"dealt": 100.0}

    monkeypatch.setattr(B, "_Reverted", lambda paths, base, root: __import__("contextlib").nullcontext())
    monkeypatch.setattr(B, "run_scenario", lambda cwd, script, seed: {"dealt": 999.0})   # no half ever matches
    assert B._narrow(files, "HEAD", "script", 1, target) == files
