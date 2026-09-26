"""Slice F8: STATE ops (snapshot, restore_state, time_loop, write, rename, wish, confiscate, respawn_at) + `kill.cause`.

Forward-only: a restore puts a SAVED state back and the sim continues forward from there; already simulated ticks are never rewritten.
  snapshot     plain-data (JSON-safe) image of one scope: `self` (an entity), `faction`, `world` (the whole manager). An entity image holds its
               fields (lua `statecraft.entity_fields`), cooldowns, effect books, stat layers, external layers, periodic ticks; the world image adds the game clock,
               the RNG stream positions, the delay queue, zones, rule layers, time/world records and the status book. Kept in a bounded ring per scope.
  restore_state  bit-exact put-back (JSON round trip included); entities that no longer exist are skipped and reported. Keeps `restore_keep` external
               layers (a spent on_lethal charge stays spent) and, inside an on_lethal, cancels the lethal part of the hit (F4 `_fire`).
  respawn_at   move the target to a named anchor (recorded by `snapshot anchor=`) or to {x, y}.
  time_loop    a repeatable restore of the world image at each death / expiry of the caster; the loop record and the `persist` memory keys live OUTSIDE
               the image, so they survive every rewind (`unit.external["memory"]`; the loop count is `memory.loop_count`).
  write        a named-target instruction the manager executes at an exact game time (or when a hp condition holds): kill with a cause; can be cancelled.
  rename       identity name / tags (`unit.external["identity"]`), what `write` resolves by name at execution time.
  wish         bounded: only outcomes of lua `statecraft.wish`, each with a cost and a cooldown, amounts clamped by the row; anything else is refused.
  confiscate   take an ability (or an item, kept in the vault) from the target into the caster's grants.
EffectRuntime (training room) has no clock or registry: it only logs (same divergence as F1-F7). Everything is opt-in: no record = no hook work.
"""
from __future__ import annotations

import json
from typing import Any

STATE_FEATURES = ("respawn_at", "kill.cause")     # spec additions provided by these ops (qa.py coverage)
ST_ATTRS = ("abilities", "applied", "cooldowns", "fired_at", "buff_granted_at", "periodic", "zones", "vision_vs", "marks", "spells",
            "adapt_stacks", "absorbed_kinetic", "absorbed_until", "faction")
UNIT_ATTRS = ("buffs", "marks", "spells", "adapt_stacks", "absorbed_kinetic", "absorbed_until", "external", "pools", "current_hp", "alive", "kills")
RT_ATTRS = ("_op_contrib", "_last_hit_at", "_last_attack_at")


def cfg() -> dict:
    from .runtime import rules
    try:
        from ..content import lua_bridge
        return lua_bridge.load(lua_bridge.CONTENT / "effect_rules.lua", cache=True).get("statecraft") or {}
    except (ImportError, RuntimeError, OSError, ValueError):
        return rules().get("statecraft") or {}


class StateCraft:
    """Manager-owned bookkeeping that is NOT part of an image: rings, loops, writes, anchors, vault, restore marker."""

    def __init__(self) -> None:
        self.rings: dict[str, list] = {}
        self.seq = 0
        self.loops: dict[str, dict] = {}
        self.writes: list[dict] = []
        self.anchors: dict[str, list] = {}
        self.vault: list = []
        self.wish_cd: dict[str, float] = {}
        self.restored: set = set()
        self.log: list[dict] = []

    def busy(self) -> bool:
        return bool(self.loops or self.writes)


# ---------------------------------------------------------------- codec: manager objects <-> JSON-safe data

class Codec:
    def __init__(self, m: Any) -> None:
        self.m = m
        self.ent_ids = {id(st.entity): eid_of(st.entity) for st in m.states.values()}
        self.st_ids = {id(st): eid_of(st.entity) for st in m.states.values()}
        self.unit_ids = {id(st.unit): eid_of(st.entity) for st in m.states.values()}
        self.by_eid = {eid_of(st.entity): st for st in m.states.values()}
        self.missing: set = set()

    def enc(self, v: Any) -> Any:
        if v is None or isinstance(v, (bool, float, str)):
            return v
        if isinstance(v, int):
            return {"$id": self.ent_ids[v]} if v in self.ent_ids and v > 4096 else v
        return self._enc_obj(v)

    def _enc_ref(self, v: Any) -> Any:
        for tag, ids in (("$st", self.st_ids), ("$ent", self.ent_ids), ("$u", self.unit_ids)):
            if id(v) in ids:
                return {tag: ids[id(v)]}
        return {"$world": 1} if v is self.m._tw.entity else None

    def _enc_obj(self, v: Any) -> Any:
        ref = self._enc_ref(v)
        if ref is not None:
            return ref
        if isinstance(v, tuple):
            return {"$t": [self.enc(x) for x in v]}
        if isinstance(v, (set, frozenset)):
            return {"$s": sorted((self.enc(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True))}
        if isinstance(v, list):
            return [self.enc(x) for x in v]
        if isinstance(v, dict):
            return self._enc_dict(v)
        raise TypeError(f"not snapshot-able: {type(v).__name__}")

    def _enc_dict(self, d: dict) -> Any:
        if all(isinstance(k, str) and not k.startswith("$") for k in d):
            return {k: self.enc(x) for k, x in d.items()}
        return {"$d": [[self.enc(k), self.enc(x)] for k, x in d.items()]}

    def dec(self, v: Any) -> Any:
        if isinstance(v, list):
            return [self.dec(x) for x in v]
        if not isinstance(v, dict):
            return v
        if len(v) == 1:
            (k, x), = v.items()
            if k in ("$st", "$ent", "$u", "$id", "$world", "$t", "$s", "$d"):
                return self._dec_tag(k, x)
        return {k: self.dec(x) for k, x in v.items()}

    def _dec_tag(self, tag: str, x: Any) -> Any:
        if tag == "$t":
            return tuple(self.dec(i) for i in x)
        if tag == "$s":
            return {self.dec(i) for i in x}
        if tag == "$d":
            return {self.dec(k): self.dec(i) for k, i in x}
        if tag == "$world":
            return self.m._tw.entity
        st = self.by_eid.get(x)
        if st is None:
            self.missing.add(x)
            return None
        return {"$st": st, "$u": st.unit, "$id": id(st.entity)}.get(tag, st.entity)


def eid_of(entity: Any) -> str:
    return str(getattr(entity, "entity_id", None) or id(entity))


# ---------------------------------------------------------------- images

def _members(m: Any, scope: str, st: Any) -> list:
    if scope == "world":
        return list(m.states.values())
    if scope == "faction":
        return [s for s in m.states.values() if s.faction == st.faction]
    return [st]


def _ent_image(cd: Codec, st: Any, fields: list) -> dict:
    e = st.entity
    return {"fields": {f: cd.enc(getattr(e, f)) for f in fields if hasattr(e, f)},
           "state": {a: cd.enc(getattr(st, a)) for a in ST_ATTRS if hasattr(st, a)},
           "unit": {a: cd.enc(getattr(st.unit, a)) for a in UNIT_ATTRS if hasattr(st.unit, a)},
           "base": cd.enc(dict(st.unit._base)), "mods": cd.enc(dict(st.unit._mods)),
           "external": cd.enc(dict(st.external)), "rt": {a: cd.enc(getattr(st.runtime, a)) for a in RT_ATTRS if hasattr(st.runtime, a)}}


def _rng_state(rng: Any) -> Any:
    return rng.getstate() if hasattr(rng, "getstate") else None


def _mgr_image(cd: Codec) -> dict:
    m, tw = cd.m, cd.m._tw
    return {"now": m.now, "rng": cd.enc(_rng_state(m.rng)), "delayed": cd.enc(m._delayed), "delay_seq": m._delay_seq, "zones": cd.enc(m._zones),
            "rules": cd.enc(m._rules), "book": cd.enc(m._status_book),
            "tw": {"world": cd.enc(tw.world), "ents": cd.enc(list(tw.ents.values())), "statuses": cd.enc(tw.entity.statuses),
                   "sample_rng": cd.enc(_rng_state(tw.sample_rng))},
            "telegraphs": [cd.enc({"caster": t.caster, "ability": t.ability, "target": t.target, "x": t.x, "y": t.y, "radius": t.radius, "at": t.at})
                           for t in m.telegraphs]}


def state_image(m: Any, scope: str, st: Any) -> dict:
    """Pure: the data image of `scope` around EntityState `st` (no ids, no ring)."""
    cd, fields = Codec(m), list(cfg().get("entity_fields") or ())
    members = _members(m, scope, st)
    img: dict = {"scope": scope, "t": m.now, "ents": {eid_of(s.entity): _ent_image(cd, s, fields) for s in members}, "mgr": None}
    if scope == "world":
        img["mgr"] = _mgr_image(cd)
    else:
        ids = {id(s) for s in members}
        img["delayed"] = cd.enc([r for r in m._delayed if id(r["caster"]) in ids])
    return img


def scope_key(scope: str, st: Any) -> str:
    return "world" if scope == "world" else f"faction:{st.faction}" if scope == "faction" else f"entity:{eid_of(st.entity)}"


def take(m: Any, scope: str, st: Any, sid: str | None = None, anchor: tuple | None = None) -> dict:
    """Snapshot into the bounded ring of its scope; the same id replaces its older image. Returns the image (plain data)."""
    sc = m._sc
    sc.seq += 1
    img = state_image(m, scope, st)
    img["id"] = sid or f"s{sc.seq}"
    ring = [i for i in sc.rings.setdefault(scope_key(scope, st), []) if i["id"] != img["id"]]
    ring.append(img)
    del ring[:max(0, len(ring) - int(cfg().get("ring", 8)))]
    sc.rings[scope_key(scope, st)] = ring
    if anchor and anchor[0]:
        pos = anchor[1] or {"x": getattr(st.entity, "x", 0.0), "y": getattr(st.entity, "y", 0.0)}
        sc.anchors[anchor[0]] = [float(pos["x"]), float(pos["y"])]
    return img


def find(m: Any, sid: str) -> dict | None:
    for ring in m._sc.rings.values():
        for img in reversed(ring):
            if img["id"] == sid:
                return img
    return None


def _put_ent(cd: Codec, st: Any, img: dict, keep: tuple) -> None:
    e = st.entity
    for f, v in img["fields"].items():
        setattr(e, f, cd.dec(v))
    for a, v in img["state"].items():
        setattr(st, a, cd.dec(v))
    for a, v in img["unit"].items():
        if a != "external":
            setattr(st.unit, a, cd.dec(v))
    st.unit._base.clear()
    st.unit._base.update(cd.dec(img["base"]))
    st.unit._mods.clear()
    st.unit._mods.update(cd.dec(img["mods"]))
    ux = cd.dec(img["unit"].get("external", {}))
    for k in keep:
        ux.pop(k, None)
        if k in st.unit.external:
            ux[k] = st.unit.external[k]
    st.unit.external = ux
    st.external = cd.dec(img["external"])
    for a, v in img["rt"].items():
        setattr(st.runtime, a, cd.dec(v))
    st.unit.touch()
    st.touch()


def _put_mgr(cd: Codec, g: dict) -> None:
    m, tw = cd.m, cd.m._tw
    m.now, m._delay_seq = g["now"], g["delay_seq"]
    _set_rng(m.rng, cd.dec(g["rng"]))
    m._delayed, m._zones, m._rules, m._status_book = (cd.dec(g[k]) for k in ("delayed", "zones", "rules", "book"))
    t = g["tw"]
    tw.world = cd.dec(t["world"])
    tw.ents = {id(r["entity"]): r for r in cd.dec(t["ents"]) if r.get("entity") is not None}
    tw.entity.statuses = cd.dec(t["statuses"])
    srng = cd.dec(t["sample_rng"])
    if srng is not None and tw.sample_rng is not None:
        tw.sample_rng.setstate(srng)
    m.telegraphs = [_telegraph(cd.dec(x)) for x in g["telegraphs"]]


def _telegraph(d: dict) -> Any:
    from .manager import Telegraph
    return Telegraph(**d)


def _set_rng(rng: Any, state: Any) -> None:
    if state is not None and hasattr(rng, "setstate"):
        rng.setstate(state)


def restore(m: Any, img: dict, keep: tuple = ()) -> dict:
    """Put `img` back. Entities gone from the manager are skipped (reported `missing`); registered ones the image does not know are left (`extra`)."""
    cd = Codec(m)
    done = []
    for eid, ent in img["ents"].items():
        st = cd.by_eid.get(eid)
        if st is not None:
            _put_ent(cd, st, ent, keep)
            done.append(eid)
            m._sc.restored.add(eid)
    if img["mgr"] is not None:
        _put_mgr(cd, img["mgr"])
    elif "delayed" in img:
        ids = {id(cd.by_eid[e]) for e in done}
        m._delayed = sorted([r for r in m._delayed if id(r["caster"]) not in ids] + cd.dec(img["delayed"]), key=lambda r: r["seq"])
    return {"restored": done, "missing": sorted(set(img["ents"]) - set(done)), "extra": sorted(set(cd.by_eid) - set(img["ents"]))
            if img["scope"] == "world" else []}


def take_restored(m: Any, victim: Any) -> bool:
    """F4 hook: True once after `victim` was restored (the lethal part of the hit is then void)."""
    eid = eid_of(victim.entity)
    if eid in m._sc.restored:
        m._sc.restored.discard(eid)
        return True
    return False


# ---------------------------------------------------------------- ops

def _hosted(h: Any, cx: Any, name: str, tgt: Any = None) -> bool:
    if hasattr(h, "sc_state"):
        return True
    h.op_note(cx, name, tgt, "room")
    return False


def op_snapshot(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Image of the target (`scope` self | faction | world, default self) under `id`; `anchor` names its position (or `at` {x, y})."""
    if _hosted(h, cx, "snapshot", tgt):
        img = h.snapshot_of(tgt, o)
        h.op_note(cx, "snapshot", tgt, img["id"])


def op_restore_state(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Restore the image `id` (a `scope` other than the image's own is ignored); keeps `keep` (default lua restore_keep) external layers."""
    if not _hosted(h, cx, "restore_state", tgt):
        return
    keep = tuple(o["keep"]) if o.get("keep") is not None else tuple(cfg().get("restore_keep") or ())
    rep = h.restore_by_id(o.get("id"), keep)
    h.op_note(cx, "restore_state", tgt, o.get("id"), len(rep["restored"]) if rep else 0)


def op_respawn_at(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "respawn_at", tgt):
        return
    pos = h.sc_state().anchors.get(o.get("anchor")) if o.get("anchor") else [o.get("x", 0.0), o.get("y", 0.0)]
    if pos is not None:
        tgt.entity.x, tgt.entity.y = float(pos[0]), float(pos[1])
    h.op_note(cx, "respawn_at", tgt, o.get("anchor") or "xy")


def op_time_loop(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Loop the world: snapshot now, and at each death (`on` death | expiry | either) of the caster restore it, `count` times, `persist` memory kept."""
    if not _hosted(h, cx, "time_loop", tgt):
        return
    m, lid = h, str(o.get("id") or "loop")
    img = take(m, "world", cx.source, sid=f"loop:{lid}")
    dur = None if o.get("duration") is None else h.op_duration(o["duration"], cx.ctx)
    m._sc.loops[lid] = {"id": lid, "sid": img["id"], "left": int(o.get("count", 1)), "done": 0, "dur": dur, "until": None if dur is None else m.now + dur,
                        "on": o.get("on", "death"), "persist": list(o.get("persist") or []), "caster": eid_of(cx.source.entity)}
    h.op_note(cx, "time_loop", tgt, lid)


def _ident(st: Any) -> dict:
    return st.unit.external.setdefault("identity", {})


def name_of(st: Any) -> str:
    return str(_ident(st).get("name") or eid_of(st.entity))


def op_rename(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Registered name and tags of the target: `name`, `tags_add`, `tags_remove`."""
    if not _hosted(h, cx, "rename", tgt):
        return
    ident = _ident(tgt)
    if o.get("name") is not None:
        ident["name"] = str(o["name"])
    tags = [t for t in ident.get("tags", []) if t not in (o.get("tags_remove") or [])]
    ident["tags"] = tags + [t for t in (o.get("tags_add") or []) if t not in tags]
    tgt.unit.external["identity"] = ident
    h.op_note(cx, "rename", tgt, ident.get("name", ""))


def op_write(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Record an instruction: `effect` (lua write_effects: kill | heart_attack) on the named target (`name`, else the op target) after `after`
    seconds and/or when `when` {hp_pct_below} holds; `cause` overrides the death cause. {id, cancel: true} cancels a pending write."""
    if not _hosted(h, cx, "write", tgt):
        return
    sc = h.sc_state()
    if o.get("cancel"):
        sc.writes[:] = [w for w in sc.writes if w["id"] != o.get("id")]
        return
    eff = str(o.get("effect", "kill"))
    if eff not in (cfg().get("write_effects") or {}):
        sc.log.append({"t": h.now, "refused": f"write:{eff}"})
        return
    sc.seq += 1
    at = None if o.get("after") is None else cx.t + h.op_duration(o["after"], cx.ctx)
    sc.writes.append({"id": o.get("id") or f"w{sc.seq}", "seq": sc.seq, "at": at, "when": o.get("when"), "name": o.get("name"),
                      "target": eid_of(tgt.entity), "effect": eff, "cause": o.get("cause"), "caster": eid_of(cx.source.entity),
                      "persist": bool(o.get("persist", False))})
    h.op_note(cx, "write", tgt, eff)


def _refuse(h: Any, why: str) -> None:
    h.sc_state().log.append({"t": h.now, "refused": why})


def _pay(h: Any, cx: Any, spec: dict) -> bool:
    c = spec.get("cost") or {}
    if c and h.op_resource(cx.source, c["resource"]) < float(c["amount"]):
        return False
    if c:
        h.op_spend(cx, cx.source, c["resource"], float(c["amount"]), False)
    return True


def _wish_ops(kind: str, spec: dict, o: dict) -> list:
    if kind == "heal":
        return [{"kind": "heal", "stat": "hp", "value": {"flat": min(float(o.get("amount", 0)), float(spec["max"]))}}]
    if kind == "grant_stat":
        stat = o.get("stat")
        return [{"kind": "mod", "stat": stat, "op": "add", "value": {"flat": min(float(o.get("amount", 0)), float(spec["max"]))},
                 "duration": {"flat": float(spec["duration"])}}] if stat in spec["stats"] else []
    return [{"kind": "erase"}] if kind == "erase" else []


def op_wish(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """A bounded wish: `outcome` in lua statecraft.wish (heal | revive | grant_stat | erase); pays the cost, honours the cooldown, clamps amounts."""
    if not _hosted(h, cx, "wish", tgt):
        return
    kind, sc = str(o.get("outcome", "")), h.sc_state()
    spec = (cfg().get("wish") or {}).get(kind)
    key = f"{eid_of(cx.source.entity)}:{kind}"
    if spec is None or sc.wish_cd.get(key, -1.0) > h.now or not _pay(h, cx, spec):
        _refuse(h, f"wish:{kind}")
        return
    sc.wish_cd[key] = h.now + float(spec.get("cooldown", 0.0))
    if kind == "revive":
        h.op_restore_hp(tgt, min(float(o.get("pct", spec["max_pct"])), float(spec["max_pct"])))
    for w in _wish_ops(kind, spec, o):
        h.op_apply_op(cx, tgt, w)
    h.op_note(cx, "wish", tgt, kind)


def op_confiscate(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Take an ability (default) or an item `id` from the target into the caster's grants (`unit.external["grants"]`)."""
    if not _hosted(h, cx, "confiscate", tgt):
        return
    what, xid, src = str(o.get("what", "ability")), o.get("id"), cx.source
    grants = src.unit.external.setdefault("grants", [])
    if what == "ability" and xid in tgt.abilities:
        tgt.abilities.remove(xid)
        src.abilities.append(xid) if xid not in src.abilities else None
        grants.append({"kind": "ability", "id": xid, "from": eid_of(tgt.entity)})
    elif what == "item":
        it = next((i for i in tgt.items if getattr(i, "id", None) == xid), None)
        if it is not None:
            h.sc_state().vault.append(it)
            h.sc_take_item(tgt, it)
            grants.append({"kind": "item", "id": xid, "from": eid_of(tgt.entity)})
    h.op_note(cx, "confiscate", tgt, xid)


STATE_HANDLERS = {"snapshot": op_snapshot, "restore_state": op_restore_state, "respawn_at": op_respawn_at, "time_loop": op_time_loop,
                  "rename": op_rename, "write": op_write, "wish": op_wish, "confiscate": op_confiscate}


# ---------------------------------------------------------------- per-tick hooks (EffectManager.update)

def _resolve(m: Any, w: dict) -> Any:
    if w["name"] is not None:
        return next((s for s in m.states.values() if name_of(s) == w["name"] and s.entity is not None), None)
    return next((s for s in m.states.values() if eid_of(s.entity) == w["target"]), None)


def _due(m: Any, w: dict) -> bool:
    if w["at"] is not None and w["at"] > m.now:
        return False
    cond = w["when"]
    if cond is None:
        return True
    tgt = _resolve(m, w)
    return tgt is not None and 100.0 * tgt.resource("hp") / max(1e-9, float(tgt.unit._eff("max_hp"))) < float(cond.get("hp_pct_below", 0.0))


def _run_write(m: Any, w: dict) -> None:
    from .manager import is_alive
    from .ops import OpCall, apply_op
    caster = next((s for s in m.states.values() if eid_of(s.entity) == w["caster"]), None)
    tgt = _resolve(m, w)
    if caster is None or tgt is None or (not w["persist"] and not is_alive(caster.entity)):
        m._sc.log.append({"t": m.now, "write": w["id"], "miss": True})
        return
    cause = w["cause"] or (cfg().get("write_effects") or {}).get(w["effect"], "written")
    cx = OpCall(ctx={}, src=f"write:{w['id']}", t=m.now, source=caster, tags=("spell",), hits=[], primary=tgt.entity)
    apply_op(m, cx, tgt, {"kind": "kill", "cause": cause})
    m._sc.log.append({"t": m.now, "write": w["id"], "cause": cause, "target": eid_of(tgt.entity)})


def _loop_trigger(m: Any, lp: dict, caster: Any) -> bool:
    from .manager import is_alive
    dead = caster is not None and not is_alive(caster.entity)
    expired = lp["until"] is not None and m.now >= lp["until"]
    return dead if lp["on"] == "death" else expired if lp["on"] == "expiry" else dead or expired


def _harvest(m: Any, keys: list) -> dict:
    return {eid_of(s.entity): {k: s.unit.external["memory"][k] for k in keys if k in (s.unit.external.get("memory") or {})}
            for s in m.states.values()}


def _rewind(m: Any, lp: dict) -> None:
    kept = _harvest(m, lp["persist"])
    lp["done"] += 1
    lp["left"] -= 1
    restore(m, find(m, lp["sid"]), keep=())
    for s in m.states.values():
        mem = s.unit.external.setdefault("memory", {})
        mem.update(kept.get(eid_of(s.entity)) or {})
        if eid_of(s.entity) == lp["caster"]:
            mem["loop_count"] = lp["done"]
    lp["until"] = None if lp["dur"] is None else m.now + lp["dur"]


def _run_writes(m: Any) -> None:
    sc = m._sc
    due = sorted((w for w in sc.writes if _due(m, w)), key=lambda w: (w["at"] if w["at"] is not None else m.now, w["seq"]))
    sc.writes[:] = [w for w in sc.writes if w not in due]
    for w in due:
        _run_write(m, w)


def _run_loops(m: Any) -> None:
    sc = m._sc
    for lid, lp in list(sc.loops.items()):
        caster = next((s for s in m.states.values() if eid_of(s.entity) == lp["caster"]), None)
        if not _loop_trigger(m, lp, caster):
            continue
        if lp["left"] <= 0:
            del sc.loops[lid]
        else:
            _rewind(m, lp)


def update(m: Any) -> None:
    """Per tick: due writes, then loop triggers; nothing recorded = nothing done."""
    if m._sc.busy():
        _run_writes(m)
        _run_loops(m)
