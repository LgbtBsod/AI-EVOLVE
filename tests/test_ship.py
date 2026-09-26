"""qa.py ship: temp repo + bare temp remote (no network, no CI)."""
import argparse
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from qa_plugins import ship

OK_LINES = ["QA verdict=OK checks=3 ok=2 fail=0 warn=1", "ok     x"]


def g(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    bare, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    work.mkdir()
    g(work, "init", "-q", "-b", "main")
    g(work, "config", "user.email", "t@example.com")
    g(work, "config", "user.name", "t")
    g(work, "config", "commit.gpgsign", "false")
    (work / "a.txt").write_text("a\n")
    g(work, "add", ".")
    g(work, "commit", "-qm", "init")
    g(work, "remote", "add", "origin", str(bare))
    g(work, "push", "-q", "-u", "origin", "main")
    return work


def args(**kw):
    base = {"message": "msg", "paths": None, "all": False, "no_ci": True, "dry_run": False}
    return argparse.Namespace(**{**base, **kw})


def ok_check(_all):
    return 0, OK_LINES


def test_ok_path_commits_pushes_and_honours_exclude(repo, capsys):
    (repo / "b.txt").write_text("b\n")
    (repo / "junk.pyc").write_text("x")
    (repo / ".env").write_text("SECRET=1")
    (repo / "dev_probe_output").mkdir()
    (repo / "dev_probe_output" / "r.txt").write_text("x")
    assert ship.cmd_ship(args(), root=repo, check_fn=ok_check) == 0
    out = capsys.readouterr().out
    assert "SHIP verdict=OK" in out and "files=1" in out and "check=OK(2/3 warn=1)" in out and "ci=skipped" in out
    assert g(repo, "show", "--name-only", "--format=%B", "HEAD").splitlines()[-1] == "b.txt"
    assert "Co-Authored-By: Claude Sonnet 5" in g(repo, "log", "-1", "--format=%B")
    assert g(repo, "rev-parse", "HEAD") == g(repo, "rev-parse", "origin/main")


def test_failing_check_stops_before_staging(repo, capsys):
    (repo / "b.txt").write_text("b\n")
    bad = ["QA verdict=FAIL checks=2 ok=1 fail=1", "FAIL   play:x hp=0 | repro: python tools/agent_play.py x", "ok     y"]
    assert ship.cmd_ship(args(), root=repo, check_fn=lambda a: (1, bad)) == 1
    out = capsys.readouterr().out
    assert "FAIL   play:x" in out and "ok     y" not in out and "repro:" in out
    assert g(repo, "diff", "--cached", "--name-only") == ""
    assert g(repo, "rev-list", "--count", "HEAD") == "1"


def test_behind_origin_refused(repo, tmp_path, capsys):
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "remote.git"), str(other)], check=True)
    g(other, "config", "user.email", "t@example.com")
    g(other, "config", "user.name", "t")
    (other / "c.txt").write_text("c\n")
    g(other, "add", ".")
    g(other, "commit", "-qm", "c")
    g(other, "push", "-q", "origin", "main")
    (repo / "b.txt").write_text("b\n")
    assert ship.cmd_ship(args(), root=repo, check_fn=ok_check) == 1
    assert "behind origin/main" in capsys.readouterr().out
    assert g(repo, "rev-list", "--count", "HEAD") == "1"


def test_wrong_branch_and_dry_run(repo, capsys):
    (repo / "b.txt").write_text("b\n")
    assert ship.cmd_ship(args(dry_run=True), root=repo, check_fn=ok_check) == 0
    assert "DRY-RUN would stage files=1" in capsys.readouterr().out
    assert g(repo, "diff", "--cached", "--name-only") == "" and g(repo, "rev-list", "--count", "HEAD") == "1"
    g(repo, "checkout", "-q", "-b", "feature")
    assert ship.cmd_ship(args(), root=repo, check_fn=ok_check) == 1
    assert "not in ship.branches" in capsys.readouterr().out


def test_choose_paths_and_exclude():
    keep, dropped = ship.choose("src,x.txt", ["src/a.py", "src/b.pyc", "x.txt", "y.txt"], ["*.pyc"])
    assert keep == ["src/a.py", "x.txt"] and dropped == ["src/b.pyc"]
