"""Slice F5: ZONES, auras and reality marbles as data + hooks of EffectManager (the SPACE family).

A zone is a manager-owned record in `EffectManager._zones` (created by the ops `zone` / `zone_mod` / `rule_override`; aliases `aura` = zone
follow=true, `reality_marble` = zone marble=true, `space_manipulation` = zone with on_inside swap/teleport; kind_aliases.lua):
  id owner center|follow radius duration(GAME clock) affects(all|others|enemies|allies) tick{every, ops} on_enter on_exit
  barrier(open|closed) guaranteed_hit shield{bypass} on_inside[modes] rules{consts, flags} link persist
Ops of a zone run through the normal op pipeline with the OWNER as caster and the MEMBER as primary (target `enemy` / `source` = the member,
`self` = the owner). `EffectManager.update` calls `update()` once per frame: O(members) per zone, members visited in entity-id order.
  enter / exit  fire once when an entity crosses the boundary between two updates (an entity that dies or is unregistered exits).
  tick          every `every` game seconds for each member (at most 8 catch-up runs per update).
  barrier       closed: a non-owner member cannot leave and an affected outsider cannot enter. Enforced in `EffectManager._place` (the seam of
                every `move` mode) and `EffectManager.constrain_move(entity, x, y)` for game movement; free walking is NOT blocked until the
                game calls it (no live wiring in this slice).
  guaranteed_hit a hit by or on a member is resolved as `unavoidable` (no dodge / block / miss) and is not negated by precognition.
  shield        aura: a hit on the OWNER by another member (inside the radius) is nullified (like invulnerable) unless the hit carries the flag
                `shield.bypass` (default `bypass_infinity`).
  on_inside     modes the owner may apply to ANY two members: `move swap with=<entity id>` (Room / Shambles); without a zone it does nothing.
  rules         (reality marble) overrides that hold for hits by or on a member: `consts` (fields of damage.Consts = lua_content/damage.lua
                constants) and `flags` (damage flags). `rule_override` = the same table for `duration` seconds or scoped to `zone`.
                Unbounded overrides are refused; nothing is written into the constants: the layer is dropped at the end (restore = removal).
  link          portal pair: an entrant is placed at the centre of the zone named `link` and becomes its member without an enter event.
A zone ends on expiry, owner death (unless `persist`) or unregistration: on_exit runs for the remaining members, layers vanish, ticks stop.
EffectRuntime (training room) has no zones: it records a log line only (same divergence as F1-F4).
"""
from __future__ import annotations

import math
from typing import Any

from . import damage

ZONE_FEATURES = ("zone.sure_hit", "zone.on_inside")     # spec additions of the corpus that a zone provides (qa.py coverage)
_MAX_CATCHUP = 8
_FLAGS = damage.CERTAIN_FLAGS | damage.NO_CRIT_FLAGS | {"true_damage"}


def _pos(e: Any) -> tuple[float, float]:
    return float(getattr(e, "x", 0.0)), float(getattr(e, "y", 0.0))


def _eid(e: Any) -> str:
    return str(getattr(e, "entity_id", None) or id(e))


def _alive(e: Any) -> bool:
    fn = getattr(e, "is_alive", None)
    return bool(fn()) if callable(fn) else getattr(e, "health", 0) > 0


def clean_rules(rules: Any) -> dict:
    """Keep only overrides of constants / flags that already exist (damage.Consts fields, damage flags); the rest is dropped."""
    rules = rules if isinstance(rules, dict) else {}
    consts = {k: float(v) for k, v in (rules.get("consts") or {}).items() if k in damage.Consts._fields and isinstance(v, (int, float))}
    flags = sorted(f for f in (rules.get("flags") or ()) if f in _FLAGS)
    return {"consts": consts, "flags": flags}


def center(z: dict) -> tuple[float, float]:
    return _pos(z["anchor"]) if z["anchor"] is not None else z["pos"]


# ---------------------------------------------------------------- ops
def _tick_of(h: Any, cx: Any, o: dict) -> dict | None:
    tk = o.get("tick") or {}
    every = float(h.op_duration(tk["every"], cx.ctx)) if tk.get("every") is not None else 0.0
    return {"every": every, "ops": list(tk.get("ops") or []), "next": cx.t + every} if every > 0 else None


def _shield_of(o: dict) -> dict | None:
    return {"bypass": (o["shield"] or {}).get("bypass", "bypass_infinity")} if o.get("shield") else None


def _zone_record(h: Any, cx: Any, tgt: Any, o: dict) -> dict:
    to = o.get("to")
    pos = (float(to[0]), float(to[1])) if isinstance(to, (list, tuple)) and len(to) == 2 else _pos(tgt.entity)
    until = None if o.get("duration") is None else cx.t + h.op_duration(o["duration"], cx.ctx)
    return {"id": str(o.get("id") or f"{cx.src}#zone"), "owner": cx.source.entity, "anchor": tgt.entity if o.get("follow") else None,
            "pos": pos, "radius": float(o.get("radius", 5.0)), "affects": o.get("affects", "all"), "until": until,
            "tick": _tick_of(h, cx, o), "on_enter": list(o.get("on_enter") or []), "on_exit": list(o.get("on_exit") or []),
            "barrier": o.get("barrier", "open"), "sure_hit": bool(o.get("guaranteed_hit", False)), "shield": _shield_of(o),
            "on_inside": {str(m) for m in (o.get("on_inside") or ())}, "rules": clean_rules(o.get("rules")),
            "link": o.get("link"), "persist": bool(o.get("persist", False)), "members": {}, "marble": bool(o.get("marble", False))}


def op_zone(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Create (or replace, same id + owner) a zone around / attached to the target entity. `radius` required."""
    if not hasattr(h, "op_zone_add"):                       # training room: no zones, a log line only
        h.op_note(cx, "zone", tgt, o.get("id") or "-")
        return
    rec = _zone_record(h, cx, tgt, o)
    h.op_zone_add(rec)
    h.op_note(cx, "zone", tgt, rec["id"])


_MOD_FIELDS = {"radius": float, "affects": str, "barrier": str}


def op_zone_mod(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Change parameters of a live zone (same id, owned by the caster): radius / affects / barrier / guaranteed_hit / duration (from now) / rules."""
    for z in (h.op_zones() if hasattr(h, "op_zones") else ()):
        if z["id"] != o.get("id") or z["owner"] is not cx.source.entity:
            continue
        for k, cast in _MOD_FIELDS.items():
            if o.get(k) is not None:
                z[k] = cast(o[k])
        if o.get("guaranteed_hit") is not None:
            z["sure_hit"] = bool(o["guaranteed_hit"])
        if o.get("duration") is not None:
            z["until"] = cx.t + h.op_duration(o["duration"], cx.ctx)
        if o.get("rules") is not None:
            z["rules"] = clean_rules(o["rules"])
        h.op_note(cx, "zone_mod", tgt, z["id"])


def op_rule_override(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Bounded rule override: `rules` = {consts, flags}, for `duration` seconds (global) or scoped to zone `zone`. Neither -> refused."""
    if not hasattr(h, "op_rules"):
        h.op_note(cx, "rule_override", tgt, "room")
        return
    rules = clean_rules(o.get("rules"))
    zone = next((z for z in h.op_zones() if z["id"] == o.get("zone")), None) if o.get("zone") else None
    if zone is not None:
        zone["rules"] = {"consts": {**zone["rules"]["consts"], **rules["consts"]},
                         "flags": sorted(set(zone["rules"]["flags"]) | set(rules["flags"]))}
    elif o.get("duration") is not None:
        h.op_rules().append({"id": str(o.get("id") or cx.src), "until": cx.t + h.op_duration(o["duration"], cx.ctx), **rules})
    else:
        h.op_note(cx, "rule_override", tgt, "refused: unbounded")
        return
    h.op_note(cx, "rule_override", tgt, o.get("zone") or "duration")


ZONE_HANDLERS = {"zone": op_zone, "zone_mod": op_zone_mod, "rule_override": op_rule_override}


# ---------------------------------------------------------------- update
def _affects(m: Any, z: dict, s: Any) -> bool:
    own = m.state(z["owner"])
    return own is not None and not m._area_excludes(own, s, z["affects"], 0.0, None)


def _members(m: Any, z: dict) -> dict:
    cx, cy = center(z)
    r2 = z["radius"] * z["radius"]
    out = {}
    for s in m.states.values():
        e = s.entity
        if _alive(e) and (e.x - cx) ** 2 + (e.y - cy) ** 2 <= r2 and _affects(m, z, s):
            out[_eid(e)] = e
    return out


def _fire(m: Any, z: dict, ops: list, ent: Any, what: str) -> None:
    own = m.state(z["owner"])
    if ops and own is not None:
        m.op_run_nested(own, ops, ent, f"zone:{z['id']}#{what}")


def _portal(m: Any, z: dict, key: str, ent: Any) -> bool:
    """Move an entrant to the linked zone (it becomes a member there, no enter event). False when there is no partner."""
    other = next((p for p in m._zones if p["id"] == z["link"] and p is not z), None)
    if other is None:
        return False
    m._place(ent, *center(other))
    other["members"][key] = ent
    return True


def _sync(m: Any, z: dict) -> None:
    new, old = _members(m, z), z["members"]
    entered = [(k, new[k]) for k in sorted(new) if k not in old]
    exited = [(k, old[k]) for k in sorted(old) if k not in new]
    z["members"] = new
    for _k, e in exited:
        _fire(m, z, z["on_exit"], e, "exit")
    for k, e in entered:
        _fire(m, z, z["on_enter"], e, "enter")
        if z["link"] and _portal(m, z, k, e):
            new.pop(k, None)


def _tick(m: Any, z: dict) -> None:
    t = z["tick"]
    runs = 0
    while t is not None and t["next"] <= m.now + 1e-9 and runs < _MAX_CATCHUP:
        runs += 1
        t["next"] += t["every"]
        for k in sorted(z["members"]):
            e = z["members"][k]
            if _alive(e):
                _fire(m, z, t["ops"], e, "tick")


def end(m: Any, z: dict) -> None:
    """Clean end: on_exit for the remaining members (id order), then the zone (rules, barrier, ticks) is gone."""
    m._zones.remove(z)
    members, z["members"] = z["members"], {}
    for k in sorted(members):
        _fire(m, z, z["on_exit"], members[k], "exit")


def _over(m: Any, z: dict) -> bool:
    return (z["until"] is not None and z["until"] <= m.now + 1e-9) or m.state(z["owner"]) is None \
        or (not z["persist"] and not _alive(z["owner"]))


def update(m: Any) -> None:
    """Once per EffectManager.update: expire, sync membership (enter / exit), tick. Global rule layers expire here too."""
    if m._rules:
        m._rules[:] = [r for r in m._rules if r["until"] > m.now]
    for z in list(m._zones):
        if _over(m, z):
            end(m, z)
        else:
            _sync(m, z)
            _tick(m, z)


# ---------------------------------------------------------------- hooks
def constrain(m: Any, ent: Any, nx: float, ny: float) -> tuple[float, float]:
    """Closed barriers: a member stays inside, an affected outsider stays outside (the owner is exempt). Pure clamping, no events."""
    key = _eid(ent)
    for z in m._zones:
        if z["barrier"] != "closed" or ent is z["owner"]:
            continue
        cx, cy = center(z)
        d = math.hypot(nx - cx, ny - cy)
        inside = key in z["members"]
        if (inside and d > z["radius"]) or (not inside and d < z["radius"] and _outsider_blocked(m, z, ent)):
            nx, ny = _project((cx, cy), (nx, ny), d, z["radius"] * (0.999 if inside else 1.001))
    return nx, ny


def _project(c: tuple, p: tuple, d: float, limit: float) -> tuple[float, float]:
    ux, uy = ((p[0] - c[0]) / d, (p[1] - c[1]) / d) if d > 1e-9 else (1.0, 0.0)
    return c[0] + ux * limit, c[1] + uy * limit


def _outsider_blocked(m: Any, z: dict, ent: Any) -> bool:
    s = m.state(ent)
    return s is not None and _affects(m, z, s)


def swap_partner(m: Any, owner: Any, victim: Any, with_id: Any) -> Any:
    """`move swap with=<id>`: the entity to swap the victim with, only when a zone of the owner allows `swap` inside and both are members."""
    for z in m._zones:
        if z["owner"] is owner and "swap" in z["on_inside"] and _eid(victim) in z["members"] and str(with_id) in z["members"]:
            return z["members"][str(with_id)]
    return None


def _involved(z: dict, src: Any, tgt: Any) -> bool:
    return _eid(src) in z["members"] or _eid(tgt) in z["members"]


def pre_hit(m: Any, src: Any, tgt: Any, flags: set) -> tuple:
    """-> (nullified, flags, consts, sure): zone shield / guaranteed_hit / rule layers for one hit. Nothing armed -> (False, flags, None, False)."""
    if not m._zones and not m._rules:
        return False, flags, damage.config().consts, False
    sure, consts, extra = False, {}, set()
    for z in m._zones:
        if _shielded(z, src, tgt, flags):
            return True, flags, None, False
        if _involved(z, src, tgt):
            sure = sure or z["sure_hit"]
            consts.update(z["rules"]["consts"])
            extra.update(z["rules"]["flags"])
    for r in m._rules:
        consts.update(r["consts"])
        extra.update(r["flags"])
    if sure:
        extra.add("unavoidable")
    return False, (flags | extra if extra else flags), _apply_consts(consts), sure


def _shielded(z: dict, src: Any, tgt: Any, flags: set) -> bool:
    sh = z["shield"]
    return bool(sh) and z["owner"] is tgt and src is not tgt and _eid(src) in z["members"] and sh["bypass"] not in flags


def _apply_consts(over: dict) -> Any:
    base = damage.config().consts
    return tuple(over.get(name, v) for name, v in zip(damage.Consts._fields, base, strict=True)) if over else base
