"""Repo hygiene guard (tools/repo_hygiene.py, `hygiene` check of lua_content/qa.lua): tracked junk and a .gitignore that lost its patterns.

Real temporary git repositories (`git init` + `git add -f`, no commits, no network): the check reads the index, so that is all it needs.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import repo_hygiene as RH  # noqa: E402
from probe_settings import qa_settings  # noqa: E402
from qa_plugins import check as C  # noqa: E402

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

# what the task / CLAUDE.md promise the guard covers: qa.lua must never lose one of these
MUST_FORBID = {".venv*/", "target/", "*.so", "*.pyd", "*.pyc", "saves/*.db", "dev_probe_output/"}
MUST_REQUIRE = {".venv-*/", ".venv/", "target/", "dev_probe_output/", "saves/*.db", "__pycache__/", "*.pyc", "*.so", "*.pyd", "build/", "dist/"}


@pytest.fixture(scope="module")
def cfg():
    return qa_settings()["hygiene"]


GOOD_IGNORE = "\n".join(["# junk", "__pycache__/", "*.py[cod]", ".venv/", ".venv-*/", "venv/", "target/", "build/", "dist/", "*.so",
                         "*.pyd", "saves/*.db", "dev_probe_output/", ""])


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def make_repo(root: Path, ignore: str | None = GOOD_IGNORE, files: dict | None = None) -> Path:
    git(root, "init", "-q")
    if ignore is not None:
        (root / ".gitignore").write_text(ignore, encoding="utf-8")
    for name, content in (files or {"src/game.py": "print('hi')\n", "README.md": "# game\n"}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    git(root, "add", "-A", "-f" if ignore is None else "--")           # -f: with no .gitignore nothing hides the junk anyway
    return root


# ---------------------------------------------------------------- the config (the promise)

def test_qa_lua_keeps_every_promised_pattern(cfg):
    assert MUST_FORBID <= set(cfg["forbidden"]) and MUST_REQUIRE <= set(cfg["required_ignore"])
    assert cfg["max_file_kb"] <= 1024


def test_hygiene_is_a_fast_check_that_runs_in_qa_check_and_ci():
    chk = C.load_registry()["hygiene"]
    assert chk.cost == "low" and chk.ci and chk.always and chk.spec["parse"] == "result_line"
    assert chk.spec["cmd"] == "python tools/qa.py hygiene --result"


# ---------------------------------------------------------------- the matcher

@pytest.mark.parametrize("path,rules,expected", [
    ("pkg/__pycache__/a.cpython-312.pyc", ["__pycache__/"], True),
    ("a.pyc", ["__pycache__/"], False),
    ("pkg/a.pyc", ["*.py[cod]"], True),                         # char class
    (".venv-x/lib/site.py", [".venv-*/"], True),                # a directory rule ignores everything below
    (".venv", [".venv/"], False),                               # a FILE named like the directory is not the directory
    ("src/target/x.txt", ["target/"], True),                    # unanchored: any depth
    ("saves/game.db", ["saves/*.db"], True),
    ("other/saves/game.db", ["saves/*.db"], False),             # a `/` inside anchors the rule to the root
    ("saves/sub/game.db", ["saves/*.db"], False),               # `*` does not cross `/`
    ("a/b/c.txt", ["/a/**/c.txt"], True),
    ("keep/a.pyc", ["*.pyc", "!keep/a.pyc"], False),            # `!` re-includes (last rule wins)
    ("docs/build/index.html", ["build/"], True),
])
def test_ignored_matches_gitignore_semantics(path, rules, expected):
    assert RH.ignored(path, rules) is expected


def test_required_pattern_is_covered_semantically_not_by_spelling():
    rules = RH.parse_ignore(GOOD_IGNORE)
    assert all(RH.ignored(RH.sample_path(p), rules) for p in MUST_REQUIRE)      # `*.py[cod]` covers `*.pyc`
    two_lines = RH.parse_ignore("*.log\ntmp/\n")                               # what the bot left behind
    assert [p for p in sorted(MUST_REQUIRE) if RH.ignored(RH.sample_path(p), two_lines)] == []
    assert not RH.ignored(RH.sample_path("*.pyc"), RH.parse_ignore("*.py[cod]\n!*.pyc"))    # a re-include uncovers it


# ---------------------------------------------------------------- scan (pure)

def test_scan_reports_each_kind(cfg):
    files = [("src/a.py", 10), (".venv-x/bin/python", 5), ("a/__pycache__/b.pyc", 5), ("data/blob.bin", 3 * 1024 * 1024), ("ok/big.ttf", 2 * 1024 * 1024)]
    found = RH.scan(files, GOOD_IGNORE, {**cfg, "allow": ["ok/*.ttf"]})
    assert sorted((f.kind, f.subject) for f in found) == [("big", "data/blob.bin"), ("tracked", ".venv-x/bin/python"),
                                                          ("tracked", "a/__pycache__/b.pyc")]


def test_scan_without_a_gitignore_lacks_every_required_pattern(cfg):
    found = RH.scan([("src/a.py", 1)], None, cfg)
    assert {f.subject for f in found} == set(cfg["required_ignore"]) and {f.why for f in found} == {"no .gitignore"}


# ---------------------------------------------------------------- real git repositories

@needs_git
def test_clean_repo_is_ok(tmp_path, cfg):
    res = RH.check(make_repo(tmp_path), cfg)
    assert res.status == "ok" and res.metrics == {"files": 3, "tracked": 0, "big": 0, "missing_ignore": 0}, res.detail


@needs_git
def test_tracked_junk_fails_with_a_fix_hint(tmp_path, cfg):
    files = {"src/game.py": "x\n", ".venv-3.13/Scripts/python.exe": b"MZ", "src/__pycache__/game.cpython-312.pyc": b"\0",
             "rust_core/target/release/lib.so": b"\x7fELF", "ext/mod.pyd": b"MZ", "saves/game_database.db": b"SQLite",
             "dev_probe_output/probe.sqlite": b"x", "assets/huge.bin": b"\0" * (2 * 1024 * 1024)}
    root = make_repo(tmp_path, files=files)
    git(root, "add", "-f", "--", *[n for n in files if n != "src/game.py"])
    res = RH.check(root, cfg)
    assert res.status == "fail" and res.metrics["tracked"] == 6 and res.metrics["big"] == 1 and res.metrics["missing_ignore"] == 0
    text = "\n".join(res.detail)
    for needle in (".venv*/", "*.pyc", "target/", "*.pyd", "saves/*.db", "dev_probe_output/", "assets/huge.bin", "git rm -r --cached"):
        assert needle in text
    assert "src/game.py" not in text


@needs_git
def test_overwritten_gitignore_fails(tmp_path, cfg):
    root = make_repo(tmp_path, ignore="*.log\ntmp/\n")            # the bot overwrote .gitignore with two lines
    res = RH.check(root, cfg)
    assert res.status == "fail" and res.metrics["missing_ignore"] == len(cfg["required_ignore"]) and res.metrics["tracked"] == 0
    assert ".gitignore lacks" in "\n".join(res.detail) and ".venv-*/" in "\n".join(res.detail)


@needs_git
def test_missing_gitignore_fails(tmp_path, cfg):
    res = RH.check(make_repo(tmp_path, ignore=None), cfg)
    assert res.status == "fail" and res.metrics["missing_ignore"] == len(cfg["required_ignore"])


@needs_git
def test_untracking_the_junk_makes_it_ok_again(tmp_path, cfg):
    root = make_repo(tmp_path, files={"src/game.py": "x\n", "src/__pycache__/g.cpython-312.pyc": b"\0"})
    git(root, "add", "-f", "--", "src/__pycache__/g.cpython-312.pyc")
    assert RH.check(root, cfg).status == "fail"
    git(root, "rm", "-r", "--cached", "-q", "--", "src/__pycache__")             # what the fix hint says
    assert RH.check(root, cfg).status == "ok"                                    # the file stays on disk, git ignores it


def hygiene_cli(root: Path):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "qa.py"), "hygiene", "--root", str(root), "--result"],
                          capture_output=True, text=True, cwd=ROOT, timeout=120)


@needs_git
def test_cli_prints_a_result_line_and_the_exit_code(tmp_path, cfg):
    bad = tmp_path / "bad"
    bad.mkdir()
    run = hygiene_cli(make_repo(bad, ignore="*.log\n"))
    assert run.returncode == 1 and run.stdout.strip().splitlines()[-1].startswith("RESULT status=FAIL ")
    assert f"missing_ignore={len(cfg['required_ignore'])}" in run.stdout
    good = tmp_path / "good"
    good.mkdir()
    run = hygiene_cli(make_repo(good))
    assert run.returncode == 0 and run.stdout.strip().splitlines()[-1].startswith("RESULT status=OK ")


@needs_git
def test_not_a_git_repository_is_an_error_not_a_pass(tmp_path, cfg):
    res = RH.check(tmp_path, cfg)          # tmp_path has no .git (pytest's tmp dir is outside any repository)
    assert res.status == "error" and "git" in res.detail[0]
