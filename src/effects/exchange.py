"""Slice G1a: BOUNDED exchange / roster ops (whitelists and caps live in lua effect_rules.lua `exchange`).

  create_ex_nihilo  a WHITELISTED recipe (item | object | summon) paid in the caster's resources; unknown recipe or short pay = refused.
  mass_resurrect    revive the dead of a faction within a radius: hp fraction, cost once, `max_targets` cap.
  status_mod        change an ACTIVE status of the target: duration (add / mult), stacks (delta), potency (mult); all clamped by the row.
  debuff            negative-potency `mod` (a thin wrapper: the value is forced negative).
  unbounded         lift a stat cap for a duration: multiplier clamped by `exchange.unbounded.stats[stat]`; expiry restores.
  copy_last_cast    replay the target's last cast (manager `_last_cast`) from the caster onto the target; never a copy of itself.
  read              the target's registered data (identity, abilities, last cast) into the caster's `perception["read"]`.
  steal / learn_technique  take (steal) or copy (learn_technique) a named technique from the target with a fidelity and a cost.
  time_erase        erase the target and revert its effect state to the newest F8 entity snapshot inside `window` seconds (plain erase without).
  change_tier       move an entity along a named tier track (lua `exchange.tiers`) with per-tier stat mods (form mods, replaced on each move).
Everything is opt-in: no op = no work. EffectRuntime (training room) only logs, like F1-F8.
"""
from __future__ import annotations

import math
from typing import Any

EXCHANGE_FEATURES = ("exchange.equal_mass", "read.wand_history")   # spec gaps these ops say


def cfg() -> dict:
    from .runtime import rules
    try:
        from ..content import lua_bridge
        return lua_bridge.load(lua_bridge.CONTENT / "effect_rules.lua", cache=True).get("exchange") or {}
    except (ImportError, RuntimeError, OSError, ValueError):
        return rules().get("exchange") or {}


def _hosted(h: Any, cx: Any, name: str, tgt: Any = None) -> bool:
    if hasattr(h, "sc_state"):
        return True
    h.op_note(cx, name, tgt, "room")
    return False


def _refuse(h: Any, why: str) -> None:
    h.sc_state().log.append({"t": h.now, "refused": why})


def _pay(h: Any, cx: Any, cost: dict | None, times: int = 1) -> bool:
    if not cost:
        return True
    need = float(cost["amount"]) * times
    if h.op_resource(cx.source, cost["resource"]) < need:
        return False
    h.op_spend(cx, cx.source, cost["resource"], need, False)
    return True


def _ext(st: Any) -> dict:
    return st.unit.external


# ---------------------------------------------------------------- create_ex_nihilo
def op_create_ex_nihilo(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "create_ex_nihilo", tgt):
        return
    name = str(o.get("recipe", ""))
    spec = (cfg().get("recipes") or {}).get(name)
    count = min(int(o.get("count", 1) or 1), int((spec or {}).get("max_count", 1)))
    if spec is None or count < 1 or not _pay(h, cx, spec.get("cost"), count):
        _refuse(h, f"create:{name}")
        return
    if spec["kind"] == "summon":
        h.op_summon(cx, {"summon": spec["id"], "count": count})
    made = _ext(cx.source).setdefault("created", [])
    made.extend({"recipe": name, "id": spec["id"], "kind": spec["kind"], "t": cx.t} for _ in range(count))
    del made[:max(0, len(made) - int(cfg().get("created_keep", 32)))]
    h.op_note(cx, "create_ex_nihilo", tgt, name)


# ---------------------------------------------------------------- mass_resurrect
def _dist(a: Any, b: Any) -> float:
    return math.hypot(getattr(a, "x", 0.0) - getattr(b, "x", 0.0), getattr(a, "y", 0.0) - getattr(b, "y", 0.0))


def _fallen(h: Any, cx: Any, faction: Any, radius: float) -> list:
    from .manager import is_alive
    src = cx.source
    return [s for s in h.states.values() if not is_alive(s.entity) and not _ext(s).get("erased") and s.faction == faction
            and _dist(s.entity, src.entity) <= radius]


def op_mass_resurrect(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "mass_resurrect", tgt):
        return
    c = cfg().get("resurrect") or {}
    radius = min(float(o.get("radius", c.get("max_radius", 20))), float(c.get("max_radius", 20)))
    dead = _fallen(h, cx, o.get("faction", cx.source.faction), radius)[:int(c.get("max_targets", 3))]
    if not dead or not _pay(h, cx, c.get("cost")):
        _refuse(h, "mass_resurrect")
        return
    pct = min(float(o.get("pct", c.get("max_pct", 50))), float(c.get("max_pct", 50)))
    for s in dead:
        h.op_restore_hp(s, pct)
    h.op_note(cx, "mass_resurrect", tgt, len(dead))


# ---------------------------------------------------------------- status_mod / debuff / unbounded
def _row_cap(sid: str) -> int:
    from . import statuses
    return int((statuses.get_status(sid).get("stack") or {}).get("max", 1))


def _scale_periodic(tgt: Any, sid: str, mult: float, until: float | None) -> None:
    for p in tgt.periodic:
        if p["ability"] == f"status:{sid}":
            p["amount"] *= mult
            p["until"] = p["until"] if until is None else until


def op_status_mod(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "status_mod", tgt):
        return
    c, sid = cfg().get("status_mod") or {}, str(o.get("status", ""))
    key = (id(tgt.entity), sid)
    stacks, until = h._status_book.get(key, (0, 0.0))
    if h.now >= until:
        _refuse(h, f"status_mod:{sid}")
        return
    until = h.now + (until - h.now) * min(float(o.get("duration_mult", 1.0)), float(c.get("max_duration_mult", 2.0))) + float(o.get("duration_add", 0.0))
    stacks = max(1, min(stacks + int(o.get("stacks_delta", 0)), _row_cap(sid)))
    h._status_book[key] = (stacks, until)
    _scale_periodic(tgt, sid, min(float(o.get("potency_mult", 1.0)), float(c.get("max_potency_mult", 2.0))), until)
    h.op_note(cx, "status_mod", tgt, sid)


def op_debuff(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    val = dict(o.get("value") or {"flat": 1})
    val = {k: -abs(v) for k, v in val.items() if isinstance(v, (int, float))} or {"flat": -1}
    h.op_apply_op(cx, tgt, {"kind": "mod", "stat": o.get("stat", "defense"), "op": "add", "value": val, "duration": o.get("duration", {"flat": 10})})


def op_unbounded(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    c, stat = cfg().get("unbounded") or {}, str(o.get("stat", ""))
    cap = (c.get("stats") or {}).get(stat)
    if cap is None:
        _refuse(h, f"unbounded:{stat}") if hasattr(h, "sc_state") else None
        return
    dur = min(float(h.op_duration(o.get("duration", {"flat": 10}), cx.ctx)), float(c.get("max_duration", 30)))
    h.op_apply_op(cx, tgt, {"kind": "mod", "stat": stat, "op": "mul", "value": {"flat": min(float(o.get("mult", cap)), float(cap))},
                            "duration": {"flat": dur}})
    h.op_note(cx, "unbounded", tgt, stat)


# ---------------------------------------------------------------- copy_last_cast / read
def op_copy_last_cast(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "copy_last_cast", tgt):
        return
    aid = h._last_cast.get(id(tgt.entity))
    ab = h.ability(aid) if aid else None
    if ab is None or any(x.get("kind") == "copy_last_cast" for x in ab.get("ops") or []):
        _refuse(h, "copy_last_cast")
        return
    h.op_run_nested(cx.source, list(ab["ops"]), tgt.entity, f"copy_last_cast:{aid}")
    h.op_note(cx, "copy_last_cast", tgt, aid)


def op_read(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "read", tgt):
        return
    ident = _ext(tgt).get("identity") or {}
    data = {"name": ident.get("name"), "tags": list(ident.get("tags") or []), "abilities": list(tgt.abilities),
            "last_cast": h._last_cast.get(id(tgt.entity))}
    keep = o.get("fields") or list(data)
    dur = None if o.get("duration") is None else cx.t + h.op_duration(o["duration"], cx.ctx)
    h.op_perception(cx.source).setdefault("read", {})[h.op_ident(tgt)] = {"until": dur, "data": {k: data[k] for k in keep if k in data}}
    h.op_note(cx, "read", tgt, ",".join(keep))


# ---------------------------------------------------------------- steal / learn_technique
def _take_technique(h: Any, cx: Any, tgt: Any, o: dict, remove: bool) -> None:
    c, tech = cfg().get("steal") or {}, o.get("technique")
    if tech not in tgt.abilities or not _pay(h, cx, c.get("cost")):
        _refuse(h, f"steal:{tech}")
        return
    fid = min(1.0, max(float(c.get("min_fidelity", 0.25)), float(o.get("fidelity", 1.0))))
    _ext(cx.source).setdefault("mimic", {}).setdefault("learned", {})[tech] = {"until": None, "fidelity": fid, "src": h.op_ident(tgt)}
    if tech not in h.op_spells(cx.source):
        h.op_spells(cx.source).append(tech)
    if remove:
        tgt.abilities.remove(tech)
        _ext(cx.source).setdefault("grants", []).append({"kind": "ability", "id": tech, "from": h.op_ident(tgt)})
    h.op_note(cx, "steal" if remove else "learn_technique", tgt, tech)


def op_steal(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if _hosted(h, cx, "steal", tgt):
        _take_technique(h, cx, tgt, o, True)


def op_learn_technique(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if _hosted(h, cx, "learn_technique", tgt):
        _take_technique(h, cx, tgt, o, False)


# ---------------------------------------------------------------- time_erase / change_tier
def _recent_image(h: Any, tgt: Any, window: float) -> dict | None:
    from .statecraft import eid_of
    ring = h._sc.rings.get(f"entity:{eid_of(tgt.entity)}") or []
    return next((i for i in reversed(ring) if i["t"] >= h.now - window), None)


def op_time_erase(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    from . import mimic, statecraft
    if not _hosted(h, cx, "time_erase", tgt):
        return
    b = h.op_buffs(tgt).get("erase_immune")
    if b is not None and b.get("until", 1e18) > cx.t:
        h.op_note(cx, "time_erase", tgt, "immune")
        return
    window = min(float(o.get("window", 5.0)), float((cfg().get("time_erase") or {}).get("max_window", 10)))
    img = _recent_image(h, tgt, window)
    if img is not None:
        statecraft.restore(h, img, ())
    mimic.erase(h, tgt)
    h.op_note(cx, "time_erase", tgt, "reverted" if img is not None else "plain")


def op_change_tier(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    track = str(o.get("track", ""))
    tiers = (cfg().get("tiers") or {}).get(track)
    if not tiers or not _hosted(h, cx, "change_tier", tgt):
        return
    rec = _ext(tgt).setdefault("tiers", {})
    ids = [t["id"] for t in tiers]
    cur = rec.get(track, -1)
    new = ids.index(o["to"]) if o.get("to") in ids else max(0, min(cur + int(o.get("steps", 1)), len(ids) - 1))
    rec[track] = new
    h.op_form_clear_mods(cx, tgt, f"tier:{track}")
    h.op_form_mods(cx, tgt, f"tier:{track}", list(tiers[new].get("stats") or []), None)
    h.op_note(cx, "change_tier", tgt, ids[new])


EXCHANGE_HANDLERS = {"create_ex_nihilo": op_create_ex_nihilo, "mass_resurrect": op_mass_resurrect, "status_mod": op_status_mod,
                     "debuff": op_debuff, "unbounded": op_unbounded, "copy_last_cast": op_copy_last_cast, "read": op_read,
                     "steal": op_steal, "learn_technique": op_learn_technique, "time_erase": op_time_erase, "change_tier": op_change_tier}
