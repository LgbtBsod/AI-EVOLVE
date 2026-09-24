"""Валидатор Effect Schema v1: JSON/dict -> список ошибок."""

from __future__ import annotations

from .schema import (OP_KINDS, TARGETS, OPS, TRIGGER_KINDS, EVENTS,
                     CONTEXT_ONLY_STATS, is_stat)


def _validate_pred(pred, path: str) -> list[str]:
    """Строка-предикат должна компилироваться безопасным интерпретатором sim."""
    if not isinstance(pred, str) or not pred.strip():
        return [f"{path}: predicate must be a non-empty string"]
    from .sim import eval_pred, PREDICATES  # лениво: sim импортирует только stdlib
    if pred.strip() in PREDICATES:
        return []
    try:
        # фиктивный ctx покрывает стандартные поля Unit.ctx + enemy_*/ally_*
        smoke_ctx = {k: 50.0 for k in (
            "hp", "max_hp", "hp_pct", "hp_missing", "strength", "stamina",
            "crit_chance", "crit_dmg", "aspd", "hp_regen", "lifesteal",
            "defense", "kills", "mana", "max_mana")}
        smoke_ctx.update({f"enemy_{k}": 50.0 for k in
                          ("hp", "max_hp", "hp_pct", "alive")})
        smoke_ctx.update({f"ally_{k}": 50.0 for k in
                          ("hp", "max_hp", "hp_pct", "alive")})
        eval_pred(pred, smoke_ctx)   # smoke-прогон на фиктивном ctx
        return []
    except Exception as e:
        return [f"{path}: invalid predicate {pred!r} ({type(e).__name__}: {e})"]


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
    for pk in ("when", "filter"):
        pv = tr.get(pk) if isinstance(tr, dict) else None
        if isinstance(pv, str) and pv:
            errs += _validate_pred(pv, f"{path}.trigger.{pk}")
    amp = ef.get("amplify")
    if amp is not None:
        if not isinstance(amp, dict):
            err("amplify must be a table {when, every, of, factor}")
        else:
            if not isinstance(amp.get("every"), (int, float)) or amp["every"] <= 0:
                err("amplify.every must be a positive number")
            if not isinstance(amp.get("factor"), (int, float)):
                err("amplify.factor must be a number")
            if not isinstance(amp.get("of"), str) or not amp["of"]:
                err("amplify.of must name a ctx field (e.g. hp_missing_below_40)")
            if not amp.get("when") and not amp.get("while_buff"):
                err("amplify needs `when` (predicate) or `while_buff`")
            if isinstance(amp.get("when"), str):
                errs += _validate_pred(amp["when"], f"{path}.amplify.when")
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
    if st in CONTEXT_ONLY_STATS:
        err(f"stat {st!r} is read-only context field (usable only in value.of/scale.of)")
    if kind in ("buff", "extend", "remove_buff") and not o.get("buff_id"):
        err(f"kind={kind} requires buff_id")
    v = o.get("value")
    if kind in ("mod", "heal", "drain", "set", "deal") and v is None and o.get("scale") is None:
        err("needs value or scale")
    when = o.get("when")
    if isinstance(when, str) and when:
        errs += _validate_pred(when, f"{path}.when")
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
