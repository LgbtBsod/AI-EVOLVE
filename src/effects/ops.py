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

import logging
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, NamedTuple, Optional, Protocol

from src.core.adaptation import WHEEL_MAX_DEFAULT
from src.effects.control import CONTROL_HANDLERS
from src.effects.perception import PERCEPTION_HANDLERS
from src.effects.triggers import TRIGGER_HANDLERS
from src.effects.zones import ZONE_HANDLERS

# ---------------------------------------------------------------- spec kind names -> canon (lua_content/kind_aliases.lua)


@lru_cache(maxsize=1)
def _exact_rows() -> dict:
    """spec kind -> row for the `exact = true` rows of lua_content/kind_aliases.lua (empty without a Lua backend)."""
    try:
        from ..content import lua_bridge
        rows = lua_bridge.load(lua_bridge.CONTENT / "kind_aliases.lua", cache=True).get("aliases") or {}
    except (ImportError, OSError, RuntimeError, ValueError):
        return {}
    return {k: v for k, v in rows.items() if v.get("exact")}


def _exact_aliases() -> dict:
    """spec kind -> canon kind for the exact rows."""
    return {k: v["canon"] for k, v in _exact_rows().items()}


def canonical_kind(kind: Any) -> Any:
    """Spec name of an op kind -> canon name (exact aliases only); anything else comes back unchanged."""
    return _exact_aliases().get(kind, kind) if isinstance(kind, str) else kind


def canonicalize_op(op: Any) -> Any:
    """Op with a spec kind -> the canon op: kind renamed and the alias row's implied `params` filled in (op's own fields win).
    An op that is not an exact alias comes back as the SAME object."""
    row = _exact_rows().get(op.get("kind")) if isinstance(op, dict) and isinstance(op.get("kind"), str) else None
    if row is None:
        return op
    out = dict(op)
    out["kind"] = row["canon"]
    for key, val in (row.get("params") or {}).items():
        out.setdefault(key, val)
    return out


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


def _hp_missing_below(threshold: float) -> Callable[[dict], float]:
    """Псевдо-стат: сколько % HP не хватает ДО ПОРОГА `threshold`% (0..threshold)."""
    return lambda ctx: max(0.0, threshold - ctx.get("hp_pct", 100.0))


_hp_missing_below_40 = _hp_missing_below(40.0)          # порог берсерка (lost_my_self / sorrow_of_berserk)

# вычисляемые поля контекста (нет в ctx -> считаются от него): имя -> функция
_ALLOWED_CTX: dict[str, Callable[[dict], float]] = {
    "hp_missing_below_40": _hp_missing_below_40,
}
_HP_MISSING_BELOW = re.compile(r"hp_missing_below_(\d{1,3})")     # семейство: hp_missing_below_<N>, N = любой порог в %


def derived_ctx(key: str) -> Optional[Callable[[dict], float]]:
    """Вычисляемое поле ctx по имени (таблица `_ALLOWED_CTX` + семейство `hp_missing_below_<N>`) или None. ЕДИНСТВЕННОЕ
    место, где живут псевдо-статы: им пользуются и значения (`ctx_get`), и предикаты условий (`runtime._field`)."""
    fn = _ALLOWED_CTX.get(key)
    if fn is None and (m := _HP_MISSING_BELOW.fullmatch(key)):
        fn = _hp_missing_below(float(m[1]))
    return fn


def ctx_get(ctx: dict, key: Optional[str]) -> float:
    if key is None:
        return 0.0
    if key in ctx:
        return float(ctx[key])
    if (derived := derived_ctx(key)) is not None:
        return float(derived(ctx))
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
    def op_forms(self, tgt: Any) -> dict: ...                             # exclusive_group -> запись активной формы (stance/transform)
    def op_form_mods(self, cx: OpCall, tgt: Any, fid: str, mods: list, until: Optional[float]) -> None: ...
    def op_form_clear_mods(self, cx: OpCall, tgt: Any, fid: str) -> None: ...
    def op_note(self, cx: OpCall, what: str, *args: Any) -> None: ...     # строка лога (рантайм) / ничего (менеджер)

    # --- примитивы новых kinds (resist/immune/mark/detonate/purge/nullify/...) ------
    def op_marks(self, tgt: Any) -> dict: ...              # mark_id -> {stacks, until} (живые метки цели)
    def op_grant_mark(self, cx: OpCall, tgt: Any, mid: str, stacks: float, until: float) -> None: ...
    def op_spells(self, tgt: Any) -> list: ...             # id выученных/скопированных техник (learn/adapt)
    def op_adapt_stacks(self, tgt: Any) -> dict: ...       # damage_type -> число адаптаций (Mahoraga)
    def op_absorb_add(self, cx: OpCall, tgt: Any, amount: float, window: float) -> None: ...  # absorbed_kinetic
    def op_apply_mod_op(self, cx: OpCall, tgt: Any, o: dict) -> None: ...  # mod-механика для resist/immune/adapt
    def op_refresh(self, cx: OpCall, tgt: Any) -> None: ...               # пересчёт статов цели после правок
    def op_damage_taken(self, cx: OpCall, tgt: Any) -> float: ...         # сколько урона обработчик уже нанёс цели
    # --- протокол Махораги (src/core/adaptation.py; поля external["mahoraga"] / external["aggro"] ---
    def op_adaptation(self, cx: OpCall, tgt: Any) -> dict: ...  # сериализуемое состояние колеса/памяти цели
    def set_adaptation(self, cx: OpCall, tgt: Any, state: dict) -> None: ...
    def op_aggro(self, cx: OpCall, tgt: Any) -> dict: ...       # {faction, aggro_mode, targeting, target}
    def set_aggro(self, cx: OpCall, tgt: Any, **kv: Any) -> None: ...
    def op_nested_ops(self, cx: OpCall, tgt: Any, ops: list) -> None: ...  # on_adapt/on_max поддеревья
    # --- control (src/effects/control.py) ---
    def op_control(self, tgt: Any) -> dict: ...                          # {"rec": запись активного контроля}
    def op_controller(self, cx: OpCall) -> Any: ...                      # id того, кто контролирует (источник вызова)
    def op_faction(self, cx: OpCall, tgt: Any, new: Any = None) -> Any: ...  # фракция цели (new -> сменить); вернуть прежнюю
    def op_resisted(self, cx: OpCall, tgt: Any, sid: str) -> bool: ...   # status_resist_<sid> (одна seeded-выборка при 0<p<100)
    def op_roll(self, cx: OpCall) -> float: ...                          # [0,1) из seeded RNG хоста
    def op_stat_of(self, cx: OpCall, who: str, tgt: Any, stat: str) -> float: ...  # стат источника ("source") / цели ("target")
    # --- perception (src/effects/perception.py) ---
    def op_triggers(self, tgt: Any) -> dict: ...                         # unit.external["triggers"]: lethal interceptors / last_lethal
    def op_schedule(self, rec: dict) -> None: ...                        # delay queue (manager only)
    def op_apply_op(self, cx: OpCall, tgt: Any, o: dict) -> None: ...
    def op_perception(self, tgt: Any) -> dict: ...                       # unit.external["perception"]: perceived / revealed / precog
    def op_ident(self, tgt: Any) -> Any: ...                             # id цели (ключ perceived)


# ---------------------------------------------------------------- shared helpers (Mahoraga specs)

def _damage_gate_ok(thr: dict, sign: str, dealt: float, st: dict) -> bool:
    """threshold.damage_total: урон этого вызова + уже виденный по подписи должен дойти до порога (нет порога - проходит)."""
    need = float(thr.get("damage_total", 0.0) or 0.0)
    return not need or dealt + float(st.get("damage_seen", {}).get(sign, 0.0)) >= need


def _custom_gate_ok(custom: Any, ctx: dict) -> bool:
    """threshold.custom: предикат схемы над ctx вызова (+ wheel, phenomenon_hits); нет предиката - проходит."""
    if not custom:
        return True
    from .runtime import eval_pred              # лениво: runtime сам импортирует этот модуль
    return bool(eval_pred(custom, ctx))


def _threshold_ok(thr: dict, sign: str, dealt: float, st: dict, ctx: dict) -> bool:
    """ThresholdSpec (ЧАСТЬ 3.3): hits/damage_total/wheel_min/custom — все заданные условия сразу.
    `dealt` = урон, уже нанесённый цели этим вызовом; `st` = состояние колеса цели (dict); `ctx` = контекст вызова."""
    if not thr:
        return True
    hits = int(st.get("progress", {}).get(sign, 0))
    return (hits >= int(thr.get("hits", 1) or 1)
            and _damage_gate_ok(thr, sign, dealt, st)
            and int(st.get("wheel", 0)) >= int(thr.get("wheel_min", 0) or 0)
            and _custom_gate_ok(thr.get("custom"), {**ctx, "wheel": st.get("wheel", 0), "phenomenon_hits": hits}))


# ---------------------------------------------------------------- handlers: one per op kind

Handler = Callable[[OpHost, OpCall, Any, dict, float], None]


def _nested(h: OpHost, cx: OpCall, tgt: Any, ops_: list) -> None:
    """Поддерево одной операцией (on_adapt/on_max/cost/gain): общий путь через op_nested_ops хоста."""
    for sub in ops_ or []:
        h.op_nested_ops(cx, tgt, [sub])


def _damage_dealt_to(h: OpHost, cx: OpCall, tgt: Any) -> float:
    """Урон, уже нанесённый ЦЕЛИ в этом вызове (hits от deal/use_learned) — порог damage_total."""
    return h.op_damage_taken(cx, tgt)


def _phenomenon_damage_ctx(p: dict, cx: OpCall) -> dict:
    """Что известно об ударе-феномене: тип урона и техника (из спецификации, иначе из ctx вызова)."""
    return {"damage_type": p.get("damage_type") or cx.ctx.get("last_damage_type") or "physical",
            "technique_id": p.get("technique_id") or cx.ctx.get("observed_technique")}


def _is_literal_formula(formula: Any) -> bool:
    """Шаблон id_formula без вызовов: строка с ':' и без скобок."""
    return isinstance(formula, str) and ":" in formula and not any(c in formula for c in "()")


def _formula_signature(formula: str, dmg_ctx: dict) -> str:
    """Литеральный шаблон "damage_type..':'..technique_id" из справочника -> `<тип>:<техника>`."""
    dt, tech = (formula.split("..':'..") + [""])[:2]
    dt = dmg_ctx["damage_type"] if "damage_type" in dt else (dt.strip("'\"") or dt)
    tech = dmg_ctx["technique_id"] or "basic" if "technique_id" in tech else (tech.strip("'\"") or "basic")
    return f"{dt}:{tech}"


def _phenomenon_signature(o: dict, cx: OpCall) -> str:
    """PhenomenonSpec (ЧАСТЬ 3.2): id_formula или damage_type..':'..(technique_id or 'basic')."""
    from src.core.adaptation import SignatureHasher
    p = o.get("phenomenon") or {}
    dmg_ctx = _phenomenon_damage_ctx(p, cx)
    if _is_literal_formula(p.get("id_formula")):
        return _formula_signature(p["id_formula"], dmg_ctx)
    gran = p.get("granularity", "exact")
    sign = SignatureHasher().signature(dmg_ctx, gran)
    flags = p.get("source_flag") or cx.ctx.get("last_damage_flags")
    if not flags or gran != "exact":
        return sign
    fl = "+".join(sorted(flags)) if isinstance(flags, (list, tuple, set)) else str(flags)
    return f"{sign}#{fl}"                # составной феномен true_damage+imaginary_mass - отдельная подпись


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


def _take_mark_stacks(marks: dict, mid: Optional[str], now: float) -> float:
    """Снять метку `mid` и вернуть её стаки; без mark_id - взрыв ВСЕХ живых меток (сумма стаков)."""
    if mid is None:
        total = sum(float(r["stacks"]) for r in marks.values() if r.get("until", 0.0) > now)
        marks.clear()
        return total
    rec = marks.pop(mid, None) if mid else None
    return float(rec["stacks"]) if rec else 0.0


def _detonate_value(o: dict, stacks: float) -> dict:
    """Value урона взрыва: scale {every, value} - плюс N шагов по стакам метки; без scale - base за каждую метку."""
    v = dict(o.get("value") or {"flat": 0.0})
    base = float(v.get("flat", 0.0))
    s = o.get("scale")
    if not s:
        v["flat"] = base * stacks
        return v
    steps = int(stacks // max(float(s.get("every", 1.0)), 1e-9))
    sv = (s.get("value") or {}) if isinstance(s.get("value"), dict) else {"flat": s.get("value")}
    v["flat"] = base + steps * float(sv.get("flat", 0.0)) * float(s.get("factor", 1.0))
    return v


def op_detonate(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    mid = o.get("mark_id")
    stacks = _take_mark_stacks(h.op_marks(tgt), mid, cx.t)
    if stacks <= 0:
        h.op_note(cx, "detonate_empty", tgt, mid)
        return
    d = {"kind": "deal", "target": "enemy", "stat": o.get("stat") or "hp", "op": "sub",
         "flags": ["true_damage", "no_crit"], "value": _detonate_value(o, stacks)}
    h.op_nested(cx, [d], f".detonate({mid})", True)
    h.op_note(cx, "detonate", tgt, mid, stacks)


_DEBUFF_IDS = ("debuff", "block:", "nullified")         # по префиксу id: что считается дебаффом при purge kind=debuff


def _purge_spec(o: dict) -> tuple[str, Optional[str]]:
    """filter = "kind" | {kind, tag} -> (kind, tag); kind: buff (по умолчанию) | debuff | mark | all."""
    f = o.get("filter") or {}
    if isinstance(f, str):
        return f, None
    return f.get("kind", "buff"), f.get("tag")


def _purgeable(bid: Any, rec: dict, want: str, tag: Optional[str], now: float) -> bool:
    """Живая запись баффа (с нужным тегом-флагом), которую снимает фильтр `want`."""
    if rec.get("until", 1e18) <= now or (tag and tag not in (rec.get("flags") or [])):
        return False
    return want in ("all", "buff") or (want == "debuff" and str(bid).startswith(_DEBUFF_IDS))


def op_purge(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    want, tag = _purge_spec(o)
    buffs = h.op_buffs(tgt)
    for bid in [b for b, rec in buffs.items() if _purgeable(b, rec, want, tag, cx.t)]:
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


def _run_adapt_hooks(h: OpHost, cx: OpCall, tgt: Any, o: dict, st: Any) -> None:
    """Адаптация состоялась: поддерево on_adapt, а на wheel_max ещё и on_max (по умолчанию - trigger_true_form)."""
    _nested(h, cx, tgt, o.get("on_adapt"))
    if st.at_max:
        _nested(h, cx, tgt, o.get("on_max") or [{"kind": "trigger_true_form"}])


def op_adapt(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Ядро адаптации (adapt из справочника): подпись феномена -> порог -> wheel+1 + on_adapt."""
    from src.core.adaptation import AdaptationState
    st = AdaptationState.from_dict(_mahoraga_state(h, cx, tgt))
    sign = _phenomenon_signature(o, cx)
    if o.get("exclude_self", True) and cx.src == getattr(tgt, "name", None):
        h.op_note(cx, "adapt_excluded", tgt, sign)      # cannot_adapt_to_self
        return
    dealt = _damage_dealt_to(h, cx, tgt)
    adapted = st.observe(sign, tick=int(cx.t), amount=dealt, source_id=cx.src)
    if adapted and _threshold_ok(o.get("threshold") or {}, sign, dealt, st.to_dict(), cx.ctx):
        _run_adapt_hooks(h, cx, tgt, o, st)
    tech = cx.ctx.get("observed_technique")
    if tech and o.get("learned_use", True):
        st.learn(str(tech))                                    # learn_technique в составе adapt
    h.set_adaptation(cx, tgt, st.to_dict())
    h.op_refresh(cx, tgt)
    h.op_note(cx, "adapt", tgt, sign, st.wheel)


# ЕДИНАЯ таблица диспетчеризации: ключи = schema.OP_KINDS (тест: tests/test_ops_table.py)

def _mahoraga_state(h: OpHost, cx: OpCall, tgt: Any) -> dict:
    """Состояние Махораги цели как сериализуемый dict (src/core/adaptation.AdaptationState)."""
    st = h.op_adaptation(cx, tgt)
    if not st.get("initialized"):
        st = dict(st)
        st.update({"initialized": True, "wheel_max": WHEEL_MAX_DEFAULT, "wheel": 0,
                   "known_phenomena": [], "progress": {}, "adaptation_power": {},
                   "learned_techniques": [], "true_form": False})
        h.set_adaptation(cx, tgt, st)
    return st


def op_unadapt(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Сброс адаптации к феномену: memory_key (или ctx.phenomenon_id); освобождает слот колеса."""
    from src.core.adaptation import AdaptationState
    st = AdaptationState.from_dict(_mahoraga_state(h, cx, tgt))
    sign = o.get("memory_key") or o.get("sign") or cx.ctx.get("phenomenon_id") or ""
    changed = st.unadapt(str(sign))
    h.set_adaptation(cx, tgt, st.to_dict())
    h.op_refresh(cx, tgt)
    h.op_note(cx, "unadapt", tgt, sign, changed)


def op_reset_adaptation(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Полный сброс колеса (wheel=0, память очищается; true form — только через deescalate)."""
    from src.core.adaptation import AdaptationState
    st = AdaptationState.from_dict(_mahoraga_state(h, cx, tgt))
    st.reset()
    h.set_adaptation(cx, tgt, st.to_dict())
    h.op_refresh(cx, tgt)
    h.op_note(cx, "reset_adaptation", tgt)


def _learn_phenomenon(st: dict, sign: str, o: dict) -> bool:
    """Порог hits по подписи набран впервые: в память, сила адаптации, колесо +1. True - адаптация состоялась."""
    thr = int((o.get("threshold") or {}).get("hits", 1) or 1)
    if st["progress"][sign] < thr or sign in st["known_phenomena"]:
        return False
    st["known_phenomena"].append(sign)
    st["adaptation_power"][sign] = float((o.get("max_immunity") or {}).get("pct", 100.0))
    st["wheel"] = min(int(st.get("wheel", 0)) + 1, int(st.get("wheel_max", WHEEL_MAX_DEFAULT)))
    return True


def op_observe_phenomenon(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Наблюдение феномена без урона: тот же путь SignatureHasher -> observe (порог hits)."""
    from src.core.adaptation import SignatureHasher
    st = _mahoraga_state(h, cx, tgt)
    sign = SignatureHasher().signature(_phenomenon_damage_ctx(o, cx))
    hit = int(st.get("progress", {}).get(sign, 0)) + 1
    st.setdefault("progress", {})[sign] = hit
    st["last_damage_signature"] = sign
    if _learn_phenomenon(st, sign, o):
        _nested(h, cx, tgt, o.get("on_adapt"))
    h.set_adaptation(cx, tgt, st)
    h.op_note(cx, "observe_phenomenon", tgt, sign, hit)


def op_register_phenomenon(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Записать подпись феномена в память носителя (без порога/колеса — просто знание)."""
    st = _mahoraga_state(h, cx, tgt)
    sign = str(o.get("memory_key") or o.get("sign") or cx.ctx.get("phenomenon_id") or "")
    if sign and sign not in st["known_phenomena"]:
        st["known_phenomena"].append(sign)
        st.setdefault("first_seen_tick", {})[sign] = int(cx.t)
    h.set_adaptation(cx, tgt, st)
    h.op_note(cx, "register_phenomenon", tgt, sign)


def op_use_learned_technique(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Применить украденную технику: pick = highest_threat | random | last; deal с adapt_damage."""
    spells = h.op_spells(tgt)
    if not spells:
        h.op_note(cx, "use_learned_none", tgt)
        return
    pick = o.get("pick", "last")
    if pick == "random":
        tech = spells[int(cx.ctx.get("rng_roll", 0)) % len(spells)]
    elif pick == "highest_threat":
        tech = max(spells, key=lambda s: float(cx.ctx.get(f"threat_{s}", 0.0)))
    else:
        tech = spells[-1]
    bonus = o.get("adapt_damage")                      # % к урону: число или Value ({flat} / {pct, of} / {ref})
    boost = 1.0 + (resolve_value(bonus, cx.ctx) if isinstance(bonus, dict) else float(bonus or 0.0)) / 100.0
    base = o.get("value") or {"flat": amount}
    if isinstance(base, dict):
        base = {**base, "pct": float(base.get("pct", 100.0)) * boost} if "pct" in base else base
    h.op_nested_ops(cx, tgt, [{"kind": "deal", "target": o.get("tech_target", "enemy"),
                               "stat": "hp", "op": "sub", "value": base,
                               "flags": list(o.get("flags") or []) + [f"learned:{tech}"]}])
    h.op_note(cx, "use_learned_technique", tgt, tech)


def op_set_faction(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    ag = h.op_aggro(cx, tgt)
    ag["faction"] = str(o.get("faction") or o.get("stat") or "neutral")
    h.set_aggro(cx, tgt, **ag)
    h.op_note(cx, "set_faction", tgt, ag["faction"])


def op_set_aggro(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    ag = h.op_aggro(cx, tgt)
    ag["aggro_mode"] = str(o.get("aggro_mode") or o.get("mode") or "nearest_any")
    if o.get("targeting"):
        ag["targeting"] = o["targeting"]
    h.set_aggro(cx, tgt, **ag)
    h.op_note(cx, "set_aggro", tgt, ag["aggro_mode"])


def op_set_targeting(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    ag = h.op_aggro(cx, tgt)
    ag["targeting"] = o.get("targeting") or {k: o[k] for k in
                                             ("mode", "filter", "switch_on", "switch_interval", "prefer")
                                             if k in o}
    h.set_aggro(cx, tgt, **ag)
    h.op_note(cx, "set_targeting", tgt)


def op_retarget(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    ag = h.op_aggro(cx, tgt)
    ag["target"] = o.get("target_ref")
    h.set_aggro(cx, tgt, **ag)
    h.op_note(cx, "retarget", tgt, ag["target"])


def op_clear_aggro(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    ag = h.op_aggro(cx, tgt)
    ag["target"] = None
    ag.pop("threat", None)
    h.set_aggro(cx, tgt, **ag)
    h.op_note(cx, "clear_aggro", tgt)


def op_rotate_wheel(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Оборот колеса: wheel_delta (или value.delta/flat); на wheel_max -> on_max (trigger_true_form)."""
    st = _mahoraga_state(h, cx, tgt)
    delta = o.get("wheel_delta")
    if delta is None:
        v = o.get("value") or {}
        delta = v.get("delta", v.get("flat", amount or 1))
    wheel_max = int(st.get("wheel_max", WHEEL_MAX_DEFAULT))
    st["wheel"] = max(0, min(wheel_max, int(st.get("wheel", 0)) + int(delta)))
    h.set_adaptation(cx, tgt, st)
    if st["wheel"] >= wheel_max and not st.get("true_form"):
        for sub in o.get("on_max") or [{"kind": "trigger_true_form"}]:
            h.op_nested_ops(cx, tgt, [sub])
    h.op_note(cx, "rotate_wheel", tgt, st["wheel"])


def _escalate_delta(o: dict, amount: float) -> int:
    d = o.get("escalation_delta")
    if d is None:
        v = o.get("value") or {}
        d = v.get("flat", amount or 1)
    return int(d)


def op_escalate(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Эскалация: escalation_level += delta (обычно синхронно колесу)."""
    st = _mahoraga_state(h, cx, tgt)
    st["escalation_level"] = max(0, int(st.get("escalation_level", st.get("wheel", 0)))
                                 + _escalate_delta(o, amount))
    h.set_adaptation(cx, tgt, st)
    h.op_note(cx, "escalate", tgt, st["escalation_level"])


def op_deescalate(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Откат эскалации (rewind-механики): уровень вниз, true form спадает до порога."""
    st = _mahoraga_state(h, cx, tgt)
    st["escalation_level"] = max(0, int(st.get("escalation_level", 0)) - _escalate_delta(o, amount))
    if st["escalation_level"] < int(st.get("wheel_max", WHEEL_MAX_DEFAULT)):
        st["true_form"] = False
    h.set_adaptation(cx, tgt, st)
    h.op_note(cx, "deescalate", tgt, st["escalation_level"])


def op_trigger_true_form(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Истинная форма: флаг + поддеревья ops (mod статов ×3, transform, display_wheel golden)."""
    st = _mahoraga_state(h, cx, tgt)
    if st.get("true_form"):
        return
    st["true_form"] = True
    h.set_adaptation(cx, tgt, st)
    for sub in o.get("ops") or []:
        h.op_nested_ops(cx, tgt, [sub])
    h.op_note(cx, "trigger_true_form", tgt)


def op_display_wheel(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """UI-хук: показать состояние колеса (mode='golden' в true form); счётчик не трогается."""
    st = _mahoraga_state(h, cx, tgt)
    st["wheel_display"] = {"visible": True, "mode": o.get("mode", "default")}
    h.set_adaptation(cx, tgt, st)
    h.op_note(cx, "display_wheel", tgt, st["wheel"], o.get("mode"))


def op_halt_wheel(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Остановить вращение колеса (визуал); счётчик адаптаций сохраняется."""
    st = _mahoraga_state(h, cx, tgt)
    st["wheel_display"] = {"visible": bool(st.get("wheel_display", {}).get("visible")), "mode": "halted"}
    h.set_adaptation(cx, tgt, st)
    h.op_note(cx, "halt_wheel", tgt, st["wheel"])


# ---------------------------------------------------------------- формы: stance / transform / timed_power_up

_FORM_GROUPS = {"stance": "stance", "transform": "transform"}


def _form_group(o: dict, kind: str) -> str:
    return o.get("exclusive_group") or _FORM_GROUPS.get(kind) or f"power_up:{o.get('id')}"


def _form_blocked(forms: dict, fid: Any, o: dict) -> bool:
    """conflict_with: новая форма отвергается, если активна конфликтующая (в обе стороны)."""
    mine = set(o.get("conflict_with") or ())
    return any(r["id"] in mine or fid in (r.get("conflict_with") or ()) for r in forms.values())


def exit_form(h: OpHost, cx: OpCall, tgt: Any, group: str) -> None:
    """Снять форму группы: моды формы уходят, её on_exit ops выполняются."""
    rec = h.op_forms(tgt).pop(group, None)
    if rec is None:
        return
    h.op_form_clear_mods(cx, tgt, rec["id"])
    if rec.get("on_exit"):
        h.op_nested_ops(cx, tgt, list(rec["on_exit"]))
    h.op_note(cx, "form_exit", rec["id"])


def _enter_form(h: OpHost, cx: OpCall, tgt: Any, o: dict, kind: str) -> None:
    fid, group = o.get("id"), _form_group(o, kind)
    forms = h.op_forms(tgt)
    cur = forms.get(group)
    if cur is not None and cur["id"] == fid:
        return
    if _form_blocked(forms, fid, o):
        h.op_note(cx, "form_blocked", fid)
        return
    if cur is not None:
        exit_form(h, cx, tgt, group)                 # сначала on_exit старой формы
    rec = _form_record(h, cx, o, kind)
    forms[group] = rec
    _form_start(h, cx, tgt, o, rec)
    h.op_note(cx, "form_enter", fid)


def _form_record(h: OpHost, cx: OpCall, o: dict, kind: str) -> dict:
    dur = o.get("duration")
    return {"id": o.get("id"), "kind": kind, "until": cx.t + h.op_duration(dur, cx.ctx) if dur is not None else None,
            "on_exit": list(o.get("on_exit") or []), "conflict_with": list(o.get("conflict_with") or []),
            "abilities": dict(o.get("abilities") or {})}


def _form_start(h: OpHost, cx: OpCall, tgt: Any, o: dict, rec: dict) -> None:
    if o.get("stats"):
        h.op_form_mods(cx, tgt, rec["id"], list(o["stats"]), rec["until"])
    if o.get("on_enter"):
        h.op_nested_ops(cx, tgt, list(o["on_enter"]))   # потом on_enter новой


def form_abilities(forms: dict) -> dict:
    """Набор способностей активных форм: {"add": [...], "remove": [...]} (данные; игра сама их не применяет)."""
    out: dict = {"add": [], "remove": []}
    for rec in forms.values():
        for key in out:
            out[key] += [a for a in (rec.get("abilities") or {}).get(key, ()) if a not in out[key]]
    return out


def op_stance(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    _enter_form(h, cx, tgt, o, "stance")


def op_transform(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    _enter_form(h, cx, tgt, o, "transform")


def op_timed_power_up(h: OpHost, cx: OpCall, tgt: Any, o: dict, amount: float) -> None:
    """Временное усиление: форма со своей группой, duration обязателен; по истечении on_exit = расплата/последствия."""
    _enter_form(h, cx, tgt, o, "timed_power_up")


OP_HANDLERS: dict[str, Handler] = {
    "deal": op_deal, "heal": op_heal, "drain": op_drain, "set": op_set, "mod": op_mod,
    "buff": op_buff, "extend": op_extend, "remove_buff": op_remove_buff,
    "apply_effect": op_apply_effect, "kill": op_kill, "summon": op_summon, "move": op_move,
    "resist": op_resist, "immune": op_immune, "mark": op_mark, "detonate": op_detonate,
    "purge": op_purge, "nullify": op_nullify, "cancel_technique": op_cancel_technique,
    "block": op_block, "absorb_damage": op_absorb_damage, "binding_vow": op_binding_vow,
    "sever": op_sever, "untargetable": op_untargetable, "learn": op_learn, "adapt": op_adapt,
    # Махорага (ЧАСТЬ 2/7.1 справочника)
    "unadapt": op_unadapt, "reset_adaptation": op_reset_adaptation,
    "use_learned_technique": op_use_learned_technique,
    "observe_phenomenon": op_observe_phenomenon, "register_phenomenon": op_register_phenomenon,
    "set_faction": op_set_faction, "set_aggro": op_set_aggro, "set_targeting": op_set_targeting,
    "retarget": op_retarget, "clear_aggro": op_clear_aggro,
    "escalate": op_escalate, "deescalate": op_deescalate, "trigger_true_form": op_trigger_true_form,
    "rotate_wheel": op_rotate_wheel, "display_wheel": op_display_wheel, "halt_wheel": op_halt_wheel,
    "stance": op_stance, "transform": op_transform, "timed_power_up": op_timed_power_up,
    **CONTROL_HANDLERS, **PERCEPTION_HANDLERS, **TRIGGER_HANDLERS, **ZONE_HANDLERS,
}


def _every(o: dict, ctx: dict) -> float:
    every = o["every"]
    return max(0.1, float(resolve_value(every, ctx) if isinstance(every, dict) else every))


UNKNOWN_KIND_COUNT: dict = {}    # kind -> сколько раз op с неизвестным kind был пропущен (для тестов)


def _note_unknown_kind(kind: Any) -> None:
    """Неизвестный kind = ошибка контента: одно предупреждение на kind за процесс + счётчик."""
    first = kind not in UNKNOWN_KIND_COUNT
    UNKNOWN_KIND_COUNT[kind] = UNKNOWN_KIND_COUNT.get(kind, 0) + 1
    if first:
        logging.getLogger(__name__).warning("effect op: unknown kind %r ignored (no handler)", kind)


def apply_op(h: OpHost, cx: OpCall, tgt: Any, o: dict) -> None:
    """Одна операция на одной цели (условие `when` и выбор цели - забота хоста): значение -> DoT/HoT? -> обработчик."""
    o = canonicalize_op(o)
    kind = o.get("kind")
    amount = compute_amount(o, cx.ctx, default_stat_of(o, h.op_stat_prefix(cx, tgt)))
    if kind in ("deal", "heal") and o.get("every") and h.op_periodic_ok(o):
        # DoT/HoT: тик каждые every с в течение duration
        every = _every(o, cx.ctx)
        h.op_add_periodic(cx, tgt, o, Periodic(kind, amount, every, cx.t + h.op_duration(o["duration"], cx.ctx)))
        return
    handler = OP_HANDLERS.get(kind)
    if handler is None:
        _note_unknown_kind(kind)
        return
    handler(h, cx, tgt, o, amount)
