"""pack_builder - the logic behind `qa.py pack`: rank files for a task, pick symbol pointers, collect importers/tests, tools, state, verify, do-not-read, answer map.

Stdlib + existing helpers (qa_graph, file_toc, tool_registry). Weights, globs and the answer map: the `pack` table of lua_content/qa.lua.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path

import file_toc
import qa_graph
import tool_registry as TR
from probe_settings import ROOT, qa_settings

_DECL = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?(?:def|fn|class|struct|function)\s+([\w.]+)|^\s*([A-Za-z_]\w*)\s*=\s*\{")
_INDEX_VERSION = 2          # bump when the index layout changes (the cache stamp covers files only)
_EXTS = (".py", ".rs", ".lua")
_WORD = re.compile(r"[a-z][a-z0-9]+")


def _sh(*args: str, root: Path = ROOT) -> str:
    done = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return done.stdout


def _ws(text: str) -> list:
    return sorted({w[:-1] if len(w) > 4 and w.endswith("s") else w for w in _WORD.findall(text.lower()) if len(w) > 2})


def words_of(text: str, stop: set) -> set:
    """Lower-case words (plural -s cut, 3+ letters) that are not stop words."""
    return {w for w in _ws(text) if w not in stop}


def declarations(text: str) -> list:
    """[(line, name)] of the declarations of a source text (regex, cheap)."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        m = _DECL.match(line)
        if m:
            out.append((n, m.group(1) or m.group(2)))
    return out


def churn(root: Path, commits: int) -> Counter:
    text = _sh("git", "log", f"-{commits}", "--name-only", "--pretty=format:", root=root)
    return Counter(ln for ln in text.splitlines() if ln)


def neighbors(graph: dict, seeds: list) -> set:
    near = set(seeds)
    for s in seeds:
        near |= set(graph.get(s, {}).get("imports", [])) | set(qa_graph.importers(graph, s))
    return near


def read(rel: str, root: Path = ROOT) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _blocked(rel: str, cfg: dict) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in cfg.get("do_not_read") or [])


def _is_test(rel: str) -> bool:
    return rel.startswith("tests/") or "/tests/" in rel or qa_graph.is_test(rel)


def _entry(rel: str, text: str, doc: str) -> dict:
    decl = declarations(text)
    head = doc or text[:500]
    return {"pw": _ws(rel.replace("/", " ").replace("_", " ")), "dw": _ws(head), "sw": _ws(" ".join(n.replace("_", " ") for _, n in decl)), "bw": _ws(text), "decl": decl}


def _tool_rows(settings: dict, root: Path) -> list:
    reg = TR.build(root, settings)
    return [[t.owner, _ws(f"{t.id} {t.purpose} {t.when}")] for t in reg.tools if t.owner]


def _corpus_files(cfg: dict, root: Path) -> list:
    return [f for f in _sh("git", "ls-files", "-co", "--exclude-standard", root=root).splitlines() if f.endswith(_EXTS) and not _blocked(f, cfg)]


def _stamp(files: list, root: Path) -> str:
    parts = []
    for rel in files:
        try:
            st = (root / rel).stat()
        except OSError:
            continue
        parts.append(f"{rel}:{st.st_mtime_ns}:{st.st_size}")
    return hashlib.sha1((str(_INDEX_VERSION) + chr(10) + chr(10).join(parts)).encode()).hexdigest()


def load_index(cfg: dict, graph: dict, settings: dict, root: Path = ROOT) -> dict:
    """The corpus index {stamp, files, tools, df}; cached under dev_probe_output/.qa_cache/pack_index.json by a stamp of every file (path, mtime, size)."""
    files = _corpus_files(cfg, root)
    stamp = _stamp(files, root)
    path = root / "dev_probe_output" / ".qa_cache" / "pack_index.json"
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("stamp") == stamp:
            return cached
    except (OSError, ValueError):
        pass
    entries = {rel: _entry(rel, read(rel, root), graph.get(rel, {}).get("doc", "")) for rel in files}
    df = Counter(w for e in entries.values() for w in {*e["pw"], *e["dw"], *e["sw"], *e["bw"]})
    index = {"stamp": stamp, "files": entries, "tools": _tool_rows(settings, root), "df": df}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index), encoding="utf-8")
    return index


def _tool_hits_by_file(index: dict, query: set) -> dict:
    out: dict = {}
    for owner, words in index["tools"]:
        out.setdefault(owner, set()).update(query & set(words))
    return out


def score_entry(rel: str, e: dict, ctx: dict) -> float:
    """IDF-weighted task-word match: path and docstring and registry rows above function names; proximity and churn only break ties."""
    w, q, idf = ctx["weights"], ctx["query"], ctx["idf"]
    tool = ctx["tool_words"].get(rel, set())
    score = sum(idf[x] * (w["path"] * (x in e["pw"]) + w["doc"] * (x in e["dw"]) + w["tool"] * (x in tool) + w["symbol"] * (x in e["sw"]) + w["body"] * (x in e["bw"])) for x in q)
    if score:
        score += w["neighbor"] * (rel in ctx["near"]) + w["churn"] * min(ctx["churn"].get(rel, 0), 5) / 5
    return score


def rank_files(task: str, seeds: list, cfg: dict, graph: dict, root: Path = ROOT) -> list:
    """[(score, rel, [pointer])] best first; tests only when the task mentions test/pytest; pointers are `file:Lstart-Lend symbol`."""
    stop = set(cfg.get("stopwords") or [])
    index = load_index(cfg, graph, qa_settings(), root)
    query = words_of(task, stop)
    n = len(index["files"])
    idf = {w: math.log(1 + n / (1 + index["df"].get(w, 0))) for w in query}
    ctx = {"weights": cfg["weights"], "query": query, "idf": idf, "near": neighbors(graph, seeds), "churn": churn(root, int(cfg["churn_commits"])), "tool_words": _tool_hits_by_file(index, query)}
    want_tests = bool(set(_WORD.findall(task.lower())) & {"test", "tests", "pytest"})
    scored = [(score_entry(rel, e, ctx), rel, e) for rel, e in index["files"].items() if want_tests or not _is_test(rel)]
    scored = sorted((x for x in scored if x[0] > 0), key=lambda x: (-x[0], x[1]))[: int(cfg["top"])]
    return [(s, rel, pointers(rel, _matching(e, query, stop), int(cfg["pointers"]), root)) for s, rel, e in scored]


def _matching(e: dict, query: set, stop: set) -> list:
    return [(n, name) for n, name in e["decl"] if query & words_of(name.replace("_", " "), stop)]


def pointers(rel: str, hits: list, limit: int, root: Path = ROOT) -> list:
    text = read(rel, root)
    ext = rel.rsplit(".", 1)[-1]
    out = []
    for _, name in hits[:limit]:
        span = file_toc.symbol_span(text, ext, name.split(".")[-1].split("::")[-1])
        if span:
            out.append(f"{rel}:L{span[0]}-{span[1]} {name}")
    return out or [f"{rel}: see `qa.py ctx {rel}`"]


def links(tops: list, graph: dict, limit: int) -> tuple:
    """(importers, tests) of the top files."""
    files = [rel for rel in tops if rel in graph]
    imp = sorted({p for f in files for p in qa_graph.importers(graph, f)} - set(tops))
    direct = [p for p in imp if qa_graph.is_test(p)]
    return [p for p in imp if not qa_graph.is_test(p)][:limit], direct[:limit]


def tool_hits(task: str, cfg: dict, settings: dict, root: Path = ROOT) -> list:
    hits = TR.find(TR.build(root, settings), task, settings.get("tools") or {}, int(cfg["tools"]))
    return [f"{t.command or t.id} - {t.purpose}"[:120] for t in hits]


def _last_rows(path: Path, tail: int) -> dict:
    last = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            last[row.get("name")] = row
    return last


def state_lines(root: Path, cfg: dict, history: Path | None = None) -> list:
    """Latest non-ok check lines from history.jsonl + dirty files."""
    last = _last_rows(history or root / "dev_probe_output" / "qa" / "history.jsonl", int(cfg["history_rows"]))
    bad = [f"{r['status']} {n}" for n, r in last.items() if r.get("status") not in ("ok", "cached", "skip")]
    dirty = [ln[3:] for ln in _sh("git", "status", "--porcelain", root=root).splitlines()]
    out = [f"last check not ok: {', '.join(bad[:6])}" if bad else "last check: no failing line in history"]
    return out + ([f"dirty ({len(dirty)}): {', '.join(dirty[:6])}"] if dirty else ["dirty: none"])


def answers(task: str, cfg: dict) -> list:
    low = task.lower() + " "
    return [f"{row['use']}  ({row['why']})" for row in cfg.get("answers") or [] if any(w in low for w in row["words"])]


def verify_cmd(top: list) -> str:
    """The narrowest check command for the top files."""
    return "python tools/qa.py check --changed" if top else "python tools/qa.py check"


def build_pack(task: str, seeds: list, cfg: dict, settings: dict, root: Path = ROOT) -> dict:
    graph = qa_graph.build(True)
    ranked = rank_files(task, seeds, cfg, graph, root)
    tops = [rel for _, rel, _ in ranked]
    imp, tests = links(tops, graph, int(cfg["links"]))
    return {"files": [p for _, _, ptrs in ranked for p in ptrs], "top": tops, "importers": imp, "tests": tests,
            "tools": tool_hits(task, cfg, settings, root), "state": state_lines(root, cfg),
            "verify": verify_cmd(tops), "answers": answers(task, cfg), "skip": list(cfg["do_not_read"])}


def fit_tokens(lines: list, max_tok: int, per_tok: int) -> list:
    """Whole lines while the total stays under max_tok (chars/per_tok); a `verify` line is always kept; the cut is announced."""
    out, used = [], 0
    for i, line in enumerate(lines):
        cost = len(line) // per_tok + 1
        if used + cost > max_tok - 8 and not line.startswith("verify"):
            out.append(f"... +{len(lines) - i} lines cut (--max-tok {max_tok})")
            out += [x for x in lines[i:] if x.startswith("verify")]
            return out
        out.append(line)
        used += cost
    return out
