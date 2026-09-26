"""Генерик-вычислитель правил probe_analysis: правила - данные (lua_content/probe_rules.lua).

evaluate(rules, facts, cfg) -> список гипотез (порядок правил, затем стабильная сортировка
по severity); first_say(rules, facts) -> текст первого сработавшего правила (outlook).
Условие: лист {m, op, v} или {all|any = [...]}; None в сравнении = ложь; деление на 0 = None.
"""
import json
import operator
from functools import lru_cache
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
RULES_PATH = _REPO / "lua_content" / "probe_rules.lua"
SNAPSHOT_PATH = _REPO / "tools" / "probe_rules_snapshot.json"  # JSON twin for a Python without Lua (test: == Lua; regen: python tools/probe_rules.py)
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
_CMP = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt, "ge": operator.ge,
        "lt": operator.lt, "le": operator.le}
_UNARY = {"truthy": bool, "falsy": lambda x: not x, "isnone": lambda x: x is None, "notnone": lambda x: x is not None}


@lru_cache(maxsize=None)
def rules_table():
    try:
        import lua_bridge  # lazy: ~50 ms
        return lua_bridge.load(RULES_PATH)
    except RuntimeError:  # no rust_core / lupa: the snapshot of the same table
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _value(spec, facts, cfg):
    if isinstance(spec, str) and spec[:1] == "$":
        return cfg[spec[1:]]
    if isinstance(spec, str) and spec[:1] == "@":
        return facts.get(spec[1:])
    return spec


def _metric(m, facts):
    if isinstance(m, list):
        num, den = facts.get(m[0]), facts.get(m[1])
        return num / den if num is not None and den else None
    return facts.get(m)


def holds(cond, facts, cfg):
    if "all" in cond:
        return all(holds(c, facts, cfg) for c in cond["all"])
    if "any" in cond:
        return any(holds(c, facts, cfg) for c in cond["any"])
    x, op = _metric(cond["m"], facts), cond["op"]
    if op in _UNARY:
        return _UNARY[op](x)
    y = _value(cond.get("v"), facts, cfg)
    return x is not None and y is not None and _CMP[op](x, y)


def _evidence(rows, facts):
    out = {}
    for row in rows:
        v = facts.get(row[1])
        out[row[0]] = round(v, 1) if len(row) > 2 and v is not None else v
    return out


def _pick(spec, facts):
    return facts.get(spec[1:]) if isinstance(spec, str) else list(spec or [])


def _hypothesis(rule, facts):
    sev = rule["severity"]
    return {"id": rule["id"], "severity": facts.get(sev[1:]) if sev[0] == "@" else sev,
            "claim": rule["say"].format(**facts), "evidence": _evidence(rule.get("evidence") or [], facts),
            "look_at": _pick(rule.get("look"), facts), "next": rule.get("next")}


def evaluate(rules, facts, cfg):
    facts = {**facts, "cfg": cfg}
    out = [_hypothesis(r, facts) for r in rules if holds(r["when"], facts, cfg)]
    out.sort(key=lambda h: SEVERITY_ORDER.get(h["severity"], 9))
    return out


def first_say(rules, facts):
    for r in rules:
        if holds(r["when"], facts, {}):
            return r["say"].format(**facts)
    return None


if __name__ == "__main__":  # regenerate the snapshot (needs a Lua backend)
    import lua_bridge
    text = json.dumps(lua_bridge.load(RULES_PATH), ensure_ascii=False, indent=1) + chr(10)
    SNAPSHOT_PATH.write_text(text, encoding="utf-8", newline=chr(10))
