import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import git_util  # noqa: E402


def _repo(tmp_path):
    for cmd in (["init", "-q"], ["config", "user.email", "a@b.c"], ["config", "user.name", "t"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    return tmp_path


def test_git_failure_is_empty_string(tmp_path):
    assert git_util.git("rev-parse", "HEAD", root=tmp_path) == ""
    assert git_util.head(tmp_path) == ""


def test_head_dirty_changed(tmp_path):
    repo = _repo(tmp_path)
    assert len(git_util.head(repo)) >= 7 and git_util.dirty(repo) == []
    (repo / "b.txt").write_text("2\n")
    (repo / "a.txt").write_text("3\n")
    assert sorted(git_util.dirty(repo)) == ["a.txt", "b.txt"]
    assert git_util.changed_files("HEAD", repo) == ["a.txt", "b.txt"]


def test_raw_keeps_leading_space(tmp_path):
    repo = _repo(tmp_path)
    (repo / "a.txt").write_text("3\n")
    assert git_util.git("status", "--porcelain", root=repo, raw=True).startswith(" M")
    assert git_util.git("status", "--porcelain", root=repo).startswith("M")
