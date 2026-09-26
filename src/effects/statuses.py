"""Statuses as Lua data (lua_content/statuses/core_statuses.lua): the loader and the stacking rule.

A status row is a bundle of ordinary schema ops (ops.py) plus `duration` and `stack = {max, add}`. Both hosts
(EffectManager in the game, EffectRuntime in the training room) apply it through `plan()` and their own
`run_ops`, so a status is not a separate mechanism: it is an effect chain built from data. Nothing in live
content applies a status yet, so loading is lazy and traces of existing content are unchanged.
"""
from __future__ import annotations

import copy
from functools import lru_cache
from typing import NamedTuple

STATUS_FILE = "statuses/core_statuses.lua"
TIMED_KINDS = ("deal", "mod", "nullify", "cancel_technique")


@lru_cache(maxsize=1)
def load_statuses() -> dict[str, dict]:
    """id -> row (read once)."""
    from ..content import lua_bridge
    rows = lua_bridge.load(lua_bridge.CONTENT / STATUS_FILE, cache=True)
    return {r["id"]: r for r in rows}


def get_status(status_id: str) -> dict:
    """Row by id, aliases followed (disoriented -> blind). KeyError for an unknown id."""
    rows = load_statuses()
    row = rows[status_id]
    return rows[row["alias"]] if row.get("alias") else row


class Plan(NamedTuple):
    stacks: int
    ops: list
    until: float


def cc_priority(status_id: str) -> int | None:
    """`cc_priority` of a CC row (data), None for a non-CC status; aliases share the target row's priority."""
    row = load_statuses().get(status_id) or {}
    if row.get("alias"):
        row = load_statuses()[row["alias"]]
    return row.get("cc_priority")


def cc_strongest(active: list[str]) -> str | None:
    """The strongest active CC (highest cc_priority) wins; the first of equals."""
    ranked = [(cc_priority(s), s) for s in active if cc_priority(s) is not None]
    return max(ranked, key=lambda r: r[0])[1] if ranked else None


def resist_percent(unit, status_id: str) -> float:
    """Chance to resist a status: stat status_resist_<id> of the carrier (base + mods), 0..100."""
    key = f"status_resist_{status_id}"
    return min(100.0, float(unit.base.get(key, 0.0)) + float(unit.mods.get(key, 0.0)))


def resisted(unit, status_id: str, roll) -> bool:
    """>=100 always resists; 0 never (and no rng draw: traces stay unchanged); else one draw from `roll()` in [0,1)."""
    pct = resist_percent(unit, status_id)
    return pct >= 100.0 or (pct > 0.0 and roll() * 100.0 < pct)


def materialize(row: dict, stacks: int) -> list[dict]:
    """The row's ops for `stacks`: value.flat += stack.add * stacks, row duration for timed ops without their own."""
    add = float((row.get("stack") or {}).get("add", 0.0))
    dur = row.get("duration")
    out = []
    for o in copy.deepcopy(row.get("ops") or []):
        if add and isinstance(o.get("value"), dict):
            o["value"]["flat"] = float(o["value"].get("flat", 0.0)) + add * stacks
        if isinstance(dur, (int, float)) and o.get("kind") in TIMED_KINDS and o.get("duration") is None:
            o["duration"] = {"flat": float(dur)}
        out.append(o)
    return out


def plan(book: dict, key, row: dict, now: float, add: int = 1) -> Plan:
    """Re-apply rule: stacks += add up to stack.max (1 without `stack`), the timer restarts; expired stacks are gone.
    `book[key] = (stacks, until)` is the host's memory."""
    prev, until = book.get(key, (0, 0.0))
    if now >= until:
        prev = 0
    cap = int((row.get("stack") or {}).get("max", 1))
    stacks = max(1, min(prev + max(1, int(add)), cap))
    dur = row.get("duration")
    until = now + (float(dur) if isinstance(dur, (int, float)) else 0.0)
    book[key] = (stacks, until)
    return Plan(stacks, materialize(row, stacks), until)


def nullify_buffs(ops: list) -> tuple[str, ...]:
    """Buff ids a re-apply must drop so the timer restarts instead of extending (op_nullify extends `until`)."""
    return tuple({"nullified"} if any(o.get("kind") == "nullify" for o in ops) else ())
