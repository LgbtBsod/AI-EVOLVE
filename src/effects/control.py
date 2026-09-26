"""Slice F2: the CONTROL family (hypnosis, command, possess, dominance, tame, temptation) as ONE mechanism.

A control is a record `unit.external["control"] = {"rec": {...}}` on the target: what it is (kind/id), who holds it (`controller`
= entity id), when it ends (`until`, None = permanent) and what to restore (`saved_aggro`, `saved_faction`). Applying it goes
through the seams that already existed: `set_aggro` (aggro_mode / targeting / target) and the host's faction. It ends by expiry
or when the controller dies (EffectManager.update calls `release_control`); `tame` is permanent and never ends.
The game has no "player drives another entity" concept, so `possess` = faction switch + targeting override + restore (docs/EFFECT_SCHEMA.md "Control").
Gates before anything is applied: an `immune` op with effect=control (buff block:control), `status_resist_<id|kind|control>`
(>=100 always resists, 0<p<100 one seeded draw), and the optional `requires` = {stat, cmp: lt|le|gt|ge, vs: "source" | number}.
"""
from __future__ import annotations

from typing import Any

_CMP = {"lt": lambda a, b: a < b, "le": lambda a, b: a <= b, "gt": lambda a, b: a > b, "ge": lambda a, b: a >= b}
_FACTION_KINDS = ("possess", "dominance", "tame")          # these also change the faction (the rest only steer the target)
_MODES = {"hypnosis": "illusion", "command": "command", "possess": "controlled", "dominance": "dominated",
          "tame": "tamed", "temptation": "tempted"}


def _blocked(h: Any, cx: Any, tgt: Any, kind: str, o: dict) -> str | None:
    """Why the control does not land (None = it lands): immune / resisted / condition not met."""
    b = h.op_buffs(tgt).get("block:control")
    if b is not None and b.get("until", 1e18) > cx.t:
        return "immune"
    for sid in dict.fromkeys((o.get("id") or kind, kind, "control")):
        if h.op_resisted(cx, tgt, sid):
            return "resisted"
    req = o.get("requires")
    if req:
        mine = h.op_stat_of(cx, "target", tgt, req["stat"])
        vs = req.get("vs", 0.0)
        other = h.op_stat_of(cx, "source", tgt, req["stat"]) if vs == "source" else float(vs)
        if not _CMP[req.get("cmp", "lt")](mine, other):
            return "condition"
    return None


def _roll_lands(h: Any, cx: Any, o: dict) -> bool:
    ch = float(o.get("chance", 100.0))
    return ch >= 100.0 or (ch > 0.0 and h.op_roll(cx) * 100.0 < ch)


def release_control(h: Any, cx: Any, tgt: Any) -> dict | None:
    """End the control on `tgt`: restore aggro and faction. Returns the record (its on_exit ops are the host's to run)."""
    rec = h.op_control(tgt).pop("rec", None)
    if rec is None:
        return None
    h.set_aggro(cx, tgt, **rec["saved_aggro"])
    if rec["saved_faction"] is not None:
        h.op_faction(cx, tgt, rec["saved_faction"])
    h.op_note(cx, "control_end", tgt, rec["id"])
    return rec


def _steer(h: Any, cx: Any, tgt: Any, o: dict, rec: dict) -> None:
    kind = rec["kind"]
    ag = dict(rec["saved_aggro"])
    ag["aggro_mode"] = f"{_MODES[kind]}:{o.get('action') or o.get('mode') or 'obey'}"
    ag["controller"] = rec["controller"]
    if o.get("target_ref") is not None:
        ag["target"] = o["target_ref"]
    ag["targeting"] = {"mode": "controller" if kind in _FACTION_KINDS else _MODES[kind], **dict(o.get("targeting") or {})}
    if kind == "hypnosis":
        ag["perception"] = o.get("perception") or "illusion"
    h.set_aggro(cx, tgt, **ag)


def _record(h: Any, cx: Any, tgt: Any, o: dict, kind: str) -> dict:
    dur = o.get("duration")
    return {"id": o.get("id") or kind, "kind": kind, "controller": h.op_controller(cx),
            "until": None if kind == "tame" or dur is None else cx.t + h.op_duration(dur, cx.ctx),
            "saved_aggro": dict(h.op_aggro(cx, tgt)), "saved_faction": h.op_faction(cx, tgt),
            "on_exit": list(o.get("on_exit") or [])}


def _control(h: Any, cx: Any, tgt: Any, o: dict, kind: str) -> None:
    why = _blocked(h, cx, tgt, kind, o)
    if why or (kind == "tame" and not _roll_lands(h, cx, o)):
        h.op_note(cx, "control_blocked", tgt, why or "failed")
        return
    holder = h.op_control(tgt)
    if "rec" in holder:
        release_control(h, cx, tgt)                       # a new control replaces the old one; the first saved state is restored first
    holder["rec"] = rec = _record(h, cx, tgt, o, kind)
    _steer(h, cx, tgt, o, rec)
    if kind in _FACTION_KINDS:
        h.op_faction(cx, tgt, h.op_faction(cx, cx.source))
    if kind == "tame":
        holder.pop("rec")                                  # permanent: nothing to restore, no record of an active control
    h.op_note(cx, "control_start", tgt, kind)


def _make(kind: str):
    def handler(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
        _control(h, cx, tgt, o, kind)
    handler.__name__ = f"op_{kind}"
    return handler


CONTROL_HANDLERS = {k: _make(k) for k in _MODES}
