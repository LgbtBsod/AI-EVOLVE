#!/usr/bin/env python3
"""Настройки агентских инструментов из lua_content/dev_tools.lua.

Lua - слой контента/настроек проекта (стандарт Lua 5.5, lupa.lua55): пороги
гипотез, клавиши игрока для agent_play, путь к БД прогонов меняются там, без
правки Python. Если lupa не установлен или файл сломан, действуют DEFAULTS
ниже (те же значения), а причина видна в settings()["_source"].
"""
import copy
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LUA_PATH = ROOT / "lua_content" / "dev_tools.lua"

DEFAULTS = {
    "runtime": {"fps": 30, "render": "none", "sample_interval": 1.0},
    "analysis": {
        "low_hp_fraction": 0.2, "pinned_seconds": 5.0, "stuck_seconds": 8.0, "stuck_distance": 0.5,
        "close_range": 5.0, "zero_damage_ratio": 0.2, "crit_min_hits": 40, "crit_min_chance": 0.05,
        "pressure_per_min": 4.0, "forecast_window_min": 5.0, "forecast_window_max": 15.0,
        "hypotheses_shown": 5,
    },
    "agent": {
        "player_keys": {"enemy": "1", "trap": "2", "chest": "3", "attack": "space", "interact": "e"},
        "max_wait_per_command": 600, "max_repeat": 10, "observe_nearest": 3,
    },
    "db": {"path": "dev_probe_output/probe.sqlite", "keep_runs": 200},
}


def _lua_to_py(obj):
    if hasattr(obj, "keys") and callable(obj.keys):
        keys = list(obj.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [_lua_to_py(obj[k]) for k in sorted(keys)]
        return {str(k): _lua_to_py(obj[k]) for k in keys}
    if isinstance(obj, bytes):
        return obj.decode("utf-8")
    return obj


def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


@lru_cache(maxsize=None)
def _load(path_str):
    result = copy.deepcopy(DEFAULTS)
    path = Path(path_str)
    try:
        import lupa.lua55 as lua
    except ImportError:
        result["_source"] = "python defaults (lupa not installed)"
        return result
    try:
        table = lua.LuaRuntime().execute(path.read_text(encoding="utf-8"))
        _merge(result, _lua_to_py(table))
        result["_source"] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    except Exception as exc:  # битый Lua не должен ронять инструмент
        result["_source"] = f"python defaults ({path.name} failed: {exc})"
    return result


def settings(path=None):
    """Полные настройки (копия - можно мутировать)."""
    return copy.deepcopy(_load(str(path or LUA_PATH)))


def section(name, path=None):
    return settings(path)[name]
