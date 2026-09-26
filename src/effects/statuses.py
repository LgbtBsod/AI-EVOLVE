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


class Apply(NamedTuple):
    """One application: `stacks` to add and the carrier's CC duration multiplier."""
    stacks: int = 1
    dur_mult: float = 1.0


ONCE = Apply()


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


def row_duration(row: dict) -> float:
    """How long the status lasts: the row number, else the longest timed op duration (blind/root/silence carry theirs on the op)."""
    dur = row.get("duration")
    if isinstance(dur, (int, float)):
        return float(dur)
    own = [float((o.get("duration") or {}).get("flat", 0.0)) for o in row.get("ops") or []
           if o.get("kind") in TIMED_KINDS and isinstance(o.get("duration"), dict)]
    return max(own, default=0.0)


def duration_mult(unit, row: dict) -> float:
    """Stat `cc_duration_mult` of the carrier (default 1.0, effect_rules.lua) for a CC row; other rows 1.0. <= 0 = immune."""
    return max(0.0, float(unit._eff("cc_duration_mult"))) if row.get("cc") else 1.0


def cc_ids(book: dict, unit_key, now: float) -> list[str]:
    """Ids of the CC statuses active on a unit (book key = (unit_key, status id))."""
    return [sid for (uk, sid), (_, until) in book.items()
            if uk == unit_key and now < until and cc_priority(sid) is not None]


def active_cc_row(book: dict, unit_key, now: float) -> dict | None:
    """The winning (highest cc_priority) active CC row of a unit, None when free of CC."""
    sid = cc_strongest(cc_ids(book, unit_key, now))
    return get_status(sid) if sid else None


def _timed_duration(o: dict, row_dur, dur_mult: float) -> None:
    """A timed op without its own duration takes the row's; then x dur_mult."""
    if o.get("kind") not in TIMED_KINDS:
        return
    if isinstance(row_dur, (int, float)) and o.get("duration") is None:
        o["duration"] = {"flat": float(row_dur)}
    if dur_mult != 1.0 and isinstance(o.get("duration"), dict):
        o["duration"]["flat"] = float(o["duration"].get("flat", 0.0)) * dur_mult


def materialize(row: dict, stacks: int, dur_mult: float = 1.0) -> list[dict]:
    """The row's ops for `stacks`: value.flat += stack.add * stacks, row duration for timed ops without their own;
    every timed duration x dur_mult (cc_duration_mult)."""
    add = float((row.get("stack") or {}).get("add", 0.0))
    dur = row.get("duration")
    out = []
    for o in copy.deepcopy(row.get("ops") or []):
        if add and isinstance(o.get("value"), dict):
            o["value"]["flat"] = float(o["value"].get("flat", 0.0)) + add * stacks
        _timed_duration(o, dur, dur_mult)
        out.append(o)
    return out


def plan(book: dict, key, row: dict, now: float, how: Apply = ONCE) -> Plan:
    """Re-apply rule: stacks += add up to stack.max (1 without `stack`), the timer restarts; expired stacks are gone.
    `book[key] = (stacks, until)` is the host's memory."""
    prev, until = book.get(key, (0, 0.0))
    if now >= until:
        prev = 0
    cap = int((row.get("stack") or {}).get("max", 1))
    stacks = max(1, min(prev + max(1, int(how.stacks)), cap))
    until = now + row_duration(row) * how.dur_mult
    book[key] = (stacks, until)
    return Plan(stacks, materialize(row, stacks, how.dur_mult), until)


def nullify_buffs(ops: list) -> tuple[str, ...]:
    """Buff ids a re-apply must drop so the timer restarts instead of extending (op_nullify extends `until`)."""
    return tuple({"nullified"} if any(o.get("kind") == "nullify" for o in ops) else ())
