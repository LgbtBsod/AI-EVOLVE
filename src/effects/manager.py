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

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol

from .runtime import EffectRuntime, Unit, buff_fields, compute_amount, resolve_value, rules

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
    (регистратор боя в tools/probe_runtime.py читает source/target/damage/...)."""
    source: str
    target: str
    damage: float
    is_critical: bool = False
    is_dodged: bool = False
    ability: str = ""
    blocked: bool = False       # неуязвимость (iframe)
    killed: bool = False


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


# ================================================================ entity state

class EntityState:
    """Статы схемы одной сущности поверх её полей и рантайм её пассивов."""

    def __init__(self, entity, faction: str, abilities: Iterable[str] = ()):
        self.entity = entity
        self.faction = faction
        self.abilities = list(abilities)
        self.unit = Unit(entity_id(entity))
        self.items: list = []
        self.item_effects: list[dict] = []        # все эффекты надетых предметов
        self.extra_effects: list[dict] = []       # действующие части расходников (Тоник ярости)
        self.perk_effects: list[dict] = []        # перки характеристик (lua_content/perks.lua)
        self.equipment_stats: dict[str, float] = {}
        self.external: dict[Any, tuple[float, dict[str, float]]] = {}   # ключ -> (до, {стат: вклад})
        self.applied: dict[str, float] = {}
        self.cooldowns: dict[str, float] = {}      # способность -> когда готова
        self.fired_at: dict[str, float] = {}       # Effect.cooldown эффектов предметов
        self.buff_granted_at: dict[str, float] = {}
        self.periodic: list[dict] = []             # DoT/HoT на этой сущности
        self.zones: dict[str, bool] = {}           # hp_cross
        self.vision_vs: dict[Any, tuple[float, str, float]] = {}  # ключ -> (до, id цели, вклад в обзор на неё)
        self.weapon_ability: Optional[str] = None  # удар надетого оружия (item.attack)
        self.runtime = EffectRuntime(self.unit, [], enemy=Unit("nobody"))
        if not hasattr(entity, "lifesteal"):
            entity.lifesteal = 0.0
        if not hasattr(entity, "kills"):
            entity.kills = 0

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
        for k in list(u.base):
            u.base[k] = float(defaults.get(k, 0.0))
        for stat, (attr, scale, shift) in STAT_MAP.items():
            if attr in base:
                u.base[stat] = base[attr] * scale + shift
        u.base["move_speed"] = base.get(self._speed_attr(), float(defaults.get("move_speed", 5.0)))
        allocated = getattr(self.entity, "attributes", None) or {}
        for attr in rules()["attributes"]:
            u.base[attr] = float(allocated.get(attr, 0.0))   # очки уровня; предметы/эффекты - поверх
        for k, v in self.equipment_stats.items():
            u.base[k] = u.base.get(k, 0.0) + v
        for until, layer in self.external.values():
            if until > now:
                for k, v in layer.items():
                    u.base[k] = u.base.get(k, 0.0) + v
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
        attrs = rules()["attributes"]
        for stat, (attr, scale, shift) in STAT_MAP.items():
            if attr not in base:
                continue
            v = u._eff(stat)
            for a, conv in attrs.items():
                v += u._eff(a) * float(conv.get(stat, 0.0))
            value = (v - shift) / scale
            self.applied[attr] = value - base[attr]
            setattr(e, attr, value)
        speed = self._speed_attr()
        if speed in base:
            value = max(0.0, u._eff("move_speed"))
            self.applied[speed] = value - base[speed]
            setattr(e, speed, value)
        for res in ("health",) + POOLS:
            cap = getattr(e, "max_health" if res == "health" else f"max_{res}", None)
            if cap is not None and getattr(e, res, 0) > cap:
                setattr(e, res, cap)

    def refresh(self, now: float) -> None:
        base = self.pull(now)
        self.runtime._now = now
        if self.runtime.effects or self.runtime._op_contrib:
            self.runtime.refresh_passives(now)
        else:
            self.unit.mods = {}
        self.push_stats(base)

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
            r = o.get("radius", radius) or radius or 3.0
            r = float(st.unit.stat(r)) if isinstance(r, str) else float(r)   # radius = "attack_range"
            arc = float(o.get("arc", 0.0) or 0.0)       # конус к цели (взмах меча), 0 - полный круг
            cx, cy = center or (position(primary) if primary is not None and o.get("center", "target") == "target"
                                else position(st.entity))
            affects = o.get("affects", "all")      # френдли фаер: по умолчанию все в круге
            out = []
            for s in self.states.values():
                if not is_alive(s.entity) or math.dist((cx, cy), position(s.entity)) > r:
                    continue
                if (affects == "others" and s is st) or (affects == "enemies" and s.faction == st.faction) \
                        or (affects == "allies" and s.faction != st.faction):
                    continue
                if arc and s is not st and not _in_arc(st.entity, primary, s.entity, arc):
                    continue
                out.append(s.entity)
            return out
        return []

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
        kind = o.get("kind")
        other = tgt_st is not st
        default_stat = ("enemy_" if other else "") + (o.get("stat") or "hp") if o.get("stat") else None
        amount = compute_amount(o, ctx, default_stat)
        flags = set(o.get("flags") or ()) | ({"reflect"} if "reflect" in tags else set())
        if kind in ("deal", "heal") and o.get("every") and o.get("duration"):
            every = max(0.1, float(resolve_value(o["every"], ctx) if isinstance(o["every"], dict) else o["every"]))
            tgt_st.periodic.append({"kind": kind, "stat": o.get("stat") or "hp", "amount": amount, "every": every,
                                    "next": self.now + every, "until": self.now + self._duration(o["duration"], ctx),
                                    "flags": sorted(flags), "source": st.entity, "ability": src})
            return
        if kind == "deal":
            res = o.get("stat") or "hp"
            if res == "hp":
                hit = self._damage(st, tgt_st, amount, flags, src, tags)
                if hit:
                    hits.append(hit)
            else:
                self._spend(tgt_st, res, amount)
        elif kind == "heal":
            self._heal(tgt_st, o.get("stat") or "hp", amount)
        elif kind == "drain":
            res = o.get("stat") or "hp"
            if amount > tgt_st.resource(res):
                self._run_ops(st, o.get("fail") or [], primary, src + ".fail", tags, hits)
            else:
                self._spend(tgt_st, res, amount, lethal=True)
        elif kind == "set":
            self._set_resource(tgt_st, o.get("stat") or "hp", amount)
        elif kind == "mod":
            self._mod(st, tgt_st, o, ctx, src, idx)
        elif kind == "buff":
            self._buff(st, tgt_st, o, ctx, src)
        elif kind == "extend":
            b = tgt_st.unit.buffs.get(o.get("buff_id"))
            ext = o.get("extend") or (b or {}).get("extend") or {}
            if b and (not ext.get("on") or src.endswith("#" + ext["on"])):
                b["until"] += float(ext.get("flat", 0.0))
        elif kind == "remove_buff":
            tgt_st.unit.buffs.pop(o.get("buff_id"), None)
        elif kind == "apply_effect":
            ef = next((e for e in st.all_effects() if e.get("id") == o.get("buff_id")), None) \
                or self.ability(o.get("buff_id"))
            if ef:
                self._run_ops(st, ef.get("ops") or [], primary, f"{src}->{ef['id']}", tags, hits)
        elif kind == "kill":
            if is_alive(tgt_st.entity):
                hit = self._damage(st, tgt_st, tgt_st.resource("hp"), {"true_damage", "no_crit", "unavoidable"}, src, tags)
                if hit:
                    hits.append(hit)
        elif kind == "summon":
            self._summon(st, o, ctx)
        elif kind == "move":
            self._move(st, tgt_st, o, primary)

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

    def _mod(self, st, tgt_st, o, ctx, src, idx) -> None:
        stat = o.get("stat")
        if o.get("toward") == "source":
            # обзор цели в сторону заклинателя (стелс); на себя смысла не имеет
            if tgt_st is not st:
                scratch: dict[str, float] = {}
                st.runtime._apply_mod(o, ctx, tgt_st.unit, sink=scratch)
                until = self.now + (self._duration(o["duration"], ctx) if o.get("duration") is not None
                                    else DEFAULT_DEBUFF_SECONDS)
                tgt_st.vision_vs[(entity_id(st.entity), src, idx)] = (until, entity_id(st.entity),
                                                                     scratch.get(stat, 0.0))
            return
        timed = o.get("duration") is not None or tgt_st is not st
        if not timed:
            # событийный мод на себя: вклад операции заменяет прошлый (семантика схемы)
            before = st.unit.mods.get(stat, 0.0)
            key = (src, idx)
            old = st.runtime._op_contrib.get(key)
            if old:
                st.unit.mods[old[1]] = st.unit.mods.get(old[1], 0.0) - old[2]
            st.runtime._apply_mod(o, ctx, st.unit)
            st.runtime._op_contrib[key] = (st.unit, stat, st.unit.mods.get(stat, 0.0) - before)
            st.refresh(self.now)
            return
        scratch: dict[str, float] = {}
        st.runtime._apply_mod(o, ctx, tgt_st.unit, sink=scratch)
        until = self.now + (self._duration(o["duration"], ctx) if o.get("duration") is not None else DEFAULT_DEBUFF_SECONDS)
        tgt_st.external[(entity_id(st.entity), src, idx)] = (until, scratch)
        tgt_st.refresh(self.now)

    def _buff(self, st, tgt_st, o, ctx, src) -> None:
        bid = o.get("buff_id")
        cd = resolve_value(o["cooldown"], ctx) if o.get("cooldown") else None
        granted = st.buff_granted_at.get(bid)
        if cd is not None and granted is not None and self.now - granted < cd:
            return
        prev = tgt_st.unit.buffs.get(bid)
        until = max(prev.get("until", self.now) if prev else self.now, self.now) + self._duration(o.get("duration"), ctx)
        st.buff_granted_at[bid] = self.now
        tgt_st.unit.buffs[bid] = {"until": until, "extend": o.get("extend"), "flags": list(o.get("flags") or [])}
        tgt_st.refresh(self.now)

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
    def _damage(self, st: EntityState, tgt_st: EntityState, amount: float, flags: set, ability: str,
                tags: tuple) -> Optional[HitInfo]:
        """Единый урон: уклонение -> крит -> броня -> iframe -> HP -> лайфстил -> события."""
        src, tgt = st.entity, tgt_st.entity
        if not is_alive(tgt) or amount <= 0:
            return None
        info = HitInfo(entity_id(src), entity_id(tgt), 0.0, ability=ability)
        certain = {"true_damage", "unavoidable", "periodic"} & flags
        if not certain and self.rng.random() < float(getattr(tgt, "dodge_chance", 0.0) or 0.0):
            info.is_dodged = True
            self._notify(info)
            self.emit(tgt, "dodge", other=src)
            return info
        if "no_crit" not in flags and "periodic" not in flags and \
                self.rng.random() < float(getattr(src, "critical_chance", 0.0) or 0.0):
            info.is_critical = True
            amount *= float(getattr(src, "critical_damage", 1.5) or 1.5)
        if "true_damage" not in flags:
            amount = max(1.0, amount - float(getattr(tgt, "defense", 0.0) or 0.0))
        if tgt_st.invulnerable(self.now):
            info.blocked = True
            self._notify(info)
            return info
        amount = min(amount, tgt_st.resource("hp"))
        self._set_health(tgt_st, tgt_st.resource("hp") - amount)
        info.damage = amount
        info.killed = not is_alive(tgt)
        self._notify(info)
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
        return info

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
