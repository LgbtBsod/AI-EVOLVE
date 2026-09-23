"""Валидатор Effect Schema v1: JSON/dict -> список ошибок."""

from __future__ import annotations

from .schema import OP_KINDS, TARGETS, OPS, TRIGGER_KINDS, EVENTS, is_stat


def validate_effect(ef: dict, path: str = "effect") -> list[str]:
    errs: list[str] = []

    def err(msg):
        errs.append(f"{path}: {msg}")

    if not isinstance(ef, dict):
        err("not a dict")
        return errs
    if not ef.get("id"):
        err("missing id")
    tr = ef.get("trigger")
    if not isinstance(tr, dict):
        err("missing trigger")
    else:
        k = tr.get("kind")
        if k not in TRIGGER_KINDS:
            err(f"trigger.kind={k!r} not in {sorted(TRIGGER_KINDS)}")
        if k == "event" and tr.get("event") not in EVENTS:
            err(f"unknown event {tr.get('event')!r}")
        if k == "condition" and not tr.get("when"):
            err("condition trigger requires `when`")
    ops = ef.get("ops")
    if not isinstance(ops, list) or not ops:
        err("ops must be a non-empty list")
    else:
        for i, o in enumerate(ops):
            errs += validate_op(o, f"{path}.ops[{i}]")
    return errs


def validate_op(o: dict, path: str) -> list[str]:
    errs: list[str] = []

    def err(msg):
        errs.append(f"{path}: {msg}")

    if not isinstance(o, dict):
        err("not a dict")
        return errs
    kind = o.get("kind")
    if kind not in OP_KINDS:
        err(f"unknown kind {kind!r}")
        return errs
    if o.get("target", "self") not in TARGETS:
        err(f"unknown target {o.get('target')!r}")
    if o.get("op") is not None and o["op"] not in OPS:
        err(f"unknown op {o['op']!r}")
    st = o.get("stat")
    if kind in ("mod", "heal", "drain", "set", "deal") and st and not is_stat(st):
        err(f"unknown stat {st!r} (use custom:<name> for new stats)")
    if kind in ("mod", "heal", "drain", "set") and not st:
        err(f"kind={kind} requires stat")
    if kind in ("buff", "extend", "remove_buff") and not o.get("buff_id"):
        err(f"kind={kind} requires buff_id")
    v = o.get("value")
    if kind in ("mod", "heal", "drain", "set", "deal") and v is None and o.get("scale") is None:
        err("needs value or scale")
    if isinstance(v, dict):
        if not any(k in v for k in ("flat", "pct", "ref")):
            err("value needs one of flat/pct/ref")
        if "pct" in v and v.get("of") and not is_stat(v["of"]):
            err(f"value.of unknown stat {v['of']!r}")
    s = o.get("scale")
    if isinstance(s, dict):
        if "every" not in s or s["every"] in (0, None):
            err("scale.every required (>0)")
        if not s.get("of"):
            err("scale.of required")
        elif not is_stat(s["of"]):
            err(f"scale.of unknown stat {s['of']!r}")
    for i, f in enumerate(o.get("fail", []) or []):
        errs += validate_op(f, f"{path}.fail[{i}]")
    return errs


def validate_item(item: dict) -> list[str]:
    errs = []
    effects = item.get("effects", [])
    ids = set()
    for i, ef in enumerate(effects):
        errs += validate_effect(ef, f"effects[{i}]")
        eid = ef.get("id") if isinstance(ef, dict) else None
        if eid in ids:
            errs.append(f"effects[{i}]: duplicate id {eid!r}")
        ids.add(eid)
    return errs
