"""Repo hygiene: what must never be tracked by git, and the .gitignore that keeps it out.

    python tools/qa.py hygiene [--result]    # one report (--result = the machine form `qa.py check` parses); exit 1 on a finding
    python tools/repo_hygiene.py [--root DIR]

Why: an automated session once overwrote .gitignore with two lines and committed virtualenvs, `__pycache__` and a save database.
Nothing in the tests notices that, so this is a check of its own (`hygiene` in lua_content/qa.lua, runs in `qa.py check` and in CI).

Data = the `hygiene` table of lua_content/qa.lua, every list in .gitignore syntax (one matcher, `ignored()`, serves all of them):
    forbidden        a TRACKED file matching one of these fails (virtualenv, build output, saves, probe output)
    required_ignore  .gitignore must cover each pattern (semantically: `*.py[cod]` covers `*.pyc`; a `!` re-include uncovers it)
    max_file_kb      a tracked file bigger than this fails, unless `allow` (gitignore syntax) lists it
"""
from __future__ import annotations

import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import qa_report as R

FIX_TRACKED = "git rm -r --cached -q -- <the listed paths>   (files stay on disk; .gitignore keeps them out of the next commit)"
FIX_IGNORE = "restore the lost patterns in .gitignore (`git log -p -- .gitignore` shows what was overwritten)"


# ---------------------------------------------------------------- the gitignore matcher (the subset this repo uses)

def _segments(path: list[str], pat: list[str]) -> bool:
    """Whole-path match, segment by segment: `*` `?` `[..]` inside a segment, a `**` segment = zero or more directories."""
    if not pat:
        return not path
    if pat[0] == "**":
        return any(_segments(path[i:], pat[1:]) for i in range(len(path) + 1))
    return bool(path) and fnmatch.fnmatchcase(path[0], pat[0]) and _segments(path[1:], pat[1:])


def _rule_hits(path: str, rule: str) -> bool:
    """Does the .gitignore rule ignore `path` (a repo-relative posix path): gitignore(5) - trailing `/` = directories only,
    a `/` inside (or leading) = anchored to the root, otherwise the rule matches the name at any depth; a rule that hits a
    parent directory ignores everything below it."""
    dir_only, body = rule.endswith("/"), rule.rstrip("/")
    anchored, body = body.startswith("/") or "/" in body, body.lstrip("/")
    parts = path.split("/")
    for depth in range(1, len(parts) + 1):
        if dir_only and depth == len(parts):
            break                                       # the path itself is a file: a directory rule does not name it
        head = parts[:depth]
        hit = _segments(head, body.split("/")) if anchored else fnmatch.fnmatchcase(head[-1], body)
        if hit:
            return True
    return False


def parse_ignore(text: str) -> list[str]:
    """Rules of a .gitignore text: comments and blank lines dropped."""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def ignored(path: str, rules: list[str]) -> bool:
    """Last matching rule wins; `!rule` re-includes."""
    verdict = False
    for rule in rules:
        negated = rule.startswith("!")
        if _rule_hits(path, rule[1:] if negated else rule):
            verdict = not negated
    return verdict


def sample_path(pattern: str) -> str:
    """A path the pattern must ignore: `.venv-*/` -> `.venv-x/probe`, `*.pyc` -> `x.pyc`, `saves/*.db` -> `saves/x.db`."""
    plain = pattern.replace("*", "x").replace("?", "x")
    return plain + "probe" if pattern.endswith("/") else plain


# ---------------------------------------------------------------- scan (pure) + git

@dataclass(frozen=True)
class Finding:
    kind: str        # tracked | big | ignore
    subject: str     # path / pattern
    why: str         # the rule that fired


def scan(files: list[tuple[str, int]], gitignore: str | None, cfg: dict) -> list[Finding]:
    """`files` = (tracked path, size in bytes); `gitignore` = its text (None: there is none)."""
    out: list[Finding] = []
    forbidden = [str(p) for p in cfg.get("forbidden") or []]
    allow = parse_ignore("\n".join(str(p) for p in cfg.get("allow") or []))
    limit = int(cfg.get("max_file_kb") or 0) * 1024
    for path, size in files:
        hit = next((p for p in forbidden if ignored(path, [p])), None)
        if hit:
            out.append(Finding("tracked", path, hit))
        elif limit and size > limit and not ignored(path, allow):
            out.append(Finding("big", path, f"{size // 1024} KB > {limit // 1024} KB"))
    rules = parse_ignore(gitignore or "")
    for pattern in cfg.get("required_ignore") or []:
        if not ignored(sample_path(str(pattern)), rules):
            out.append(Finding("ignore", str(pattern), ".gitignore does not cover it" if gitignore is not None else "no .gitignore"))
    return out


def git_files(root: Path) -> list[tuple[str, int]]:
    """Tracked files of the repo at `root` (the index: staged deletions are already gone) with their size on disk."""
    res = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z"], cwd=root, capture_output=True, timeout=60, check=False)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout).decode("utf-8", "replace").strip() or f"git ls-files rc={res.returncode}")
    out = []
    for name in filter(None, res.stdout.decode("utf-8").split("\0")):
        try:
            out.append((name, (root / name).stat().st_size))
        except OSError:                                 # in the index, not on disk (deleted in the worktree): nothing to weigh
            out.append((name, 0))
    return out


def read_gitignore(root: Path) -> str | None:
    try:
        return (root / ".gitignore").read_text(encoding="utf-8")
    except OSError:
        return None


# ---------------------------------------------------------------- report

def evaluate(findings: list[Finding], scanned: int, examples: int = 3) -> R.Result:
    tracked = [f for f in findings if f.kind == "tracked"]
    big = [f for f in findings if f.kind == "big"]
    missing = [f for f in findings if f.kind == "ignore"]
    detail: list[str] = []
    for rule in dict.fromkeys(f.why for f in tracked):                 # one line per rule, first paths as examples
        paths = [f.subject for f in tracked if f.why == rule]
        more = f" (+{len(paths) - examples} more)" if len(paths) > examples else ""
        detail.append(f"tracked {rule} x{len(paths)}: " + ", ".join(paths[:examples]) + more)
    detail += [f"big {f.subject}: {f.why}" for f in big]
    if missing:
        detail.append(".gitignore lacks: " + " ".join(f.subject for f in missing))
    if tracked or big:
        detail.append("fix: " + FIX_TRACKED)
    if missing:
        detail.append("fix: " + FIX_IGNORE)
    metrics = {"files": scanned, "tracked": len(tracked), "big": len(big), "missing_ignore": len(missing)}
    status = "fail" if findings else "ok"
    return R.Result(status, metrics, detail, "python tools/qa.py hygiene" if findings else None)


def check(root: Path = ROOT, cfg: dict | None = None) -> R.Result:
    """What the `hygiene` check runs: git ls-files + .gitignore vs the `hygiene` table of qa.lua."""
    if cfg is None:
        from probe_settings import qa_settings
        cfg = qa_settings().get("hygiene") or {}
    try:
        files = git_files(root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return R.Result("error", {}, [f"git: {exc}"], "python tools/qa.py hygiene")
    return evaluate(scan(files, read_gitignore(root), cfg), len(files))


def result_lines(res: R.Result) -> list[str]:
    """Machine form for the Lua-declared check (`parse = "result_line"`): detail lines, `repro:`, one RESULT line."""
    lines = list(res.detail)
    if res.repro:
        lines.append(f"repro: {res.repro}")
    if res.status != "error":
        lines.append(f"RESULT status={res.status.upper()} " + " ".join(f"{k}={R.fmt_num(v)}" for k, v in res.metrics.items()))
    return lines


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="repository to scan (default: this one)")
    ap.add_argument("--result", action="store_true", help="machine form: detail lines, repro, one RESULT line")
    args = ap.parse_args(argv)
    res = check(args.root)
    print("\n".join(result_lines(res) if args.result else [*res.detail, f"hygiene {res.status.upper()} " +
                                                            " ".join(f"{k}={R.fmt_num(v)}" for k, v in res.metrics.items())]))
    return R.exit_code([res])


if __name__ == "__main__":
    sys.exit(main())
