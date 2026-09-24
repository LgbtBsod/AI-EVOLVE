#!/usr/bin/env python3
"""Настройки агентских инструментов из lua_content/dev_tools.lua.

Lua - слой контента/настроек проекта (стандарт Lua 5.5, читает
tools/lua_bridge.py: rust_core или lupa): пороги гипотез, клавиши игрока для
agent_play, путь к БД прогонов меняются там, без правки Python. Если Lua
недоступен или файл сломан, действуют DEFAULTS ниже (те же значения), а
причина видна в settings()["_source"].
"""
import copy
from functools import lru_cache
from pathlib import Path

import lua_bridge

ROOT = Path(__file__).resolve().parent.parent
LUA_PATH = ROOT / "lua_content" / "dev_tools.lua"
QA_LUA_PATH = ROOT / "lua_content" / "qa.lua"

DEFAULTS = {
    "runtime": {"fps": 30, "render": "none", "sample_interval": 1.0},
    "analysis": {
        "low_hp_fraction": 0.2, "pinned_seconds": 5.0, "stuck_seconds": 8.0, "stuck_distance": 0.5,
        "close_range": 5.0, "zero_damage_ratio": 0.2, "crit_min_hits": 40, "crit_min_chance": 0.05,
        "pressure_per_min": 4.0, "forecast_window_min": 5.0, "forecast_window_max": 15.0,
        "forecast_recent_s": 3.0,
        "hypotheses_shown": 5,
    },
    "agent": {
        "player_keys": {"enemy": "1", "trap": "2", "chest": "3", "boss": "4", "attack": "space", "interact": "e"},
        "max_wait_per_command": 600, "max_repeat": 10, "observe_nearest": 3,
    },
    "db": {"path": "dev_probe_output/probe.sqlite", "keep_runs": 200},
}


QA_DEFAULTS = {
    "scenarios": [
        {"name": "melee_three", "seed": 1, "script": "spawn enemy x3; until kills>=3 or dead max 90; expect alive"},
        {"name": "trap_and_chest", "seed": 2, "script": "spawn trap; spawn chest; wait 15; expect alive"},
        {"name": "swarm", "seed": 3, "script": "spawn enemy x10; wait 45"},
        {"name": "idle_explore", "seed": 4, "script": "wait 90"},
        {"name": "forced_attacks", "seed": 5, "script": "spawn enemy x2; attack x5; wait 20; expect kills>=1"},
    ],
    "golden_fields": ["t", "hp", "max_hp", "lvl", "xp", "kills", "despawns", "enemies",
                      "dealt", "taken", "attacks", "hits", "crits", "alive"],
    "fuzz": {"runs": 24, "length": 16, "jobs": 4, "actions": [
        ["spawn enemy", 4], ["spawn enemy x3", 1], ["spawn trap", 2], ["spawn chest", 2], ["attack", 3],
        ["interact 0.5", 1], ["wait 1", 4], ["wait 5", 3], ["wait 15", 1]]},
    "invariants": {"enabled": True, "hp_epsilon": 0.01, "world_slack": 5.0, "max_enemies_slack": 12,
                   "dead_enemy_frames": 3, "max_violations_kept": 20},
    "sweep": {"seeds": 16, "jobs": 4, "bootstrap_resamples": 2000,
              "metrics": ["kills", "dealt", "taken", "hp", "lvl", "t"]},
    "tests": {"always": ["tools/combat_smoke_test.py"], "base_ref": "origin/main",
              "known_failures": "tests/qa_known_failures.json"},
}


def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


@lru_cache(maxsize=None)
def _load(path_str, qa=False):
    result = copy.deepcopy(QA_DEFAULTS if qa else DEFAULTS)
    path = Path(path_str)
    try:
        _merge(result, lua_bridge.load(path))
        result["_source"] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    except RuntimeError as exc:  # нет ни rust_core, ни lupa
        result["_source"] = f"python defaults ({exc})"
    except Exception as exc:  # битый Lua не должен ронять инструмент
        result["_source"] = f"python defaults ({path.name} failed: {exc})"
    return result


def settings(path=None):
    """Полные настройки (копия - можно мутировать)."""
    return copy.deepcopy(_load(str(path or LUA_PATH)))


def section(name, path=None):
    return settings(path)[name]


def qa_settings(path=None):
    """lua_content/qa.lua: сценарии, фаззинг, инварианты, sweep, выбор тестов.
    Списки (scenarios/actions) заменяются целиком, словари - сливаются."""
    return copy.deepcopy(_load(str(path or QA_LUA_PATH), qa=True))
