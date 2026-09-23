"""
UI-логика билдера (без Flet) — общий слой для web_builder/app.py и тестов.

Цикл:  форма(dict) -> build_item_json -> validate -> render Lua
       -> lupa load (опционально) -> sim.EffectRuntime (тренировочная комната).

Форма повторяет чек-лист полей схемы Effect Schema v1:
  Effect: id, tags, trigger{kind,event,when,filter,owner_has}, ops[]
  Op:     kind,target,stat,op,value{flat,pct,of,ref},scale{every,of,value,factor,cap,floor},
          when,fail[],duration,cooldown,extend,buff_id,flags[]
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .schema import Effect, Op, Trigger, Value, Scale
from .validate import validate_item
from .lua_gen import render_item
from .lua_parse import parse_lua
from .sim import EffectRuntime, Unit


# ---------------------------------------------------------------- parsing

def _num(x) -> Optional[float]:
    if x is None or x == "":
        return None
    return float(x)


def value_from_form(d: Optional[dict]) -> Optional[Value]:
    """value = {flat|pct|ref, of} из полей формы (''/'None' выкидываются)."""
    if not d:
        return None
    flat, pct_ = _num(d.get("flat")), _num(d.get("pct"))
    ref = d.get("ref") or None
    of = d.get("of") or None
    if flat is None and pct_ is None and ref is None:
        return None
    return Value(flat=flat, pct=pct_, of=of, ref=ref)


def scale_from_form(d: Optional[dict]) -> Optional[Scale]:
    if not d or not d.get("of"):
        return None
    every = _num(d.get("every"))
    if not every:
        return None
    return Scale(
        every=every, of=d["of"],
        value=value_from_form(d.get("value")),
        factor=_num(d.get("factor")) or 1.0,
        cap=_num(d.get("cap")), floor=_num(d.get("floor")),
    )


def op_from_form(d: dict) -> Op:
    fail = d.get("fail") or []
    kind = d["kind"]
    raw_dur, raw_cd = d.get("duration"), d.get("cooldown")
    duration = None
    if isinstance(raw_dur, dict):
        duration = dict(raw_dur)
        if isinstance(duration.get("scale"), dict):
            s = scale_from_form(duration["scale"])
            duration["scale"] = s.to_json() if s else None
    cooldown = value_from_form(raw_cd).to_json() if isinstance(raw_cd, dict) else raw_cd
    value = value_from_form(d.get("value"))
    scale = scale_from_form(d.get("scale"))
    # buff/extend/remove_buff/apply_effect не требуют value; пустые поля формы -> None
    return Op(
        kind=kind,
        target=d.get("target") or "self",
        stat=d.get("stat") or None,
        op=d.get("op") or None,
        value=value,
        scale=scale,
        when=d.get("when") or None,
        fail=[op_from_form(f) for f in fail],
        duration=duration,
        cooldown=cooldown,
        extend=d.get("extend") or None,
        buff_id=d.get("buff_id") or None,
        flags=[f for f in (d.get("flags") or []) if f],
    )


def effect_from_form(d: dict) -> Effect:
    tr = d.get("trigger") or {}
    return Effect(
        id=d["id"],
        trigger=Trigger(
            kind=tr.get("kind") or "passive",
            event=tr.get("event") or None,
            when=tr.get("when") or None,
            filter=tr.get("filter") or None,
            owner_has=tr.get("owner_has") or None,
        ),
        ops=[op_from_form(o) for o in d.get("ops", [])],
        tags=[t for t in (d.get("tags") or []) if t],
        duration=d.get("duration") or None,
        cooldown=d.get("cooldown") or None,
        stacks=d.get("stacks") or None,
        meta=d.get("meta") or None,
    )


def build_item_json(form: dict) -> dict:
    """Форма билдера -> JSON предмета {name, description, effects:[...]}.

    form.effects может содержать объекты Effect (dataclass), dict-формы или
    уже готовые JSON-эффекты каталога (распознаются по наличию ops с kind).
    """
    effects = []
    for ef in form.get("effects", []):
        if isinstance(ef, Effect):
            effects.append(ef.to_json())
            continue
        if isinstance(ef, dict) and _looks_like_json_effect(ef):
            effects.append(json.loads(json.dumps(ef)))  # deep copy
        else:
            effects.append(effect_from_form(ef).to_json())
    item = {"name": form.get("name", ""), "description": form.get("description", "")}
    item["effects"] = effects
    return item


def _looks_like_json_effect(d: dict) -> bool:
    """Эффект уже в JSON-форме схемы (например, шаблон каталога to_json()).

    Признак — есть `trigger` (в UI-форме триггер тоже есть, но ops у формы
    не содержат готовых schema-ключей 'value' c flat/pct одновременно с
    пустыми строками; надёжнее всего смотреть на то, что все ops имеют
    'kind' и значения в формате Value.to_json, а ключи формы ('stat'/'' )
    отсутствуют как пустые строки).
    """
    if "ops" not in d or "id" not in d or "trigger" not in d:
        return False
    if not isinstance(d["ops"], list) or not d["ops"]:
        return False
    for o in d["ops"]:
        if not isinstance(o, dict) or "kind" not in o:
            return False
        # UI-форма никогда не присылает заполненный scale.value без scale.every
        if "scale" in o and isinstance(o["scale"], dict):
            if "every" not in o["scale"]:
                return False
        # форма хранит пустые поля как '' (stat/op), схема их вообще не имеет
        if o.get("stat", None) == "" or o.get("op", None) == "":
            return False
        # то же рекурсивно для fail-веток
        for f in o.get("fail") or []:
            if not isinstance(f, dict) or "kind" not in f:
                return False
            if f.get("stat", None) == "" or f.get("op", None) == "":
                return False
    return True


# ---------------------------------------------------------------- pipeline

def validate(item: dict) -> list[str]:
    return validate_item(item)


def to_lua(item: dict) -> str:
    return render_item({"name": item.get("name", ""),
                        "description": item.get("description", "")},
                       item["effects"])


def lua_load(lua_text: str) -> dict:
    """Загрузка Lua через lupa (syntax-check + round-trip в python-таблицу)."""
    import lupa
    rt = lupa.LuaRuntime()
    tbl = rt.execute(lua_text)                       # `return {...}`
    py = _lua_to_py(rt, tbl)
    # sanity: собственный парсер должен дать тот же набор id/ops
    parsed = parse_lua(lua_text)
    assert [e.get("id") for e in parsed.get("effects", [])] == \
           [e.get("id") for e in py.get("effects", [])], "parser/lupa mismatch"
    return py


def _is_lua_table(obj) -> bool:
    return hasattr(obj, "keys") and callable(getattr(obj, "keys", None))


def _lua_to_py(rt, obj):
    if _is_lua_table(obj):
        keys = list(obj.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [_lua_to_py(rt, obj[k]) for k in sorted(keys)]
        return {str(k): _lua_to_py(rt, obj[k]) for k in keys}
    if isinstance(obj, bytes):
        return obj.decode("utf-8")
    return obj


def run_training_room(item: dict, scenario: Optional[dict] = None) -> dict:
    """Прогнать предмет в тренировочной комнате (sim.EffectRuntime).

    scenario: {hero_hp, hero_max_hp, dummy_max_hp, base_stats, events[]}
      - "use"            — использовать предмет
      - "attack"         — полный цикл атаки героя (attack -> dmg -> attack_hit
                           -> kill), урон = base_damage (или attack_damage-стат)
      - "enemy_attack N" — враг бьёт героя на N (take_damage +Possible die)
      - "kill"           — убить текущего манекена и возродить нового
      - "tick T DT"      — тик времени
      - "die" / прочие   — прямое fire_event
    Возвращает отчёт: шаги событий + финальное состояние героя/манекена.
    """
    sc = {"hero_max_hp": 1000.0, "dummy_max_hp": 5000.0, "hero_hp": None,
          "base_stats": {}, "events": ["use", "attack"], "base_damage": 0.0}
    sc.update(scenario or {})
    hero = Unit("hero", max_hp=sc["hero_max_hp"], **sc["base_stats"])
    dummy = Unit("mannequin", max_hp=sc["dummy_max_hp"])
    rt = EffectRuntime(hero, item["effects"], enemy=dummy)
    if sc["hero_hp"] is not None:
        hero.current_hp = float(sc["hero_hp"])
    rt.refresh_passives()
    steps = []
    t = 0.0
    for ev in sc["events"]:
        label = str(ev)
        parts = label.split()
        kind = parts[0]
        if kind == "attack":
            rt.attack(t, base_damage=float(parts[1]) if len(parts) > 1
                      else sc["base_damage"])
        elif kind == "enemy_attack" and len(parts) > 1:
            rt.receive_damage(float(parts[1]), t)
        elif kind == "kill":
            # убить и возродить манекен (для стеков типа Vampire's Fang)
            dummy.deal_damage(dummy.current_hp)
            rt.fire_event("kill", t)
            dummy = Unit("mannequin", max_hp=sc["dummy_max_hp"])
            rt.enemy = dummy
        elif kind == "set_dummy" and len(parts) > 1:
            # установить HP текущего манекена (для execute-сценариев)
            dummy.current_hp = float(parts[1])
            dummy.alive = dummy.current_hp > 0
        elif kind == "tick" and len(parts) > 2:
            t += float(parts[1])
            rt.tick(t, float(parts[2]))
        else:
            rt.fire_event(label, t)
        steps.append({"event": label, "t": round(t, 3),
                      "hero_hp": round(hero.current_hp, 3),
                      "hero_alive": hero.alive,
                      "dummy_hp": round(dummy.current_hp, 3),
                      "kills": hero.kills})
    from .sim import summarize
    return {"steps": steps, "summary": summarize(rt), "log": list(rt.log)}


def full_cycle(form: dict, scenario: Optional[dict] = None,
               with_lupa: bool = True) -> dict:
    """Весь UI-цикл: форма -> JSON -> validate -> Lua -> lupa -> sim."""
    item = build_item_json(form)
    errs = validate(item)
    out: dict[str, Any] = {"item": item, "errors": errs}
    if errs:
        return out
    out["lua"] = to_lua(item)
    if with_lupa:
        try:
            out["lupa_ok"] = True
            lua_load(out["lua"])
        except ImportError:
            out["lupa_ok"] = None
    out["room"] = run_training_room(item, scenario)
    return out
