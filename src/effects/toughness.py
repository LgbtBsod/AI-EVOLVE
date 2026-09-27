"""Toughness / break bar (S4, docs/CC_PORT_SPEC.md 2.3): pure data + helpers over `lua_content/toughness.lua`.

The ONE bar (owner decision 3): `EffectManager` keeps `toughness`/`toughness_max` per entity (manager.py),
this module only reads the data file and does the small pure math (type factor, base by class, growth cap)
so the manager stays a thin caller. `enabled()` is the kill switch (default off): every caller must check it
before touching entity state so the feature is fully inert until a designer flips the flag.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

CONFIG_FILE = "toughness.lua"


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    """The live config: lua_content/toughness.lua (read once, like statuses.load_statuses)."""
    from ..content import lua_bridge
    return lua_bridge.load(lua_bridge.CONTENT / CONFIG_FILE, cache=True)


def enabled() -> bool:
    return bool(config().get("enabled"))


def base_for(cls: str) -> float:
    """Base toughness for a class name (player/npc/enemy/boss/elite); unknown -> the "enemy" default."""
    table = config().get("base_by_class") or {}
    return float(table.get(cls, table.get("enemy", 100.0)))


def type_factor(damage_type: str | None) -> float:
    """Multiplier of `damage_type` against toughness (row 21); unknown/missing type -> neutral 1.0."""
    table = config().get("type_factor") or {}
    return float(table.get(damage_type or "", 1.0))


def break_duration() -> float:
    return float(config().get("break_duration", 5.0))


def growth_step(current_pct: float) -> float:
    """How much `break_growth_pct` still fits under `break_growth_cap_pct` given the growth so far."""
    cap = float(config().get("break_growth_cap_pct", 20.0))
    step = float(config().get("break_growth_pct", 5.0))
    return max(0.0, min(step, cap - current_pct))


def toughness_class(entity: Any, faction: str | None = None) -> str:
    """Class name for `base_for`: an explicit `entity.toughness_class` wins; else a faction/flag guess.

    `faction` is the caller's `EntityState.faction` string (manager.py `register`), not an attribute of
    `entity` -- the raw game entity never sets `.faction` itself (checked against `src/entities/character.py`
    and `main_game_scene.py` `register(..., "hero"|"monsters")`), so an entity-only faction guess always
    missed the player. `is_boss`/`is_elite` ARE set directly on the raw entity (`main_game_scene.py`
    `boss.is_boss = True`) and do classify real entities correctly.
    """
    explicit = getattr(entity, "toughness_class", None)
    if explicit:
        return str(explicit)
    if str(faction or "").lower() == "hero":
        return "player"
    if getattr(entity, "is_boss", False):
        return "boss"
    if getattr(entity, "is_elite", False):
        return "elite"
    return "enemy"
