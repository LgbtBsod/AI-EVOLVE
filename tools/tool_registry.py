"""tool_registry - the registry of every tool (qa.py subcommand, check, tools/ script, Rust export, Lua header): harvest, docs/TOOLS.md, gaps.

Logic behind `qa.py tools`; data (required keys, similarity threshold, allowlist, groups, hand-written rows) = the `tools` table of lua_content/qa.lua.
Sources of one tool's metadata, weakest first: what the code says about itself (`help=`, docstring, argparse description, a check's `what`,
Rust `///` docs) < `TOOL = {...}` in a plugin / `-- tool: purpose` header of a Lua file < a row of `tools.rows` in qa.lua (by id; `manual = true`
adds a tool no harvester can see). Everything is sorted and free of timestamps, so `render` is byte-for-byte reproducible and `report` can diff
it against docs/TOOLS.md.
"""
from __future__ import annotations

import ast
import re
import shlex
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import qa_report as R

DOC = "docs/TOOLS.md"
REPRO = "python tools/qa.py tools --write"
TEXT_KEYS = ("command", "purpose", "when", "replaces", "output", "owner", "cost", "status", "group", "wraps")
KIND_GROUP = {"check": "verify", "rust": "kernels", "lua": "content", "lib": "libs"}     # any other kind: analyse


@dataclass
class Tool:
    id: str                 # unique and shown as the name: `ctx`, `check:tests`, `agent_play`, `rust:QaKernels`, `lua:qa.lua`
    kind: str               # qa | check | script | lib | dir | rust | lua | manual
    command: str = ""
    purpose: str = ""       # one line: what it answers
    when: str = ""          # the situation to reach for it (used by --find only)
    replaces: str = ""      # the raw action it makes unnecessary
    output: str = ""        # the shape of what it prints
    owner: str = ""         # file that implements it
    cost: str = ""          # low | medium | high
    status: str = "active"
    group: str = ""
    wraps: str = ""         # the command a check runs: (check, the tool it runs) is by construction not a duplicate


@dataclass
class Registry:
    tools: list
    problems: list = field(default_factory=list)      # (kind, text): kind = dup | drift


# ---------------------------------------------------------------- small helpers

def _as_list(x) -> list:
    """Lua turns {} into {} and {"a"} into ["a"]: accept both (and a bare string)."""
    return [x] if isinstance(x, str) else list(x.values()) if isinstance(x, dict) else list(x or [])


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _first_line(text: str | None) -> str:
    return next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(_read(path))
    except (SyntaxError, ValueError):
        return None


def _apply(tool: Tool, meta: dict) -> None:
    for key in TEXT_KEYS:
        if meta.get(key):
            setattr(tool, key, str(meta[key]))


def _literal(tree: ast.Module, name: str):
    """Module-level `NAME = <literal>` -> its value (None when absent or not a literal)."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def _str_kw(call: ast.Call, key: str) -> str:
    return next((k.value.value for k in call.keywords if k.arg == key and isinstance(k.value, ast.Constant)
                 and isinstance(k.value.value, str)), "")


def _is_add_parser(node: ast.AST, receiver: str) -> bool:
    """`<receiver>.add_parser("literal", ...)`."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_parser"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == receiver
            and bool(node.args) and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str))


def _subcommands(tree: ast.Module, func: str, receiver: str | None = None) -> list:
    """[(name, help)] of every `<receiver>.add_parser("name", help=...)` in `def func` (receiver None = its first argument)."""
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if fn is None:
        return []
    recv = receiver or (fn.args.args[0].arg if fn.args.args else "")
    return [(c.args[0].value, _str_kw(c, "help")) for c in ast.walk(fn) if _is_add_parser(c, recv)]


# ---------------------------------------------------------------- harvest: qa.py subcommands

_HEADER_CMD = re.compile(r"^\s*python tools/qa\.py (\w[\w-]*)[^#\n]*#\s*(.+?)\s*$", re.MULTILINE)


def _qa_tool(name: str, purpose: str, owner: str) -> Tool:
    return Tool(name, "qa", command=f"python tools/qa.py {name}", purpose=purpose, owner=owner)


def _plugin_tools(root: Path, path: Path) -> list:
    tree = None if path.name.startswith("_") else _parse(path)
    if tree is None:
        return []
    doc = _first_line(ast.get_docstring(tree))
    tools = [_qa_tool(name, help_ or doc, path.relative_to(root).as_posix()) for name, help_ in _subcommands(tree, "register")]
    meta = _literal(tree, "TOOL") or {}
    for t in tools:
        if len(tools) == 1 or t.id == path.stem:
            _apply(t, meta)
    return tools


def harvest_qa(root: Path) -> list:
    """The built-in subcommands (`sub.add_parser` in qa.py, purpose from its header docstring) + one per tools/qa_plugins/*.py."""
    qa = root / "tools" / "qa.py"
    tree = _parse(qa) if qa.is_file() else None
    tools = []
    if tree is not None:
        header: dict = {}
        for name, purpose in _HEADER_CMD.findall(ast.get_docstring(tree) or ""):
            header.setdefault(name, purpose)                     # first mention wins (`test`, then `test --update-known`)
        tools = [_qa_tool(name, help_ or header.get(name, ""), "tools/qa.py") for name, help_ in _subcommands(tree, "main", "sub")]
    for path in sorted((root / "tools" / "qa_plugins").glob("*.py")):
        tools += _plugin_tools(root, path)
    return tools


# ---------------------------------------------------------------- harvest: tools/ scripts, libraries, directories

def _argparse_description(tree: ast.Module) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "ArgumentParser":
            return _str_kw(node, "description")
    return ""


_MAIN_GUARD = re.compile(r"^(?:if __name__ == [\"']__main__[\"']|sys\.exit\()", re.MULTILINE)     # a runnable script, not a library


def _script_tool(root: Path, path: Path) -> Tool:
    text, tree = _read(path), _parse(path)
    purpose = (_first_line(ast.get_docstring(tree)) or _first_line(_argparse_description(tree))) if tree is not None else ""
    is_main = bool(_MAIN_GUARD.search(text))
    return Tool(path.stem, "script" if is_main else "lib", command=f"python tools/{path.name}" if is_main else f"import {path.stem}",
                purpose=purpose, owner=path.relative_to(root).as_posix())


def _dir_tool(root: Path, path: Path) -> Tool:
    init, readme = path / "__init__.py", path / "README.md"
    purpose = ""
    if init.is_file() and (tree := _parse(init)) is not None:
        purpose = _first_line(ast.get_docstring(tree))
    if not purpose and readme.is_file():
        purpose = next((ln.strip() for ln in _read(readme).splitlines() if ln.strip() and not ln.startswith("#")), "")
    return Tool(path.name, "dir", purpose=purpose, owner=path.relative_to(root).as_posix() + "/")


def harvest_scripts(root: Path, skip_dirs=()) -> list:
    """tools/*.py (script when it has a `__main__` guard, else a library; `_x.py` and qa.py itself are skipped) + subdirectories with code."""
    base = root / "tools"
    if not base.is_dir():
        return []
    tools = [_script_tool(root, p) for p in sorted(base.glob("*.py")) if not p.name.startswith("_") and p.name != "qa.py"]
    return tools + [_dir_tool(root, d) for d in sorted(base.iterdir())
                    if d.is_dir() and d.name not in skip_dirs and not d.name.startswith(("_", ".")) and any(d.glob("*.py"))]


# ---------------------------------------------------------------- harvest: checks (qa.lua data, scenarios, @check)

def _check_tool(name: str, what: str, cost: str, cmd: str, owner: str) -> Tool:
    return Tool(f"check:{name}", "check", command=f"python tools/qa.py check --name {name}", purpose=what, cost=cost,
                output="qa_report line", owner=owner, wraps=cmd)


def harvest_checks(root: Path, cfg: dict) -> list:
    """Lua-declared checks, ONE row for all `play:NAME` gameplay checks (scenarios + plays), and tools/qa_checks/*.py `@check`s."""
    tools = [_check_tool(d["name"], d.get("what", ""), d.get("cost", "medium"), d.get("cmd", ""), "lua_content/qa.lua")
             for d in _as_list(cfg.get("checks")) if d.get("name")]
    plays = sorted(p["name"] for p in [*_as_list(cfg.get("scenarios")), *_as_list(cfg.get("plays"))] if p.get("name"))
    if plays:
        base = cfg.get("scenario_check") or {}
        tools.append(Tool("check:play:*", "check", command="python tools/qa.py check --tag play", cost=base.get("cost", "low"),
                          purpose=f"{len(plays)} gameplay checks (agent_play scripts of qa.lua scenarios/plays): {', '.join(plays)}",
                          output="qa_report line", owner="lua_content/qa.lua", wraps="python tools/agent_play.py"))
    tools += [_check_tool(c.name, c.what, c.cost, "", c.source) for c in R.load_python_checks(root / "tools" / "qa_checks")]
    return tools


# ---------------------------------------------------------------- harvest: Rust exports, Lua headers

_RUST_ITEM = re.compile(r"^((?:[ \t]*///.*\n)*)[ \t]*(#\[py(?:class|function)[^\n]*\n(?:[ \t]*#\[[^\n]*\n)*)"
                        r"[ \t]*(?:pub(?:\([^)]*\))?\s+)?(?:struct|fn)\s+(\w+)", re.MULTILINE)
_PY_NAME = re.compile(r'name\s*=\s*"(\w+)"')


def _rust_tools(root: Path, path: Path) -> list:
    tools = []
    for docs, attrs, ident in _RUST_ITEM.findall(_read(path)):
        given = _PY_NAME.search(attrs)
        name = given.group(1) if given else re.sub(r"^(?:Py|py_)", "", ident)
        text = " ".join(ln.strip()[3:].strip() for ln in docs.splitlines())
        rel = path.relative_to(root).as_posix()
        tools.append(Tool(f"rust:{name}", "rust", command=f"rust_core.{name}", purpose=re.split(r"(?<=\.)\s", text, maxsplit=1)[0],
                          owner=rel))
    return tools


def harvest_rust(root: Path) -> list:
    """`#[pyclass]` / `#[pyfunction]` items of rust_core/src/**/*.rs as `rust_core.NAME`; purpose = the first sentence of their `///` docs."""
    return [t for path in sorted((root / "rust_core" / "src").rglob("*.rs")) for t in _rust_tools(root, path)]


_LUA_TOOL = re.compile(r"^--\s*tool(?:\.(\w+))?:\s*(.+?)\s*$")


def _lua_meta(path: Path) -> dict:
    """`-- tool: purpose` and `-- tool.KEY: value` lines in the first 30 lines of a Lua file."""
    meta = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for _, line in zip(range(30), fh, strict=False):
            if m := _LUA_TOOL.match(line):
                meta[m.group(1) or "purpose"] = m.group(2)
    return meta


def harvest_lua(root: Path) -> list:
    """lua_content/**/*.lua files that declare a purpose with a `-- tool:` header (settings/content files without one are not tools)."""
    tools = []
    for path in sorted((root / "lua_content").rglob("*.lua")):
        if meta := _lua_meta(path):
            rel = path.relative_to(root / "lua_content").as_posix()
            t = Tool(f"lua:{rel}", "lua", command=f"python tools/qa.py lua show lua_content/{rel}", owner=f"lua_content/{rel}")
            _apply(t, meta)
            tools.append(t)
    return tools


# ---------------------------------------------------------------- merge

def _apply_rows(tools: dict, rows: list) -> list:
    problems = []
    for row in rows:
        rid = str(row.get("id", ""))
        if rid not in tools and row.get("manual"):
            tools[rid] = Tool(rid, "manual")
        if rid in tools:
            _apply(tools[rid], row)
        else:
            problems.append(("drift", f"tools.rows: id {rid!r} matches no tool (renamed or removed?) - fix the id or set manual = true"))
    return problems


def build(root: Path, cfg: dict) -> Registry:
    """Harvest everything, apply explicit metadata, fill the default group, sort (group order, then id)."""
    tcfg = cfg.get("tools") or {}
    found = [*harvest_qa(root), *harvest_scripts(root, _as_list(tcfg.get("skip_dirs"))), *harvest_checks(root, cfg),
             *harvest_rust(root), *harvest_lua(root)]
    tools: dict = {}
    problems = []
    for t in found:
        if t.id in tools:
            problems.append(("dup", f"same name twice: {t.id!r} ({tools[t.id].owner} and {t.owner}) - rename one or extend the other"))
        else:
            tools[t.id] = t
    problems += _apply_rows(tools, [r for r in _as_list(tcfg.get("rows")) if isinstance(r, dict)])
    rank = {g: i for i, (g, _) in enumerate(_groups(tcfg))}
    for t in tools.values():
        t.group = t.group or KIND_GROUP.get(t.kind, "analyse")
    return Registry(sorted(tools.values(), key=lambda t: (rank.get(t.group, len(rank)), t.group, t.id)), problems)


# ---------------------------------------------------------------- render

def _groups(tcfg: dict) -> list:
    return [(g["id"], g.get("title", g["id"])) for g in _as_list(tcfg.get("groups")) if isinstance(g, dict) and g.get("id")]


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _clip(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 3].rsplit(" ", 1)[0] + "..."


def _row(t: Tool, width: int) -> str:
    purpose = t.purpose + ("" if t.status == "active" else f" [{t.status}]")
    cells = [f"`{t.id}`", f"`{t.command}`" if t.command else "-", _clip(purpose, width) or "?", _clip(t.replaces, width) or "-",
             t.output or "-", t.cost or "-"]
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def render(reg: Registry, cfg: dict) -> str:
    """docs/TOOLS.md: header + one table per group. Deterministic (sorted, no timestamps)."""
    tcfg = cfg.get("tools") or {}
    width = int(tcfg.get("cell_width", 110))
    titles = dict(_groups(tcfg))
    lines = ["# Tools registry", "",
             f"Generated by `{REPRO}` - do not edit: change a tool's docstring/`help=`/`TOOL = {{}}` or a row of `tools.rows` in lua_content/qa.lua.",
             "Before writing any tool or script, run `python tools/qa.py tools --find \"words\"`: extend a match instead of adding a twin.", ""]
    for group in dict.fromkeys(t.group for t in reg.tools):
        lines += [f"### {titles.get(group, group)}", "| tool | command | purpose | replaces | output | cost |", "|---|---|---|---|---|---|"]
        lines += [_row(t, width) for t in reg.tools if t.group == group]
    return "\n".join(lines) + "\n"


def write(root: Path, cfg: dict) -> Path:
    path = root / DOC
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(build(root, cfg), cfg), encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------- gaps: undocumented, near-duplicates, stale docs, drift

def _tokens(text: str, stop: set) -> frozenset:
    words = re.findall(r"[a-z][a-z0-9]+", text.lower())
    return frozenset(w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words if w not in stop)


def _argv(cmd: str) -> list:
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _wraps(a: Tool, b: Tool) -> bool:
    """One command is the other with more arguments (a check that runs a tool, `qa.py lua` vs `qa.py lua check`): not a duplicate."""
    x, y = _argv(a.wraps or a.command), _argv(b.wraps or b.command)
    n = min(len(x), len(y))
    return n >= 2 and x[:n] == y[:n]


def similarity(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def dup_suspects(tools: list, tcfg: dict) -> list:
    """[(similarity, a, b)] worst first: token-set (Jaccard) similarity of name + purpose >= tools.dup_threshold, minus wrappers and allow-listed pairs."""
    stop, allow = set(_as_list(tcfg.get("stopwords"))), set(_as_list(tcfg.get("dup_allow")))
    limit = float(tcfg.get("dup_threshold", 0.6))
    toks = [(t, _tokens(f"{t.id.split(':', 1)[-1]} {t.purpose}", stop)) for t in tools]
    out = []
    for (a, ta), (b, tb) in combinations(toks, 2):
        if _wraps(a, b) or "~".join(sorted((a.id, b.id))) in allow:
            continue
        if (s := similarity(ta, tb)) >= limit:
            out.append((s, a, b))
    return sorted(out, key=lambda x: (-x[0], x[1].id, x[2].id))


def undocumented(tools: list, tcfg: dict) -> list:
    """[(tool, [missing keys])]: a required key (default: purpose) that is empty; a purpose under 8 characters counts as missing."""
    required = _as_list(tcfg.get("required")) or ["purpose"]
    out = []
    for t in tools:
        gone = [k for k in required if not getattr(t, k, "") or (k == "purpose" and len(t.purpose.strip()) < 8)]
        if gone:
            out.append((t, gone))
    return out


def _word_score(word: str, name: frozenset, body: frozenset) -> int:
    if word in name:
        return 3
    if word in body:
        return 2
    return int(any(p.startswith(word) or word.startswith(p) for p in name | body if len(p) > 3))


def find(reg: Registry, words: str, tcfg: dict, limit: int | None = None) -> list:
    """Tools ranked by how well they match `words`: a hit in the name counts 3, in purpose/when/replaces 2, a prefix match 1."""
    stop = set(_as_list(tcfg.get("stopwords")))
    query = _tokens(words, stop)
    scored = []
    for t in reg.tools:
        name, body = _tokens(t.id, stop), _tokens(f"{t.purpose} {t.when} {t.replaces}", stop)
        if score := sum(_word_score(w, name, body) for w in query):
            scored.append((-score, t.id, t))
    return [t for *_, t in sorted(scored, key=lambda x: x[:2])][:limit or int(tcfg.get("max_find", 8))]


_CLAUDE_CMD = re.compile(r"(?:tools/)?qa\.py\s+([a-z][\w-]*)")


def claude_drift(root: Path, reg: Registry, tcfg: dict) -> list:
    """`qa.py WORD` in CLAUDE.md where WORD is not a subcommand (a documented command that was renamed or never existed)."""
    md = root / "CLAUDE.md"
    if not md.is_file():
        return []
    known = {t.id for t in reg.tools if t.kind == "qa"} | set(_as_list(tcfg.get("drift_ignore")))
    return [f"CLAUDE.md: `qa.py {w}` is not a qa.py subcommand" for w in sorted(set(_CLAUDE_CMD.findall(_read(md)))) if w not in known]


def doc_state(root: Path, reg: Registry, cfg: dict) -> str:
    """'' when docs/TOOLS.md equals the harvest, else why not."""
    path = root / DOC
    if not path.is_file():
        return f"{DOC} is missing"
    return "" if _read(path).replace("\r\n", "\n") == render(reg, cfg) else f"{DOC} differs from the harvest"


def _lines_of_gaps(missing: list, dups: list) -> list:
    out = [f"undocumented: {t.id} ({t.owner or t.kind}) lacks {', '.join(gone)} -> docstring / help= / TOOL = {{}} / row in qa.lua tools.rows"
           for t, gone in missing]
    return out + [f"dup: {a.id} ~ {b.id} sim={sim:.2f} -> extend one instead, or list \"{'~'.join(sorted((a.id, b.id)))}\" in qa.lua tools.dup_allow"
                  for sim, a, b in dups]


def _result(metrics: dict, detail: list, tcfg: dict) -> R.Result:
    failed = bool(detail)
    limit = int(tcfg.get("max_lines", 140))
    if not failed and metrics["lines"] > limit:
        detail = [f"{DOC} has {metrics['lines']} lines (> tools.max_lines {limit}): shorten purposes or fold rows"]
    cap = int(tcfg.get("max_detail", 10))
    detail = detail[:cap] + ([f"(+{len(detail) - cap} more)"] if len(detail) > cap else [])
    return R.Result("fail" if failed else "warn" if detail else "ok", metrics, detail, REPRO if failed else None)


def report(root: Path, cfg: dict) -> R.Result:
    """The `tools` check: one Result (ok / fail / warn when the doc grows past tools.max_lines) with counts and one detail line per problem."""
    tcfg = cfg.get("tools") or {}
    reg = build(root, cfg)
    missing, dups = undocumented(reg.tools, tcfg), dup_suspects(reg.tools, tcfg)
    same_name = [text for kind, text in reg.problems if kind == "dup"]
    drift = [text for kind, text in reg.problems if kind == "drift"] + claude_drift(root, reg, tcfg)
    stale = doc_state(root, reg, cfg)
    detail = [*_lines_of_gaps(missing, dups), *same_name, *([f"stale: {stale} -> {REPRO}"] if stale else []), *drift]
    metrics = {"tools": len(reg.tools), "documented": len(reg.tools) - len(missing), "undocumented": len(missing),
               "dup_suspects": len(dups) + len(same_name), "stale": int(bool(stale)), "drift": len(drift),
               "lines": render(reg, cfg).count(chr(10))}
    return _result(metrics, detail, tcfg)
