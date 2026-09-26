"""Slice F6a: the MIMIC family (fusion_strike, remove_restriction, dispel + on_dispel, copy_technique, copy, false_percept,
control_link / break_link, erase) as small handlers on the machinery that already exists (statuses, control, perception, forms).

Records live in `unit.external["mimic"]` of the entity they concern; nothing changes unless content uses them.
  restrictions  {id: {until, cost}}                 a lifted self-imposed limit (query: EffectManager.restriction_lifted)
  learned       {technique: {until, fidelity, src}} copied techniques (also appended to `spells`, so use_learned_technique works)
  granted       {ability id: {until, orig}}         copied assets: a row `<id>~copy:<caster>` in EffectManager.abilities + the caster's list
  dispel        {owner, ops, fired}                 on a summon: ops run ONCE as the owner when it dies / is dispelled (`fire_dispel`)
Forged percepts live in unit.external["perception"]["forged"] (perception.view merges them over the real facts); a control link is
a permanent control record with rec["link"] = {break_if} (EffectManager._expire_control asks `link_broken`); an erased entity carries
external["erased"] (no die / kill events, no on_lethal, no revive).
EffectRuntime (training room) has no clock hooks: it records a log line only (same divergence as F1-F5).
"""
from __future__ import annotations

from functools import partial
from typing import Any

from . import control

MIMIC_FEATURES = ("on_dispel", "false_percept", "control_link")   # spec additions of the corpus that these ops provide (qa.py coverage)
_LINK_KINDS = ("possess", "command", "dominance", "hypnosis", "temptation")
_CMP = control._CMP


def _ext(tgt: Any) -> dict:
    return getattr(tgt, "unit", tgt).external


def _mim(tgt: Any) -> dict:
    return _ext(tgt).setdefault("mimic", {})


def _until(h: Any, cx: Any, o: dict) -> float | None:
    return None if o.get("duration") is None else cx.t + h.op_duration(o["duration"], cx.ctx)


def _num(h: Any, cx: Any, v: Any) -> float:
    from .ops import resolve_value
    return float(resolve_value(v, cx.ctx)) if isinstance(v, dict) else float(v or 0.0)


# ---------------------------------------------------------------- fusion_strike
def _part(h: Any, cx: Any, tgt: Any, p: dict) -> float:
    """One payload of a fusion: a stat of the caster (times `scale`) or a Value."""
    if p.get("stat"):
        return h.op_stat_of(cx, "source", tgt, p["stat"]) * float(p.get("scale", 1.0))
    return _num(h, cx, p.get("value"))


def op_fusion_strike(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Merge two payloads (`parts`, exactly two: {stat, scale} | {value}) into ONE hit: merge sum|mul, times `mult`; `consume` pays first."""
    parts = list(o.get("parts") or [])[:2]
    if len(parts) != 2:
        h.op_note(cx, "fusion_strike", tgt, "needs two parts")
        return
    for c in o.get("consume") or []:
        h.op_apply_op(cx, cx.source, {"kind": "drain", "target": "self", "stat": c["stat"], "value": c["value"]})
    a, b = (_part(h, cx, tgt, p) for p in parts)
    dmg = (a * b if o.get("merge") == "mul" else a + b) * float(o.get("mult", 1.0))
    h.op_apply_op(cx, tgt, {"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": dmg},
                            "flags": list(o.get("flags") or [])})
    h.op_note(cx, "fusion_strike", tgt, dmg)


# ---------------------------------------------------------------- remove_restriction
def op_remove_restriction(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Lift the self-imposed limit `id` for `duration` (None = forever) and trade: `gain` mods apply, `cost` mods apply with it; both end together."""
    rid, until = str(o.get("id") or "restriction"), _until(h, cx, o)
    mods = [{**m, "target": "self", **({"duration": o["duration"]} if o.get("duration") is not None else {})}
            for m in list(o.get("gain") or []) + list(o.get("cost") or [])]
    if mods:
        h.op_nested_ops(cx, tgt, mods)                       # one batch: each mod gets its own slot (the owner is the caster)
    _mim(tgt).setdefault("restrictions", {})[rid] = {"until": until}
    h.op_note(cx, "remove_restriction", tgt, rid)


def restriction_lifted(m: Any, entity: Any, rid: str) -> bool:
    st = m.state(entity)
    rec = ((st.unit.external.get("mimic") or {}).get("restrictions") or {}).get(rid) if st else None
    return bool(rec) and (rec["until"] is None or rec["until"] > m.now)


# ---------------------------------------------------------------- dispel / on_dispel
def register_dispel(m: Any, creature: Any, owner_st: Any, ops: list) -> None:
    """A summon carries ops that run once, as its owner, when it dies or is dispelled."""
    st = m.state(creature) or m.register(creature, owner_st.faction)
    _mim(st)["dispel"] = {"owner": owner_st.entity, "ops": list(ops), "fired": False}


def fire_dispel(m: Any, victim_st: Any, cause: str) -> None:
    rec = (victim_st.unit.external.get("mimic") or {}).get("dispel")
    if not rec or rec["fired"] or _ext(victim_st).get("erased"):
        return
    rec["fired"] = True
    owner = m.state(rec["owner"])
    if owner is not None and rec["ops"] and m.op_depth() < m.max_depth():
        m.op_enter()
        try:
            m.op_run_nested(owner, rec["ops"], victim_st.entity, f"dispel:{cause}")
        finally:
            m.op_leave()


def _dispellable(tgt: Any) -> bool:
    return "dispel" in (_ext(tgt).get("mimic") or {}) or getattr(getattr(tgt, "entity", None), "summoned_by", None) is not None


def op_dispel(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """End a summon / clone now: it dies (its `on_dispel` ops fire from the death hook, once)."""
    if not _dispellable(tgt):
        h.op_note(cx, "dispel", tgt, "not a summon")
        return
    h.op_note(cx, "dispel", tgt)
    h.op_kill(cx, tgt)


# ---------------------------------------------------------------- copy_technique / copy
def _observed(h: Any, cx: Any, tgt: Any) -> bool:
    rec = (h.op_perception(cx.source).get("perceived") or {}).get(h.op_ident(tgt))
    return bool(rec) and (rec["until"] is None or rec["until"] > cx.t) and "techniques" in rec["what"]


def _pick(tgt: Any, wanted: Any) -> str | None:
    have = list(getattr(tgt, "abilities", None) or [])
    return wanted if wanted in have else (None if wanted else (have[0] if have else None))


def op_copy_technique(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Copy a technique OBSERVED on the target (perceive what=techniques) into the caster's learned set; `fidelity` scales its use."""
    if o.get("observed", True) and not _observed(h, cx, tgt):
        h.op_note(cx, "copy_technique", tgt, "not observed")
        return
    tech = _pick(tgt, o.get("technique"))
    if tech is None:
        h.op_note(cx, "copy_technique", tgt, "nothing to copy")
        return
    _mim(cx.source).setdefault("learned", {})[tech] = {"until": _until(h, cx, o), "fidelity": float(o.get("fidelity", 1.0)),
                                                       "src": h.op_ident(tgt)}
    spells = h.op_spells(cx.source)
    if tech not in spells:
        spells.append(tech)
    h.op_note(cx, "copy_technique", tgt, tech)


def scaled(tgt: Any, tech: str, base: Any) -> Any:
    """`use_learned_technique` value of a copied technique times its fidelity (unchanged for learned / stolen ones)."""
    rec = ((_ext(tgt).get("mimic") or {}).get("learned") or {}).get(tech)
    if not rec or rec["fidelity"] == 1.0 or not isinstance(base, dict):
        return base
    k = "pct" if "pct" in base else "flat"
    return {**base, k: float(base.get(k, 0.0)) * rec["fidelity"]}


def op_copy(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Duplicate an ability instance of the target (`asset`, default its first) into a temporary granted one `<asset>~copy:<caster>`."""
    if not hasattr(h, "mimic_grant"):
        h.op_note(cx, "copy", tgt, o.get("asset") or "-")
        return
    orig = _pick(tgt, o.get("asset"))
    if orig is None or (o.get("observed", False) and not _observed(h, cx, tgt)):
        h.op_note(cx, "copy", tgt, "nothing to copy")
        return
    new = h.mimic_grant(cx.source, orig, _until(h, cx, o))
    h.op_note(cx, "copy", tgt, new)


def grant(m: Any, st: Any, orig: str, until: float | None) -> str | None:
    row = m.ability(orig)
    if row is None:
        return None
    new = f"{orig}~copy:{m.op_ident(st)}"
    m.abilities[new] = {**row, "id": new}
    if new not in st.abilities:
        st.abilities.append(new)
    _mim(st).setdefault("granted", {})[new] = {"until": until, "orig": orig}
    return new


def update(m: Any) -> None:
    """Expire copied techniques / granted assets and restrictions (game clock)."""
    for st in list(m.states.values()):
        rec = st.unit.external.get("mimic")
        if rec:
            _drop(rec.get("learned"), m.now, partial(_forget, st.spells))
            _drop(rec.get("granted"), m.now, partial(_forget_asset, m, st))
            _drop(rec.get("restrictions"), m.now, str)


def _forget(seq: list, name: str) -> None:
    if name in seq:
        seq.remove(name)


def _forget_asset(m: Any, st: Any, name: str) -> None:
    m.abilities.pop(name, None)
    _forget(st.abilities, name)


def _drop(recs: dict | None, now: float, on_drop: Any) -> None:
    """Remove the records of `recs` whose `until` has passed (None = forever) and call `on_drop(name)` for each."""
    for name in [k for k, r in (recs or {}).items() if r["until"] is not None and r["until"] <= now]:
        recs.pop(name)
        on_drop(name)


# ---------------------------------------------------------------- false_percept
def op_false_percept(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """For a duration the victim's `perceived` facts are replaced (key by key) by the forged `facts` (Kyoka Suigetsu)."""
    h.op_perception(tgt)["forged"] = {"until": _until(h, cx, o), "facts": dict(o.get("facts") or {})}
    h.op_note(cx, "false_percept", tgt, ",".join(sorted(o.get("facts") or {})))


def forged_over(per: dict | None, facts: dict, now: float) -> dict:
    f = (per or {}).get("forged")
    if not f or (f["until"] is not None and f["until"] <= now):
        return facts
    return {**facts, **f["facts"]}


# ---------------------------------------------------------------- control_link
def op_control_link(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """A persistent control (`as` possess|command|dominance|hypnosis|temptation): no timer, no distance limit; ends when the controller
    dies, on `break_link`, or when `break_if` = {stat, cmp, vs: number} holds for the controlled."""
    kind = o.get("as") if o.get("as") in _LINK_KINDS else "possess"
    lid = str(o.get("id") or "link")
    control._control(h, cx, tgt, {**o, "id": lid, "duration": None}, kind)
    rec = h.op_control(tgt).get("rec")
    if rec is not None and rec["id"] == lid:
        rec["link"] = {"break_if": dict(o["break_if"]) if o.get("break_if") else None}
        h.op_note(cx, "control_link", tgt, lid)


def op_break_link(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """End a link held by the caster (or any, `force`): the control expires at the next update (aggro / faction restored, on_exit runs)."""
    rec = h.op_control(tgt).get("rec")
    if rec and rec.get("link") is not None and (o.get("force") or rec["controller"] == h.op_controller(cx)):
        rec["until"] = cx.t
        h.op_note(cx, "break_link", tgt, rec["id"])


def _value(st: Any, stat: str) -> float:
    return st.resource(stat) if stat in ("hp", "mana", "stamina") else float(st.unit._eff(stat))


def control_over(st: Any, rec: dict, boss: Any, now: float, alive: bool) -> bool:
    """A control record ends by its timer, the controller's death / absence, or a broken link condition."""
    return (rec["until"] is not None and rec["until"] <= now) or boss is None or not alive or link_broken(st, rec)


def link_broken(st: Any, rec: dict) -> bool:
    cond = (rec.get("link") or {}).get("break_if")
    return bool(cond) and _CMP[cond.get("cmp", "lt")](_value(st, cond["stat"]), float(cond.get("vs", 0.0)))


# ---------------------------------------------------------------- erase
def op_erase(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    """Remove the target from existence: no die / kill events, no on_lethal, no revive. Only the flag buff `erase_immune` stops it."""
    b = h.op_buffs(tgt).get("erase_immune")
    if b is not None and b.get("until", 1e18) > cx.t:
        h.op_note(cx, "erase", tgt, "immune")
        return
    if hasattr(h, "mimic_erase"):
        h.mimic_erase(tgt)
    h.op_note(cx, "erase", tgt)


def erase(m: Any, st: Any) -> None:
    ext = st.unit.external
    if ext.get("erased"):
        return
    ext["erased"] = True
    st.entity.erased = True                       # the flag the game reads to skip loot / corpse (not wired)
    m._set_health(st, 0.0)
    st.periodic.clear()
    ext.pop("control", None)
    ext.get("mimic", {}).pop("dispel", None)


MIMIC_HANDLERS = {"fusion_strike": op_fusion_strike, "remove_restriction": op_remove_restriction, "dispel": op_dispel,
                  "copy_technique": op_copy_technique, "copy": op_copy, "false_percept": op_false_percept,
                  "control_link": op_control_link, "break_link": op_break_link, "erase": op_erase}
