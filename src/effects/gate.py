"""Slice G2: ONE reusable op precondition (`requires` / `cost`) any op can carry, plus a bounded reaction/interrupt window.

  requires   {stat, cmp: lt|le|gt|ge|eq|ne, vs: "source" | number} or a list of such (AND, no side effect on failure). Read via
             `op_stat_of` (the target's, or the source's when `who`="source", effective stat/flag). Generalises the per-family
             condition gate that used to live only in control.py `_blocked` (same field name/shape) so ANY op can carry it:
             a moon-phase flag, a near-death hp fraction, eye contact, ancestry, terrain -- all just a stat comparison.
  cost       {stat, amount} or a list, paid by the CASTER before the op runs (`op_spend`); short pay refuses the WHOLE op
             (no partial pay, no side effect) unless `lethal` is true.
  arm_interrupt  arm a bounded window on the target (an F4 `on_lethal` sibling): the next op resolved against it whose tags
             overlap `match.tags` (empty = any) is nullified once, before it runs, then the window is spent. `window` /
             `charges` bound it; expiry (or the op it is meant for) clears it. Never re-entrant: an op cannot interrupt itself.
Opt-in: an op with none of these fields behaves exactly as before it existed. `apply_op` (ops.py) checks all three before any
handler runs, for every op kind, one gate. EffectRuntime (training room) has no `op_triggers`/`op_resource`, so on it `requires`
degrades to a stat read of 0.0 by default (harmless unless a spec sets one) and `arm_interrupt` only logs (same divergence as F4).
"""
from __future__ import annotations

from typing import Any

GATE_FEATURES = ("condition.full_moon_only", "state.triggered_by_near_death", "nullify.while_eye_contact",
                  "command.ancestry_gated", "heal.terrain_gated", "transform.requires_self_injury",
                  "target.sphere_area", "reaction.interrupt_cast")

_CMP = {"lt": lambda a, b: a < b, "le": lambda a, b: a <= b, "gt": lambda a, b: a > b, "ge": lambda a, b: a >= b,
        "eq": lambda a, b: a == b, "ne": lambda a, b: a != b}


def _req_ok(h: Any, cx: Any, tgt: Any, req: dict) -> bool:
    who = req.get("who", "target")
    mine = h.op_stat_of(cx, who, tgt, req["stat"])
    vs = req.get("vs", 0.0)
    other = h.op_stat_of(cx, "source", tgt, req["stat"]) if vs == "source" else vs
    cmp = req.get("cmp", "lt")
    return _CMP[cmp](mine, other) if cmp in ("eq", "ne") else _CMP[cmp](float(mine), float(other))


def requires_blocked(h: Any, cx: Any, tgt: Any, o: dict) -> str | None:
    """Why `o.get("requires")` refuses the op (None = every condition holds, or there is none)."""
    reqs = o.get("requires")
    if not reqs:
        return None
    for req in (reqs if isinstance(reqs, list) else [reqs]):
        if not _req_ok(h, cx, tgt, req):
            return req.get("fail") or "condition"
    return None


def pay_costs(h: Any, cx: Any, o: dict) -> str | None:
    """Pay `o.get("cost")` (one {stat, amount} or a list) from the CASTER; "cost" (refused, nothing paid) on a short pay."""
    costs = o.get("cost")
    if not costs:
        return None
    costs = costs if isinstance(costs, list) else [costs]
    for c in costs:
        amount = float(c.get("amount", 0.0))
        if amount > 0.0 and h.op_resource(cx.source, c.get("stat", "hp")) < amount and not c.get("lethal", False):
            return "cost"
    for c in costs:
        amount = float(c.get("amount", 0.0))
        if amount > 0.0:
            h.op_spend(cx, cx.source, c.get("stat", "hp"), amount, bool(c.get("lethal", False)))
    return None


def op_arm_interrupt(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Arm a bounded interrupt window on `tgt` (F4 `on_lethal` sibling): the next matching op against it is nullified once."""
    until = cx.t + h.op_duration(o.get("window") or {"flat": 6}, cx.ctx)
    rid = o.get("id") or "interrupt"
    h.op_triggers(tgt).setdefault("interrupt", {})[rid] = {
        "id": rid, "until": until, "charges": int(o.get("charges", 1)) or 1, "match": dict(o.get("match") or {})}
    h.op_note(cx, "interrupt_armed", tgt, rid)


def is_interrupted(h: Any, cx: Any, tgt: Any, o: dict) -> bool:
    """True (consuming one charge) when a live `arm_interrupt` window of `tgt` matches this op's tags; never self-interrupts."""
    if o.get("kind") == "arm_interrupt" or not hasattr(h, "op_triggers"):
        return False
    recs = h.op_triggers(tgt).get("interrupt") or {}
    for rid, rec in list(recs.items()):
        if rec["until"] < cx.t:
            del recs[rid]
            continue
        want = rec["match"].get("tags")
        if want and not (set(want) & set(cx.tags)):
            continue
        rec["charges"] -= 1
        if rec["charges"] <= 0:
            del recs[rid]
        return True
    return False


GATE_HANDLERS = {"arm_interrupt": op_arm_interrupt}
