"""Единый менеджер эффектов: через него идёт ВСЁ, что меняет сущности в бою.

Удар оружием, навык, зелье, эффект предмета, дебафф, навык босса - это
способности на языке схемы Effect -> Ops[] (docs/EFFECT_SCHEMA.md), и все они
исполняются здесь одним конвейером:

    cast(caster, "weapon_attack", target)
      -> проверки (жив, кулдаун, стоимость, дальность) -> оплата
      -> событие attack/cast (эффекты предметов: казнь, цена крови ...)
      -> операции способности: deal / heal / drain / set / mod / buff / extend /
         remove_buff / apply_effect / kill / summon; цели self / enemy / area
      -> урон: уклонение -> крит -> броня -> неуязвимость (iframe) -> HP
         -> лайфстил -> события attack_hit / crit / dodge / take_damage / kill / die
      -> на события реагируют эффекты надетых предметов - тем же конвейером.

Удар оружием - та же способность, что и навык: урон = ctx.attack_damage,
кулдаун = 1 / скорость атаки, модификаторы дают предметы и баффы.

Каждая сущность - EntityState: блок статов схемы (Unit) поверх полей игры
(health, physical_damage, critical_chance ...) и EffectRuntime для пассивов и
условий (Lost My Self). Вклад эффектов прибавляется к полям игры «дельтой»:
код игры (прокачка, реген) меняет поля как раньше, не зная про эффекты.

Операции со временем: deal/heal с every + duration - это DoT/HoT; mod с
duration (или на чужую цель) - временный бафф/дебафф. Урон от реакций на
take_damage (шипы) помечается reflect и сам реакций не вызывает.

Всё по-честному: area бьёт ВСЕХ живых в круге - союзников и самого
заклинателя тоже (френдли фаер); affects = others | enemies | allies сужает.
Удар оружием - способность САМОГО оружия (item.attack): меч и топор бьют
дугой (area + arc) всех впереди, копьё и лук - одну цель, посох - взрыв по
площади; без оружия - weapon_attack (одна цель).
Дальность удара и обзора - статы (attack_range, vision_range): лук даёт
дальность, стелс - это area-мод vision_range с toward = "source" (в круге
заклинателя видят хуже). can_see(observer, target) - единственная проверка
«заметил ли», её спрашивают ИИ героя и врагов.
"""
from __future__ import annotations

import itertools
import logging
import math
import operator
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol

from . import damage
from .ops import OpCall, Periodic, Tracked, apply_op, replace_contribution_game
from .runtime import EffectRuntime, Unit, buff_fields, resolve_value, rules

logger = logging.getLogger(__name__)

# стат схемы -> (поле сущности, масштаб, сдвиг): schema = game * scale + shift
STAT_MAP: dict[str, tuple[str, float, float]] = {
    "max_hp": ("max_health", 1.0, 0.0),
    "max_mana": ("max_mana", 1.0, 0.0),
    "max_stamina": ("max_stamina", 1.0, 0.0),
    "hp_regen": ("health_regen", 1.0, 0.0),
    "mana_regen": ("mana_regen", 1.0, 0.0),
    "stamina_regen": ("stamina_regen", 1.0, 0.0),
    "attack_damage": ("physical_damage", 1.0, 0.0),
    "spell_power": ("magical_damage", 1.0, 0.0),
    "defense": ("defense", 1.0, 0.0),
    "aspd": ("attack_speed", 1.0, 0.0),
    "crit_chance": ("critical_chance", 100.0, 0.0),      # 0.05 -> 5 пунктов
    "crit_dmg": ("critical_damage", 100.0, -100.0),      # x1.5 -> 50 пунктов
    "dodge": ("dodge_chance", 100.0, 0.0),
    "lifesteal": ("lifesteal", 1.0, 0.0),
    "attack_range": ("attack_range", 1.0, 0.0),
    "vision_range": ("vision_range", 1.0, 0.0),
}
POOLS = ("mana", "stamina")
DEFAULT_DEBUFF_SECONDS = 5.0
MAX_EVENT_DEPTH = 6


class World(Protocol):
    """Что менеджеру нужно от мира (сцены)."""

    def entities(self) -> Iterable[Any]: ...

    def spawn_summon(self, kind: str, x: float, y: float, faction: str, level: int, owner: Any) -> Any: ...


@dataclass
class HitInfo:
    """Попадание. Поля совместимы с DamageInfo старой боевой системы
    (регистратор боя в tools/probe_runtime.py читает source/target/damage/...).
    Стадии конвейера урона (docs/DAMAGE_PIPELINE.md) - в полях ниже: что сняли броня, сопротивление и блок."""
    source: str
    target: str
    damage: float
    is_critical: bool = False
    is_dodged: bool = False
    ability: str = ""
    invulnerable: bool = False  # неуязвимость цели (iframe): урона нет
    killed: bool = False
    missed: bool = False        # промах по меткости (accuracy против evasion)
    blocked: bool = False       # блок цели (шанс block_chance): урон срезан
    hit_type: str = "physical"  # тип урона (lua_content/damage.lua)
    damage_before: float = 0.0  # урон после множителей и крита, до брони / сопротивления / блока
    armor_reduced: float = 0.0
    resisted: float = 0.0
    blocked_amount: float = 0.0
    armor_ignored: float = 0.0  # очков брони, снятых пробитием

    @property
    def landed(self) -> bool:
        """Удар дошёл до цели (не уклонение и не промах); неуязвимость - отдельно (invulnerable)."""
        return not (self.is_dodged or self.missed)


@dataclass
class CastResult:
    ok: bool
    reason: str = ""
    hits: list[HitInfo] = field(default_factory=list)


@dataclass
class Telegraph:
    """Отложенная способность (навыки боссов): круг на земле до срабатывания."""
    caster: Any
    ability: dict
    target: Any
    x: float
    y: float
    radius: float
    at: float


def entity_id(entity) -> str:
    return str(getattr(entity, "entity_id", None) or id(entity))


def position(entity) -> tuple[float, float]:
    return float(getattr(entity, "x", 0.0)), float(getattr(entity, "y", 0.0))


def is_alive(entity) -> bool:
    alive = getattr(entity, "is_alive", None)
    return bool(alive()) if callable(alive) else getattr(entity, "health", 0) > 0


# ---- кэш итоговых статов: входы EntityState.refresh ------------------------------------------------------------
# поля сущности, которые читает pull()/base_game(): STAT_MAP + оба имени скорости (какое из них - решает hasattr)
_FIELD_NAMES = tuple(dict.fromkeys([attr for attr, _s, _o in STAT_MAP.values()] + ["speed", "move_speed"]))
_CLAMPS = (("health", "max_health"),) + tuple((res, f"max_{res}") for res in POOLS)


def _bit_same(a: float, b: float) -> bool:
    """Бит-в-бит для float (NaN не равен ничему, знак нуля учитывается)."""
    return a == b and (a != 0 or math.copysign(1.0, a) == math.copysign(1.0, b))


@dataclass(slots=True)
class StatCache:
    """Для каких входов посчитаны итоговые статы сущности (см. EntityState.refresh)."""
    version: int           # EntityState.version: equipment_stats / external / перестройка рантайма
    unit_version: int      # Unit.version: любая запись в base / mods
    rules: Any             # rules() - правила статов не перезагружались
    t0: float              # время расчёта; кэш действует на [t0, valid_until)
    valid_until: float     # ближайшее истечение временного слоя (external): в этот кадр пересчёт
    getter: Any            # attrgetter по полям, которые у сущности есть (один вызов на кадр)
    absent: tuple          # поля, которых у сущности нет: не должны появиться (hasattr в base_game)
    fields: tuple          # значения полей после записи статов
    attr_names: tuple      # характеристики уровня (rules()["attributes"])
    alloc: tuple           # их значения у сущности (очки уровня)


# ================================================================ entity state

class EntityState:
    """Статы схемы одной сущности поверх её полей и рантайм её пассивов."""

    # False: refresh всегда считает статы заново (сравнение с кэшем в тестах: результат бит-в-бит тот же)
    stat_cache = True

    def __init__(self, entity, faction: str, abilities: Iterable[str] = ()):
        self.entity = entity
        self.faction = faction
        self.abilities = list(abilities)
        self.version = 0                          # dirty-флаг входов статов (Tracked-словари, rebuild_runtime, touch)
        self._cache: Optional[StatCache] = None
        self.unit = Unit(entity_id(entity), derive=True)   # характеристики -> статы (сила -> урон, HP)
        self.items: list = []
        self.item_effects: list[dict] = []        # все эффекты надетых предметов
        self.extra_effects: list[dict] = []       # действующие части расходников (Тоник ярости)
        self.perk_effects: list[dict] = []        # перки характеристик (lua_content/perks.lua)
        self._equipment_stats: Tracked = Tracked(self)
        self.innate: dict[str, float] = dict(getattr(entity, "innate_stats", None) or {})   # статы вида (бестиарий `stats`)
        self._external: Tracked = Tracked(self)   # ключ -> (до, {стат: вклад})
        self.applied: dict[str, float] = {}
        self.cooldowns: dict[str, float] = {}      # способность -> когда готова
        self.fired_at: dict[str, float] = {}       # Effect.cooldown эффектов предметов
        self.buff_granted_at: dict[str, float] = {}
        self.periodic: list[dict] = []             # DoT/HoT на этой сущности
        self.zones: dict[str, bool] = {}           # hp_cross
        self.vision_vs: dict[Any, tuple[float, str, float]] = {}  # ключ -> (до, id цели, вклад в обзор на неё)
        # --- слои примитивов аудита (mark/absorb/learn/adapt), как у Unit тренировочной комнаты ---
        self.marks: dict[str, dict] = {}            # mark_id -> {stacks, until}
        self.spells: list[str] = []                 # выученные/скопированные техники (learn)
        self.adapt_stacks: dict[str, int] = {}      # damage_type -> число адаптаций (Mahoraga)
        self.absorbed_kinetic: float = 0.0          # поглощённый кинетический урон (Playful Cloud)
        self.absorbed_until: float = 0.0            # до какого момента окно поглощения
        self.weapon_ability: Optional[str] = None  # удар надетого оружия (item.attack)
        self.runtime = EffectRuntime(self.unit, [], enemy=Unit("nobody"))
        if not hasattr(entity, "lifesteal"):
            entity.lifesteal = 0.0
        if not hasattr(entity, "kills"):
            entity.kills = 0

    # ---------------------------------------------------------------- dirty flag
    def touch(self) -> None:
        """Вход итоговых статов изменился: кэш refresh недействителен."""
        self.version += 1

    @property
    def equipment_stats(self) -> Tracked:
        return self._equipment_stats

    @equipment_stats.setter
    def equipment_stats(self, value: dict) -> None:
        self._equipment_stats = Tracked(self, value)
        self.touch()

    @property
    def external(self) -> Tracked:
        return self._external

    @external.setter
    def external(self, value: dict) -> None:
        self._external = Tracked(self, value)
        self.touch()

    # ---------------------------------------------------------------- effects
    @property
    def event_effects(self) -> list[dict]:
        return [ef for ef in self.all_effects() if (ef.get("trigger") or {}).get("kind") == "event"]

    def rebuild_runtime(self) -> None:
        """Пассивы и условия - в EffectRuntime (слои модов, amplify); события - в менеджере."""
        passive = [ef for ef in self.all_effects()
                   if (ef.get("trigger") or {}).get("kind") in ("passive", "condition")]
        keep = self.runtime
        self.runtime = EffectRuntime(self.unit, passive, enemy=keep.enemy)
        self.runtime._compiled = keep._compiled
        self.runtime._last_hit_at, self.runtime._last_attack_at = keep._last_hit_at, keep._last_attack_at
        # поля buff_<id> - для всех баффов предмета, не только пассивных
        self.runtime._buff_fields = buff_fields(self.all_effects())
        ids = {ef["id"] for ef in self.all_effects()}
        self.runtime._op_contrib = {k: v for k, v in keep._op_contrib.items()
                                    if str(k[0]).split("#")[0].split("->")[0] in ids}
        self.touch()

    def all_effects(self) -> list[dict]:
        return self.item_effects + self.extra_effects + self.perk_effects

    # ---------------------------------------------------------------- sync
    def _speed_attr(self) -> str:
        return "speed" if hasattr(self.entity, "speed") else "move_speed"

    def base_game(self) -> dict[str, float]:
        e, out = self.entity, {}
        for attr in [a for a, _s, _o in STAT_MAP.values()] + [self._speed_attr()]:
            if hasattr(e, attr):
                out[attr] = float(getattr(e, attr) or 0.0) - self.applied.get(attr, 0.0)
        return out

    def pull(self, now: float, base: Optional[dict] = None) -> dict[str, float]:
        """Поля сущности -> Unit (база без вклада эффектов + ресурсы)."""
        base = self.base_game() if base is None else base
        u = self.unit
        # стат без поля у сущности (attack_range у манекена, custom:*) - каждый раз с
        # умолчания: иначе бонус предмета прибавлялся бы к базе на каждом refresh
        defaults = rules()["defaults"]
        new = {k: float(defaults.get(k, 0.0)) for k in u.base}
        for stat, (attr, scale, shift) in STAT_MAP.items():
            if attr in base:
                new[stat] = base[attr] * scale + shift
        new["move_speed"] = base.get(self._speed_attr(), float(defaults.get("move_speed", 5.0)))
        allocated = getattr(self.entity, "attributes", None) or {}
        for attr in rules()["attributes"]:
            new[attr] = float(allocated.get(attr, 0.0))   # очки уровня; предметы/эффекты - поверх
        for k, v in itertools.chain(self.innate.items(), self.equipment_stats.items()):
            new[k] = new.get(k, 0.0) + v
        for until, layer in self.external.values():
            if until > now:
                for k, v in layer.items():
                    new[k] = new.get(k, 0.0) + v
        u.assign_base(new)                    # version растёт только если база и правда изменилась
        self.pull_resources()
        return base

    def pull_resources(self) -> None:
        e, u = self.entity, self.unit
        u.current_hp = float(getattr(e, "health", 0.0))
        u.alive = is_alive(e)
        for res in POOLS:
            if hasattr(e, res):
                u.pools[res] = float(getattr(e, res))
        u.kills = int(getattr(e, "kills", 0) or 0)

    def push_stats(self, base: dict[str, float]) -> None:
        """Итоговые статы Unit -> поля сущности (вклад запоминается дельтой)."""
        u, e = self.unit, self.entity
        for stat, (attr, scale, shift) in STAT_MAP.items():
            if attr not in base:
                continue
            v = u._eff(stat)                      # уже с производными от характеристик
            value = (v - shift) / scale
            self.applied[attr] = value - base[attr]
            setattr(e, attr, value)
        speed = self._speed_attr()
        if speed in base:
            value = max(0.0, u._eff("move_speed"))
            self.applied[speed] = value - base[speed]
            setattr(e, speed, value)
        self._clamp_resources()

    def _clamp_resources(self) -> None:
        """Текущее значение ресурса не выше максимума (игра могла поднять HP/ману, не глядя на потолок)."""
        e = self.entity
        for res, cap_attr in _CLAMPS:
            cap = getattr(e, cap_attr, None)
            if cap is not None and getattr(e, res, 0) > cap:
                setattr(e, res, cap)

    def refresh(self, now: float) -> None:
        """Пересчитать статы сущности. Итог - функция входов (поля сущности, очки характеристик, надетое, временные
        слои по времени, правила); пока ни один не менялся, а прошлый расчёт был неподвижной точкой (повтор дал бы те же
        значения бит-в-бит), статы не пересчитываются: обновляются только ресурсы и потолки (они меняются каждый кадр)."""
        cache = self._cache if self.stat_cache else None
        if cache is not None and self._cache_hit(cache, now):
            self.runtime._now = now
            self.pull_resources()
            self._clamp_resources()
            return
        passive = bool(self.runtime.effects or self.runtime._op_contrib)
        base = self.pull(now)
        self.runtime._now = now
        if passive:                       # пассивы/условия зависят от HP, времени, баффов: считаем каждый раз
            self.runtime.refresh_passives(now)
        else:
            self.unit.mods = {}
        self.push_stats(base)
        self._cache = self._make_cache(now, base) if self.stat_cache and not passive else None

    def _cache_hit(self, c: StatCache, now: float) -> bool:
        if not (c.t0 <= now < c.valid_until and c.version == self.version and c.unit_version == self.unit.version):
            return False
        if self.runtime.effects or self.runtime._op_contrib or c.rules is not rules():
            return False
        return self._inputs_same(c)

    def _inputs_same(self, c: StatCache) -> bool:
        """Поля сущности и очки характеристик те же, что при расчёте (игра их не трогала с прошлого кадра)."""
        e = self.entity
        try:
            fields = c.getter(e)
        except AttributeError:
            return False
        if fields != c.fields or any(hasattr(e, name) for name in c.absent):
            return False
        allocated = getattr(e, "attributes", None) or {}
        return tuple([allocated.get(a, 0.0) for a in c.attr_names]) == c.alloc

    def _fixed_point(self, base: dict[str, float]) -> bool:
        """Повторный расчёт без изменений извне даст те же значения бит-в-бит: то, что прочитал бы СЛЕДУЮЩИЙ
        refresh (поле - вклад), совпадает с базой этого. Иначе (дрейф в последнем бите) кэшировать нельзя."""
        nxt = self.base_game()
        return nxt.keys() == base.keys() and all(_bit_same(nxt[k], base[k]) for k in base)

    def _field_probe(self) -> Optional[tuple]:
        """(attrgetter по имеющимся полям, отсутствующие имена, значения) - или None, если кэшировать нечем."""
        e = self.entity
        present = tuple(n for n in _FIELD_NAMES if hasattr(e, n))
        if len(present) < 2:                  # attrgetter одного поля возвращает не кортеж
            return None
        getter = operator.attrgetter(*present)
        try:
            fields = getter(e)
        except AttributeError:
            return None
        return getter, tuple(n for n in _FIELD_NAMES if n not in present), fields

    def _make_cache(self, now: float, base: dict[str, float]) -> Optional[StatCache]:
        probe = self._field_probe()
        if probe is None or not self._fixed_point(base):
            return None
        r = rules()
        names = tuple(r["attributes"])
        allocated = getattr(self.entity, "attributes", None) or {}
        return StatCache(self.version, self.unit.version, r, now,
                         min((until for until, _l in self.external.values() if until > now), default=math.inf),
                         *probe, names, tuple([allocated.get(a, 0.0) for a in names]))

    # ---------------------------------------------------------------- queries
    def invulnerable(self, now: float) -> bool:
        return any("iframe" in (b.get("flags") or []) and b.get("until", 1e18) > now
                   for b in self.unit.buffs.values())

    def buffs(self, now: float) -> dict[str, float]:
        return {bid: round(b.get("until", 0.0) - now, 1) for bid, b in self.unit.buffs.items()
                if b.get("until", 1e18) > now}

    def resource(self, name: str) -> float:
        return float(getattr(self.entity, "health" if name == "hp" else name, 0.0))


# ================================================================ manager

class EffectManager:
    def __init__(self, world: Optional[World] = None, abilities: Optional[dict[str, dict]] = None,
                 rng: Optional[random.Random] = None):
        self.world = world
        self.abilities: dict[str, dict] = dict(abilities or {})
        self.rng = rng or random
        self.now = 0.0
        self.states: dict[int, EntityState] = {}
        self.telegraphs: list[Telegraph] = []
        self._handlers: list[Callable[[HitInfo], None]] = []
        self._depth = 0

    # ---------------------------------------------------------------- registry
    def register(self, entity, faction: str, abilities: Iterable[str] = ()) -> EntityState:
        st = self.states.get(id(entity))
        if st is None:
            st = self.states[id(entity)] = EntityState(entity, faction, abilities)
            entity.effect_state = st
            st.refresh(self.now)
        return st

    def unregister(self, entity) -> None:
        self.states.pop(id(entity), None)
        self.telegraphs = [tg for tg in self.telegraphs if tg.caster is not entity]

    def state(self, entity) -> Optional[EntityState]:
        return self.states.get(id(entity)) if entity is not None else None

    def register_event_handler(self, handler: Callable[[HitInfo], None]) -> None:
        self._handlers.append(handler)

    def _notify(self, info: HitInfo) -> None:
        for h in self._handlers:
            try:
                h(info)
            except Exception as exc:  # наблюдатель не должен ломать бой
                logger.error("hit handler failed: %s", exc)

    # ---------------------------------------------------------------- equipment
    def equip(self, entity, items: Iterable[Any]) -> None:
        """Надетые предметы: их эффекты и плоские статы."""
        st = self.state(entity)
        if st is None:
            return
        st.items = list(items)
        st.weapon_ability = next((getattr(it, "attack", None) for it in st.items
                                  if getattr(it, "slot", None) == "weapon" and getattr(it, "attack", None)), None)
        st.item_effects = [dict(ef) for it in st.items for ef in getattr(it, "effects", ())]
        st.equipment_stats = {}
        for it in st.items:
            for k, v in getattr(it, "stats", {}).items():
                st.equipment_stats[k] = st.equipment_stats.get(k, 0.0) + float(v)
        st.rebuild_runtime()
        st.refresh(self.now)

    def set_perks(self, entity, effects: list[dict]) -> None:
        """Перки характеристик (src/gameplay/progression.perk_effects) - такие же эффекты, как у предметов."""
        st = self.state(entity)
        if st is None:
            return
        if [e["id"] for e in effects] == [e["id"] for e in st.perk_effects] and \
                [e.get("meta") for e in effects] == [e.get("meta") for e in st.perk_effects]:
            return
        st.perk_effects = [dict(e) for e in effects]
        st.rebuild_runtime()
        st.refresh(self.now)

    # ---------------------------------------------------------------- time
    def update(self, dt: float) -> None:
        self.now += dt
        now = self.now
        for st in list(self.states.values()):
            if not is_alive(st.entity) and not st.periodic:
                continue
            for k in [k for k, (until, _l) in st.external.items() if until <= now]:
                del st.external[k]
            for k in [k for k, (until, _t, _v) in st.vision_vs.items() if until <= now]:
                del st.vision_vs[k]
            for bid in [b for b, d in st.unit.buffs.items() if d.get("until", 1e18) <= now]:
                st.unit.buffs.pop(bid)
            self._run_periodic(st)
            last_tick = st.fired_at.get("#tick", -1.0)
            if st.event_effects and now - last_tick >= 1.0:
                st.fired_at["#tick"] = now
                self.emit(st.entity, "tick")
            st.refresh(now)
            self._scan_zones(st)
        for tg in [tg for tg in self.telegraphs if tg.at <= now]:
            self.telegraphs.remove(tg)
            if is_alive(tg.caster) and self.state(tg.caster):
                self._execute(self.state(tg.caster), tg.ability, tg.target, center=(tg.x, tg.y))

    def _run_periodic(self, st: EntityState) -> None:
        keep = []
        for p in st.periodic:
            while p["next"] <= self.now and p["next"] <= p["until"] + 1e-9:
                p["next"] += p["every"]
                src = self.state(p["source"]) or st
                if p["kind"] == "deal":
                    self._damage(src, st, p["amount"], set(p["flags"]) | {"periodic"}, p["ability"], ())
                elif p["kind"] == "heal":
                    self._heal(st, p["stat"], p["amount"])
            if p["next"] <= p["until"] + 1e-9 and is_alive(st.entity):
                keep.append(p)
        st.periodic = keep

    def _scan_zones(self, st: EntityState) -> None:
        """hp_cross: эффект с threshold объявляет зону; пересечение -> событие."""
        for ef in st.all_effects():
            if ef.get("threshold") is None:
                continue
            name = (ef.get("meta") or {}).get("name") or ef["id"]
            above = st.unit.stat("hp_pct") >= float(ef["threshold"])
            prev = st.zones.get(name)
            st.zones[name] = above
            if prev is not None and prev != above:
                self.emit(st.entity, "hp_cross", crossed=name)

    # ---------------------------------------------------------------- abilities
    def ability(self, ability) -> Optional[dict]:
        return ability if isinstance(ability, dict) else self.abilities.get(ability)

    def cooldown_of(self, st: EntityState, ab: dict) -> float:
        cd = ab.get("cooldown", 0.0)
        if cd == "attack":  # удар оружием: 1 / скорость атаки
            return 1.0 / max(0.1, float(getattr(st.entity, "attack_speed", 1.0) or 1.0))
        return float(cd or 0.0)

    def resolve(self, caster, ability):
        """weapon_attack -> удар надетого оружия (меч дугой, лук в цель); иначе как есть."""
        if ability == "weapon_attack":
            st = self.state(caster)
            own = (st.weapon_ability if st is not None else None) or getattr(caster, "weapon_ability", None)
            if own and own in self.abilities:
                return own
        return ability

    def can_cast(self, caster, ability, target=None) -> tuple[bool, str]:
        ability = self.resolve(caster, ability)
        st, ab = self.state(caster), self.ability(ability)
        if st is None or ab is None:
            return False, "unknown"
        if not is_alive(caster):
            return False, "dead"
        if st.cooldowns.get(ab["id"], 0.0) > self.now + 1e-9:
            return False, "cooldown"
        for res, amount in (ab.get("cost") or {}).items():
            if st.resource(res) < float(amount):
                return False, f"no {res}"
        if ab.get("needs_target", _needs_target(ab)):
            if target is None or not is_alive(target):
                return False, "no target"
            rng = self.range_of(caster, ab) + float(getattr(target, "size", 0.0)) * 0.3
            if math.dist(position(caster), position(target)) > rng:
                return False, "out of range"
        when = ab.get("when")
        if when:
            try:
                if not st.runtime._test(when, self._ctx(st, self.state(target))):
                    return False, "condition"
            except Exception as exc:  # условие ссылается на поле, которого сейчас нет
                return False, f"condition error: {exc}"
        return True, ""

    def range_of(self, caster, ability) -> float:
        """Дальность способности: число, имя стата ("attack_range") или value
        ({ pct = 110, of = "attack_range" }) - удар оружием бьёт на дальность оружия."""
        ab, st = self.ability(self.resolve(caster, ability)), self.state(caster)
        r = (ab or {}).get("range", 2.0)
        if isinstance(r, (int, float)):
            return float(r)
        if st is None:
            return float(getattr(caster, "attack_range", 2.0) or 2.0)
        if isinstance(r, str):
            return float(st.unit.stat(r))
        return float(resolve_value(r, self._ctx(st, None)))

    # ---------------------------------------------------------------- perception
    def vision_toward(self, observer, target) -> float:
        """Как далеко observer видит именно target: его vision_range плюс моды
        с toward = "source" от target (стелс в круге)."""
        st = self.state(observer)
        base = float(getattr(observer, "vision_range", None) or rules()["defaults"].get("vision_range", 20.0))
        if st is None or not st.vision_vs:
            return base
        tid = entity_id(target)
        delta = sum(v for until, t, v in st.vision_vs.values() if t == tid and until > self.now)
        return max(0.0, base + delta)

    def can_see(self, observer, target) -> bool:
        """Заметил ли observer цель: дистанция до края цели <= обзор на неё."""
        if target is None or not is_alive(target):
            return False
        d = math.dist(position(observer), position(target)) - float(getattr(target, "size", 0.0) or 0.0) * 0.5
        return d <= self.vision_toward(observer, target)

    def area_preview(self, caster, ability, target=None) -> list:
        """Кого заденет способность (все её area-операции) - ИИ проверяет френдли фаер
        до применения: не бить по кругу, в котором стоит сам или свои."""
        st, ab = self.state(caster), self.ability(self.resolve(caster, ability))
        if st is None or ab is None:
            return []
        out: list = []
        for o in ab.get("ops") or []:
            if o.get("target") == "area":
                for e in self._targets(st, o, target, None, float(ab.get("radius", 0.0))):
                    if e not in out:
                        out.append(e)
        return out

    def cast(self, caster, ability, target=None) -> CastResult:
        ability = self.resolve(caster, ability)
        st = self.state(caster)
        if st is not None:
            st.refresh(self.now)  # прокачка/реген игры могли поменять поля с прошлого кадра
        ok, why = self.can_cast(caster, ability, target)
        if not ok:
            return CastResult(False, why)
        ab = self.ability(ability)
        for res, amount in (ab.get("cost") or {}).items():
            self._spend(st, res, float(amount))
        st.cooldowns[ab["id"]] = self.now + self.cooldown_of(st, ab)
        tags = tuple(ab.get("tags") or ())
        if "attack" in tags:
            st.runtime._last_attack_at = self.now
            self.emit(caster, "attack", other=target)
            if target is not None and not is_alive(target):
                return CastResult(True, "executed")   # казнь предметом на событии attack
        if "spell" in tags:
            self.emit(caster, "cast", other=target)
        if ab.get("cast_time"):
            cx, cy = position(target) if target is not None else position(caster)
            self.telegraphs.append(Telegraph(caster, ab, target, cx, cy, float(ab.get("radius", 0.0)),
                                             self.now + float(ab["cast_time"])))
            return CastResult(True, "telegraphed")
        return CastResult(True, "", self._execute(st, ab, target))

    def use_item(self, entity, item) -> bool:
        """Выпить/использовать предмет: его эффекты с событием use - этим же конвейером."""
        st = self.state(entity)
        if st is None or not is_alive(entity):
            return False
        effects = [dict(ef) for ef in getattr(item, "effects", ())]
        used = False
        for ef in effects:
            tr = ef.get("trigger") or {}
            if tr.get("kind") == "event" and tr.get("event") == "use":
                self._run_ops(st, ef.get("ops") or [], None, f"{ef['id']}#use", ())
                used = True
        lasting = [ef for ef in effects if (ef.get("trigger") or {}).get("kind") in ("passive", "condition")]
        if lasting:
            have = {ef["id"] for ef in st.extra_effects}
            st.extra_effects += [ef for ef in lasting if ef["id"] not in have]
            st.rebuild_runtime()
        st.refresh(self.now)
        return used

    def _execute(self, st: EntityState, ab: dict, target, center=None) -> list[HitInfo]:
        hits: list[HitInfo] = []
        self._run_ops(st, ab.get("ops") or [], target, ab["id"], tuple(ab.get("tags") or ()), hits=hits,
                      center=center, radius=float(ab.get("radius", 0.0)))
        return hits

    # ---------------------------------------------------------------- events
    def emit(self, entity, event: str, other=None, last_damage: float = 0.0, crossed: str = "") -> None:
        """Событие для эффектов предметов сущности (и продление баффов по extend.on)."""
        st = self.state(entity)
        if st is None or self._depth >= MAX_EVENT_DEPTH:
            return
        now = self.now
        for bid, b in list(st.unit.buffs.items()):
            ext = b.get("extend") or {}
            if ext.get("on") == event and b.get("until", 1e18) > now:
                b["until"] += float(ext.get("flat", 0.0))
        effects = [ef for ef in st.event_effects if (ef.get("trigger") or {}).get("event") == event]
        if not effects:
            return
        self._depth += 1
        try:
            other_st = self.state(other)
            for ef in effects:
                tr = ef.get("trigger") or {}
                if tr.get("cross") and tr["cross"] != crossed:
                    continue
                if tr.get("owner_has") and not self._parent_active(st, tr["owner_has"]):
                    continue
                ctx = self._ctx(st, other_st, last_damage)
                if tr.get("filter") and not st.runtime._test(tr["filter"], ctx):
                    continue
                if ef.get("cooldown"):
                    last = st.fired_at.get(ef["id"])
                    if last is not None and now - last < resolve_value(ef["cooldown"], ctx):
                        continue
                    st.fired_at[ef["id"]] = now
                tags = ("reflect",) if event == "take_damage" else ()
                self._run_ops(st, ef.get("ops") or [], other, f"{ef['id']}#{event}", tags, last_damage=last_damage)
        finally:
            self._depth -= 1

    def _parent_active(self, st: EntityState, parent_id: str) -> bool:
        parent = next((ef for ef in st.all_effects() if ef.get("id") == parent_id), None)
        if parent is None:
            return False
        tr = parent.get("trigger") or {}
        if tr.get("kind") == "condition":
            return st.runtime._test(tr.get("when"), self._ctx(st, None))
        return True

    # ---------------------------------------------------------------- ops
    def _ctx(self, st: EntityState, target_st: Optional[EntityState], last_damage: float = 0.0) -> dict:
        st.pull_resources()
        st.runtime._now = self.now
        if target_st is not None:
            target_st.pull_resources()
            st.runtime.enemy = target_st.unit
        else:
            st.runtime.enemy = None
        st.runtime.last_damage = float(last_damage)
        return st.runtime.context()

    def _targets(self, st: EntityState, o: dict, primary, center, radius: float) -> list:
        tgt = o.get("target", "self")
        if tgt in ("self", "ally", "allies"):
            return [st.entity]
        if tgt in ("enemy", "source"):
            return [primary] if primary is not None else []
        if tgt == "area":
            return self._area_targets(st, o, primary, center, radius)
        return []

    def _area_targets(self, st: EntityState, o: dict, primary, center, radius: float) -> list:
        """target=area: все живые в круге (френдли фаер: заклинатель тоже), суженные affects / arc и невыбираемостью."""
        r = self._area_radius(st, o, radius)
        cx, cy = self._area_center(st, o, primary, center)
        arc = float(o.get("arc", 0.0) or 0.0)       # конус к цели (взмах меча), 0 - полный круг
        affects, by = o.get("affects", "all"), str(o.get("by", "all"))     # affects: френдли фаер по умолчанию (все в круге)
        return [s.entity for s in self.states.values()
                if is_alive(s.entity) and not math.dist((cx, cy), position(s.entity)) > r
                and not self._area_excludes(st, s, affects, arc, primary) and not self._untargetable(s, by)]

    @staticmethod
    def _area_radius(st: EntityState, o: dict, radius: float) -> float:
        r = o.get("radius", radius) or radius or 3.0
        return float(st.unit.stat(r)) if isinstance(r, str) else float(r)   # radius = "attack_range"

    @staticmethod
    def _area_center(st: EntityState, o: dict, primary, center) -> tuple:
        if center:
            return center
        on_target = primary is not None and o.get("center", "target") == "target"
        return position(primary) if on_target else position(st.entity)

    @staticmethod
    def _area_excludes(st: EntityState, s: EntityState, affects: str, arc: float, primary) -> bool:
        """`affects` (others / enemies / allies) и конус `arc` выкидывают сущность из области."""
        if ((affects == "others" and s is st) or (affects == "enemies" and s.faction == st.faction)
                or (affects == "allies" and s.faction != st.faction)):
            return True
        return bool(arc) and s is not st and not _in_arc(st.entity, primary, s.entity, arc)

    def _untargetable(self, s: EntityState, by: str) -> bool:
        """Сущность невыбираема этим селектором (Toji для six_eyes / en): живой бафф `untargetable:<scope>`, scope = all
        или список селекторов через запятую."""
        for bid, rec in s.unit.buffs.items():
            if bid.startswith("untargetable:") and rec.get("until", 1e18) > self.now:
                scope = bid.split(":", 1)[1]
                if scope == "all" or by in scope.split(","):
                    return True
        return False

    def _run_ops(self, st: EntityState, ops: list, primary, src: str, tags: tuple, hits=None,
                 center=None, radius: float = 0.0, last_damage: float = 0.0) -> None:
        hits = hits if hits is not None else []
        for idx, o in enumerate(ops):
            if o.get("when") and not st.runtime._test(o["when"], self._ctx(st, self.state(primary), last_damage)):
                continue
            for tgt in self._targets(st, o, primary, center, radius):
                tgt_st = self.state(tgt)
                if tgt_st is None:
                    continue
                ctx = self._ctx(st, tgt_st if tgt is not st.entity else self.state(primary), last_damage)
                self._run_op(st, tgt_st, o, ctx, f"{src}", idx, tags, hits, primary)

    def _run_op(self, st, tgt_st, o, ctx, src, idx, tags, hits, primary) -> None:
        """Одна операция на одной цели: общий интерпретатор ops.apply_op; цели, области, телеграфы - выше."""
        apply_op(self, OpCall(ctx=ctx, src=src, t=self.now, source=st, key=(src, idx), tags=tags,
                              hits=hits, primary=primary), tgt_st, o)

    # OpHost: примитивы для обработчиков ops.py (сущности игры: урон, кулдауны, мир) ----------------------
    @staticmethod
    def _flags(o: dict, tags: tuple) -> set:
        """Флаги удара: флаги операции + reflect + тип урона (первый тег-тип способности, если он не тип по умолчанию)."""
        return set(o.get("flags") or ()) | ({"reflect"} if "reflect" in tags else set()) | damage.type_flags(tags)

    def op_stat_prefix(self, cx: OpCall, tgt: EntityState) -> str:
        return "enemy_" if tgt is not cx.source else ""

    def op_periodic_ok(self, o: dict) -> bool:
        return bool(o.get("duration"))

    def op_duration(self, d, ctx: dict) -> float:
        return self._duration(d, ctx)

    def op_add_periodic(self, cx: OpCall, tgt: EntityState, o: dict, p: Periodic) -> None:
        tgt.periodic.append({"kind": p.kind, "stat": o.get("stat") or "hp", "amount": p.amount, "every": p.every,
                             "next": self.now + p.every, "until": p.until,
                             "flags": sorted(self._flags(o, cx.tags)), "source": cx.source.entity, "ability": cx.src})

    def op_resource(self, tgt: EntityState, res: str) -> float:
        return tgt.resource(res)

    def op_damage(self, cx: OpCall, tgt: EntityState, o: dict, amount: float) -> None:
        hit = self._damage(cx.source, tgt, amount, self._flags(o, cx.tags), cx.src, cx.tags)
        if hit:
            cx.hits.append(hit)

    def op_spend(self, _cx: OpCall, tgt: EntityState, res: str, amount: float, lethal: bool) -> None:
        self._spend(tgt, res, amount, lethal=lethal)

    def op_heal(self, _cx: OpCall, tgt: EntityState, res: str, amount: float) -> None:
        self._heal(tgt, res, amount)

    def op_set_resource(self, _cx: OpCall, tgt: EntityState, stat: Optional[str], amount: float) -> None:
        self._set_resource(tgt, stat or "hp", amount)

    def op_mod(self, cx: OpCall, tgt: EntityState, o: dict) -> None:
        st = cx.source
        if o.get("toward") == "source":
            if tgt is not st:      # обзор цели в сторону заклинателя (стелс); на себя смысла не имеет
                self._mod_vision(cx, tgt, o)
        elif o.get("duration") is not None or tgt is not st:
            self._mod_timed(cx, tgt, o)
        else:
            self._mod_event(cx, st, o)

    def _mod_until(self, o: dict, ctx: dict) -> float:
        return self.now + (self._duration(o["duration"], ctx) if o.get("duration") is not None
                           else DEFAULT_DEBUFF_SECONDS)

    def _mod_vision(self, cx: OpCall, tgt: EntityState, o: dict) -> None:
        st = cx.source
        scratch: dict[str, float] = {}
        st.runtime._apply_mod(o, cx.ctx, tgt.unit, sink=scratch)
        tgt.vision_vs[(entity_id(st.entity), cx.src, cx.key[1])] = (
            self._mod_until(o, cx.ctx), entity_id(st.entity), scratch.get(o.get("stat"), 0.0))

    def _mod_timed(self, cx: OpCall, tgt: EntityState, o: dict) -> None:
        st = cx.source
        scratch: dict[str, float] = {}
        st.runtime._apply_mod(o, cx.ctx, tgt.unit, sink=scratch)
        tgt.external[(entity_id(st.entity), cx.src, cx.key[1])] = (self._mod_until(o, cx.ctx), scratch)
        tgt.refresh(self.now)

    def _mod_event(self, cx: OpCall, st: EntityState, o: dict) -> None:
        # событийный мод на себя: вклад операции заменяет прошлый (диалект игры - см. ops.replace_contribution)
        replace_contribution_game(st.runtime._op_contrib, cx.key, st.unit, o.get("stat"),
                                  lambda: st.runtime._apply_mod(o, cx.ctx, st.unit))
        st.refresh(self.now)

    def op_buffs(self, tgt: EntityState) -> dict:
        return tgt.unit.buffs

    def op_granted(self, cx: OpCall) -> dict:
        return cx.source.buff_granted_at

    def op_buff_record(self, _cx: OpCall, o: dict, until: float, _cd: Optional[float]) -> dict:
        return {"until": until, "extend": o.get("extend"), "flags": list(o.get("flags") or [])}

    def op_after_buff(self, _cx: OpCall, tgt: EntityState, _bid, _o: dict) -> None:
        tgt.refresh(self.now)

    def op_extend(self, cx: OpCall, _bid, ext: dict, buff: dict) -> None:
        if not ext.get("on") or cx.src.endswith("#" + ext["on"]):
            buff["until"] += float(ext.get("flat", 0.0))

    def op_find_effect(self, cx: OpCall, eid) -> Optional[dict]:
        return next((e for e in cx.source.all_effects() if e.get("id") == eid), None) or self.ability(eid)

    def op_nested(self, cx: OpCall, ops: list, suffix: str, _keep_event: bool) -> None:
        self._run_ops(cx.source, ops, cx.primary, cx.src + suffix, cx.tags, cx.hits)

    def op_kill(self, cx: OpCall, tgt: EntityState) -> None:
        if is_alive(tgt.entity):
            hit = self._damage(cx.source, tgt, tgt.resource("hp"), {"true_damage", "no_crit", "unavoidable"},
                               cx.src, cx.tags)
            if hit:
                cx.hits.append(hit)

    def op_summon(self, cx: OpCall, o: dict) -> None:
        self._summon(cx.source, o, cx.ctx)

    def op_move(self, cx: OpCall, tgt: EntityState, o: dict) -> None:
        self._move(cx.source, tgt, o, cx.primary)

    def op_note(self, cx: OpCall, what: str, *args) -> None:
        """В игре лога операций нет (его ведёт только тренировочная комната)."""

    # --- примитивы новых kinds (mark/absorb/learn/adapt), как у EffectRuntime тренировочной комнаты ---
    def op_marks(self, tgt: EntityState) -> dict:
        return tgt.marks

    def op_grant_mark(self, _cx: OpCall, tgt: EntityState, mid: str, stacks: float, until: float) -> None:
        tgt.marks[mid] = {"stacks": stacks, "until": until}

    def op_spells(self, tgt: EntityState) -> list:
        return tgt.spells

    def op_adapt_stacks(self, tgt: EntityState) -> dict:
        return tgt.adapt_stacks

    def op_absorb_add(self, _cx: OpCall, tgt: EntityState, amount: float, window: float) -> None:
        if self.now > tgt.absorbed_until:             # новое окно: счётчик обнуляется
            tgt.absorbed_kinetic = 0.0
        tgt.absorbed_kinetic += amount
        tgt.absorbed_until = max(tgt.absorbed_until, self.now) + window

    def op_apply_mod_op(self, cx: OpCall, tgt: EntityState, o: dict) -> None:
        tgt.runtime.op_apply_mod_op(cx, tgt.unit, o)   # тот же событийный слой mod-вкладов

    def op_refresh(self, _cx: OpCall, tgt: EntityState) -> None:
        tgt.refresh(self.now)

    def op_damage_taken(self, cx: OpCall, tgt: EntityState) -> float:
        """Урон, который этот вызов (cx.hits: deal/use_learned) уже нанёс цели: порог damage_total адаптации."""
        tid = entity_id(tgt.entity)
        return sum(h.damage for h in cx.hits or () if h.target == tid)

    # --- протокол Махораги (ops.OpHost; состояние в unit.external, см. src/core/adaptation.py) ---
    def op_adaptation(self, _cx: OpCall, tgt: EntityState) -> dict:
        return tgt.unit.external.setdefault("mahoraga", {})

    def set_adaptation(self, _cx: OpCall, tgt: EntityState, state: dict) -> None:
        tgt.unit.external["mahoraga"] = state

    def op_aggro(self, _cx: OpCall, tgt: EntityState) -> dict:
        return tgt.unit.external.setdefault("aggro", {})

    def set_aggro(self, _cx: OpCall, tgt: EntityState, **kv: Any) -> None:
        tgt.unit.external["aggro"] = dict(kv)

    def op_nested_ops(self, cx: OpCall, tgt: EntityState, ops: list) -> None:
        """on_adapt/on_max поддеревья: те же цели, что у родительской операции."""
        ent = tgt.entity
        primary = cx.primary if (cx.primary is not None and self.state(cx.primary) is not None) else ent
        self._run_ops(cx.source, ops, primary, f"{cx.src}.nested", cx.tags, cx.hits, center=None, radius=0.0)

    def _duration(self, d, ctx) -> float:
        if isinstance(d, (int, float)):
            return float(d)
        if isinstance(d, dict):
            base = resolve_value({"flat": d.get("base", d.get("flat")), "pct": d.get("pct"), "of": d.get("of")}, ctx)
            s = d.get("scale")
            if s:
                steps = math.floor(float(ctx.get(s["of"], 0.0)) / float(s["every"]))
                if s.get("cap") is not None:
                    steps = min(steps, s["cap"])
                base += steps * float((s.get("value") or {}).get("flat", 0.0)) * float(s.get("factor", 1.0))
            return base
        return DEFAULT_DEBUFF_SECONDS

    def _summon(self, st, o, ctx) -> None:
        if self.world is None or not hasattr(self.world, "spawn_summon"):
            return
        count = int(o.get("count", 1) or 1)
        x, y = position(st.entity)
        for i in range(count):
            ang = 2 * math.pi * i / max(1, count) + self.rng.random()
            self.world.spawn_summon(o.get("summon", "basic"), x + 2.5 * math.cos(ang), y + 2.5 * math.sin(ang),
                                    st.faction, int(getattr(st.entity, "level", 1) or 1), st.entity)

    def _move(self, st, tgt_st, o, primary) -> None:
        """Рывок к цели, отбрасывание, притягивание, переход за спину цели."""
        mode, dist = o.get("mode"), float(o.get("distance", 5.0) or 5.0)
        other = primary if tgt_st is st else st.entity   # от кого/к кому двигаться
        if other is None:
            return
        mx, my = position(tgt_st.entity)
        ox, oy = position(other)
        dx, dy = mx - ox, my - oy
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        if mode == "knockback":          # цель - от источника
            nx, ny = mx + ux * dist, my + uy * dist
        elif mode == "pull":             # цель - к источнику, до 1.5 от него
            step = max(0.0, min(dist, d - 1.5))
            nx, ny = mx - ux * step, my - uy * step
        elif mode == "charge":           # сам - к цели, до 1.5 от неё
            step = max(0.0, min(dist, d - 1.5))
            nx, ny = mx - ux * step, my - uy * step
        elif mode == "strafe":           # шаг в сторону, поперёк линии атаки
            side = 1.0 if self.rng.random() < 0.5 else -1.0
            nx, ny = mx - uy * dist * side, my + ux * dist * side
        else:                            # blink: за спину цели
            nx, ny = ox - ux * 1.5, oy - uy * 1.5
        if self.world is not None and hasattr(self.world, "clamp_position"):
            nx, ny = self.world.clamp_position(nx, ny)
        e = tgt_st.entity
        if hasattr(e, "move_to"):
            e.move_to(nx, ny)
        else:
            e.x, e.y = nx, ny

    # ---------------------------------------------------------------- resources
    def _spend(self, st: EntityState, res: str, amount: float, lethal: bool = False) -> None:
        if res == "hp":
            if lethal and amount >= st.resource("hp"):
                self._set_resource(st, "hp", 0.0)
            else:
                self._set_resource(st, "hp", st.resource("hp") - amount)
            return
        e = st.entity
        if hasattr(e, res):
            setattr(e, res, max(0.0, float(getattr(e, res)) - amount))

    def _heal(self, st: EntityState, res: str, amount: float) -> None:
        if res == "hp" and not is_alive(st.entity):
            return  # лечение не воскрешает
        if amount < 0:
            self._spend(st, res, -amount, lethal=True)
            return
        cap = getattr(st.entity, "max_health" if res == "hp" else f"max_{res}", None)
        cur = st.resource(res)
        new = cur + amount if cap is None else min(float(cap), cur + amount)
        if res == "hp":
            self._set_health(st, new)
        elif hasattr(st.entity, res):
            setattr(st.entity, res, new)

    def _set_resource(self, st: EntityState, res: str, value: float) -> None:
        if res == "hp":
            cap = float(getattr(st.entity, "max_health", value))
            revived = not is_alive(st.entity) and value > 0
            self._set_health(st, max(0.0, min(cap, value)), revive=revived)
        elif hasattr(st.entity, res):
            cap = getattr(st.entity, f"max_{res}", value)
            setattr(st.entity, res, max(0.0, min(float(cap), value)))

    def _set_health(self, st: EntityState, value: float, revive: bool = False) -> None:
        e = st.entity
        e.health = value
        if value <= 0:
            if hasattr(e, "is_defeated"):
                e.is_defeated = True
            if hasattr(e, "state") and isinstance(getattr(e, "state"), str):
                e.state = "dead"
        elif revive:
            if hasattr(e, "is_defeated"):
                e.is_defeated = False
            if getattr(e, "state", None) == "dead":
                e.state = "idle"
        hc = getattr(e, "_health_component", None)
        if hc is not None and hasattr(hc, "sync"):
            hc.sync(e.health, getattr(e, "max_health", e.health))

    # ---------------------------------------------------------------- damage
    def _hit_params(self, st: EntityState, tgt_st: EntityState, amount: float, flags: set, kind: str) -> tuple:
        """Один удар -> входы ядра (damage.PARAMS): поля сущностей (крит, уклонение, броня) и статы Unit."""
        src, tgt, cfg = st.entity, tgt_st.entity, damage.config()
        mine, theirs = st.unit._eff, tgt_st.unit._eff
        crit_mult = float(getattr(src, "critical_damage", cfg.crit_mult_default) or cfg.crit_mult_default)
        return (amount, float(damage.flag_bits(flags, theirs("broken") > 0.0)),
                mine("accuracy"), theirs("evasion"), float(getattr(tgt, "dodge_chance", 0.0) or 0.0),
                theirs("block_chance"), theirs("block_reduction"), float(getattr(src, "critical_chance", 0.0) or 0.0),
                crit_mult, mine("damage_" + kind), theirs("resist_" + kind), mine("resist_pen"),
                float(getattr(tgt, "defense", 0.0) or 0.0), mine("penetration_pct"), mine("penetration_flat"),
                theirs("damage_taken"))

    def _damage(self, st: EntityState, tgt_st: EntityState, amount: float, flags: set, ability: str,
                tags: tuple) -> Optional[HitInfo]:
        """Единый урон: конвейер damage.py (меткость, уклонение, блок, крит, тип, броня + пробитие, сопротивление,
        итоговые модификаторы) -> iframe -> HP -> лайфстил -> события."""
        src, tgt = st.entity, tgt_st.entity
        if not is_alive(tgt) or amount <= 0:
            return None
        info = HitInfo(entity_id(src), entity_id(tgt), 0.0, ability=ability)
        kind = damage.type_of_flags(flags)
        out = damage.roll_hit(self._hit_params(st, tgt_st, amount, flags, kind), self.rng, damage.config().consts)
        damage.fill_info(info, out, kind)
        if not info.landed:
            self._notify(info)
            if info.is_dodged:
                self.emit(tgt, "dodge", other=src)
            return info
        amount = out.final
        if tgt_st.invulnerable(self.now):
            info.invulnerable = True
            self._notify(info)
            return info
        amount = min(amount, tgt_st.resource("hp"))
        self._set_health(tgt_st, tgt_st.resource("hp") - amount)
        info.damage = amount
        info.killed = not is_alive(tgt)
        self._notify(info)
        self._after_hit(st, tgt_st, info, flags, tags)
        return info

    def _after_hit(self, st: EntityState, tgt_st: EntityState, info: HitInfo, flags: set, tags: tuple) -> None:
        """Лайфстил и события после нанесённого урона (attack_hit, crit, take_damage, kill, die)."""
        src, tgt, amount = st.entity, tgt_st.entity, info.damage
        is_attack = "attack" in tags
        if is_attack and float(getattr(src, "lifesteal", 0.0) or 0.0) > 0:
            self._heal(st, "hp", amount * float(src.lifesteal) / 100.0)
        if is_attack:
            self.emit(src, "attack_hit", other=tgt, last_damage=amount)
            if info.is_critical:
                self.emit(src, "crit", other=tgt, last_damage=amount)
        if "reflect" not in flags:
            self.emit(tgt, "take_damage", other=src, last_damage=amount)
        # since_hit обновляется ПОСЛЕ реакций: их условия видят время до этого удара
        tgt_st.runtime._last_hit_at = self.now
        if info.killed:
            src.kills = int(getattr(src, "kills", 0) or 0) + 1
            self.emit(src, "kill", other=tgt, last_damage=amount)
            self.emit(tgt, "die", other=src, last_damage=amount)

    # ---------------------------------------------------------------- describe
    def describe(self, entity) -> dict:
        st = self.state(entity)
        if st is None:
            return {}
        return {"buffs": st.buffs(self.now),
                "mods": {k: round(v, 2) for k, v in st.unit.mods.items() if abs(v) > 1e-9},
                "equipment_stats": dict(st.equipment_stats),
                "debuffs": len([1 for until, _l in st.external.values() if until > self.now]),
                "periodic": len(st.periodic),
                "cooldowns": {k: round(v - self.now, 1) for k, v in st.cooldowns.items() if v > self.now}}


def _in_arc(caster, primary, other, arc_deg: float) -> bool:
    """other в конусе arc_deg от caster в сторону primary (без цели - во все стороны)."""
    if primary is None:
        return True
    cx, cy = position(caster)
    px, py = position(primary)
    ox, oy = position(other)
    a = math.atan2(py - cy, px - cx)
    b = math.atan2(oy - cy, ox - cx)
    diff = abs((b - a + math.pi) % (2 * math.pi) - math.pi)
    return diff <= math.radians(arc_deg) / 2 + 1e-9 or math.dist((cx, cy), (ox, oy)) < 0.3


def _needs_target(ab: dict) -> bool:
    return any((o.get("target") in ("enemy", "source")) or (o.get("target") == "area" and o.get("center", "target") == "target")
               for o in ab.get("ops") or [])
