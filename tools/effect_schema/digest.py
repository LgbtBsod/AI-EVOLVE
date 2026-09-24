"""Сжатый вид предметов для агентов: одна строка на эффект и diff по id.

Читать Lua-файл предмета целиком почти никогда не нужно: digest() даёт
`id | триггер | op; op; ...`, diff() - только изменившиеся эффекты.
"""
from __future__ import annotations

import json


def _value(v: dict) -> str:
    if "flat" in v:
        return f"{v['flat']}"
    if "pct" in v:
        return f"{v['pct']}%" + (f" of {v['of']}" if v.get("of") else "")
    if "ref" in v:
        return f"ref {v['ref']}"
    return ""


def op_brief(o: dict) -> str:
    parts = [o.get("kind", "?"), o.get("target", ""), o.get("stat") or "", o.get("op") or "",
             _value(o.get("value") or {})]
    s = o.get("scale")
    if s:
        sv = s.get("value") or {}
        parts.append(f"+{sv.get('flat', sv.get('pct'))}/{s.get('every')} {s.get('of')}"
                     + (f" x{s['factor']}" if s.get("factor", 1) != 1 else "")
                     + (f" cap{s['cap']}" if s.get("cap") is not None else ""))
    if o.get("when"):
        parts.append(f"when[{o['when']}]")
    if o.get("fail"):
        parts.append("fail{" + "; ".join(op_brief(f) for f in o["fail"]) + "}")
    if o.get("buff_id"):
        parts.append(f"buff={o['buff_id']}")
    if o.get("flags"):
        parts.append("+".join(o["flags"]))
    return " ".join(p for p in parts if p != "")


def effect_brief(ef: dict) -> str:
    tr = ef.get("trigger", {})
    trig = tr.get("kind", "?") + (f":{tr['event']}" if tr.get("event") else "")
    for key in ("when", "filter"):
        if tr.get(key):
            trig += f" {key}[{tr[key]}]"
    if tr.get("owner_has"):
        trig += f" owner_has={tr['owner_has']}"
    amp = ef.get("amplify")
    extra = f" | amplify x{amp['factor']}/{amp['every']} {amp['of']} when[{amp.get('when')}]" if amp else ""
    return f"{ef.get('id')} | {trig}{extra} | " + "; ".join(op_brief(o) for o in ef.get("ops", []))


def digest(item: dict) -> list[str]:
    """Заголовок + одна строка на эффект."""
    effects = item.get("effects", [])
    return [f"{item.get('name', '?')}: {len(effects)} effect(s)"] + [effect_brief(e) for e in effects]


def diff(a: dict, b: dict) -> list[str]:
    """Изменения между двумя версиями предмета по id эффектов."""
    ea = {e["id"]: e for e in a.get("effects", [])}
    eb = {e["id"]: e for e in b.get("effects", [])}
    out = [f"+ {i}" for i in eb if i not in ea] + [f"- {i}" for i in ea if i not in eb]
    for i in (i for i in ea if i in eb):
        if json.dumps(ea[i], sort_keys=True) != json.dumps(eb[i], sort_keys=True):
            out.append(f"~ {i}\n    was: {effect_brief(ea[i])}\n    now: {effect_brief(eb[i])}")
    return out or ["no differences"]
