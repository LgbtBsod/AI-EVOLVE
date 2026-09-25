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

    # --- примитивы новых kinds (resist/immune/mark/detonate/purge/nullify/...) ------
    def op_marks(self, tgt: Any) -> dict: ...              # mark_id -> {stacks, until} (живые метки цели)
    def op_grant_mark(self, cx: OpCall, tgt: Any, mid: str, stacks: float, until: float) -> None: ...
    def op_spells(self, tgt: Any) -> list: ...             # id выученных/скопированных техник (learn/adapt)
    def op_adapt_stacks(self, tgt: Any) -> dict: ...       # damage_type -> число адаптаций (Mahoraga)
    def op_absorb_add(self, cx: OpCall, tgt: Any, amount: float, window: float) -> None: ...  # absorbed_kinetic
    def op_apply_mod_op(self, cx: OpCall, tgt: Any, o: dict) -> None: ...  # mod-механика для resist/immune/adapt
    def op_refresh(self, cx: OpCall, tgt: Any) -> None: ...               # пересчёт статов цели после правок


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


# ---------------------------------------------------------------- новые kinds: аудит Сукуна / Годжо / Тоджи


def _resist_stat(o: dict) -> str:
    """Тип урона операции -> стат resist_<тип>; "all" -> общий входящий урон (damage_taken)."""
    dt = o.get("damage_type") or o.get("what") or "all"
    return "damage_taken" if dt == "all" else f"resist_{dt}"


def _timed(o: dict) -> bool:
    """Есть duration - временный слой (external), нет - пассивный мод владельца."""
    return o.get("duration") is not None


def op_resist(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    m = {"kind": "mod", "stat": _resist_stat(o), "op": o.get("op") or "add", "value": o.get("value") or {"flat": amount}}
    if _timed(o):
        m["duration"] = o["duration"]
    h.op_apply_mod_op(cx, tgt, m)
    h.op_note(cx, "resist", tgt, m["stat"], amount)


def op_immune(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    # иммунитет к типу урона = резист на 100% (конвейер гасит тип полностью);
    # иммунитет к действию/эффекту ("heal_mana", "cursed_technique") = block того же слоя
    what = o.get("effect") or o.get("status")
    if what and not o.get("damage_type"):
        bid = f"block:{what}"
        b = h.op_buffs(tgt).get(bid)
        until = max(b.get("until", cx.t) if b else cx.t, cx.t) + h.op_duration(o.get("duration"), cx.ctx)
        h.op_buffs(tgt)[bid] = h.op_buff_record(cx, o, until, None)
        h.op_note(cx, "immune_effect", tgt, what)
        return
    pct = 100.0 if not o.get("value") else min(100.0, amount)
    m = {"kind": "mod", "stat": _resist_stat(o), "op": "max", "value": {"flat": pct}}
    if _timed(o):
        m["duration"] = o["duration"]
    h.op_apply_mod_op(cx, tgt, m)
    h.op_note(cx, "immune", tgt, m["stat"], pct)


def op_mark(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    mid = o.get("mark_id") or o.get("stat")
    if not mid:
        return
    marks = h.op_marks(tgt)
    rec = marks.get(mid)
    until = cx.t + h.op_duration(o.get("duration"), cx.ctx)
    stacks = amount if amount > 0 else 1.0
    if rec and rec.get("until", 0.0) > cx.t:      # stack-правило max_stacks (refresh по умолчанию)
        stacks = min(stacks + rec["stacks"], float(o.get("max_stacks", stacks)))
        until = max(until, rec["until"])
    h.op_grant_mark(cx, tgt, mid, stacks, until)
    h.op_note(cx, "mark", tgt, mid, stacks)


def op_detonate(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    mid = o.get("mark_id")
    marks = h.op_marks(tgt)
    rec = marks.pop(mid, None) if mid else None
    stacks = float(rec["stacks"]) if rec else 0.0
    if mid is None:                                # без mark_id — взрыв всех живых меток
        for k_, r_ in list(marks.items()):
            if r_.get("until", 0.0) > cx.t:
                stacks += float(r_["stacks"])
            marks.pop(k_)
    if stacks <= 0:
        h.op_note(cx, "detonate_empty", tgt, mid)
        return
    d = {"kind": "deal", "target": "enemy", "stat": o.get("stat") or "hp", "op": "sub",
         "flags": ["true_damage", "no_crit"]}
    v = dict(o.get("value") or {"flat": 0.0})
    base = float(v.get("flat", 0.0))
    s = o.get("scale")                             # scale {every, value} -> плюс N шагов по стакам метки
    if s:
        steps = int(stacks // max(float(s.get("every", 1.0)), 1e-9))
        sv = (s.get("value") or {}) if isinstance(s.get("value"), dict) else {"flat": s.get("value")}
        v["flat"] = base + steps * float(sv.get("flat", 0.0)) * float(s.get("factor", 1.0))
    else:
        v["flat"] = base * stacks                  # без scale: базовый урон за каждую метку
    d["value"] = v
    h.op_nested(cx, [d], f".detonate({mid})", True)
    h.op_note(cx, "detonate", tgt, mid, stacks)


def op_purge(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    f = o.get("filter") or {}
    want = f.get("kind") or f if isinstance(f, str) else f.get("kind", "buff")
    tag = f.get("tag") if isinstance(f, dict) else None
    buffs = h.op_buffs(tgt)
    for bid in list(buffs):
        rec = buffs[bid]
        if rec.get("until", 1e18) <= cx.t:
            continue
        flags = rec.get("flags") or []
        if tag and tag not in flags:
            continue
        if want in ("all", "buff") or (want == "debuff" and str(bid).startswith(("debuff", "block:", "nullified"))):
            buffs.pop(bid)
    if want in ("all", "mark"):
        h.op_marks(tgt).clear()
    h.op_refresh(cx, tgt)
    h.op_note(cx, "purge", tgt, want, tag)


def _disable_buff(h: OpHost, cx: OpCall, tgt: Any, bid: str, o: dict) -> None:
    buffs = h.op_buffs(tgt)
    prev = buffs.get(bid)
    until = max(prev.get("until", cx.t) if prev else cx.t, cx.t) + h.op_duration(o.get("duration"), cx.ctx)
    buffs[bid] = h.op_buff_record(cx, o, until, None)
    h.op_after_buff(cx, tgt, bid, o)


def op_nullify(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Отмена активных сил: снять баффы и заблокировать способности на duration (Inverted Spear / домен-контр)."""
    _disable_buff(h, cx, tgt, "nullified", o)
    h.op_note(cx, "nullify", tgt)


def op_cancel_technique(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Копьё Неба: прерывает ТЕКУЩУЮ технику при касании; уже выпущенный снаряд летит."""
    _disable_buff(h, cx, tgt, "technique_cancelled", o)
    if o.get("duration"):
        _disable_buff(h, cx, tgt, "nullified", o)
    h.op_note(cx, "cancel_technique", tgt)


def op_block(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Запрет действия: stat/effect = "cursed_technique" | "domain_expansion" | "reverse_cursed_technique"..."""
    what = o.get("stat") or o.get("effect") or o.get("what") or "actions"
    _disable_buff(h, cx, tgt, f"block:{what}", o)
    h.op_note(cx, "block", tgt, what)


def op_absorb_damage(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    window = resolve_value(o.get("window"), cx.ctx) if isinstance(o.get("window"), dict) else float(o.get("window") or 0.5)
    h.op_absorb_add(cx, tgt, max(amount, 0.0), max(window, 0.05))
    h.op_note(cx, "absorb_damage", tgt, amount, window)


def op_binding_vow(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Обет: цена (cost ops) платится сразу, награда (gain ops) живёт пока действует метка обета."""
    vid = o.get("vow_id") or o.get("id") or "vow"
    _disable_buff(h, cx, tgt, f"vow:{vid}", o)     # метка: purge/ссылки видят активный обет
    cost = o.get("cost_ops") or o.get("cost")
    if cost:
        h.op_nested(cx, cost if isinstance(cost, list) else [cost], f".vow({vid}).cost", True)
    gain = o.get("gain_ops") or o.get("gain") or o.get("ops")
    if gain:
        h.op_nested(cx, gain if isinstance(gain, list) else [gain], f".vow({vid}).gain", True)
    h.op_note(cx, "binding_vow", tgt, vid)


def op_sever(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Разрыв связи (Split Soul Katana): soul_body_link -> блок регена/исцеления цели на duration."""
    what = o.get("what") or "technique_link"
    _disable_buff(h, cx, tgt, f"severed:{what}", o)
    if what in ("soul_body_link", "body_link"):
        _disable_buff(h, cx, tgt, "block:heal", o)
        h.op_apply_mod_op(cx, tgt, {"kind": "mod", "stat": "hp_regen", "op": "set", "value": {"flat": 0},
                                    "duration": o.get("duration")})
    h.op_note(cx, "sever", tgt, what)


def op_untargetable(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Невыбираемость селекторами (Toji для six_eyes/en/divination): флаг-бафф читает выбор целей."""
    by = o.get("by") or "all"
    by = ",".join(sorted(by)) if isinstance(by, (list, tuple)) else str(by)
    _disable_buff(h, cx, tgt, f"untargetable:{by}", o)
    h.op_note(cx, "untargetable", tgt, by)


def op_learn(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Скопировать технику (Sukuna <- Mahoraga): id из from или ctx.observed_technique; uses=-1 навсегда."""
    src_ref = o.get("from")
    tech = cx.ctx.get("observed_technique") if (not src_ref or src_ref == "ctx.observed_technique") else src_ref
    tech = tech or o.get("ability_id") or o.get("id")
    if not tech:
        h.op_note(cx, "learn_nothing", tgt)
        return
    spells = h.op_spells(tgt)
    if tech not in spells:
        spells.append(str(tech))
    h.op_note(cx, "learn", tgt, tech)


def op_adapt(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Адаптация Махораги: после попадания по типу - permanent resist_<тип> += rate за стек адаптаций."""
    dt = o.get("to") or o.get("damage_type") or cx.ctx.get("last_damage_type") or "physical"
    rate = float(o.get("rate", 20.0))
    stacks = h.op_adapt_stacks(tgt)
    stacks[dt] = stacks.get(dt, 0) + 1
    total = min(rate * stacks[dt], 100.0)
    h.op_apply_mod_op(cx, tgt, {"kind": "mod", "stat": _resist_stat({"damage_type": dt}),
                                "op": "max", "value": {"flat": total}})
    h.op_note(cx, "adapt", tgt, dt, stacks[dt])


# ЕДИНАЯ таблица диспетчеризации: ключи = schema.OP_KINDS (тест: tests/test_ops_table.py)
OP_HANDLERS: dict[str, Handler] = {
    "deal": op_deal, "heal": op_heal, "drain": op_drain, "set": op_set, "mod": op_mod,
    "buff": op_buff, "extend": op_extend, "remove_buff": op_remove_buff,
    "apply_effect": op_apply_effect, "kill": op_kill, "summon": op_summon, "move": op_move,
    "resist": op_resist, "immune": op_immune, "mark": op_mark, "detonate": op_detonate,
    "purge": op_purge, "nullify": op_nullify, "cancel_technique": op_cancel_technique,
    "block": op_block, "absorb_damage": op_absorb_damage, "binding_vow": op_binding_vow,
    "sever": op_sever, "untargetable": op_untargetable, "learn": op_learn, "adapt": op_adapt,
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
