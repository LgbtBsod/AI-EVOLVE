"""qa.py ckpt - a checkpoint of unfinished work: one journal line + a safety snapshot, so a crash or a call cap costs nothing to continue (`qa.py resume`).

    qa.py ckpt "what is done" --next "next action" [--files a,b] [--agent NAME]
    qa.py ckpt --auto            # the Stop hook: only when the tree is dirty, no `next` text

Journal: dev_probe_output/qa/journal.jsonl (ts, head, dirty files + sha256, last check verdict, done, next, agent). Snapshot: a commit of the working tree (untracked files
included, ignored ones not) stored as refs/qa/ckpt/N - built with a temporary index, so the working tree, the index and the branch never change. The last `keep` are kept.
Limits: the `ckpt` table of lua_content/qa.lua.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from git_util import git as _git
from jsonl_io import append_jsonl, read_jsonl
from probe_settings import ROOT, qa_settings

REF = "refs/qa/ckpt"
DEFAULTS = {"keep": 20, "history_tail_bytes": 30000, "hook_timeout_s": 8}


def cfg() -> dict:
    return {**DEFAULTS, **(qa_settings().get("ckpt") or {})}


def git_at(root: Path, *args: str, env: dict | None = None) -> str:
    """stdout of one git call ('' on any failure: the callers treat 'no answer' as 'nothing')."""
    return _git(*args, root=root, env=env, timeout=30, raw=True)


git = git_at  # name used by resume.py and tests


def out_dir(root: Path) -> Path:
    return root / "dev_probe_output" / "qa"


def status_all(root: Path) -> tuple[list[tuple[str, str]], int, int]:
    """([(status, path)], behind, ahead): the working tree (modified, added, untracked) and the sync with its upstream, from ONE `git status -b -z` call."""
    raw = git_at(root, "-c", "core.quotepath=off", "status", "--porcelain=v1", "-z", "-uall", "-b")
    parts, rows, i = raw.split("\0"), [], 0
    behind = ahead = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if entry.startswith("## "):
            m, n = re.search(r"ahead (\d+)", entry), re.search(r"behind (\d+)", entry)
            ahead, behind = int(m.group(1)) if m else 0, int(n.group(1)) if n else 0
        elif len(entry) > 3:
            rows.append((entry[:2].strip() or "M", entry[3:]))
            i += 1 if entry[0] in "RC" else 0
    return rows, behind, ahead


def dirty_files(root: Path) -> list[tuple[str, str]]:
    return status_all(root)[0]


def sha_of(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return "-"


def last_verdict(root: Path, tail: int) -> str:
    """ok / fail / none: worst status of the newest row of every check in history.jsonl."""
    path = out_dir(root) / "history.jsonl"
    if not path.is_file():
        return "none"
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - tail))
        lines = fh.read().decode("utf-8", errors="replace").splitlines()[1:]
    newest: dict[str, str] = {}
    for line in lines:
        try:
            row = json.loads(line)
            newest[row["name"]] = row["status"]
        except (ValueError, KeyError, TypeError):
            continue
    if not newest:
        return "none"
    return "fail" if any(s in ("fail", "error") for s in newest.values()) else "ok"


def next_number(root: Path) -> int:
    refs = git_at(root, "for-each-ref", "--format=%(refname)", REF).splitlines()
    nums = [int(r.rsplit("/", 1)[1]) for r in refs if r.rsplit("/", 1)[1].isdigit()]
    return max(nums, default=0) + 1


def prune(root: Path, keep: int) -> int:
    refs = git_at(root, "for-each-ref", "--format=%(refname)", REF).splitlines()
    nums = sorted(int(r.rsplit("/", 1)[1]) for r in refs if r.rsplit("/", 1)[1].isdigit())
    old = nums[:-keep] if keep > 0 else nums
    for n in old:
        git_at(root, "update-ref", "-d", f"{REF}/{n}")
    return len(old)


def snapshot(root: Path, number: int, message: str) -> str:
    """Commit the whole working tree (tracked + untracked, not ignored) under refs/qa/ckpt/N. A temporary index: the real one and the tree are untouched. '' = failed."""
    gd = Path(git_at(root, "rev-parse", "--absolute-git-dir") or "")
    if not gd.is_dir():
        return ""
    fd, tmp = tempfile.mkstemp(prefix="qa_ckpt_index_", dir=gd)
    os.close(fd)
    try:
        if (gd / "index").is_file():
            shutil.copyfile(gd / "index", tmp)
        env = {"GIT_INDEX_FILE": tmp, "GIT_AUTHOR_NAME": "qa", "GIT_AUTHOR_EMAIL": "qa@localhost",
               "GIT_COMMITTER_NAME": "qa", "GIT_COMMITTER_EMAIL": "qa@localhost"}
        git_at(root, "add", "-A", env=env)
        tree = git_at(root, "write-tree", env=env)
        head = git_at(root, "rev-parse", "--verify", "-q", "HEAD")
        commit = git_at(root, "commit-tree", tree, *(["-p", head] if head else []), "-m", message, env=env) if tree else ""
        if commit:
            git_at(root, "update-ref", f"{REF}/{number}", commit)
        return commit
    finally:
        Path(tmp).unlink(missing_ok=True)


def read_journal(root: Path) -> list[dict]:
    return read_jsonl(out_dir(root) / "journal.jsonl")


def save(root: Path, done: str, nxt: str, files: str = "", agent: str = "", auto: bool = False) -> dict | None:
    """Journal line + snapshot. None when auto and the tree is clean (nothing to keep)."""
    settings = cfg()
    dirty = dirty_files(root)
    if auto and not dirty:
        return None
    number = next_number(root)
    commit = snapshot(root, number, f"qa ckpt #{number}: {done}"[:200])
    row = {"ts": int(time.time()), "n": number, "head": git_at(root, "rev-parse", "--short", "HEAD"), "snapshot": commit[:12],
           "dirty": [{"path": p, "st": s, "sha": sha_of(root / p)} for s, p in dirty], "verdict": last_verdict(root, settings["history_tail_bytes"]),
           "done": done, "next": nxt, "files": [f for f in files.split(",") if f], "agent": agent, "auto": auto}
    out_dir(root).mkdir(parents=True, exist_ok=True)
    append_jsonl(out_dir(root) / "journal.jsonl", row)
    prune(root, int(settings["keep"]))
    return row


def cmd_ckpt(args) -> int:
    root = Path(args.root) if args.root else ROOT
    row = save(root, args.done or ("auto" if args.auto else ""), args.next or "", args.files or "", args.agent or "", bool(args.auto))
    if row is None or args.auto:
        return 0
    print(f"ckpt #{row['n']} saved: dirty={len(row['dirty'])} next=\"{row['next']}\"" + ("" if row["snapshot"] else " (snapshot failed: journal only)"))
    return 0


def register(sub):
    p = sub.add_parser("ckpt", help="checkpoint: journal line + safety snapshot (refs/qa/ckpt/N) of the unfinished work; read back by `qa.py resume`",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("done", nargs="?", default="", help="what is done")
    p.add_argument("--next", help="the next action (the first thing the next agent does)")
    p.add_argument("--files", help="files touched, comma separated")
    p.add_argument("--agent", help="agent name")
    p.add_argument("--auto", action="store_true", help="hook mode: only when the tree is dirty, no output")
    p.add_argument("--root", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_ckpt)
