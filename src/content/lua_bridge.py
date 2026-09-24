"""Lua -> Python одним куском: единственный загрузчик Lua-контента проекта.

Контент и настройки лежат в Lua (lua_content/**). Раньше их читали тремя
копиями конвертера lupa -> dict (каждый ключ - отдельный переход между
языками) и самописным текстовым парсером (токенизация регулярками). Теперь
Lua ИСПОЛНЯЕТСЯ готовым движком, а данные пересекают границу один раз:

  1. cache - sha256(исходник + формат экспорта) -> готовый JSON на диске;
  2. rust  - rust_core.LuaContent: mlua в песочнице, serde mlua -> одна
             JSON-строка -> json.loads (C);
  3. lupa  - lupa.lua55 (фолбэк без собранного rust_core).

Правила экспорта (pred("src", fn) -> "src", функции отбрасываются) - один
Lua-файл lua_content/lib/export.lua (его копию встраивает rust_core), его
исполняют оба бэкенда.
Песочница одинаковая: без io/os/package/debug, без dofile/loadfile/load,
print заглушён (вывод файла-данных - только шум в отчётах).

API:
    load(src_or_path, globals=None, cache=False, backend=None) -> данные
    eval_preds(src_or_path, ctxs, backend=None) -> [{условие: результат}]
    available_backends(), bench(src_or_path)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

# Корень приложения: каталог exe в собранной игре (build_apps), иначе корень репозитория
ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
CONTENT = ROOT / "lua_content"
# Копия rust_core/src/lua_content/export.lua (её встраивает include_str!);
# тест tests/test_lua_bridge.py следит, чтобы копии совпадали
EXPORT_LUA_PATH = CONTENT / "lib" / "export.lua"
CACHE_DIR = ROOT / "dev_probe_output" / ".cache" / "lua"

try:
    from rust_core import LuaContent as _RustLua
except ImportError:
    _RustLua = None


class LuaContentError(ValueError):
    """Lua-файл не исполнился (синтаксис, ошибка времени выполнения, лимиты)."""


def _export_lua() -> str:
    if _RustLua is not None:
        return _RustLua.EXPORT_LUA
    return EXPORT_LUA_PATH.read_text(encoding="utf-8")


def lua_to_py(obj) -> Any:
    """Таблица lupa -> dict/list (после export.lua в ней только данные)."""
    if hasattr(obj, "keys") and callable(obj.keys):
        keys = list(obj.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [lua_to_py(obj[k]) for k in sorted(keys)]
        return {str(k): lua_to_py(obj[k]) for k in keys}
    if isinstance(obj, bytes):
        return obj.decode("utf-8")
    return obj


# ---------------------------------------------------------------- backends

# то же, что sandbox() в rust_core/src/lua_content/mod.rs
_LUPA_SANDBOX = ("io, os, package, debug, require, dofile, loadfile, load = nil, nil, nil, nil, nil, nil, nil, nil\n"
                 "print = function() end")


def _lupa_runtime():
    import lupa.lua55 as lua
    rt = lua.LuaRuntime(register_eval=False, register_builtins=False)
    rt.execute(_LUPA_SANDBOX)
    helpers = rt.execute(_export_lua())
    return rt, helpers


def _lupa_root(rt, source: str, globals: Sequence[str]):
    try:
        returned = rt.execute(source)
    except Exception as exc:  # lupa.LuaError и ошибки из Lua-кода
        raise LuaContentError(str(exc)) from exc
    if globals:
        g = rt.globals()
        picked = {name: g[name] for name in globals if g[name] is not None}
        if picked:
            return rt.table_from(picked)
    return returned


def _load_lupa(source: str, globals: Sequence[str]) -> Any:
    rt, helpers = _lupa_runtime()
    root = _lupa_root(rt, source, globals)
    try:
        return lua_to_py(helpers.export(root))
    except Exception as exc:
        raise LuaContentError(str(exc)) from exc


def _rust(method: str, *args, **kwargs) -> Any:
    try:
        text = getattr(_RustLua, method)(*args, **kwargs)
    except ValueError as exc:  # PyValueError из rust_core: ошибка Lua или лимит песочницы
        raise LuaContentError(str(exc)) from exc
    return json.loads(text)


def _rows(rows, n: int) -> list:
    """Пустая Lua-таблица неотличима от {} - нормализуем к списку длины n."""
    rows = rows if isinstance(rows, list) else []
    return [r if isinstance(r, dict) else {} for r in rows] + [{}] * (n - len(rows))


def _load_rust(source: str, globals: Sequence[str]) -> Any:
    return _rust("load_json", source, globals=list(globals) or None)


def _preds_lupa(source: str, ctxs: list) -> list:
    rt, helpers = _lupa_runtime()
    root = _lupa_root(rt, source, ())
    lua_ctxs = rt.table_from([rt.table_from(c) for c in ctxs])
    return _rows(lua_to_py(helpers.preds(root, lua_ctxs)), len(ctxs))


def _preds_rust(source: str, ctxs: list) -> list:
    return _rows(_rust("eval_preds_json", source, json.dumps(ctxs)), len(ctxs))


LOADERS: dict[str, Optional[Callable[[str, Sequence[str]], Any]]] = {
    "rust": _load_rust if _RustLua is not None else None,
    "lupa": _load_lupa,
}
PRED_EVALUATORS: dict[str, Optional[Callable[[str, list], list]]] = {
    "rust": _preds_rust if _RustLua is not None else None,
    "lupa": _preds_lupa,
}


def available_backends() -> list[str]:
    out = [n for n, fn in LOADERS.items() if fn is not None]
    if "lupa" in out:
        try:
            import lupa.lua55  # noqa: F401
        except ImportError:
            out.remove("lupa")
    return out


# ---------------------------------------------------------------- public API

def _source(src_or_path) -> tuple[str, str]:
    """(исходник, имя для сообщений об ошибках)."""
    if isinstance(src_or_path, Path) or (isinstance(src_or_path, str) and src_or_path.endswith(".lua")
                                         and "\n" not in src_or_path):
        path = Path(src_or_path)
        return path.read_text(encoding="utf-8"), path.name
    return src_or_path, "<string>"


def _cache_file(source: str, globals: Sequence[str]) -> Path:
    key = hashlib.sha256("\0".join([_export_lua(), ",".join(globals), source]).encode("utf-8"))
    return CACHE_DIR / f"{key.hexdigest()[:32]}.json"


def load(src_or_path, globals: Sequence[str] = (), cache: bool = False,
         backend: Optional[str] = None) -> Any:
    """Lua-файл или исходник -> данные (dict/list/скаляр).

    globals: вернуть эти глобальные таблицы (файлы-настройки без `return`),
             если ни одна не задана - то, что вернул chunk.
    cache:   JSON-кэш по sha256 исходника (повторная загрузка без Lua).
    backend: "rust" | "lupa" | None (быстрейший доступный)."""
    source, _name = _source(src_or_path)
    globals = tuple(globals)
    cache_file = _cache_file(source, globals) if cache and backend is None else None
    if cache_file is not None and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # битый/недописанный кэш - просто перечитать Lua
    order = [backend] if backend else available_backends()
    for name in order:
        fn = LOADERS.get(name)
        if fn is None:
            continue
        data = fn(source, globals)
        if cache_file is not None:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = cache_file.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, cache_file)  # атомарно: параллельные шарды тестов не видят половину файла
        return data
    raise RuntimeError(f"no Lua backend available (asked for {order}); install lupa or build rust_core")


def eval_preds(src_or_path, ctxs: list[dict], backend: Optional[str] = None) -> list[dict]:
    """Все условия pred() файла на каждом ctx - одним вызовом.
    Результат: [{исходник условия: значение | "error: ..."}] по ctx."""
    source, _name = _source(src_or_path)
    order = [backend] if backend else available_backends()
    for name in order:
        fn = PRED_EVALUATORS.get(name)
        if fn is not None:
            return fn(source, list(ctxs))
    raise RuntimeError(f"no Lua backend available (asked for {order})")


def bench(src_or_path, repeat: int = 5) -> dict[str, float]:
    """Миллисекунды на одну загрузку каждым бэкендом и из кэша."""
    source, _name = _source(src_or_path)
    out = {}
    for name in available_backends():
        t0 = time.perf_counter()
        for _ in range(repeat):
            load(source, backend=name)
        out[name] = round((time.perf_counter() - t0) / repeat * 1000, 3)
    load(source, cache=True)  # прогреть кэш
    t0 = time.perf_counter()
    for _ in range(repeat):
        load(source, cache=True)
    out["cache"] = round((time.perf_counter() - t0) / repeat * 1000, 3)
    return out
