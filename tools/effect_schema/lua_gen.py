"""
Lua-генератор для Effect Schema v1.

Сериализует Python/JSON модель (Effect/Op/Value/Scale/Trigger) в читаемый
Lua-table. Условия пишутся как pred("исходник", function(ctx) ... end):
движок вызывает функцию, инструменты получают исходник без разбора текста.
Сгенерированный код:

  * валиден как Lua 5.5 (исполняется в тестах через tools/lua_bridge.py),
  * round-trip-ится обратно в JSON тем же мостом (rust_core/mlua или lupa).

API:
    render_effect(ef: Effect|dict) -> str
    render_item(item: dict, effects: list[Effect|dict]) -> str
"""

from __future__ import annotations

import math
from datetime import datetime


# ---------------------------------------------------------------- helpers

def _num(v) -> str:
    f = float(v)
    if math.isfinite(f) and f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return repr(f)


def _str(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _is_expr(pred: str) -> bool:
    """Строка-выражение ('ctx.hp_pct < 40') vs именованный предикат."""
    return any(ch in pred for ch in "<>=!()") or "." in pred


# Ключи, значения которых - условия (предикаты)
PRED_KEYS = ("when", "filter")

# Хелпер в начале каждого Lua-файла предмета: условие = исходник (для
# инструментов: экспорт без разбора текста функции) + функция (для Lua-движка:
# p(ctx) вызывается напрямую через __call)
PRED_PRELUDE = (
    "local PRED_MT = { __call = function(p, ctx) return p.fn(ctx) end }\n"
    "local function pred(src, fn) return setmetatable({ src = src, fn = fn }, PRED_MT) end"
)


def _pred_value(src: str) -> str:
    """Условие -> `pred("src", function(ctx) return <lua> end)`; именованное -> из реестра PRED."""
    if not _is_expr(src):
        return f"pred({_str(src)}, PRED[{_str(src)}])"
    # транслятор по белому списку AST: `!=` -> `~=`, max -> math.max,
    # цепочки сравнений -> and (раньше выражение копировалось как есть)
    from .pred_lua import to_lua
    lua = to_lua(src)
    return f"pred({_str(src)}, function(ctx) return {lua if lua.startswith('(') else f'({lua})'} end)"


# ---------------------------------------------------------------- scalars

def _scalar_str(v) -> str | None:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return _num(v)
    if isinstance(v, str):
        return _str(v)
    return None


def _render_kv(k: str, v, pad_in: str) -> list[str]:
    """Одна строка `k = ...` (или несколько) с запятой."""
    if k in PRED_KEYS and isinstance(v, str) and v:
        return [f"{pad_in}{k} = {_pred_value(v)},"]
    s = _scalar_str(v)
    if s is not None:
        return [f"{pad_in}{k} = {s},"]
    if isinstance(v, dict):
        return [f"{pad_in}{k} = {_table_expr(v, pad_in)},"]
    if isinstance(v, list):
        return [f"{pad_in}{k} = {{"] + _render_list_items(v, pad_in + "  ") + \
               [f"{pad_in}}},"]
    return [f"{pad_in}{k} = {_str(str(v))},"]


def _render_list_items(items: list, pad_in: str) -> list[str]:
    out = []
    for x in items:
        s = _scalar_str(x)
        if s is not None:
            out.append(f"{pad_in}{s},")
        elif isinstance(x, dict):
            out.append(f"{pad_in}{{")
            for k, v in x.items():
                if v is None or v == "" or v == [] or v == {}:
                    continue
                out.extend(_render_kv(k, v, pad_in + "  "))
            out.append(f"{pad_in}}},")
        elif isinstance(x, list):
            out.append(f"{pad_in}{{")
            out.extend(_render_list_items(x, pad_in + "  "))
            out.append(f"{pad_in}}},")
    return out


def _parts(d: dict, outer_pad: str) -> list[tuple[str, str]]:
    """[(key, rendered_value)] c пропуском пустых полей."""
    out = []
    for k, v in d.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        if k in PRED_KEYS and isinstance(v, str):
            out.append((k, _pred_value(v)))
            continue
        s = _scalar_str(v)
        if s is not None:
            out.append((k, s))
        elif isinstance(v, dict):
            out.append((k, _table_expr(v, outer_pad)))
        elif isinstance(v, list):
            if all(_scalar_str(x) is not None for x in v):
                items = ", ".join(_scalar_str(x) for x in v)
                out.append((k, f"{{ {items} }}"))
            else:
                pad_in = outer_pad + "  "
                lines = ["{"]
                lines.extend(_render_list_items(v, pad_in))
                lines.append(pad_in + "}")
                out.append((k, "\n".join(lines)))
        else:
            out.append((k, _str(str(v))))
    return out


def _table_expr(d: dict, outer_pad: str) -> str:
    """Инлайн если короткий и без вложенных таблиц-списков, иначе многострочно.

    Все элементы списка разделены запятыми -- синтаксис Lua-table корректен.
    """
    parts = _parts(d, outer_pad)
    inline = "{ " + ", ".join(f"{k} = {v}" for k, v in parts) + " }"
    if len(inline) <= 92 and "\n" not in inline:
        return inline
    pad_in = outer_pad + "  "
    lines = ["{"]
    for i, (k, v) in enumerate(parts):
        # разделитель ОБЯЗАТЕЛЕН, если значение заканчивается на `}` --
        # иначе `{a={...}}{b={...}}` склеится в невалидный `}}{`
        nxt = parts[i + 1][1] if i + 1 < len(parts) else None
        need_sep = i < len(parts) - 1 and (
            str(v).rstrip().endswith("}") or (nxt is not None and
                                              str(nxt).lstrip().startswith("{")))
        sep = "," if (i < len(parts) - 1 or need_sep) else ""
        lines.append(f"{pad_in}{k} = {v}{sep}")
    lines.append(outer_pad + "}")
    return "\n".join(lines)


# ---------------------------------------------------------------- effect

def render_effect(ef, indent: int = 0) -> str:
    """Эффект -> Lua-table (значение, без `return`)."""
    from .schema import Effect
    if isinstance(ef, Effect):
        ef = ef.to_json()
    pad = "  " * indent
    d = {}
    d["id"] = ef["id"]
    if ef.get("tags"):
        d["tags"] = list(ef["tags"])
    tr = ef.get("trigger", {"kind": "passive"})
    trd = {"kind": tr.get("kind", "passive")}
    for k in ("event", "filter", "owner_has", "cross"):
        if tr.get(k):
            trd[k] = tr[k]
    when = tr.get("when")
    if when:
        # функция-предикат рендерим отдельно (не сериализуется как скаляр)
        d["trigger"] = trd
        d["_trigger_when"] = when
    else:
        d["trigger"] = trd
    if ef.get("threshold") is not None:
        d["threshold"] = ef["threshold"]
    for k in ("duration", "cooldown", "stacks", "amplify", "meta"):
        if ef.get(k):
            d[k] = ef[k]
    d["ops"] = ef.get("ops", [])

    lines = ["{"]
    pad_in = pad + "  "
    for k, v in d.items():
        if k == "_trigger_when":
            lines.append(f'{pad_in}trigger = {{ ' +
                         ", ".join([f'{kk} = {_vv}' for kk, _vv in
                                    ((kk, _scalar_str(vv) if _scalar_str(vv) is not None else _table_expr(vv, pad_in))
                                     for kk, vv in trd.items())]) +
                         f', when = {_pred_value(v)} }},')
            continue
        if k == "trigger" and when:
            continue  # уже выведена вместе с when
        if k == "ops":
            lines.append(f"{pad_in}ops = {{")
            op_pad = pad_in + "  "
            for idx, o in enumerate(v):
                desc = (f"-- op: {o.get('kind')} {o.get('target','self')} "
                        f"{o.get('stat') or ''} {o.get('op') or ''}").rstrip()
                lines.append(f"{op_pad}{desc}")
                expr = _table_expr({kk: vv for kk, vv in o.items()
                                    if vv not in (None, "", [], {})}, op_pad)
                sep = "," if idx < len(v) - 1 else ""
                # многострочное выражение уже начинается с "{" на op_pad
                lines.append(op_pad + expr + sep)
            lines.append(f"{pad_in}}},")
            continue
        lines.extend(_render_kv(k, v, pad_in))
    lines.append(pad + "}")
    return "\n".join(lines)


# ---------------------------------------------------------------- item file

def collect_predicates(effects: list) -> list[str]:
    names = set()

    def walk_ops(ops):
        for o in ops:
            if o.get("when"):
                names.add(o["when"])
            for f in o.get("fail", []) or []:
                walk_ops([f])

    for ef in effects:
        tr = ef.get("trigger") or {}
        for w in (tr.get("when"), tr.get("filter"), (ef.get("amplify") or {}).get("when")):
            if isinstance(w, str) and w and not _is_expr(w):
                names.add(w)
        walk_ops(ef.get("ops", []))
    return sorted(n for n in names if n and not _is_expr(n))


def render_predicate_registry(effects: list) -> str:
    """Реестр PRED: именованные условия из lua_content/effect_rules.lua (predicates)
    переводятся в Lua; движок может подменить реестр своим (`PRED or {...}`)."""
    preds = collect_predicates(effects)
    if not preds:
        return ""
    from .pred_lua import to_lua
    from .sim import named_predicates
    known = named_predicates()
    lines = ["-- Именованные условия (lua_content/effect_rules.lua -> predicates)",
             "local PRED = PRED or {"]
    for p in preds:
        body = f"return {to_lua(known[p])}" if p in known else "return true -- неизвестное имя: условие даёт движок"
        lines.append(f"  [{_str(p)}] = function(ctx) {body} end,")
    lines.append("}")
    return "\n".join(lines)


def render_item(item: dict, effects: list) -> str:
    """Полный Lua-файл предмета: base_stats + effects[] по схеме Effect->Ops[]."""
    from .schema import Effect
    eff_dicts = [e.to_json() if isinstance(e, Effect) else e for e in effects]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = [
        f"-- {item.get('name', 'Unnamed Item')}",
        f"-- {item.get('description', '')}",
        f"-- Сгенерировано CAS Item Builder (effect-schema v1) : {now}",
    ]
    out.append(PRED_PRELUDE)
    reg = render_predicate_registry(eff_dicts)
    if reg:
        out.append(reg)
    out.append("")
    out.append("return {")
    for k, v in item.items():
        if k == "effects":
            continue
        if v is None or v == "" or v == [] or v == {}:
            continue
        out.extend(_render_kv(k, v, "  "))
    out.append("  effects = {")
    for ef in eff_dicts:
        out.append("    " + render_effect(ef, indent=2) + ",")
    out.append("  },")
    out.append("}")
    return "\n".join(out) + "\n"
