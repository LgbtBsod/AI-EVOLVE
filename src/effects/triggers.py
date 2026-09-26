"""Slice F4: TRIGGER kinds (on_lethal, counter_delta, delay) as data + two hooks of EffectManager.

  on_lethal      (on the PROTECTED)  unit.external["triggers"]["lethal"][id] = {priority, charges, cooldown, next_at, until, keep, restore, ops}
                                     -> EffectManager._damage asks `intercept_lethal` for a hit that would take hp to 0 or below, BEFORE it is
                                        applied. The first interceptor by (priority, id) whose charges / cooldown / duration allow fires ONCE per hit:
                                        the lethal part is cancelled (survive at `keep` hp, or `restore` = % of max_hp), `ops` run on the protected
                                        entity (forms, heals, statuses). Nobody fires -> the hit stays lethal and kill / die events are unchanged.
  counter_delta  (inside on_lethal.ops) resist to the damage type that would have killed: {"value": pct (default 50), "duration"}.
  delay          `ops` run after `after` GAME seconds on the manager clock (EffectManager.update drains a queue ordered by (at, seq));
                 cancelled if the caster is dead unless `persist`.
Re-entry is bounded by MAX_EVENT_DEPTH. EffectRuntime (training room) has no queue and no damage hook: it records nothing (same divergence as F1-F3).
"""
from __future__ import annotations

from typing import Any


def op_on_lethal(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Arm a lethal-hit interceptor on the target. charges default 1 (0 = unlimited), keep = hp left (default 1), restore = % max hp instead."""
    until = None if o.get("duration") is None else cx.t + h.op_duration(o["duration"], cx.ctx)
    cd = 0.0 if o.get("cooldown") is None else float(h.op_duration(o["cooldown"], cx.ctx))
    rid = o.get("id") or "on_lethal"
    h.op_triggers(tgt).setdefault("lethal", {})[rid] = {
        "id": rid, "priority": int(o.get("priority", 0)), "charges": int(o.get("charges", 1)) or None, "cooldown": cd, "next_at": cx.t,
        "until": until, "keep": float(o.get("keep", 1.0)), "restore": o.get("restore"), "ops": list(o.get("ops") or [])}
    h.op_note(cx, "on_lethal", tgt, rid)


def op_counter_delta(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """After a survived lethal hit: resist the damage type that would have killed (only meaningful inside on_lethal.ops)."""
    last = h.op_triggers(tgt).get("last_lethal")
    if not last:
        return
    pct = float((o.get("value") or {}).get("flat", 50.0)) if isinstance(o.get("value"), dict) else float(o.get("value", 50.0))
    m = {"kind": "resist", "damage_type": last["type"], "value": {"flat": pct}}
    if o.get("duration") is not None:
        m["duration"] = o["duration"]
    h.op_apply_op(cx, tgt, m)
    h.op_note(cx, "counter_delta", tgt, last["type"], pct)


def op_delay(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Schedule `ops` for `after` seconds later; the target is the op target, the caster is the source."""
    h.op_schedule({"at": cx.t + h.op_duration(o.get("after") or {"flat": 0}, cx.ctx), "caster": cx.source, "target": tgt,
                   "ops": list(o.get("ops") or []), "persist": bool(o.get("persist", False)), "src": cx.src, "tags": cx.tags})
    h.op_note(cx, "delay", tgt, len(o.get("ops") or []))


TRIGGER_HANDLERS = {"on_lethal": op_on_lethal, "counter_delta": op_counter_delta, "delay": op_delay}


# ---------------------------------------------------------------- hooks used by EffectManager

def _ready(rec: dict, now: float) -> bool:
    return (rec["until"] is None or rec["until"] > now) and now >= rec["next_at"] and rec["charges"] != 0 \
        and (rec["charges"] > 0 or rec["charges"] < 0 and False or True)


def _armed(m: Any, victim: Any) -> list:
    recs = (victim.unit.external.get("triggers") or {}).get("lethal") or {}
    return sorted((r for r in recs.values() if _ready(r, m.now)), key=lambda r: (r["priority"], r["id"]))


def _fire(m: Any, victim: Any, attacker: Any, rec: dict, hit: tuple) -> float:
    amount, kind = hit
    if rec["charges"] is not None:
        rec["charges"] -= 1
    rec["next_at"] = m.now + rec["cooldown"]
    hp = victim.resource("hp")
    victim.unit.external.setdefault("triggers", {})["last_lethal"] = {"type": kind, "amount": amount, "t": m.now, "id": rec["id"]}
    if rec["restore"] is not None:
        m.op_restore_hp(victim, float(rec["restore"]))
        amount = 0.0
    else:
        amount = max(0.0, hp - rec["keep"])
    m.op_run_nested(victim, rec["ops"], attacker, f"{rec['id']}#lethal")
    return amount


def intercept_lethal(m: Any, victim: Any, attacker: Any, amount: float, kind: str) -> float:
    """A hit of `amount` on `victim` (EntityState) that would kill: the amount to apply after the first ready interceptor (or unchanged)."""
    if amount < victim.resource("hp") or m.op_depth() >= m.max_depth():
        return amount
    armed = _armed(m, victim)
    if not armed:
        return amount
    m.op_enter()
    try:
        return _fire(m, victim, attacker, armed[0], (amount, kind))
    finally:
        m.op_leave()


def drain_delayed(m: Any, queue: list) -> list:
    """Due records of `queue` in stable (at, seq) order; the rest stays. Each record: {at, seq, caster, target, ops, persist, src, tags}."""
    due = sorted((r for r in queue if r["at"] <= m.now), key=lambda r: (r["at"], r["seq"]))
    queue[:] = [r for r in queue if r["at"] > m.now]
    return due
