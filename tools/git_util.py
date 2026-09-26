"""One git wrapper for the tools (stdlib only): `git(*args)` -> stdout or '' on any failure, plus small helpers on top."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def git(*args: str, root: Path | None = None, env: dict | None = None, timeout: float = 60, raw: bool = False) -> str:
    """stdout of one git call, '' on ANY failure (no git, non-zero exit, timeout): callers treat 'no answer' as 'nothing'.

    Default strips the whole output; `raw=True` only trims trailing newlines (keeps leading spaces of porcelain output).
    """
    try:
        run = subprocess.run(["git", *args], cwd=root or _ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             env={**os.environ, **env} if env else None, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if run.returncode != 0:
        return ""
    return run.stdout.rstrip("\r\n") if raw else run.stdout.strip()


def head(root: Path | None = None) -> str:
    """Short sha of HEAD ('' outside a repo)."""
    return git("rev-parse", "--short", "HEAD", root=root)


def dirty(root: Path | None = None) -> list[str]:
    """Paths with uncommitted changes (modified, added, untracked)."""
    return [ln[3:] for ln in git("status", "--porcelain", root=root, raw=True).splitlines() if len(ln) > 3]


def git_many(*calls: tuple, root: Path | None = None, timeout: float = 60) -> list[str]:
    """Run independent git calls CONCURRENTLY (a git start costs ~35 ms on Windows); stripped stdout per call, '' on failure."""
    procs = []
    for args in calls:
        try:
            procs.append(subprocess.Popen(["git", *args], cwd=root or _ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL))
        except OSError:
            procs.append(None)
    outs = []
    for proc in procs:
        try:
            out = proc.communicate(timeout=timeout)[0] if proc else b""
        except subprocess.SubprocessError:
            proc.kill()
            out = b""
        ok = proc is not None and proc.returncode == 0
        outs.append(out.decode("utf-8", "replace").strip() if ok else "")
    return outs


def changed_files(rev: str = "origin/main", root: Path | None = None) -> list[str]:
    """Existing files changed vs the merge-base with `rev` (commits of the branch + working tree + untracked), sorted."""
    root = root or _ROOT
    # `rev...HEAD` = diff against the merge-base, so the three calls are independent and run concurrently
    branch, work, untracked = git_many(("diff", "--name-only", f"{rev}...HEAD"), ("diff", "--name-only", "HEAD"),
                                       ("ls-files", "--others", "--exclude-standard"), root=root)
    files = set(branch.splitlines()) | set(work.splitlines()) | set(untracked.splitlines())
    return sorted(f for f in files if f and (root / f).exists())
