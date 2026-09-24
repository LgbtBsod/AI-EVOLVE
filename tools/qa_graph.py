#!/usr/bin/env python3
"""Граф импортов проекта: что живое, что мёртвое, какие тесты задевает правка.

Агент тратит больше всего токенов на чтение НЕ ТОГО кода: в репозитории
много модулей, которые никто не импортирует (остатки прошлых итераций), и
отчётов про них. Граф строится статически (ast, без импорта модулей - ничего
не исполняется), включая ленивые импорты внутри функций и относительные.

- liveness(): для каждого модуля - откуда он достижим: game (из main.py),
  tool (из скрипта в tools/), test (только из тестов) или dead;
- impacted(changed_files): какие тест-файлы и smoke-скрипты транзитивно
  импортируют изменённые файлы (для не-.py файлов - модули, где упомянуто
  имя файла: lua_content/*.lua, config/*.json).

Обход графа (достижимость) - rust_core.QaKernels.reach по CSR-буферам
(array('Q')), Python-двойник в probe_kernels. Разрешение имён повторяет
sys.path-хаки проекта: корень, каталог файла,
tools/, src/, python_layer/, src/core/. Кэш - dev_probe_output/.qa_cache.
"""
import ast
import json
import os
from array import array
from pathlib import Path

import probe_kernels as kernels

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "target", "dev_probe_output", "__pycache__", ".venv", "venv", "build", "dist",
             "node_modules", ".pytest_cache"}
SEARCH_ROOTS = [ROOT, ROOT / "tools", ROOT / "src", ROOT / "python_layer", ROOT / "src" / "core"]
CACHE = ROOT / "dev_probe_output" / ".qa_cache" / "graph.json"
# Импорты, которых нет в ast: игра поднимается через importlib.import_module(entry_module)
DYNAMIC_EDGES = {"tools/probe_runtime.py": ["main.py"]}


def py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".venv")]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def _parse(path):
    """-> (imports: [(module, level, names)], is_script, first_doc_line, loc)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], False, "(syntax error for this Python)", text.count("\n")
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((a.name, 0, []) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.module or "", node.level, [a.name for a in node.names]))
    # Строковые литералы-пути к .py ("tools/agent_play.py" в subprocess-тестах).
    # Только в тестах: в остальном коде такие строки - подсказки, не запуск.
    for node in (ast.walk(tree) if path.name.startswith("test_") else ()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".py") \
                and "/" in node.value and (ROOT / node.value).is_file():
            imports.append(("__path__:" + node.value, 0, []))
    # Скрипт: `if __name__ == "__main__"` или sys.exit(...) на верхнем уровне
    # (combat_smoke_test.py исполняется прямо при импорте)
    is_script = any(
        (isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name)
         and n.test.left.id == "__name__")
        or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr == "exit" and isinstance(n.value.func.value, ast.Name) and n.value.func.value.id == "sys")
        for n in tree.body)
    doc = (ast.get_docstring(tree) or "").strip().splitlines()
    return imports, is_script, (doc[0][:100] if doc else ""), text.count("\n") + 1


def _resolve(dotted, base_dirs):
    """dotted 'a.b.c' -> файл проекта или None (сторонние пакеты - None)."""
    parts = dotted.split(".") if dotted else []
    for base in base_dirs:
        cand = base.joinpath(*parts) if parts else base
        for p in (cand.with_suffix(".py") if parts else None, cand / "__init__.py"):
            if p is not None and p.is_file():
                return p
    return None


def _edges(path, imports):
    out = set()
    here = path.parent
    for module, level, names in imports:
        if module.startswith("__path__:"):
            out.add((ROOT / module.split(":", 1)[1]).resolve())
            continue
        if level:
            base = here
            for _ in range(level - 1):
                base = base.parent
            bases = [base]
        else:
            bases = [here, *SEARCH_ROOTS]
        target = _resolve(module, bases)
        if target is not None:
            out.add(target)
            # import a.b.c исполняет a/__init__.py и a/b/__init__.py
            parts = module.split(".") if module else []
            for base in bases:
                if target.is_relative_to(base):
                    for i in range(1, len(parts)):
                        init = base.joinpath(*parts[:i], "__init__.py")
                        if init.is_file():
                            out.add(init)
                    break
        # `from pkg import submodule` - имя может быть модулем
        for name in names:
            sub = _resolve(f"{module}.{name}" if module else name, bases)
            if sub is not None:
                out.add(sub)
    out.discard(path)
    return out


def _node_entry(path_str):
    f = Path(path_str)
    imports, is_script, doc, loc = _parse(f)
    edges = {rel(t) for t in _edges(f, imports)} | set(DYNAMIC_EDGES.get(rel(f), []))
    return rel(f), {"imports": sorted(edges), "script": is_script, "doc": doc, "loc": loc}


def build(use_cache=True):
    """-> {rel_path: {"imports": [...], "script": bool, "doc": str, "loc": int}}"""
    files = sorted(py_files())
    stamp = {rel(f): f.stat().st_mtime_ns for f in files}
    if use_cache and CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("stamp") == stamp:
                return cached["graph"]
        except (ValueError, KeyError):
            pass
    # Холодная сборка: ast.parse - CPU-bound, поэтому процессы, а не потоки (GIL)
    if len(files) >= 64 and (os.cpu_count() or 1) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=min(8, os.cpu_count())) as pool:
            graph = dict(pool.map(_node_entry, map(str, files), chunksize=16))
    else:
        graph = dict(map(_node_entry, map(str, files)))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"stamp": stamp, "graph": graph}), encoding="utf-8")
    return graph


def is_test(path):
    name = path.rsplit("/", 1)[-1]
    return name.startswith("test_") and name.endswith(".py")


def entry_points(graph):
    game = [p for p in ("main.py", "setup.py") if p in graph]
    tools = [p for p, n in graph.items() if p.startswith("tools/") and n["script"] and not is_test(p)]
    tests = [p for p in graph if is_test(p)]
    return {"game": game, "tool": tools, "test": tests}


def to_csr(graph, reverse=False):
    """Граф -> (nodes, index, offsets, targets): CSR для rust_core.QaKernels.reach."""
    nodes = sorted(graph)
    index = {p: i for i, p in enumerate(nodes)}
    adj = [[] for _ in nodes]
    for p, node in graph.items():
        for t in node["imports"]:
            if t in index:
                (adj[index[t]] if reverse else adj[index[p]]).append(index[p] if reverse else index[t])
    offsets, targets = array("Q", [0]), array("Q")
    for row in adj:
        targets.extend(row)
        offsets.append(len(targets))
    return nodes, index, offsets, targets


def reachable(graph, roots, reverse=False):
    nodes, index, offsets, targets = to_csr(graph, reverse)
    flags = kernels.reach(offsets, targets, array("Q", (index[r] for r in roots if r in index)))
    return {nodes[i] for i, f in enumerate(flags) if f}


def liveness(graph):
    """-> {path: 'game' | 'tool' | 'test' | 'dead'} (первая подходящая категория)."""
    eps = entry_points(graph)
    reach = {k: reachable(graph, v) for k, v in eps.items()}
    status = {}
    for p in graph:
        if is_test(p) or p.endswith("conftest.py"):
            status[p] = "test"
            continue
        for kind in ("game", "tool", "test"):
            if p in reach[kind]:
                status[p] = kind
                break
        else:
            status[p] = "dead"
    return status


def dependents(graph, targets):
    """Все файлы, транзитивно импортирующие любой из targets (включая сами targets)."""
    return reachable(graph, targets, reverse=True)


def importers(graph, target):
    """Прямые импортёры файла."""
    return sorted(p for p, node in graph.items() if target in node["imports"])


def mentions(graph, filename):
    """Модули, в тексте которых упомянуто имя файла (для .lua/.json/.prc)."""
    needle = Path(filename).name
    return {p for p in graph if needle in (ROOT / p).read_text(encoding="utf-8", errors="replace")}


def impacted(graph, changed):
    """changed: пути относительно корня. -> (tests, scripts, touched_modules)."""
    targets = set()
    for c in changed:
        if c.endswith(".py") and c in graph:
            targets.add(c)
        elif not c.endswith(".py"):
            targets |= mentions(graph, c)
    deps = dependents(graph, targets)
    tests = sorted(p for p in deps if is_test(p))
    scripts = sorted(p for p in deps if p.startswith("tools/") and graph[p]["script"] and not is_test(p))
    return tests, scripts, sorted(targets)
