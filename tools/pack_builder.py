"""pack_builder - the logic behind `qa.py pack`: rank files for a task, pick symbol pointers, collect importers/tests, tools, state, verify, do-not-read, answer map.

Stdlib + existing helpers (qa_graph, file_toc, tool_registry). Weights, globs and the answer map: the `pack` table of lua_content/qa.lua.
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import file_toc
import qa_graph
import tool_registry as TR
from probe_settings import ROOT

_DECL = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?(?:def|fn|class|struct|function)\s+([\w.]+)|^\s*([A-Za-z_]\w*)\s*=\s*\{")
_EXTS = (".py", ".rs", ".lua")
_WORD = re.compile(r"[a-z][a-z0-9]+")


def _sh(*args: str, root: Path = ROOT) -> str:
    done = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return done.stdout


def words_of(text: str, stop: set) -> set:
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in _WORD.findall(text.lower()) if w not in stop and len(w) > 2}


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


def score_file(rel: str, text: str, doc: str, ctx: dict) -> tuple:
    """(score, [(line, name)] of the declarations that match the task)."""
    w, q, stop = ctx["weights"], ctx["query"], ctx["stop"]
    decl = declarations(text)
    pw = words_of(rel.replace("/", " ").replace("_", " "), stop)
    sw = words_of(" ".join(n.replace("_", " ") for _, n in decl), stop)
    score = w["path"] * len(q & pw) + w["symbol"] * len(q & sw) + w["doc"] * len(q & words_of(doc, stop))
    if score:
        score += w["neighbor"] * (rel in ctx["near"]) + w["churn"] * min(ctx["churn"].get(rel, 0), 5) / 5
    return score, [(n, name) for n, name in decl if q & words_of(name.replace("_", " "), stop)]


def read(rel: str, root: Path = ROOT) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _blocked(rel: str, cfg: dict) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in cfg.get("do_not_read") or [])


def rank_files(task: str, seeds: list, cfg: dict, graph: dict, root: Path = ROOT) -> list:
    """[(score, rel, [pointer])] best first; pointers are `file:Lstart-Lend symbol`."""
    stop = set(cfg.get("stopwords") or [])
    ctx = {"weights": cfg["weights"], "query": words_of(task, stop), "stop": stop, "near": neighbors(graph, seeds), "churn": churn(root, int(cfg["churn_commits"]))}
    files = [f for f in _sh("git", "ls-files", "-co", "--exclude-standard", root=root).splitlines() if f.endswith(_EXTS) and not _blocked(f, cfg)]
    scored = []
    for rel in files:
        score, hits = score_file(rel, read(rel, root), graph.get(rel, {}).get("doc", ""), ctx)
        if score:
            scored.append((score, rel, hits))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(s, rel, pointers(rel, hits, int(cfg["pointers"]), root)) for s, rel, hits in scored[: int(cfg["top"])]]


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
