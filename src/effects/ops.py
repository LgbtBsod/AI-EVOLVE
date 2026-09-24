"""Effect Schema v1 -- the ONE op interpreter (semantics table: docs/EFFECT_SCHEMA.md, "Op handlers").

Every op kind of the schema has exactly one small handler in `OP_HANDLERS`. Handlers are written over

  * plain data: the op dict `o`, the context dict `ctx` of floats, numbers, strings;
  * an `OpHost`: the interpreter that owns the state the op mutates. `EffectRuntime` (runtime.py) hosts the
    isolated `Unit` (training room, item forge, tools/effect_schema); `EffectManager` (manager.py) hosts real
    game entities (`EntityState`). A host supplies ~20 tiny `op_*` primitives (read/spend/heal/set a resource,
    apply damage, buff table, nested ops, log line ...); the order of evaluation, the branching and the
    arithmetic live here, once.

No Panda3D / game / Lua imports on purpose: this module is the mechanical porting unit for the Rust effect
manager (data in -> data out; every host primitive becomes a trait method).

Value math (`resolve_value`, `compute_amount`, `apply_mod_math`, `extend_amount`) is pure: dict/float in, float out.
`Tracked` is the dirty-flag dict used by `Unit` / `EntityState` (any write bumps the owner's `version`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, NamedTuple, Optional, Protocol

# ---------------------------------------------------------------- dirty tracking


class Tracked(dict):
    """dict, который при ЛЮБОЙ записи поднимает `owner.version` (dirty-флаг кэшей владельца).

    Владелец обязан иметь метод `touch()`. Чтение и итерация - обычные, без накладных расходов."""

    __slots__ = ("_owner",)

    def __init__(self, owner, data=()):
        super().__init__(data)
        self._owner = owner

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._owner.touch()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._owner.touch()

    def __ior__(self, other):
        super().__ior__(other)
        self._owner.touch()
        return self

    def clear(self):
        super().clear()
        self._owner.touch()

    def pop(self, *args):
        try:
            return super().pop(*args)
        finally:
            self._owner.touch()

    def popitem(self):
        try:
            return super().popitem()
        finally:
            self._owner.touch()

    def setdefault(self, key, default=None):
        try:
            return super().setdefault(key, default)
        finally:
            self._owner.touch()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._owner.touch()


def same_map(a: dict, b: dict) -> bool:
    """Одинаковое содержимое, включая знак нуля (`==` считает 0.0 и -0.0 равными, а вывод float.hex - нет)."""
    if a != b:
        return False
    return all(math.copysign(1.0, v) == math.copysign(1.0, b[k]) for k, v in a.items() if v == 0)


# ---------------------------------------------------------------- values (pure)


def _hp_missing_below_40(ctx) -> float:
    """Псевдо-стат: сколько % HP не хватает ПОРОГУ 40% (0..40)."""
    return max(0.0, 40.0 - ctx.get("hp_pct", 100.0))


# вычисляемые поля контекста (нет в ctx -> считаются от него): имя -> функция
_ALLOWED_CTX: dict[str, Callable[[dict], float]] = {
    "hp_missing_below_40": _hp_missing_below_40,
}


def ctx_get(ctx: dict, key: Optional[str]) -> float:
    if key is None:
        return 0.0
    if key in ctx:
        return float(ctx[key])
    if key in _ALLOWED_CTX:
        return float(_ALLOWED_CTX[key](ctx))
    raise KeyError(f"unknown ctx field {key!r}")


def _ref_value(ref: str, ctx: dict) -> float:
    """{ref = "ctx.path"}: только dict-навигация по whitelist-полям (без getattr - см. аудит:
    getattr допускал обход вида "__class__.__subclasses__")."""
    path = ref[4:] if ref.startswith("ctx.") else ref
    cur: Any = ctx
    for part in path.split("."):
        if not isinstance(cur, dict):
            raise KeyError(f"ref {ref!r}: cannot descend into {type(cur).__name__}")
        cur = ctx_get(cur, part)
    return float(cur)


def resolve_value(v: Optional[dict], ctx: dict, default_stat: Optional[str] = None) -> float:
    """Value = flat | pct/100 * ctx[of or stat] | ref(ctx.path)."""
    if v is None:
        return 0.0
    if "flat" in v and v["flat"] is not None:
        return float(v["flat"])
    if "pct" in v and v["pct"] is not None:
        return float(v["pct"]) / 100.0 * ctx_get(ctx, v.get("of") or default_stat)
    if "ref" in v and v["ref"]:
        return _ref_value(v["ref"], ctx)
    return 0.0


def compute_amount(op: dict, ctx: dict, default_stat: Optional[str] = None) -> float:
    """Итог: base + floor(steps)*value*factor, steps из scale.
    default_stat: откуда брать pct без `of` (по умолчанию - стат операции у владельца;
    для цели-врага рантайм передаёт enemy_<стат>)."""
    default_stat = default_stat or op.get("stat")
    total = resolve_value(op.get("value"), ctx, default_stat)
    s = op.get("scale")
    if s:
        steps = ctx_get(ctx, s["of"]) / float(s["every"])
        steps = math.floor(steps)
        if s.get("cap") is not None:
            steps = min(steps, float(s["cap"]))
        if s.get("floor") is not None:
            steps = max(steps, float(s["floor"]))
        total += steps * resolve_value(s.get("value"), ctx, default_stat) \
            * float(s.get("factor", 1.0))
    return total


def default_stat_of(o: dict, prefix: str) -> Optional[str]:
    """pct без `of` - процент от того же стата ЦЕЛИ операции (у врага - enemy_<стат>)."""
    stat = o.get("stat")
    return stat and prefix + stat


def extend_amount(ext: dict, ctx: dict) -> float:
    """Сколько секунд добавляет extend-правило {on, flat | pct [of]} (pct - от max_hp по умолчанию)."""
    if ext.get("flat") is not None:
        v: dict = {"flat": ext["flat"]}
    elif ext.get("pct") is not None:
        v = {"pct": ext.get("pct"), "of": ext.get("of", "max_hp")}
    else:
        v = {}
    return resolve_value(v, ctx)


# mod-арифметика: (база стата, накопленный вклад cur, значение) -> новый вклад. base + cur = текущее значение.
MOD_MATH: dict[str, Callable[[float, float, float], float]] = {
    "add": lambda base, cur, a: cur + a,
    "sub": lambda base, cur, a: cur - a,
    "mul": lambda base, cur, a: (base + cur) * a - base,
    "div": lambda base, cur, a: (base + cur) / a - base if a else cur,
    "set": lambda base, cur, a: a - base,
    "min": lambda base, cur, a: min(base + cur, a) - base,
    "max": lambda base, cur, a: max(base + cur, a) - base,
}


def apply_mod_math(dst: dict, base: float, stat: Optional[str], mo: str, amount: float) -> None:
    """Записать вклад mod-операции `mo` в dst[stat] (dst - unit.mods или слой-накопитель)."""
    fn = MOD_MATH.get(mo)
    if fn is not None:
        dst[stat] = fn(base, dst.get(stat, 0.0), amount)


def replace_contribution(contribs: dict, key: Any, unit: Any, stat: Optional[str],
                         apply: Callable[[], None]) -> None:
    """Событийная mod-операция задаёт СВОЙ текущий вклад: вклад прошлого срабатывания этой же операции
    (contribs[key] = (юнит, стат, вклад)) снимается, новый записывается. Вклад меряется ПОСЛЕ снятия
    старого (семантика схемы, п.3 уточнений) - так считает тренировочная комната."""
    old_unit, old_stat, old = contribs.get(key) or (unit, stat, 0.0)
    if old:
        old_unit.mods[old_stat] = old_unit.mods.get(old_stat, 0.0) - old
    before = unit.mods.get(stat, 0.0)
    apply()
    contribs[key] = (unit, stat, unit.mods.get(stat, 0.0) - before)


def replace_contribution_game(contribs: dict, key: Any, unit: Any, stat: Optional[str],
                              apply: Callable[[], None]) -> None:
    """ДИВЕРГЕНЦИЯ (docs/EFFECT_SCHEMA.md, "Op handlers"): менеджер игры меряет вклад ДО снятия старого,
    поэтому при повторном срабатывании записывается amount - old (а не amount, как в схеме). Ни один
    контент игры такого пути не проходит; поведение сохранено 1-в-1 как было, выравнивать его -
    отдельное решение (с перезаписью golden)."""
    rec = contribs.get(key)
    before = unit.mods.get(stat, 0.0)
    if rec:
        unit.mods[rec[1]] = unit.mods.get(rec[1], 0.0) - rec[2]
    apply()
    contribs[key] = (unit, stat, unit.mods.get(stat, 0.0) - before)


# ---------------------------------------------------------------- op call + host


class Periodic(NamedTuple):
    """DoT/HoT, который ставит deal/heal с every + duration."""
    kind: str        # "deal" | "heal"
    amount: float    # за один тик
    every: float     # период, с
    until: float     # когда истекает (абсолютное время хоста)


@dataclass(slots=True)
class OpCall:
    """Всё, что нужно операции, кроме неё самой и цели."""
    ctx: dict                       # контекст значений (floats)
    src: str                        # "<effect>#<event>" - для логов, ключей и фильтра extend
    t: float                        # время хоста
    source: Any = None              # кто применяет: владелец Unit (рантайм) / EntityState заклинателя (менеджер)
    event: Optional[str] = None     # событие, внутри которого идёт операция (рантайм)
    key: Any = None                 # ключ событийного вклада mod: (src, индекс)
    tags: tuple = ()                # теги способности (менеджер: attack / spell / reflect)
    hits: Optional[list] = None     # сюда менеджер складывает попадания
    primary: Any = None             # основная цель способности (менеджер)


class OpHost(Protocol):
    """Что интерпретатор даёт обработчикам операций. Цель `tgt` - Unit (рантайм) или EntityState (менеджер)."""

    def op_stat_prefix(self, cx: OpCall, tgt: Any) -> str: ...            # "" для своих, "enemy_" для врага
    def op_periodic_ok(self, o: dict) -> bool: ...                        # deal/heal с every: это DoT/HoT?
    def op_duration(self, d: Any, ctx: dict) -> float: ...
    def op_add_periodic(self, cx: OpCall, tgt: Any, o: dict, p: Periodic) -> None: ...
    def op_resource(self, tgt: Any, res: str) -> float: ...
    def op_damage(self, cx: OpCall, tgt: Any, o: dict, amount: float) -> None: ...
    def op_spend(self, cx: OpCall, tgt: Any, res: str, amount: float, lethal: bool) -> None: ...
    def op_heal(self, cx: OpCall, tgt: Any, res: str, amount: float) -> None: ...
    def op_set_resource(self, cx: OpCall, tgt: Any, stat: Optional[str], amount: float) -> None: ...
    def op_mod(self, cx: OpCall, tgt: Any, o: dict) -> None: ...
    def op_buffs(self, tgt: Any) -> dict: ...                             # buff_id -> запись баффа цели
    def op_granted(self, cx: OpCall) -> dict: ...                         # buff_id -> когда выдан (кулдаун)
    def op_buff_record(self, cx: OpCall, o: dict, until: float, cd: Optional[float]) -> dict: ...
    def op_after_buff(self, cx: OpCall, tgt: Any, bid: Any, o: dict) -> None: ...
    def op_extend(self, cx: OpCall, bid: Any, ext: dict, buff: dict) -> None: ...  # фильтр по extend.on + продление
    def op_find_effect(self, cx: OpCall, eid: Any) -> Optional[dict]: ...
    def op_nested(self, cx: OpCall, ops: list, suffix: str, keep_event: bool) -> None: ...
    def op_kill(self, cx: OpCall, tgt: Any) -> None: ...
    def op_summon(self, cx: OpCall, o: dict) -> None: ...
    def op_move(self, cx: OpCall, tgt: Any, o: dict) -> None: ...
    def op_note(self, cx: OpCall, what: str, *args: Any) -> None: ...     # строка лога (рантайм) / ничего (менеджер)


# ---------------------------------------------------------------- handlers: one per op kind

Handler = Callable[[OpHost, OpCall, Any, dict, float], None]


def op_deal(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    res = o.get("stat") or "hp"
    if res == "hp":
        h.op_damage(cx, tgt, o, amount)
    else:  # mana burn
        h.op_spend(cx, tgt, res, amount, False)
    h.op_note(cx, "deal", tgt, res, amount)


def op_heal(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    res = o.get("stat") or "hp"
    h.op_heal(cx, tgt, res, amount)
    h.op_note(cx, "heal", tgt, res, amount)


def op_drain(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    res = o.get("stat") or "hp"
    have = h.op_resource(tgt, res)
    if amount > have:
        h.op_note(cx, "drain_fail", tgt, res, amount, have)
        h.op_nested(cx, o.get("fail") or [], ".fail", True)
        return
    h.op_spend(cx, tgt, res, amount, True)      # ровно до 0 HP - смерть
    h.op_note(cx, "drain", tgt, res, amount)


def op_set(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    h.op_set_resource(cx, tgt, o.get("stat"), amount)


def op_mod(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    h.op_mod(cx, tgt, o)


def op_buff(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    bid, t = o.get("buff_id"), cx.t
    buffs = h.op_buffs(tgt)
    prev = buffs.get(bid)
    # кулдаун на повторную активацию щита/баффа живёт дольше самого баффа
    cd = resolve_value(o.get("cooldown"), cx.ctx) if o.get("cooldown") else None
    granted = h.op_granted(cx)
    if cd is not None and bid in granted and t - granted[bid] < cd:
        h.op_note(cx, "buff_cooldown", bid)
        return
    dur = h.op_duration(o.get("duration"), cx.ctx)
    until = max(prev.get("until", t) if prev else t, t) + dur
    granted[bid] = t
    buffs[bid] = h.op_buff_record(cx, o, until, cd)
    h.op_note(cx, "buff", bid, dur, until)
    h.op_after_buff(cx, tgt, bid, o)


def op_extend(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    bid = o.get("buff_id")
    buff = h.op_buffs(tgt).get(bid)
    if not buff:
        return
    h.op_extend(cx, bid, o.get("extend") or buff.get("extend") or {}, buff)


def op_remove_buff(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    h.op_buffs(tgt).pop(o.get("buff_id"), None)
    h.op_note(cx, "remove_buff", o.get("buff_id"))


def op_apply_effect(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    ef = h.op_find_effect(cx, o.get("buff_id"))     # apply_effect использует buff_id как id эффекта
    if ef:
        h.op_nested(cx, ef.get("ops") or [], f"->{ef['id']}", False)


def op_kill(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    h.op_kill(cx, tgt)


def op_summon(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    h.op_summon(cx, o)


def op_move(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    h.op_move(cx, tgt, o)


# ЕДИНАЯ таблица диспетчеризации: ключи = schema.OP_KINDS (тест: tests/test_ops_table.py)
OP_HANDLERS: dict[str, Handler] = {
    "deal": op_deal, "heal": op_heal, "drain": op_drain, "set": op_set, "mod": op_mod,
    "buff": op_buff, "extend": op_extend, "remove_buff": op_remove_buff,
    "apply_effect": op_apply_effect, "kill": op_kill, "summon": op_summon, "move": op_move,
}


def _every(o: dict, ctx: dict) -> float:
    every = o["every"]
    return max(0.1, float(resolve_value(every, ctx) if isinstance(every, dict) else every))


def apply_op(h: OpHost, cx: OpCall, tgt: Any, o: dict) -> None:
    """Одна операция на одной цели (условие `when` и выбор цели - забота хоста): значение -> DoT/HoT? -> обработчик."""
    kind = o.get("kind")
    amount = compute_amount(o, cx.ctx, default_stat_of(o, h.op_stat_prefix(cx, tgt)))
    if kind in ("deal", "heal") and o.get("every") and h.op_periodic_ok(o):
        # DoT/HoT: тик каждые every с в течение duration
        every = _every(o, cx.ctx)
        h.op_add_periodic(cx, tgt, o, Periodic(kind, amount, every, cx.t + h.op_duration(o["duration"], cx.ctx)))
        return
    handler = OP_HANDLERS.get(kind)
    if handler is not None:
        handler(h, cx, tgt, o, amount)
