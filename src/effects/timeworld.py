"""Slice F7: TIME and WORLD ops (global_time_scale, time_scale, time_as_space, apply_status_to_world, polarity_control) + the seeded sample filter.

Time model (data only, NO scene / movement wiring): every EffectManager timer is an absolute stamp on the manager clock, so a scale s != 1 is
applied as a SHIFT of one entity's stamps by `dt * (1 - s)` per step (s < 1 slower: stamps move later; s = 0 frozen; s > 1 faster: earlier).
Shifted: buffs, external / vision layers, forms, control, periodic ticks, cooldowns (fired_at), the status book, the entity's delays and zones.
Scale 1.0 everywhere (no record) = the hook is not even entered: today's timings are unchanged bit for bit.
  world        {scale, until, exempt, caster}   `global_time_scale`; exempt = ["caster", "tag:x", "faction:x", entity_id]
  ents         {id(entity): {entity, scale, until, subj}}   per-entity `time_scale`; subj = {mult, until, settle, caster} `time_as_space`
                                                         (subjective time: ONLY periodic ticks run mult times per real second)
  statuses     {status_id: {until, caster, filter, persistent, applied, on_start, on_end}}   the `world` entity's statuses
Queries for the scene / AI later: EffectManager.time_scale(entity), world_time_scale(), dt_for(entity, dt), world_statuses().
EffectRuntime (training room) has no clock: it only logs (same divergence as F1-F6a).
"""
from __future__ import annotations

import math
import random
import re
from typing import Any

TIME_FEATURES = ("time_scale.exempt", "subjective_time", "filter.sample")   # spec additions provided by these ops (qa.py coverage)
MAX_SCALE = 10.0            # rules constants: bounded so a bad row cannot stall or explode the clock
MAX_SUBJECTIVE = 60.0
_EPS = 1e-9


class WorldEntity:
    """The manager-owned `world` entity: id 'world', no position; carries statuses (data), targetable as `target = "world"`."""
    entity_id = "world"

    def __init__(self) -> None:
        self.statuses: dict[str, dict] = {}


class TimeState:
    def __init__(self) -> None:
        self.world: dict | None = None
        self.ents: dict[int, dict] = {}
        self.entity = WorldEntity()
        self.sample_rng: random.Random | None = None

    def active(self) -> bool:
        return bool(self.world or self.ents or self.entity.statuses)


def _eid(e: Any) -> str:
    return str(getattr(e, "entity_id", None) or id(e))


def _clamp(v: float, hi: float) -> float:
    return max(0.0, min(float(v), hi))


# ---------------------------------------------------------------- queries
def _exempt_one(x: Any, caster: Any, st: Any) -> bool:
    if x == "caster":
        return caster is st.entity
    if isinstance(x, str) and x.startswith("tag:"):
        return x[4:] in (getattr(st.entity, "tags", None) or ())
    if isinstance(x, str) and x.startswith("faction:"):
        return x[8:] == st.faction
    return x == _eid(st.entity)


def _exempt(rec: dict, st: Any) -> bool:
    return any(_exempt_one(x, rec["caster"], st) for x in rec["exempt"])


def scale_of(m: Any, st: Any) -> float:
    tw = m._tw
    rec = tw.ents.get(id(st.entity))
    v = rec["scale"] if rec and rec.get("scale") is not None else 1.0
    w = tw.world
    if w is not None and not _exempt(w, st):
        v *= w["scale"]
    return v


# ---------------------------------------------------------------- shifting stamps
def _shift_layers(st: Any, d: float) -> None:
    for b in st.unit.buffs.values():
        if "until" in b:
            b["until"] += d
    for k, (u, lay) in list(st.external.items()):
        st.external[k] = (u + d, lay)
    for k, (u, who, v) in list(st.vision_vs.items()):
        st.vision_vs[k] = (u + d, who, v)
    _shift_records(st, d)
    for k in st.fired_at:
        st.fired_at[k] += d


def _shift_records(st: Any, d: float) -> None:
    recs = list((st.unit.external.get("forms") or {}).values()) + [(st.unit.external.get("control") or {}).get("rec") or {}]
    for r in recs:
        if r.get("until") is not None:
            r["until"] += d


def _shift_periodic(st: Any, d: float) -> None:
    for p in st.periodic:
        p["next"] += d
        p["until"] += d


def _shift_book(m: Any, st: Any, d: float) -> None:
    key = id(st.entity)
    for k in [k for k in m._status_book if k[0] == key]:
        stacks, until = m._status_book[k]
        m._status_book[k] = (stacks, until + d)


def _shift_owned(m: Any, deltas: dict) -> None:
    for r in m._delayed:
        d = deltas.get(id(r["caster"].entity))
        if d:
            r["at"] += d
    for z in m._zones:
        d = deltas.get(id(z["owner"]))
        if d:
            _shift_zone(z, d)


def _shift_zone(z: dict, d: float) -> None:
    if z.get("until") is not None:
        z["until"] += d
    tk = z.get("tick")
    if tk:
        tk["next"] += d


def _step_deltas(m: Any, dt: float) -> dict:
    """{id(entity): delta} for this step; shifts the entity's own stamps as a side effect."""
    out: dict = {}
    for st in m.states.values():
        s = scale_of(m, st)
        d = dt * (1.0 - s) if s != 1.0 else 0.0
        if d:
            _shift_layers(st, d)
            _shift_periodic(st, d)
            _shift_book(m, st, d)
            out[id(st.entity)] = d
        rec = m._tw.ents.get(id(st.entity))
        sub = rec.get("subj") if rec else None
        if sub and sub["until"] > m.now - dt + _EPS:
            _shift_periodic(st, -dt * (sub["mult"] - 1.0))
    return out


def _live(rec: dict | None, now: float, dt: float) -> bool:
    return rec is not None and rec["until"] > now - dt + _EPS


def pre_update(m: Any, dt: float) -> None:
    """Called by EffectManager.update after the clock moved, only while a scale / subjective / world status exists."""
    tw = m._tw
    if not tw.active():
        return
    if tw.world is not None and not _live(tw.world, m.now, dt):
        tw.world = None
    deltas = _step_deltas(m, dt)
    if deltas:
        _shift_owned(m, deltas)
    if tw.world is not None and tw.world["until"] <= m.now + _EPS:
        tw.world = None                                  # its last scaled step is done
    for rec in [r for r in tw.ents.values()]:
        _expire_ent(m, rec)
    _world_statuses(m)


def _expire_ent(m: Any, rec: dict) -> None:
    if rec.get("scale") is not None and rec["until"] <= m.now + _EPS:
        rec["scale"] = None
    sub = rec.get("subj")
    if sub and sub["until"] <= m.now + _EPS:
        rec["subj"] = None
        st = m.state(rec["entity"])
        if sub["settle"] and st is not None:
            caster = m.state(sub["caster"]) or st
            m._run_ops(caster, list(sub["settle"]), rec["entity"], "time_as_space#settle", ())
    if rec.get("scale") is None and not rec.get("subj"):
        m._tw.ents.pop(id(rec["entity"]), None)


# ---------------------------------------------------------------- ops
def _dur(h: Any, cx: Any, o: dict) -> float:
    return h.op_duration(o.get("duration") or {"flat": 1.0}, cx.ctx)


def _hosted(h: Any, cx: Any, name: str, tgt: Any = None) -> bool:
    if hasattr(h, "tw_state"):
        return True
    h.op_note(cx, name, tgt, "room")
    return False


def op_global_time_scale(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """The whole world runs at `rate` (default 0 = stopped) for `duration`; `exempt` = ["caster", "tag:x", "faction:x", entity id]."""
    if not _hosted(h, cx, "global_time_scale", tgt):
        return
    tw = h.tw_state()
    tw.world = {"scale": _clamp(o.get("rate", 0.0), MAX_SCALE), "until": cx.t + _dur(h, cx, o), "caster": cx.source.entity,
                "exempt": list(o.get("exempt") or [])}
    h.op_note(cx, "global_time_scale", tgt, tw.world["scale"])


def _ent(tw: TimeState, tgt: Any) -> dict:
    return tw.ents.setdefault(id(tgt.entity), {"entity": tgt.entity, "scale": None, "until": 0.0, "subj": None})


def op_time_scale(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Per-entity time: `rate` > 1 faster (its timers / cooldowns / ticks burn faster), < 1 slower; for `duration` real seconds."""
    if not _hosted(h, cx, "time_scale", tgt):
        return
    rec = _ent(h.tw_state(), tgt)
    rec["scale"] = _clamp(o.get("rate", 1.0), MAX_SCALE)
    rec["until"] = cx.t + _dur(h, cx, o)
    h.op_note(cx, "time_scale", tgt, rec["scale"])


def op_time_as_space(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Subjective time on the target: its own periodic ticks run `mult` times per real second for `duration`, then `settle` ops run."""
    if not _hosted(h, cx, "time_as_space", tgt):
        return
    rec = _ent(h.tw_state(), tgt)
    rec["subj"] = {"mult": max(1.0, min(float(o.get("mult", 2.0)), MAX_SUBJECTIVE)), "until": cx.t + _dur(h, cx, o),
                   "settle": list(o.get("settle") or []), "caster": cx.source.entity}
    h.op_note(cx, "time_as_space", tgt, rec["subj"]["mult"])


def _matches(st: Any, flt: dict) -> bool:
    if flt.get("faction") and st.faction != flt["faction"]:
        return False
    if flt.get("not_faction") and st.faction == flt["not_faction"]:
        return False
    return not flt.get("tag") or flt["tag"] in (getattr(st.entity, "tags", None) or ())


def _alive(e: Any) -> bool:
    fn = getattr(e, "is_alive", None)
    return bool(fn()) if callable(fn) else getattr(e, "health", 0) > 0


def _give(m: Any, rec: dict, st: Any) -> None:
    if id(st.entity) in rec["applied"] or not _alive(st.entity) or not _matches(st, rec["filter"]):
        return
    rec["applied"].add(id(st.entity))
    m.apply_status(st.entity, rec["id"], rec["caster"])


def op_apply_status_to_world(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """A status on the `world` entity and, per `filter` {faction, not_faction, tag}, on every living match; removed at expiry;
    `persistent` = entities registered later get it too. `on_start` / `on_end` ops run as the caster."""
    if not _hosted(h, cx, "apply_status_to_world", tgt) or not o.get("status"):
        return
    tw = h.tw_state()
    rec = {"id": str(o["status"]), "until": cx.t + _dur(h, cx, o), "caster": cx.source.entity, "filter": dict(o.get("filter") or {}),
           "persistent": bool(o.get("persistent")), "applied": set(), "on_end": list(o.get("on_end") or [])}
    tw.entity.statuses[rec["id"]] = rec
    for st in list(h.tw_states()):
        _give(h, rec, st)
    if o.get("on_start"):
        h.op_apply_ops(cx, list(o["on_start"]))
    h.op_note(cx, "apply_status_to_world", tgt, rec["id"])


def _world_statuses(m: Any) -> None:
    for sid, rec in list(m._tw.entity.statuses.items()):
        if rec["until"] <= m.now + _EPS:
            _end_status(m, sid, rec)
        elif rec["persistent"]:
            for st in list(m.states.values()):
                _give(m, rec, st)


def _strip_status(m: Any, st: Any, sid: str) -> None:
    src = f"status:{sid}"
    for k in [k for k in st.external if isinstance(k, tuple) and len(k) > 1 and k[1] == src]:
        del st.external[k]
    st.periodic = [p for p in st.periodic if p["ability"] != src]
    st.unit.buffs.pop(sid, None)
    m._status_book.pop((id(st.entity), sid), None)
    st.refresh(m.now)


def _end_status(m: Any, sid: str, rec: dict) -> None:
    del m._tw.entity.statuses[sid]
    for st in m.states.values():
        if id(st.entity) in rec["applied"]:
            _strip_status(m, st, sid)
    caster = m.state(rec["caster"])
    if rec["on_end"] and caster is not None:
        m._run_ops(caster, rec["on_end"], rec["caster"], f"status:{sid}#world_end", ())


def _polarity(h: Any, cx: Any, st: Any, sel: dict) -> float:
    """+1 / -1 / 0: sign of the selected entity (by `polarity` stat) or 1 for a plain tag match, 0 = not selected."""
    if sel.get("stat"):
        v = h.op_stat_of(cx, "target", st, sel["stat"])
        return math.copysign(1.0, v) if v else 0.0
    return 1.0 if not sel.get("tag") or sel["tag"] in (getattr(st.entity, "tags", None) or ()) else 0.0


def op_polarity_control(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Pull (attract) or push (repel) every selected entity in `radius` by `strength` (a move mode pull|push, F1).
    select = {tag} | {stat: "polarity"}: with a stat, a negative value flips the sign."""
    if not _hosted(h, cx, "polarity_control", tgt):
        return
    sign = -1.0 if o.get("sign") in ("repel", "push", -1) else 1.0
    sel, radius = o.get("select") or {}, float(o.get("radius", 20.0))
    origin = cx.source
    for st in h.tw_states():
        if st is origin or not _alive(st.entity):
            continue
        p = _polarity(h, cx, st, sel)
        if p and math.dist(_xy(st.entity), _xy(origin.entity)) <= radius:
            h.op_apply_op(cx, st, {"kind": "move", "target": "self", "mode": "pull" if sign * p > 0 else "push",
                                   "distance": float(o.get("strength", 5.0))})


def _xy(e: Any) -> tuple:
    return float(getattr(e, "x", 0.0)), float(getattr(e, "y", 0.0))


# ---------------------------------------------------------------- filter.sample
def sample_spec(o: dict) -> dict | None:
    s = o.get("sample") or (o.get("filter") or {}).get("sample")
    return s if isinstance(s, dict) else None


def _natural(eid: str) -> tuple:
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"(\d+)", str(eid)) if p)


def sample(m: Any, entities: list, spec: dict) -> list:
    """Deterministic random SAMPLE of `entities` (`fraction` rounded half up, or `count`): stable order by entity id, then a draw on a
    named stream derived ONCE from the manager rng (later unrelated draws do not shift it)."""
    ordered = sorted(entities, key=lambda e: _natural(_eid(e)))    # natural order: f9 before f10 (a plain string sort flips at digit boundaries)
    n = len(ordered)
    k = int(spec["count"]) if spec.get("count") is not None else int(n * float(spec.get("fraction", 0.5)) + 0.5)
    k = max(0, min(k, n))
    tw = m._tw
    if tw.sample_rng is None:
        tw.sample_rng = random.Random(int(m.rng.random() * 2 ** 32))
    keep = set(tw.sample_rng.sample(range(n), k))
    return [e for i, e in enumerate(ordered) if i in keep]


TIME_HANDLERS = {"global_time_scale": op_global_time_scale, "time_scale": op_time_scale, "time_as_space": op_time_as_space,
                 "apply_status_to_world": op_apply_status_to_world, "polarity_control": op_polarity_control}
