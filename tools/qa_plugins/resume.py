"""qa.py resume - where did the last session stop? <= 6 lines, SILENT when the tree is clean and in sync (so it can run on every session start).

    qa.py resume                  # head, dirty, orphans, broken files, last journal entry, verdict SAFE / RISKY / BROKEN
    qa.py resume --brief          # the same as ONE line: what `qa.py prompt ROLE --task "continue: $(qa.py resume --brief)"` embeds
    qa.py resume --check          # also RUN `qa.py check --changed` (default: the verdict of the last check in history.jsonl)
    qa.py resume --diff N         # working tree vs checkpoint N (git diff --stat)
    qa.py resume --restore N      # the same, plus the way back; restores ONLY with --apply (files of the snapshot are written over the tree, nothing is deleted)

ORPHANS = new (untracked/added) modules that nothing imports: the half-done-work signal. BROKEN = dirty files that do not compile (.py; .lua with luajit when installed).
Verdict: BROKEN = broken file or red check (fix first or --restore); RISKY = dirty and (orphans or no green check yet); SAFE = green and no orphans (continue at `next`).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from probe_settings import ROOT
from qa_plugins import ckpt as C

SKIP_ORPHAN = ("tests/", "tools/qa_plugins/", "tools/qa_checks/", "docs/")


def _importers_pattern(path: str) -> re.Pattern:
    stem = Path(path).stem
    return re.compile(rf"^\s*(?:from\s+[\w.]*\b{re.escape(stem)}\b|import\s+[\w., ]*\b{re.escape(stem)}\b|from\s+[\w.]+\s+import\s+[^#\n]*\b{re.escape(stem)}\b)", re.M)


def _is_candidate(status: str, path: str, root: Path) -> bool:
    if status not in ("??", "A") or not path.endswith(".py") or path.endswith("__init__.py"):
        return False
    if path.startswith(SKIP_ORPHAN):
        return False
    return "__main__" not in (root / path).read_text(encoding="utf-8", errors="replace")


def orphans(root: Path, dirty: list[tuple[str, str]]) -> list[str]:
    """New modules that no other .py file imports."""
    cands = [p for s, p in dirty if _is_candidate(s, p, root)]
    if not cands:
        return []
    files = [p for p in C.git(root, "ls-files", "-co", "--exclude-standard", "*.py").splitlines()]
    texts = {p: (root / p).read_text(encoding="utf-8", errors="replace") for p in files if (root / p).is_file()}
    return [c for c in cands if not any(_importers_pattern(c).search(t) for p, t in texts.items() if p != c)]


def _compiles(path: Path) -> bool:
    try:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return False
    return True


def _lua_ok(path: Path, luajit: str) -> bool:
    return subprocess.run([luajit, "-bl", str(path)], capture_output=True, timeout=10, check=False).returncode == 0


def broken(root: Path, dirty: list[tuple[str, str]]) -> list[str]:
    luajit = shutil.which("luajit")
    bad = []
    for _s, p in dirty:
        f = root / p
        if not f.is_file():
            continue
        if (p.endswith(".py") and not _compiles(f)) or (luajit and p.endswith(".lua") and not _lua_ok(f, luajit)):
            bad.append(p)
    return bad


def run_check(root: Path) -> str:
    """ok / fail from a real `qa.py check` run (header line `QA verdict=`)."""
    run = subprocess.run([sys.executable, str(root / "tools" / "qa.py"), "check"], cwd=root, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=900, check=False)
    return "ok" if "verdict=OK" in run.stdout or "verdict=WARN" in run.stdout else "fail" if "verdict=" in run.stdout else "none"


def verdict_of(dirty: list, bad: list, orph: list, check: str) -> str:
    if bad or check == "fail":
        return "BROKEN"
    return "SAFE" if check == "ok" and not orph else "RISKY"


def gather(root: Path, run: bool = False, brief: bool = False) -> dict:
    dirty, behind, ahead = C.status_all(root)
    head = C.git(root, "rev-parse", "--short", "HEAD") or "-" if (dirty or behind or ahead or brief) else "-"
    info = {"head": head, "behind": behind, "ahead": ahead, "dirty": dirty, "journal": (C.read_journal(root) or [{}])[-1],
            "clean": not dirty and not behind and not ahead}
    if dirty:
        check = run_check(root) if run else C.last_verdict(root, C.cfg()["history_tail_bytes"])
        info.update(orphans=orphans(root, dirty), broken=broken(root, dirty), check=check)
        info["verdict"] = verdict_of(dirty, info["broken"], info["orphans"], check)
    return info


def lines(info: dict) -> list[str]:
    out = [f"head={info['head']} behind/ahead origin={info['behind']}/{info['ahead']}"]
    dirty = info["dirty"]
    if dirty:
        new = sum(1 for s, _p in dirty if s in ("??", "A"))
        out.append(f"dirty={len(dirty)} ({len(dirty) - new} modified, {new} new) check={info['check']}")
        if info["orphans"]:
            out.append("ORPHANS (new, imported by nothing): " + ", ".join(info["orphans"][:5]))
        if info["broken"]:
            out.append("BROKEN files: " + ", ".join(info["broken"][:5]))
    j = info["journal"]
    if j and (dirty or info["behind"] or info["ahead"]):
        out.append(f"last ckpt #{j.get('n')}: done=\"{j.get('done', '')}\" next=\"{j.get('next', '')}\"")
    if dirty:
        out.append(f"verdict {info['verdict']}" + (" (fix first, or `qa.py resume --restore N`)" if info["verdict"] == "BROKEN" else ""))
    return out[:6]


def brief(info: dict) -> str:
    j = info["journal"] or {}
    return (f"[{info.get('verdict', 'CLEAN')}] head={info['head']} dirty={len(info['dirty'])} orphans={len(info.get('orphans', []))} "
            f"broken={len(info.get('broken', []))} done=\"{j.get('done', '')}\" next=\"{j.get('next', '')}\"")


def cmd_restore(root: Path, n: int, apply: bool) -> int:
    ref = f"{C.REF}/{n}"
    if not C.git(root, "rev-parse", "--verify", "-q", ref):
        print(f"no checkpoint #{n}")
        return 1
    print(C.git(root, "diff", "--stat", ref) or f"working tree equals checkpoint #{n} (tracked files)")
    if apply:
        C.git(root, "checkout", ref, "--", ".")
        print(f"restored files of checkpoint #{n} (nothing deleted)")
    else:
        print(f"(dry run) apply: qa.py resume --restore {n} --apply")
    return 0


def cmd_resume(args) -> int:
    root = Path(args.root) if args.root else ROOT
    if args.diff is not None or args.restore is not None:
        n = args.diff if args.diff is not None else args.restore
        return cmd_restore(root, n, bool(args.apply and args.restore is not None))
    info = gather(root, bool(args.check), bool(args.brief))
    if args.brief:
        print(brief(info))
    elif not info["clean"]:
        print("\n".join(lines(info)))
    return 0


def register(sub):
    p = sub.add_parser("resume", help="state after a crash or a call cap (<= 6 lines, silent when clean): dirty, orphans, broken, last ckpt, SAFE/RISKY/BROKEN",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--brief", action="store_true", help="one line for a `continue:` prompt")
    p.add_argument("--check", action="store_true", help="run `qa.py check` instead of reading the last verdict")
    p.add_argument("--diff", type=int, metavar="N", help="working tree vs checkpoint N")
    p.add_argument("--restore", type=int, metavar="N", help="diff vs checkpoint N; with --apply write its files back")
    p.add_argument("--apply", action="store_true", help="really restore (with --restore)")
    p.add_argument("--root", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_resume)
