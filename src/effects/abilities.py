"""Способности (удар оружием, навыки, навыки боссов) из Lua-контента."""
from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

ABILITY_FILES = ("abilities.lua", "bosses.lua")


@lru_cache(maxsize=1)
def load_abilities() -> dict[str, dict]:
    """id -> способность из lua_content/abilities.lua и навыки боссов из bosses.lua."""
    from ..content import lua_bridge
    out: dict[str, dict] = {}
    for name in ABILITY_FILES:
        path = lua_bridge.CONTENT / name
        if not path.exists():
            continue
        try:
            data = lua_bridge.load(path, cache=True)
        except Exception as exc:
            logger.warning("abilities: %s not loaded: %s", name, exc)
            continue
        for ab in data.get("abilities") or []:
            out[ab["id"]] = ab
        for boss in data.get("bosses") or []:
            for ab in boss.get("skills") or []:
                out[ab["id"]] = ab
    return out


@lru_cache(maxsize=1)
def load_bosses() -> dict[str, dict]:
    """id -> описание босса (статы, вид, skills - список id навыков)."""
    from ..content import lua_bridge
    path = lua_bridge.CONTENT / "bosses.lua"
    if not path.exists():
        return {}
    try:
        data = lua_bridge.load(path, cache=True)
    except Exception as exc:
        logger.warning("bosses: not loaded: %s", exc)
        return {}
    return {b["id"]: {**b, "skills": [ab["id"] for ab in b.get("skills") or []]} for b in data.get("bosses") or []}
