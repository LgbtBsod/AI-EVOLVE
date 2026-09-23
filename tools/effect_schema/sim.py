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

Предикаты: БЕЗОПАСНЫЙ мини-язык выражений (никакого eval!). Поддерживается
грамматика: сравнения (< <= > >= == !=) над ctx.<поле>, числовыми литералами,
скобками, + - * / и константами max/min(...). Именованные предикаты берутся
из реестра PREDICATES. Любое иное выражение отвергается PrediciationException
(ранее здесь был сырой eval, допускавший sandbox-escape через
dunder-атрибуты, например "max.__class__.__subclasses__").
"""

from __future__ import annotations

import ast
import math
import operator as _op
import re
from typing import Any, Callable, Optional

# ---------------------------------------------------------------- predicates

def _hp_missing_below_40(ctx) -> float:
    """Псевдо-стат: сколько % HP не хватает ПОРОГУ 40% (0..40)."""
    return max(0.0, 40.0 - ctx.get("hp_pct", 100.0))


PREDICATES: dict[str, Callable[[dict], bool]] = {
    "low_hp_40": lambda ctx: ctx.get("hp_pct", 100.0) < 40,
}

_ALLOWED_CTX: dict[str, Callable[[dict], float]] = {
    "hp_missing_below_40": _hp_missing_below_40,
}

_EXPR_RE = re.compile(r"^ctx\.(\w+)\s*(<=|>=|<|>|==|!=)\s*([\d.]+)$")


class PrediciationException(ValueError):
    """Выражение-предикат не проходит строгую whitelist-грамматику."""


# ---- безопасный AST-интерпретатор выражений предикатов -------------------

_BINOPS = {ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
           ast.Div: _op.truediv, ast.Mod: _op.mod, ast.Pow: _op.pow}
_CMPOPS = {ast.Lt: _op.lt, ast.LtE: _op.le, ast.Gt: _op.gt,
           ast.GtE: _op.ge, ast.Eq: _op.eq, ast.NotEq: _op.ne}
_FUNCS = {"max": max, "min": min, "floor": math.floor, "ceil": math.ceil,
          "abs": abs}


def _ast_eval(node, ctx: dict):
    if isinstance(node, ast.Expression):
        return _ast_eval(node.body, ctx)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise PrediciationException(f"literal {node.value!r} not allowed")
    if isinstance(node, ast.Name):
        if node.id in _FUNCS:
            return _FUNCS[node.id]
        raise PrediciationException(f"unknown name {node.id!r} "
                                    "(only ctx.<field> and max/min/floor/ceil/abs)")
    if isinstance(node, ast.Attribute):
        # разрешено ТОЛЬКО ctx.<известное поле>; никаких dunder-атрибутов
        if not isinstance(node.value, ast.Name) or node.value.id != "ctx":
            raise PrediciationException("attribute access must be ctx.<field>")
        key = node.attr
        if key.startswith("_"):
            raise PrediciationException(f"private attribute {key!r} forbidden")
        if key in ctx:
            return ctx[key]
        if key in _ALLOWED_CTX:
            return _ALLOWED_CTX[key](ctx)
        raise PrediciationException(f"unknown ctx field {key!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_ast_eval(node.left, ctx),
                                      _ast_eval(node.right, ctx))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _ast_eval(node.operand, ctx)
        return v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.Compare):
        left = _ast_eval(node.left, ctx)
        for c_op, comp in zip(node.ops, node.comparators):
            if type(c_op) not in _CMPOPS:
                raise PrediciationException("comparison operator not allowed")
            right = _ast_eval(comp, ctx)
            if not _CMPOPS[type(c_op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = [_ast_eval(v, ctx) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        return any(vals)
    if isinstance(node, ast.Call):
        fn = node.func
        # вызов разрешён только простому имени из whitelist (max/min/...);
        # ctx.foo(...) и (obj).__class__(...) — запрещены
        if not isinstance(fn, ast.Name) or fn.id not in _FUNCS:
            raise PrediciationException("call of non-whitelisted function")
        return _FUNCS[fn.id](*[_ast_eval(a, ctx) for a in node.args])
    raise PrediciationException(f"expression element not allowed: "
                                f"{type(node).__name__}")


_AST_CACHE: dict[str, ast.Expression] = {}


def _compile_pred(expr: str) -> ast.Expression:
    cached = _AST_CACHE.get(expr)
    if cached is not None:
        return cached
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise PrediciationException(f"invalid predicate expression {expr!r}: {e}") from e
    _AST_CACHE[expr] = tree
    return tree


def eval_pred(pred: Optional[Any], ctx: dict) -> bool:
    """Вычислить предикат (строка-выражение / имя из PREDICATES / callable)."""
    if not pred:
        return True
    if callable(pred):
        return bool(pred(ctx))
    pred = str(pred).strip()
    if pred in PREDICATES:
        return bool(PREDICATES[pred](ctx))
    m = _EXPR_RE.match(pred)
    if m:  # быстрый путь для канонической формы "ctx.x OP num"
        key, op_, rhs = m.group(1), m.group(2), float(m.group(3))
        left = ctx.get(key)
        if left is None and key in _ALLOWED_CTX:
            left = _ALLOWED_CTX[key](ctx)
        if left is None:
            raise KeyError(f"ctx.{key} not found for predicate {pred!r}")
        return {
            "<": _op.lt, ">": _op.gt, "<=": _op.le,
            ">=": _op.ge, "==": _op.eq, "!=": _op.ne,
        }[op_](left, rhs)
    # общий случай: whitelist AST (без eval!)
    return bool(_ast_eval(_compile_pred(pred), ctx))


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
        # только dict-навигация по whitelist-полям (без getattr — см. аудит:
        # getattr допускал обход вида "__class__.__subclasses__")
        cur: Any = ctx
        for part in path.split("."):
            if not isinstance(cur, dict):
                raise KeyError(f"ref {v['ref']!r}: cannot descend into {type(cur).__name__}")
            cur = _ctx_get(cur, part)
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
        self._ev_depth = 0          # ре-ентранс fire_event (attack -> attack_hit ...)

    # public API ------------------------------------------------------------
    def target_ctx(self, prefix: str, t: Optional[Unit]) -> dict:
        """Контекст цели с префиксом: enemy_hp_pct, ally_hp и т.д."""
        if t is None:
            return {}
        c = t.ctx()
        return {f"{prefix}_{k}": v for k, v in c.items()}

    def refresh_passives(self, t: float = 0.0):
        """Пересчитать все passive/condition моды (сброс -> повторный应用)."""
        self.owner.mods.clear()
        ctx = {**self.owner.ctx(),
               **self.target_ctx("enemy", self.enemy)}
        for ef in self.effects:
            tr = ef.get("trigger", {})
            kind = tr.get("kind")
            if kind not in ("passive", "condition"):
                continue
            if kind == "condition" and not eval_pred(tr.get("when"), ctx):
                continue
            if not self._owner_has_ok(tr, t):
                continue
            for o in ef.get("ops", []):
                if o.get("kind") == "mod":
                    self._apply_mod(o)

    def attack(self, t: float = 0.0, base_damage: Optional[float] = None):
        """Боевой цикл героя: attack -> (execute-ops) -> базовый урон по врагу
        -> attack_hit (лifesteal-эффекты)."""
        if not self.owner.alive or self.enemy is None or not self.enemy.alive:
            return
        self.fire_event("attack", t)
        if self.enemy is None or not self.enemy.alive:
            return  # execute (judgement) уже сработал
        dmg = base_damage if base_damage is not None else self.owner._eff("attack_damage")
        if dmg > 0:
            self.enemy.deal_damage(dmg)
            self.log.append(f"t={t:.1f} hero basic attack {dmg:.1f} "
                            f"-> {self.enemy.name} hp={self.enemy.current_hp:.1f}")
        killed = not self.enemy.alive
        self.fire_event("attack_hit", t)
        if killed and self.enemy is not None and not self.enemy.alive:
            self.owner.kills += 1
            self.log.append(f"t={t:.1f} KILL {self.enemy.name}")
            self.fire_event("kill", t)

    def receive_damage(self, amount: float, t: float = 0.0):
        """Враг бьёт героя; после урона — событие take_damage (retaliation)."""
        if not self.owner.alive:
            return
        self.owner.deal_damage(amount)
        self.log.append(f"t={t:.1f} {self.owner.name} takes {amount:.1f} "
                        f"hp={self.owner.current_hp:.1f}")
        died = not self.owner.alive
        self.fire_event("take_damage", t)
        if died and not self.owner.alive:
            self.fire_event("die", t)

    def fire_event(self, event: str, t: float = 0.0, extra: Optional[dict] = None):
        ctx = {**self.owner.ctx(extra),
               **self.target_ctx("enemy", self.enemy)}
        for ef in self.effects:
            tr = ef.get("trigger", {})
            if tr.get("kind") != "event" or tr.get("event") != event:
                continue
            if not self._owner_has_ok(tr, t):
                continue
            if tr.get("filter") and not eval_pred(tr["filter"], ctx):
                continue
            self.run_ops(ef.get("ops", []), ctx, t, f"{ef['id']}#{event}",
                         event=event)
        # каскад: attack порождает attack_hit только через attack();
        # здесь — ре-ентрансные события из ops (например kill внутри fail-ветки)

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
    def run_ops(self, ops: list[dict], ctx: dict, t: float, src: str,
                event: Optional[str] = None):
        for o in ops:
            self.run_op(o, ctx, t, src, event=event)

    def run_op(self, o: dict, ctx: dict, t: float, src: str,
               event: Optional[str] = None):
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
                self.run_ops(o.get("fail", []), ctx, t, src + ".fail", event=event)
            else:
                target.current_hp -= cost
                self.log.append(f"t={t:.1f} {src} drain {cost:.2f} -> hp={target.current_hp:.1f}")
        elif kind == "buff":
            bid = o.get("buff_id")
            prev = target.buffs.get(bid)
            # кулдаун на повторную активацию щита/баффа
            cd = resolve_value(o.get("cooldown"), ctx) if o.get("cooldown") else None
            if cd is not None and prev is not None and \
                    t - prev.get("last_cd", -1e18) < cd:
                self.log.append(f"t={t:.1f} {src} buff {bid} ON COOLDOWN")
                return
            dur = self._duration(o.get("duration"), ctx)
            until = max(prev.get("until", t) if prev else t, t) + dur
            target.buffs[bid] = {"until": until, "extend": o.get("extend"),
                                 "cooldown": cd, "last_cd": t}
            self.log.append(f"t={t:.1f} {src} buff {bid} +{dur:.1f}s (until {until:.1f})")
            # декларация extend внутри ops-buff: срабатывает при событии ext["on"]
            ext = o.get("extend") or {}
            if ext and event and event == ext.get("on"):
                self._extend_buff(target, bid, ext, ctx, t, src)
        elif kind == "extend":
            bid = o.get("buff_id")
            b = target.buffs.get(bid)
            if b:
                ext = o.get("extend") or b.get("extend") or {}
                ev = event
                if ev is None and "#" in src:
                    # fallback: событие зашито в src вида "effect#event(.fail)"
                    ev = src.rsplit("#", 1)[-1].split(".", 1)[0]
                # фильтр по событию: extend срабатывает только на ext["on"]
                if ext.get("on") and ev != ext.get("on"):
                    self.log.append(
                        f"t={t:.1f} {src} extend {bid}: on={ext['on']} "
                        f"!= event={ev!r} -> skip")
                    return
                self._extend_buff(target, bid, ext, ctx, t, src, buff_obj=b)
        elif kind == "remove_buff":
            target.buffs.pop(o.get("buff_id"), None)
            self.log.append(f"t={t:.1f} {src} remove_buff {o.get('buff_id')}")
        elif kind == "apply_effect":
            eid = o.get("buff_id")  # apply_effect использует buff_id как effect id
            ef = next((e for e in self.effects if e.get("id") == eid), None)
            if ef:
                self.run_ops(ef.get("ops", []), ctx, t, f"{src}->{eid}")
        elif kind == "kill":
            was_alive = target.alive and target.current_hp > 0
            target.deal_damage(target.current_hp, log=self._dmg_log(target))
            if was_alive:
                if target is self.owner:
                    self.log.append(f"t={t:.1f} {src} KILL {target.name} (self!)"
                                    " -- revive/set-hp ops must follow")
                else:
                    self.owner.kills += 1
                    self.log.append(f"t={t:.1f} {src} KILL {target.name}")
                    # каскад событий: die у жертвы / kill у владельца
                    if target is self.enemy:
                        self.fire_event("kill", t)
                    elif target is self.owner:
                        self.fire_event("die", t)

    # helpers -----------------------------------------------------------------
    def _extend_buff(self, target, bid: str, ext: dict, ctx: dict,
                     t: float, src: str, buff_obj=None):
        """Продлить бафф `bid` по extend-правилу {on, flat|pct}."""
        b = buff_obj if buff_obj is not None else target.buffs.get(bid)
        if b is None:
            return
        add = resolve_value(
            {"flat": ext["flat"]} if ext.get("flat") is not None
            else {"pct": ext.get("pct"), "of": ext.get("of", "max_hp")}
            if ext.get("pct") is not None else {}, ctx)
        b["until"] += add
        self.log.append(f"t={t:.1f} {src} extend {bid} +{add:.1f}s")

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
