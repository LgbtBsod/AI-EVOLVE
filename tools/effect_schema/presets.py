"""
Фабрики-хелперы: одна строка на эффект/операцию.

    from tools.effect_schema.presets import *

    heal_potion = Effect("health_potion", event("use"), [
        op.heal("self", "hp", flat=40),
    ])

    berserk_mod = mod("self", "crit_chance", add, pct=5,
                      scale=every(10, "hp_missing_below_40", pct=5))
"""

from __future__ import annotations

from .schema import Effect, Op, Value, Scale, Trigger


# ------------------------------------------------------- values

def flat(v):
    return Value(flat=v)


def pct(v, of=None):
    return Value(pct=v, of=of)


def ref(path):
    return Value(ref=path)


def every(step, of, value=None, factor=1.0, cap=None, floor=None):
    """Scale descriptor: за каждые `step` единиц ctx[of] добавить `value`."""
    return Scale(every=step, of=of, value=value, factor=factor, cap=cap, floor=floor)


# ------------------------------------------------------- triggers

def passive():
    return Trigger(kind="passive")


def condition(when):
    return Trigger(kind="condition", when=when)


def on(event, *, filter=None, owner_has=None):
    return Trigger(kind="event", event=event, filter=filter, owner_has=owner_has)


# ------------------------------------------------------- ops

class op:
    """Пространство имён конструкторов операций (op.mod(...), op.heal(...))."""

    @staticmethod
    def _make(kind, target="self", stat=None, o=None, value=None, scale=None,
              **kw):
        if isinstance(value, Value):
            pass
        elif isinstance(value, (int, float)):
            value = Value(flat=value)
        return Op(kind=kind, target=target, stat=stat, op=o, value=value,
                  scale=scale, **kw)

    @staticmethod
    def mod(target, stat, o="add", value=None, scale=None, **kw):
        return op._make("mod", target, stat, o, value, scale, **kw)

    @staticmethod
    def heal(target="self", stat="hp", value=None, scale=None, **kw):
        return op._make("heal", target, stat, "add", value, scale, **kw)

    @staticmethod
    def drain(target, stat, value=None, scale=None, fail=None, **kw):
        kw.setdefault("op", None)
        o = op._make("drain", target, stat, "sub", value, scale, **kw)
        o.fail = fail or []
        return o

    @staticmethod
    def deal(target="enemy", stat="hp", value=None, scale=None, **kw):
        return op._make("deal", target, stat, "sub", value, scale, **kw)

    @staticmethod
    def set_(target, stat, value, **kw):
        return op._make("set", target, stat, "set", value, None, **kw)

    @staticmethod
    def buff(buff_id, target="self", duration=None, cooldown=None, extend=None,
             **kw):
        return Op(kind="buff", target=target, buff_id=buff_id,
                  duration=duration, cooldown=cooldown, extend=extend, **kw)

    @staticmethod
    def extend_buff(buff_id, target="self", on="kill", flat_=None, pct_=None, **kw):
        ext = {"on": on}
        if flat_ is not None:
            ext["flat"] = flat_
        if pct_ is not None:
            ext["pct"] = pct_
        return Op(kind="extend", target=target, buff_id=buff_id, extend=ext, **kw)

    @staticmethod
    def remove_buff(buff_id, target="self", **kw):
        return Op(kind="remove_buff", target=target, buff_id=buff_id, **kw)

    @staticmethod
    def apply_effect(effect_id, target="self", **kw):
        return Op(kind="apply_effect", target=target, buff_id=effect_id, **kw)

    @staticmethod
    def kill(target="enemy", **kw):
        return Op(kind="kill", target=target, **kw)


# alias, чтобы `set` не конфликтовал
setv = op.set_
