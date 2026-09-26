"""Валидатор Effect Schema v1: JSON/dict -> список ошибок."""

from __future__ import annotations

from src.effects.ops import canonical_kind

from .schema import (OP_KINDS, TARGETS, OPS, TRIGGER_KINDS, EVENTS, FLAGS, MOVE_MODES, AREA_AFFECTS,
                     TOWARD, TOWARD_STATS, CONTEXT_ONLY_STATS, RESOURCE_STATS, is_derived_stat, is_stat)


def _validate_pred(pred, path: str, effects=()) -> list[str]:
    """Условие должно быть булевым выражением над полями рантайма (sim.sample_context);
    effects - эффекты предмета: их баффы добавляют поля buff_<id>."""
    if not isinstance(pred, str) or not pred.strip():
        return [f"{path}: predicate must be a non-empty string"]
    from .sim import eval_pred, named_predicates, sample_context  # лениво: sim - только stdlib
    if pred.strip() in named_predicates():
        return []
    from .pred_lua import check_boolean  # то же условие обязано работать и в Lua
    bool_errs = check_boolean(pred)
    if bool_errs:
        return [f"{path}: {e}" for e in bool_errs]
    try:
        eval_pred(pred, sample_context(list(effects)))   # неизвестное поле ctx -> ошибка здесь, а не в бою
        return []
    except Exception as e:
        return [f"{path}: invalid predicate {pred!r} ({type(e).__name__}: {e})"]


def validate_effect(ef: dict, path: str = "effect", item_effects=None) -> list[str]:
    item_effects = item_effects if item_effects is not None else [ef]
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
        if tr.get("cross") and tr.get("event") != "hp_cross":
            err("trigger.cross is only for event=hp_cross")
    thr = ef.get("threshold")
    if thr is not None:
        if not isinstance(thr, (int, float)) or not 0 < thr < 100:
            err("threshold must be an HP percentage in (0, 100)")
        if (tr or {}).get("kind") != "condition":
            err("threshold (hp_cross zone) needs a condition trigger")
    for pk in ("when", "filter"):
        pv = tr.get(pk) if isinstance(tr, dict) else None
        if isinstance(pv, str) and pv:
            errs += _validate_pred(pv, f"{path}.trigger.{pk}", item_effects)
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
                errs += _validate_pred(amp["when"], f"{path}.amplify.when", item_effects)
    ops = ef.get("ops")
    if not isinstance(ops, list) or not ops:
        err("ops must be a non-empty list")
    else:
        for i, o in enumerate(ops):
            errs += validate_op(o, f"{path}.ops[{i}]", item_effects)
    return errs


_VALUE_KINDS = ("mod", "heal", "drain", "set", "deal")


def _c_head(o, kind, path, ie):
    out = []
    if o.get("target", "self") not in TARGETS:
        out.append(f"unknown target {o.get('target')!r}")
    if o.get("op") is not None and o["op"] not in OPS:
        out.append(f"unknown op {o['op']!r}")
    return out


def _stat_kind_err(kind, st):
    if st in CONTEXT_ONLY_STATS or (isinstance(st, str) and is_derived_stat(st)):
        return f"stat {st!r} is read-only context field (usable only in value.of/scale.of)"
    if kind == "mod" and st in RESOURCE_STATS:
        return f"mod cannot change resource {st!r}: use heal/drain/deal/set (or mod max_{st})"
    if kind in ("heal", "drain", "deal", "set") and st and st not in RESOURCE_STATS:
        return (f"kind={kind} works on resources {sorted(RESOURCE_STATS)}, not {st!r}"
                + (" (use mod with op=set)" if kind == "set" else ""))
    return None


def _c_stat(o, kind, path, ie):
    st, out = o.get("stat"), []
    if kind in _VALUE_KINDS and st and not is_stat(st):
        out.append(f"unknown stat {st!r} (use custom:<name> for new stats)")
    if kind in ("mod", "heal", "drain", "set") and not st:
        out.append(f"kind={kind} requires stat")
    kerr = _stat_kind_err(kind, st)
    return out + ([kerr] if kerr else [])


def _c_flags_extend(o, kind, path, ie):
    out = []
    bad_flags = [f for f in o.get("flags") or [] if f not in FLAGS]
    if bad_flags:
        out.append(f"unknown flags {bad_flags} (known: {sorted(FLAGS)})")
    ext = o.get("extend")
    if isinstance(ext, dict) and ext.get("on") and ext["on"] not in EVENTS:
        out.append(f"extend.on={ext['on']!r} is not an event")
    return out


_REQ_EARLY = {
    "apply_effect": ("buff_id", "kind=apply_effect requires buff_id (the id of the effect to apply)"),
    "summon": ("summon", "kind=summon requires summon (creature type)"),
}


def _c_required_early(o, kind, path, ie):
    if kind in _REQ_EARLY and not o.get(_REQ_EARLY[kind][0]):
        return [_REQ_EARLY[kind][1]]
    if kind == "move" and o.get("mode") not in MOVE_MODES:
        return [f"kind=move requires mode in {sorted(MOVE_MODES)}"]
    return []


def _c_area(o, kind, path, ie):
    out, area = [], o.get("target") == "area"
    if area and o.get("center", "target") not in ("target", "self"):
        out.append("area center must be 'target' or 'self'")
    if o.get("arc") is not None and (not area or not 0 < float(o["arc"]) <= 360):
        out.append("arc (degrees, 0 < arc <= 360) is for target=area")
    return out + _c_radius_affects(o, area)


def _c_radius_affects(o, area):
    out = []
    if isinstance(o.get("radius"), str) and not is_stat(o["radius"]):
        out.append(f"radius {o['radius']!r} is neither a number nor a stat")
    if o.get("affects") is not None and (not area or o["affects"] not in AREA_AFFECTS):
        out.append(f"affects is for target=area, one of {sorted(AREA_AFFECTS)}")
    return out


def _c_toward_every(o, kind, path, ie):
    out = []
    if o.get("toward") is not None and (
            o["toward"] not in TOWARD or kind != "mod" or o.get("stat") not in TOWARD_STATS):
        out.append(f"toward={o['toward']!r} is for mod of {sorted(TOWARD_STATS)} (toward='source': stealth)")
    if o.get("every") is not None and (kind not in ("deal", "heal") or o.get("duration") is None):
        out.append("every (periodic op) is for deal/heal and needs duration")
    return out


def _c_required_late(o, kind, path, ie):
    out = []
    if kind in ("buff", "extend", "remove_buff") and not o.get("buff_id"):
        out.append(f"kind={kind} requires buff_id")
    if kind in _VALUE_KINDS and o.get("value") is None and o.get("scale") is None:
        out.append("needs value or scale")
    return out


def _c_when(o, kind, path, ie):
    when = o.get("when")
    if isinstance(when, str) and when:
        return _validate_pred(when, f"{path}.when", ie)
    return []


def _c_value(o, kind, path, ie):
    v, out = o.get("value"), []
    if isinstance(v, dict):
        if not any(k in v for k in ("flat", "pct", "ref")):
            out.append("value needs one of flat/pct/ref")
        if "pct" in v and v.get("of") and not is_stat(v["of"]):
            out.append(f"value.of unknown stat {v['of']!r}")
    return out


def _c_scale(o, kind, path, ie):
    s, out = o.get("scale"), []
    if isinstance(s, dict):
        if "every" not in s or s["every"] in (0, None):
            out.append("scale.every required (>0)")
        if not s.get("of"):
            out.append("scale.of required")
        elif not is_stat(s["of"]):
            out.append(f"scale.of unknown stat {s['of']!r}")
    return out


def _c_fail(o, kind, path, ie):
    out = []
    for i, f in enumerate(o.get("fail", []) or []):
        out += validate_op(f, f"{path}.fail[{i}]", ie)
    return out


# order = order of the messages; _c_when and _c_fail already return path-prefixed messages
_OP_CHECKS = (_c_head, _c_stat, _c_flags_extend, _c_required_early, _c_area, _c_toward_every,
              _c_required_late, _c_when, _c_value, _c_scale, _c_fail)
_PREFIXED = (_c_when, _c_fail)


def validate_op(o: dict, path: str, item_effects=()) -> list[str]:
    if not isinstance(o, dict):
        return [f"{path}: not a dict"]
    kind = canonical_kind(o.get("kind"))
    if kind not in OP_KINDS:
        return [f"{path}: unknown kind {kind!r}"]
    errs: list[str] = []
    for chk in _OP_CHECKS:
        found = chk(o, kind, path, item_effects)
        errs += found if chk in _PREFIXED else [f"{path}: {m}" for m in found]
    return errs


def _applied(ops: list) -> list[str]:
    """id эффектов, которые запускают ops (apply_effect, включая fail-ветки)."""
    out = []
    for o in ops or []:
        if isinstance(o, dict):
            if canonical_kind(o.get("kind")) == "apply_effect" and o.get("buff_id"):
                out.append(o["buff_id"])
            out += _applied(o.get("fail"))
    return out


def _references(effects: list) -> list[str]:
    """apply_effect / owner_has ведут на существующие эффекты; apply_effect без циклов
    (цикл = бесконечная рекурсия в рантайме)."""
    errs = []
    by_id = {ef.get("id"): ef for ef in effects if isinstance(ef, dict)}
    graph = {eid: _applied(ef.get("ops")) for eid, ef in by_id.items()}
    zones = {(ef.get("meta") or {}).get("name") or ef.get("id")
             for ef in effects if isinstance(ef, dict) and ef.get("threshold") is not None}
    for i, ef in enumerate(effects):
        if not isinstance(ef, dict):
            continue
        cross = (ef.get("trigger") or {}).get("cross")
        if cross and cross not in zones:
            errs.append(f"effects[{i}]: cross={cross!r} names no hp_cross zone (effect with threshold)")
        owner = (ef.get("trigger") or {}).get("owner_has")
        if owner and owner not in by_id:
            errs.append(f"effects[{i}]: owner_has={owner!r} is not an effect of this item")
        for target in graph.get(ef.get("id"), []):
            if target not in by_id:
                errs.append(f"effects[{i}]: apply_effect {target!r} is not an effect of this item")
    state: dict = {}  # 1 - в стеке, 2 - готово

    def visit(eid, path):
        state[eid] = 1
        for nxt in graph.get(eid, []):
            if state.get(nxt) == 1:
                errs.append("apply_effect cycle: " + " -> ".join(path + [nxt]))
            elif nxt in graph and nxt not in state:
                visit(nxt, path + [nxt])
        state[eid] = 2

    for eid in graph:
        if eid not in state:
            visit(eid, [eid])
    return errs


def validate_item(item: dict) -> list[str]:
    errs = []
    effects = item.get("effects", [])
    ids = set()
    for i, ef in enumerate(effects):
        errs += validate_effect(ef, f"effects[{i}]", effects)
        eid = ef.get("id") if isinstance(ef, dict) else None
        if eid in ids:
            errs.append(f"effects[{i}]: duplicate id {eid!r}")
        ids.add(eid)
    return errs + _references(effects)
