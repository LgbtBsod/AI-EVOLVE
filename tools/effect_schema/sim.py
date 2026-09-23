"""
Effect Schema v1 -- reference runtime (Python)

Эталонный интерпретатор схемы Effect -> Ops[] для тестов в тренировочной
комнате. Семантика 1-в-1 совпадает с lua_gen/render:

    value = flat | pct/100 * ctx[of or stat] | ref(ctx.path)
    total = value + floor(ctx[scale.of]/scale.every) * scale.value * factor
            (steps ограничены cap/floor)

Поддерживаемые триггеры: passive(mod-модификаторы), condition(то же, пока
условие true), event(use/attack/kill/tick). Поддерживаемые ops:
mod/heal/drain/deal/set/buff/extend/remove_buff/apply_effect/kill.

Предикаты: строковые выражения вида "ctx.hp_pct < 40" вычисляются через
безопасный eval над ctx; именованные -- через реестр unit.PREDICATES.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

# ---------------------------------------------------------------- predicates

def _hp_missing_below_40(ctx) -> float:
    """Псевдо-стат: сколько % HP не хватает ПОРОГУ 40% (0..40)."""
    return max(0.0, 40.0 - ctx.get("hp_pct", 100.0))


PREDICATES = {
    "low_hp_40": lambda ctx: ctx.get("hp_pct", 100.0) < 40,
}

_EXPR_RE = re.compile(r"^ctx\.(\w+)\s*(<=|>=|<|>|==|!=)\s*([\d.]+)$")

_ALLOWED_CTX = {"hp_missing_below_40": _hp_missing_below_40}


def eval_pred(pred: Optional[str], ctx: dict) -> bool:
    if not pred:
        return True
    if callable(pred):
        return bool(pred(ctx))
    m = _EXPR_RE.match(pred.strip())
    if m:
        key, op_, rhs = m.group(1), m.group(2), float(m.group(3))
        left = ctx.get(key)
        if left is None and key in _ALLOWED_CTX:
            left = _ALLOWED_CTX[key](ctx)
        if left is None:
            raise KeyError(f"ctx.{key} not found for predicate {pred!r}")
        return {
            "<": lambda a, b: a < b, ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
            "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
        }[op_](left, rhs)
    # свободное python-выражение над ctx (для генератора/редактора)
    env = dict(_ALLOWED_CTX)
    env["ctx"] = _CtxProxy(ctx)
    env["max"] = max
    env["min"] = min
    return bool(eval(pred, {"__builtins__": {}}, env))  # noqa: S307


class _CtxProxy(dict):
    def __getattr__(self, k):
        try:
            v = self[k]
        except KeyError:
            if k in _ALLOWED_CTX:
                return _ALLOWED_CTX[k](self)
            raise
        return v


# ---------------------------------------------------------------- values

def resolve_value(v: dict, ctx: dict, default_stat: Optional[str] = None) -> float:
    if v is None:
        return 0.0
    if "flat" in v and v["flat"] is not None:
        return float(v["flat"])
    if "pct" in v and v["pct"] is not None:
        of = v.get("of") or default_stat
        base = _ctx_get(ctx, of)
        return float(v["pct"]) / 100.0 * base
    if "ref" in v and v["ref"]:
        path = v["ref"]
        if path.startswith("ctx."):
            path = path[4:]
        cur: Any = ctx
        for part in path.split("."):
            cur = _ctx_get(cur if isinstance(cur, dict) else {}, part) \
                if isinstance(cur, dict) else getattr(cur, part)
        return float(cur)
    return 0.0


def _ctx_get(ctx: dict, key: Optional[str]) -> float:
    if key is None:
        return 0.0
    if key in ctx:
        return float(ctx[key])
    if key in _ALLOWED_CTX:
        return float(_ALLOWED_CTX[key](ctx))
    raise KeyError(f"unknown ctx field {key!r}")


def compute_amount(op: dict, ctx: dict) -> float:
    """Итог: base + floor(steps)*value*factor, steps из scale."""
    total = resolve_value(op.get("value"), ctx, op.get("stat"))
    s = op.get("scale")
    if s:
        steps = _ctx_get(ctx, s["of"]) / float(s["every"])
        steps = math.floor(steps)
        if s.get("cap") is not None:
            steps = min(steps, float(s["cap"]))
        if s.get("floor") is not None:
            steps = max(steps, float(s["floor"]))
        total += steps * resolve_value(s.get("value"), ctx, op.get("stat")) \
                 * float(s.get("factor", 1.0))
    return total


# ---------------------------------------------------------------- unit

class Unit:
    """Юнит тренировки: статы + контекст для резолва значений."""

    def __init__(self, name: str, max_hp: float = 1000.0, **stats):
        self.name = name
        self.base: dict[str, float] = {"max_hp": max_hp, "strength": 0.0,
                                       "stamina": 0.0, "crit_chance": 0.0,
                                       "crit_dmg": 50.0, "aspd": 1.0,
                                       "hp_regen": 0.0, "lifesteal": 0.0,
                                       "defense": 0.0}
        self.mods: dict[str, float] = {}          # mod-эффекты (add/sub/mul/div)
        self.current_hp = max_hp
        self.buffs: dict[str, dict] = {}          # buff_id -> {until, ...}
        self.alive = True
        self.kills = 0
        self.base.update({k: float(v) for k, v in stats.items()})

    # effective stats -----------------------------------------------------
    def stat(self, key: str) -> float:
        if key == "hp":
            return self.current_hp
        if key == "max_hp":
            return self._eff("max_hp")
        if key == "hp_pct":
            return self.current_hp / self._eff("max_hp") * 100.0
        return self._eff(key)

    def _eff(self, key: str) -> float:
        v = self.base.get(key, 0.0) + self.mods.get(key, 0.0)
        return v

    def ctx(self, extra: Optional[dict] = None) -> dict:
        c = {
            "hp": self.current_hp, "max_hp": self._eff("max_hp"),
            "hp_pct": self.stat("hp_pct"),
            "hp_missing": self._eff("max_hp") - self.current_hp,
            "strength": self._eff("strength"), "stamina": self._eff("stamina"),
            "crit_chance": self._eff("crit_chance"),
            "crit_dmg": self._eff("crit_dmg"), "aspd": self._eff("aspd"),
            "hp_regen": self._eff("hp_regen"), "lifesteal": self._eff("lifesteal"),
            "defense": self._eff("defense"), "kills": float(self.kills),
        }
        c["hp_missing_below_40"] = _hp_missing_below_40(c)
        if extra:
            c.update(extra)
        return c

    # damage/heal ----------------------------------------------------------
    def deal_damage(self, amount: float, log=None):
        self.current_hp = max(0.0, self.current_hp - amount)
        if log is not None:
            log.append(amount)
        if self.current_hp <= 0:
            self.alive = False

    def heal(self, amount: float):
        self.current_hp = min(self._eff("max_hp"), self.current_hp + amount)


# ---------------------------------------------------------------- runtime

class EffectRuntime:
    """Прогон эффектов схемы по юниту. Логирует каждое действие (для теста)."""

    def __init__(self, owner: Unit, effects: list[dict], enemy: Optional[Unit] = None):
        self.owner = owner
        self.enemy = enemy
        self.effects = effects
        self.log: list[str] = []
        self.active_mod_sources: set[str] = set()

    # public API ------------------------------------------------------------
    def refresh_passives(self, t: float = 0.0):
        """Пересчитать все passive/condition моды (сброс -> повторный应用)."""
        self.owner.mods.clear()
        for ef in self.effects:
            tr = ef.get("trigger", {})
            kind = tr.get("kind")
            if kind not in ("passive", "condition"):
                continue
            if kind == "condition" and not eval_pred(tr.get("when"), self.owner.ctx()):
                continue
            if not self._owner_has_ok(tr, t):
                continue
            for o in ef.get("ops", []):
                if o.get("kind") == "mod":
                    self._apply_mod(o)

    def fire_event(self, event: str, t: float = 0.0, extra: Optional[dict] = None):
        ctx = self.owner.ctx(extra)
        for ef in self.effects:
            tr = ef.get("trigger", {})
            if tr.get("kind") != "event" or tr.get("event") != event:
                continue
            if not self._owner_has_ok(tr, t):
                continue
            if tr.get("filter") and not eval_pred(tr["filter"], ctx):
                continue
            self.run_ops(ef.get("ops", []), ctx, t, f"{ef['id']}#{event}")

    def tick(self, t: float, dt: float):
        """regen + duration-истечение баффов + tick-события."""
        self.refresh_passives(t)
        regen = self.owner._eff("hp_regen")
        if regen:
            self.owner.heal(regen * dt)
        expired = [b for b, d in self.owner.buffs.items() if d.get("until", 1e18) <= t]
        for b in expired:
            self.owner.buffs.pop(b)
            self.log.append(f"t={t:.1f} buff_expired {b}")
        self.fire_event("tick", t)

    # ops -------------------------------------------------------------------
    def run_ops(self, ops: list[dict], ctx: dict, t: float, src: str):
        for o in ops:
            self.run_op(o, ctx, t, src)

    def run_op(self, o: dict, ctx: dict, t: float, src: str):
        kind = o.get("kind")
        if o.get("when") and not eval_pred(o["when"], ctx):
            return
        target = self._resolve_target(o.get("target", "self"))
        if target is None:
            return
        amount = compute_amount(o, ctx)

        if kind == "mod":
            self._apply_mod(o, ctx)
        elif kind == "heal":
            target.heal(amount)
            self.log.append(f"t={t:.1f} {src} heal {amount:.2f} -> hp={target.current_hp:.1f}")
        elif kind == "deal":
            target.deal_damage(amount, log=self._dmg_log(target))
            self.log.append(f"t={t:.1f} {src} deal {amount:.2f} -> {target.name} hp={target.current_hp:.1f}")
        elif kind == "set":
            if o.get("stat") == "hp":
                target.current_hp = min(amount, target._eff("max_hp"))
                target.alive = target.current_hp > 0
                self.log.append(f"t={t:.1f} {src} set hp={amount:.1f}")
        elif kind == "drain":
            cost = amount
            if cost > target.current_hp:
                self.log.append(f"t={t:.1f} {src} drain FAIL (cost {cost:.2f} > hp {target.current_hp:.1f})")
                self.run_ops(o.get("fail", []), ctx, t, src + ".fail")
            else:
                target.current_hp -= cost
                self.log.append(f"t={t:.1f} {src} drain {cost:.2f} -> hp={target.current_hp:.1f}")
        elif kind == "buff":
            bid = o.get("buff_id")
            dur = self._duration(o.get("duration"), ctx)
            cd = resolve_value(o.get("cooldown"), ctx) if o.get("cooldown") else None
            prev = target.buffs.get(bid)
            until = max(prev.get("until", t) if prev else t, t) + dur
            target.buffs[bid] = {"until": until, "extend": o.get("extend"),
                                 "cooldown": cd, "last_cd": t}
            self.log.append(f"t={t:.1f} {src} buff {bid} +{dur:.1f}s (until {until:.1f})")
        elif kind == "extend":
            bid = o.get("buff_id")
            b = target.buffs.get(bid)
            if b:
                ext = o.get("extend", {})
                add = resolve_value({"flat": ext.get("flat")} if ext.get("flat") is not None
                                    else {"pct": ext.get("pct"), "of": "max_hp"}
                                    if ext.get("pct") is not None else {}, ctx)
                b["until"] += add
                self.log.append(f"t={t:.1f} {src} extend {bid} +{add:.1f}s")
        elif kind == "remove_buff":
            target.buffs.pop(o.get("buff_id"), None)
            self.log.append(f"t={t:.1f} {src} remove_buff {o.get('buff_id')}")
        elif kind == "apply_effect":
            eid = o.get("buff_id")  # apply_effect использует buff_id как effect id
            ef = next((e for e in self.effects if e.get("id") == eid), None)
            if ef:
                self.run_ops(ef.get("ops", []), ctx, t, f"{src}->{eid}")
        elif kind == "kill":
            target.deal_damage(target.current_hp, log=self._dmg_log(target))
            self.owner.kills += 1
            self.log.append(f"t={t:.1f} {src} KILL {target.name}")

    # helpers -----------------------------------------------------------------
    def _apply_mod(self, o: dict, ctx: Optional[dict] = None):
        if ctx is None:
            ctx = self.owner.ctx()
        stat = o.get("stat")
        amount = compute_amount(o, ctx)
        mo = o.get("op", "add")
        cur = self.owner.mods.get(stat, 0.0)
        base = self.owner.base.get(stat, 0.0)
        if mo == "add":
            self.owner.mods[stat] = cur + amount
        elif mo == "sub":
            self.owner.mods[stat] = cur - amount
        elif mo == "mul":
            self.owner.mods[stat] = (base + cur) * amount - base
        elif mo == "div":
            self.owner.mods[stat] = (base + cur) / amount - base if amount else cur
        elif mo == "set":
            self.owner.mods[stat] = amount - base
        elif mo == "min":
            self.owner.mods[stat] = min(base + cur, amount) - base
        elif mo == "max":
            self.owner.mods[stat] = max(base + cur, amount) - base

    def _duration(self, d, ctx) -> float:
        if d is None:
            return 10.0
        if isinstance(d, (int, float)):
            return float(d)
        if "base" in d or "flat" in d or "pct" in d:
            base = resolve_value({"flat": d.get("base", d.get("flat")),
                                  "pct": d.get("pct"), "of": d.get("of")}, ctx)
            s = d.get("scale")
            if s:
                steps = math.floor(_ctx_get(ctx, s["of"]) / float(s["every"]))
                if s.get("cap") is not None:
                    steps = min(steps, s["cap"])
                base += steps * float(s.get("value", {}).get("flat", 0)) \
                        * float(s.get("factor", 1.0))
            return base
        return resolve_value(d, ctx)

    def _resolve_target(self, name):
        if name == "self":
            return self.owner
        if name in ("enemy", "source"):
            return self.enemy
        return self.owner  # allies/allies->self в одиночном тесте

    def _owner_has_ok(self, tr: dict, t: float) -> bool:
        oh = tr.get("owner_has")
        if not oh:
            return True
        # sub-effect активен, пока родительский эффект активен (condition/passive)
        parent = next((e for e in self.effects if e.get("id") == oh), None)
        if parent is None:
            return False
        ptr = parent.get("trigger", {})
        if ptr.get("kind") == "condition":
            return eval_pred(ptr.get("when"), self.owner.ctx())
        return True

    def _dmg_log(self, target):
        return None  # урон уже логируется в deal/kill


def summarize(rt: EffectRuntime) -> dict:
    o = rt.owner
    return {
        "unit": o.name,
        "hp": round(o.current_hp, 2),
        "max_hp": round(o.stat("max_hp"), 2),
        "hp_pct": round(o.stat("hp_pct"), 2),
        "mods": {k: round(v, 3) for k, v in o.mods.items() if abs(v) > 1e-9},
        "buffs": {b: round(d["until"], 1) for b, d in o.buffs.items()},
        "kills": o.kills,
    }
