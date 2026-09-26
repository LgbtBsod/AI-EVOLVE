"""Slice F3: the PERCEPTION family (perceive, reveal, precognition; grant_vision = `mod` vision_range, dodge = precognition) as data.

Everything lives in `unit.external["perception"]` of the entity it concerns and never mutates combat state by itself:
  perceived   (on the PERCEIVER)  {target id: {until, what}}       -> EffectManager.perceived(caster): what the caster knows now
  revealed    (on the CONCEALED)  {until, to}                      -> concealment (`untargetable:*` buffs, stealth vision mods) is
                                                                       suppressed while it lasts (to = None: everybody, else a viewer id)
  precog      (on the WARNED)     {until, cooldown, negate, warn, chance, next_at, warnings}
                                                                   -> EffectManager._damage asks `try_negate` before every incoming hit
A precognition fires at most once per cooldown: it records a warning (queryable: EffectManager.warnings) and may negate that hit
like a dodge; `chance` < 100 costs exactly one draw of the host's seeded RNG per armed hit. Nothing here reruns a simulated tick.
"""
from __future__ import annotations

from typing import Any

_WHAT = ("hp", "stats", "statuses", "hidden", "intent")
_STATS = ("attack", "defense", "move_speed", "vision_range")


def _until(h: Any, cx: Any, o: dict) -> float | None:
    return None if o.get("duration") is None else cx.t + h.op_duration(o["duration"], cx.ctx)


def op_perceive(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """The caster learns about the target for a duration: `what` in hp / stats / statuses / hidden / intent (default all)."""
    rec = {"until": _until(h, cx, o), "what": [w for w in (o.get("what") or _WHAT) if w in _WHAT],
           "stats": list(o.get("stat_names") or _STATS)}
    h.op_perception(cx.source).setdefault("perceived", {})[h.op_ident(tgt)] = rec
    h.op_note(cx, "perceive", tgt, ",".join(rec["what"]))


def op_reveal(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Suppress the target's concealment for a duration; `to = "caster"` reveals it to the caster only."""
    to = h.op_controller(cx) if o.get("to") == "caster" else None
    h.op_perception(tgt)["revealed"] = {"until": _until(h, cx, o), "to": to}
    h.op_note(cx, "reveal", tgt, "caster" if to is not None else "all")


def op_precognition(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Arm a warning (+ first-hit negate) on the target; cooldown = seconds between two firings."""
    cd = 0.0 if o.get("cooldown") is None else float(h.op_duration(o["cooldown"], cx.ctx))
    h.op_perception(tgt)["precog"] = {
        "id": o.get("id") or "precognition", "until": _until(h, cx, o), "cooldown": cd,
        "negate": bool(o.get("negate", True)), "warn": bool(o.get("warn", True)),
        "chance": float(o.get("chance", 100.0)), "next_at": cx.t, "warnings": []}
    h.op_note(cx, "precognition", tgt, o.get("id") or "precognition")


PERCEPTION_HANDLERS = {"perceive": op_perceive, "reveal": op_reveal, "precognition": op_precognition}


# ---------------------------------------------------------------- queries / hooks used by EffectManager

def revealed_to(per: dict | None, viewer: Any, now: float) -> bool:
    """Is the holder of `per` revealed to `viewer` right now?"""
    r = (per or {}).get("revealed")
    return bool(r) and (r["until"] is None or r["until"] > now) and r["to"] in (None, viewer)


def try_negate(m: Any, victim: Any, attacker: Any, attacker_id: Any) -> bool:
    """An incoming hit on `victim` (EntityState): does an armed precognition fire? Records the warning; True = the hit is negated."""
    rec = (victim.unit.external.get("perception") or {}).get("precog")
    now = m.now
    if not rec or (rec["until"] is not None and rec["until"] <= now) or now < rec["next_at"]:
        return False
    if rec["chance"] < 100.0 and not (rec["chance"] > 0.0 and m.rng.random() * 100.0 < rec["chance"]):
        return False
    rec["next_at"] = now + rec["cooldown"]
    if rec["warn"]:
        rec["warnings"].append({"t": now, "from": attacker_id})
    return rec["negate"]


def _stats_of(unit: Any, names: list) -> dict:
    return {k: float(unit._eff(k)) for k in names}


def _hidden_of(st: Any, now: float) -> dict:
    buffs = [b for b, r in st.unit.buffs.items() if b.startswith("untargetable:") and r.get("until", 1e18) > now]
    return {"untargetable": sorted(buffs), "stealth": sum(1 for u, _t, _v in st.vision_vs.values() if u > now)}


def _facts(st: Any, rec: dict, now: float) -> dict:
    out: dict = {}
    for w in rec["what"]:
        if w == "hp":
            out["hp"] = {"hp": st.resource("hp"), "max_hp": float(st.unit._eff("max_hp"))}
        elif w == "stats":
            out["stats"] = _stats_of(st.unit, rec["stats"])
        elif w == "statuses":
            out["statuses"] = sorted(b for b in st.unit.buffs if not b.startswith("untargetable:"))
        elif w == "hidden":
            out["hidden"] = _hidden_of(st, now)
        else:
            out["intent"] = dict(st.unit.external.get("aggro") or {})
    return out


def view(m: Any, caster: Any, entity_id: Any) -> dict:
    """What `caster` perceives now: {target id: facts}; expired records and gone targets are skipped."""
    st = m.state(caster)
    recs = ((st.unit.external.get("perception") or {}).get("perceived") or {}) if st else {}
    out: dict = {}
    for tid, rec in recs.items():
        if rec["until"] is not None and rec["until"] <= m.now:
            continue
        tst = next((s for s in m.states.values() if entity_id(s.entity) == tid), None)
        if tst is not None:
            out[tid] = _facts(tst, rec, m.now)
    return out
