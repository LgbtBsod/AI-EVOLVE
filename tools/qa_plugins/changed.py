"""qa.py changed - a semantic diff summary (<= 30 lines) instead of a raw `git diff`.

    qa.py changed              # your work vs origin/main (merge-base) + working tree + untracked files
    qa.py changed HEAD~3       # vs a revision (--since REV is the same)

    CHANGED vs HEAD~3: 5 files +412/-38 loc | symbols +9 -2 ~6
    M tools/qa.py                   +5/-1     ~main
    A tools/qa_report.py            +330/-0   +Result +format_line +render +budgeted (+3)
    areas: tools +380/-35 | tests +30/-3
    RISK: lua-content rust-ffi        (flags: ci-workflow boot-path tests-only lua-content rust-ffi)
    check: python tools/qa.py check --name tests,lua,items   (3 of 16)

Symbols: `ast` for .py (functions, methods as Class.method, classes), regex for .rs (fn/struct/enum/trait/impl) and .lua
(functions, top-level and first-level table keys). +added -removed ~changed (same name, different body).
"""
from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict

import qa_report as R
from probe_settings import ROOT, qa_settings

MAX_BYTES = 400_000
FLAGS = ("ci-workflow", "boot-path", "tests-only", "lua-content", "rust-ffi")


def _qa():
    import qa
    return qa


# ---------------------------------------------------------------- symbols (name -> body hash)

def _h(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).encode()).hexdigest()[:12]


def py_symbols(text: str) -> dict | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    out: dict = {}

    def visit(body, prefix=""):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + node.name] = _h(ast.dump(node))
            elif isinstance(node, ast.ClassDef):
                shell = ast.ClassDef(node.name, node.bases, node.keywords,
                                     [n for n in node.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))],
                                     node.decorator_list)
                out[prefix + node.name] = _h(ast.dump(shell))
                visit(node.body, prefix + node.name + ".")

    visit(tree.body)
    return out


_RS_FN = re.compile(r"^(\s*)(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)")
_RS_TYPE = re.compile(r"^(\s*)(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|type)\s+(\w+)")
_RS_IMPL = re.compile(r"^(\s*)impl(?:<[^>]*>)?\s+(?:([\w:]+)(?:<[^>]*>)?\s+for\s+)?([\w:]+)")
_LUA_FN = re.compile(r"^(\s*)(?:local\s+)?function\s+([\w.:]+)")
_LUA_KEY = re.compile(r"^(?:  )?([A-Za-z_]\w*)\s*=")


def _segments(text: str, starts: list) -> dict:
    """starts: [(line_index, name)] -> {name: hash of its lines}. A symbol ends at the next symbol start or at the first
    line indented less than its own start (the parent's closing brace); comments and blank lines do not count."""
    lines = text.splitlines()
    out: dict = {}
    for i, (ln, name) in enumerate(starts):
        nxt = starts[i + 1][0] if i + 1 < len(starts) else len(lines)
        ind = len(lines[ln]) - len(lines[ln].lstrip())
        end = next((j for j in range(ln + 1, nxt) if lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) < ind), nxt)
        body = [x for x in lines[ln:end] if x.strip() and not x.strip().startswith(("//", "--"))]
        out[name] = _h("\n".join(body))
    return out


def rs_symbols(text: str) -> dict:
    starts, impl = [], None
    for i, line in enumerate(text.splitlines()):
        if m := _RS_IMPL.match(line):
            impl = f"{m.group(2)} for {m.group(3)}" if m.group(2) else m.group(3)
            starts.append((i, f"impl {impl}"))
        elif m := _RS_FN.match(line):
            starts.append((i, f"{impl}::{m.group(2)}" if impl and m.group(1) else m.group(2)))
            if not m.group(1):
                impl = None
        elif m := _RS_TYPE.match(line):
            starts.append((i, m.group(2)))
            if not m.group(1):
                impl = None
    return _segments(text, starts)


def lua_symbols(text: str) -> dict:
    starts = []
    for i, line in enumerate(text.splitlines()):
        if m := _LUA_FN.match(line):
            starts.append((i, m.group(2) + "()"))
        elif m := _LUA_KEY.match(line):
            starts.append((i, m.group(1)))
    return _segments(text, starts)


def symbols(path: str, text: str | None) -> dict | None:
    if text is None:
        return {}
    if path.endswith(".py"):
        return py_symbols(text)
    if path.endswith(".rs"):
        return rs_symbols(text)
    if path.endswith(".lua"):
        return lua_symbols(text)
    return {}


def sym_diff(old: dict, new: dict):
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    return added, removed, changed


# ---------------------------------------------------------------- git

def _diff_rows(rev: str) -> list:
    """[(status, path, added, deleted)] of `rev` vs the working tree, untracked files included."""
    qa = _qa()
    stat = {}
    for line in qa.git("-c", "core.quotepath=false", "diff", "--name-status", "--no-renames", rev).splitlines():
        s, _, p = line.partition("\t")
        stat[p] = s[:1]
    nums = {}
    for line in qa.git("-c", "core.quotepath=false", "diff", "--numstat", "--no-renames", rev).splitlines():
        a, d, p = line.split("\t", 2)
        nums[p] = (int(a), int(d)) if a.isdigit() and d.isdigit() else None       # None = binary
    for p in qa.git("-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard").splitlines():
        if p and p not in stat and (ROOT / p).is_file():
            stat[p] = "A"
            f = ROOT / p
            nums[p] = (len(f.read_text(encoding="utf-8", errors="replace").splitlines()), 0) if f.stat().st_size < MAX_BYTES else None
    return [(s, p, *(nums.get(p) or (0, 0))) for p, s in stat.items()]


def _old_text(rev: str, path: str) -> str | None:
    import subprocess
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 and len(r.stdout) < MAX_BYTES else None


def _new_text(path: str) -> str | None:
    f = ROOT / path
    return f.read_text(encoding="utf-8", errors="replace") if f.is_file() and f.stat().st_size < MAX_BYTES else None


# ---------------------------------------------------------------- summary

def area_of(path: str) -> str:
    parts = path.split("/")
    return parts[0] if len(parts) <= 2 else "/".join(parts[:2])


def risk_flags(paths, rs_ffi=False) -> list:
    flags = []
    if any(p.startswith(".github/") for p in paths):
        flags.append("ci-workflow")
    if any(p == "main.py" or p.startswith("src/core/") for p in paths):
        flags.append("boot-path")
    if paths and all(p.startswith("tests/") for p in paths):
        flags.append("tests-only")
    if any(p.startswith("lua_content/") for p in paths):
        flags.append("lua-content")
    if rs_ffi:
        flags.append("rust-ffi")
    return flags


def _top(names) -> list:
    """Drop members whose class/impl is listed too (`Result.key` is implied by `Result`); public names first."""
    have = set(names)
    keep = [n for n in names if not any(n.startswith(x + sep) for x in have if x != n for sep in (".", "::"))]
    return sorted(keep, key=lambda n: (n.split(".")[-1].split("::")[-1].startswith("_"), n))


def fmt_symbols(added, removed, changed, cap: int = 5) -> str:
    toks = [f"+{n}" for n in _top(added)] + [f"-{n}" for n in _top(removed)] + [f"~{n}" for n in changed]
    return " ".join(toks[:cap]) + (f" (+{len(toks) - cap})" if len(toks) > cap else "")


def merge_plain(per_file) -> list:
    """>= 3 files of one directory with the same status and no symbols (fixtures, data, docs) become one line."""
    groups: dict = defaultdict(list)
    for e in per_file:
        if not e[5]:
            groups[(e[1], e[2].rsplit("/", 1)[0] if "/" in e[2] else "")].append(e)
    out, merged = [], set()
    for (status, d), items in groups.items():
        if len(items) >= 3:
            merged.update(id(e) for e in items)
            out.append((sum(e[0] for e in items), status, f"{d + '/' if d else ''}({len(items)} files)",
                        sum(e[3] for e in items), sum(e[4] for e in items), ""))
    return sorted([e for e in per_file if id(e) not in merged] + out, key=lambda t: (-t[0], t[2]))


def summarize(rows, old_text, new_text, rev_label: str, max_lines: int = 30):
    """Pure: rows [(status, path, add, del)] + text getters -> (lines, changed_paths, flags)."""
    per_file, area = [], defaultdict(lambda: [0, 0])
    tot_a = tot_d = 0
    sa = sr = sc = 0
    rs_ffi = False
    for status, path, add, dele in rows:
        old = old_text(path) if status != "A" else None
        new = new_text(path) if status != "D" else None
        if path.endswith(".rs") and any("#[py" in (t or "") for t in (old, new)):
            rs_ffi = True
        so, sn = symbols(path, old), symbols(path, new)
        if so is None or sn is None:
            a = r = c = []
            sym = "(unparsable)"
        else:
            a, r, c = sym_diff(so, sn)
            sym = fmt_symbols(a, r, c)
        sa, sr, sc = sa + len(a), sr + len(r), sc + len(c)
        tot_a, tot_d = tot_a + add, tot_d + dele
        area[area_of(path)][0] += add
        area[area_of(path)][1] += dele
        per_file.append((add + dele, status, path, add, dele, sym))
    paths = [e[2] for e in per_file]
    per_file = merge_plain(per_file)
    flags = risk_flags(paths, rs_ffi)
    head = f"CHANGED vs {rev_label}: {len(rows)} files +{tot_a}/-{tot_d} loc | symbols +{sa} -{sr} ~{sc}"
    if not rows:
        return [head], [], flags
    tail_lines = 3                                    # areas, RISK, check (added by the caller: 1 more)
    room = max_lines - 1 - tail_lines - 1
    width = min(max(len(e[2]) for e in per_file), 44)
    lines = [head]
    for _c, status, path, add, dele, sym in per_file[:room]:
        lines.append(f"{status} {path:<{width}} +{add}/-{dele}".rstrip() + (f"  {sym}" if sym else ""))
    if len(per_file) > room:
        lines.append(f"(+{len(per_file) - room} more files: git diff --stat {rev_label})")
    top = sorted(area.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))
    lines.append("areas: " + " | ".join(f"{k} +{v[0]}/-{v[1]}" for k, v in top[:5]) + (f" | +{len(top) - 5} more" if len(top) > 5 else ""))
    lines.append("RISK: " + (" ".join(flags) if flags else "none") + f"   (flags: {' '.join(FLAGS)})")
    return lines, paths, flags


def compact_names(chosen, reg) -> list:
    """Names of the selected checks; a whole family (`play:*`) collapses into its glob."""
    names = [c.name for c in chosen]
    for prefix in {n.split(":")[0] + ":" for n in reg if ":" in n}:
        family = [n for n in reg if n.startswith(prefix)]
        if all(n in names for n in family):
            names = [n for n in names if n not in family] + [prefix + "*"]
    return names


def suggest(paths, default_base: bool) -> str:
    """The `qa.py check` selection for these files (the same rule `qa.py check` applies to a diff)."""
    import argparse

    from qa_plugins import check as C
    ns = argparse.Namespace(name=None, tag=None, ci=False, all=False, fast=False, changed=True)
    reg = C.load_registry()
    chosen, _by = C.select(reg, ns, [p for p in paths if (ROOT / p).exists()])
    names = compact_names(chosen, reg)
    if default_base:
        return f"check: python tools/qa.py check   ({len(chosen)} of {len(reg)}: {','.join(names)})"
    cmd = f"python tools/qa.py check --name {','.join(names)}" if len(names) <= 8 else "python tools/qa.py check --all"
    return f"check: {cmd}   ({len(chosen)} of {len(reg)} affected)"


def cmd_changed(args) -> int:
    qa = _qa()
    rev = args.rev or args.since
    default_base = not rev
    if default_base:
        base = qa_settings()["tests"]["base_ref"]
        rev = qa.git("merge-base", "HEAD", base) or "HEAD"
        label = f"{base} (merge-base {rev[:7]})" if rev != "HEAD" else "HEAD"
    else:
        label = rev
    if not qa.git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"):
        print(f"CHANGED error: unknown revision {rev!r}")
        return 2
    rows = _diff_rows(rev)
    lines, paths, _flags = summarize(rows, lambda p: _old_text(rev, p), _new_text, label)
    if paths:
        lines.append(suggest(paths, default_base))
    else:
        lines.append("(nothing changed: no files differ from " + label + ")")
    print("\n".join(R.one_line(ln, 200) if len(ln) > 200 else ln for ln in lines[:30]))
    return 0


def register(sub):
    p = sub.add_parser("changed", help="semantic diff summary: symbols +/-/~, LOC, risk flags, suggested checks",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
    p.add_argument("rev", nargs="?", help="revision to compare with (default: merge-base with origin/main)")
    p.add_argument("--since", help="same as the positional REV")
    p.set_defaults(func=cmd_changed)
