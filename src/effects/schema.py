"""
Effect Schema v1 -- "Effect -> Ops[]" (universal structure)

Единая схема для всех эффектов предметов/скиллов/буфф:

    Effect  = триггер + список операций (ops)
    Op      = универсальная операция (mod/heal/drain/deal/buff/set/kill/...)
    Value   = {flat|pct|ref, of}
    Scale   = "за каждые N единиц X добавить Y"
    Trigger = passive | condition | event

Python-представление == JSON == Lua table (1-в-1).
Предикаты хранятся как именованные строки ("named_pred") или выражения,
поэтому вся схема сериализуема.

Примеры готовых эффектов: presets.py
Генератор Lua: lua_gen.py, парсер: lua_parse.py, валидатор: validate.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Union

SCHEMA_VERSION = "effect-schema/1"

# ---------------------------------------------------------------- enums

OP_KINDS = {
    "mod",          # модификация стата (бафф/дебафф через модификатор)
    "heal",         # лечение
    "drain",        # стоимость из ресурса (может провалиться -> fail ветка)
    "deal",         # нанесение урона
    "set",          # жёсткая установка значения
    "buff",         # повесить эффект/бафф по buff_id
    "extend",       # продлить таймер существующего баффа
    "remove_buff",  # снять бафф
    "apply_effect",  # применить другой эффект по id
    "kill",         # убить цель
    "summon",       # призвать существ: summon = тип, count = сколько (менеджер эффектов)
    "move",         # переместить: mode = charge | knockback | pull | blink | strafe | dash | push | teleport | swap, distance
    "stance",       # форма-стойка: id, exclusive_group, conflict_with, duration, on_enter/on_exit ops (docs/EFFECT_SCHEMA.md "Forms")
    "transform",    # stance + stats (mod-ops, пока форма активна) + abilities {add, remove}
    "timed_power_up",  # временное усиление: transform со своей группой; duration обязателен, on_exit = расплата
    "hypnosis", "command", "possess", "dominance", "temptation", "tame",   # контроль цели (src/effects/control.py, docs/EFFECT_SCHEMA.md "Control")

    # --- примитивы боя (аудит Сукуна/Годжо/Тоджи): все через существующие поля Op ---
    "resist",       # временный резист типа урона: damage_type + value (+ duration) -> mod resist_<тип>
    "immune",       # иммунитет типа / статуса / эффекта-действия: damage_type|status|effect + value -> 100% resist / block
    "mark",         # метка на цели: mark_id + value + duration; stack-правило max_stacks; ctx.mark_<id> для scale
    "detonate",     # взорвать метки: mark_id + value/scale (по ref mark_<id>) -> deal true_damage и обнуление
    "purge",        # снять эффекты по фильтру: filter {kind="buff"|"debuff"|"mark"|"all", tag=...}
    "nullify",      # отменить активные силы цели: what {"abilities","effects","barriers"} -> блок кастов на duration
    "cancel_technique",  # Копьё Неба: прервать ТЕКУЩУЮ технику при касании (+ nullify на duration)
    "block",        # запрет действия/способности: stat=<действие> ("cursed_technique","domain_expansion",...)
    "absorb_damage",# Поглощающее Облако: копить входящий урон в self.absorbed_kinetic за окно window
    "binding_vow",  # обет: cost (чем платим) + gain ops (что получаем); vow_id -> метка для purge/ссылок
    "sever",        # разрыв связи (душа-тело, техника): what + duration -> блок регена/техники цели
    "untargetable", # невыбираемость селекторами до duration (Todji для six_eyes/en/divination)
    "learn",        # скопировать технику: from=ctx.observed_technique -> постоянная способность (Sukuna/Mahoraga)
    "adapt",        # адаптация Махораги: после попадания по типу - permanent resist_<тип> += rate*stacks

    # --- примитивы спецификации Махораги (ЧАСТЬ 2 справочника; runtime: src/core/adaptation.py) ---
    # ядро адаптации
    "unadapt",            # сброс адаптации к феномену: memory_key/sign -> освобождает слот колеса
    "reset_adaptation",   # полный сброс колеса (wheel=0, память очищается)
    "use_learned_technique",  # применить украденную технику: from=spells, pick=highest_threat|random|last
    "observe_phenomenon",     # зарегистрировать попадание феномена в AdaptationState (без урона — observe)
    "register_phenomenon",    # записать подпись феномена в реестр/память носителя
    # фракция / агро
    "set_faction",        # faction = "feral" | ... (FactionManager)
    "set_aggro",          # aggro_mode = имя режима (nearest_any | threat_first | random_feral)
    "set_targeting",      # targeting = TargetingSpec {mode, filter, switch_on, switch_interval}
    "retarget",           # сменить текущую цель (target_ref = id|nil)
    "clear_aggro",        # сбросить агро и цель
    # эскалация
    "escalate",           # escalate_delta (или value.flat): +N к колесу/уровню эскалации
    "deescalate",         # откат эскалации на N (для rewind-механик)
    "trigger_true_form",  # активация истинной формы (обычно на wheel_max)
    # колесо (визуал + счётчик)
    "rotate_wheel",       # wheel_delta (или value.delta): оборот колеса; порог -> on_wheel_max
    "display_wheel",      # показать состояние колеса (UI; mode="golden" в true form)
    "halt_wheel",         # остановить вращение (визуал; счётчик не трогается)
}

# поля Op из спецификации Махораги (ЧАСТЬ 3.1) — расширенные опциональные поля
MAHORAGA_OP_FIELDS = {
    "phenomenon", "faction", "aggro_mode", "targeting", "wheel_delta",
    "escalation_delta", "threshold", "permanent", "memory_key",
    "source_filter", "exclude_self", "exclude_owner", "max_stacks",
}

# kinds, которые пишутся контентом как planned-обработчики над buff-слоем (op_buff переиспользуется хостом)
BUFF_BACKED_KINDS = {"block", "nullify", "cancel_technique", "untargetable", "sever", "binding_vow"}

MOVE_MODES = {"charge", "knockback", "pull", "blink", "strafe"}
MOVE_MODES_SPEC = {"dash", "push", "teleport", "swap"}   # names of the spec kinds (kind_aliases.lua params); accepted next to MOVE_MODES

# area - ВСЕ живые в радиусе (radius; center = "target" | "self"): френдли фаер,
# заклинатель тоже попадает под свой круг. affects сужает круг:
#   all (по умолчанию) | others (все, кроме заклинателя) | enemies | allies
TARGETS = {"self", "enemy", "ally", "allies", "source", "area"}
AREA_AFFECTS = {"all", "others", "enemies", "allies"}
# arc (градусы, 0 < arc <= 360) - конус от заклинателя к цели: взмах меча/топора.
# radius - число или имя стата ("attack_range": дуга на длину клинка)

# toward (только mod стата vision_range): мод действует лишь на обзор В СТОРОНУ
# источника - стелс: «в круге тебя видят на 70% хуже», остальных - как прежде
TOWARD = {"source"}
TOWARD_STATS = {"vision_range"}

OPS = {"add", "sub", "mul", "div", "set", "min", "max"}

# applied: эффект без собственного триггера, его запускает apply_effect другого эффекта
TRIGGER_KINDS = {"passive", "condition", "event", "applied"}

EVENTS = {
    "use", "attack", "attack_hit", "cast", "crit", "dodge",
    "kill", "take_damage", "die", "hp_cross", "on_shield_break",
    "combat_start", "combat_end", "tick",
}
# события из схемы, которые ни один хост пока не шлёт: подписка на них молча не сработает (itemcheck предупреждает)
NEVER_EMITTED_EVENTS = frozenset({"on_shield_break", "combat_start", "combat_end"})

# известные статы (не закрытый список; кастомные -- через "custom:<name>")
KNOWN_STATS = {
    # ресурсы (текущее значение) и их максимум/реген - как у Character в игре
    "hp", "max_hp", "hp_regen",
    "mana", "max_mana", "mana_regen",
    "stamina", "max_stamina", "stamina_regen",
    "hp_pct", "hp_missing", "hp_missing_below_40",
    # атрибуты (src/systems/attributes/attribute_system.py: BaseAttribute)
    "strength", "agility", "intelligence", "vitality", "wisdom", "charisma", "luck", "endurance",
    # боевые статы
    "defense", "aspd", "crit_chance", "crit_dmg", "lifesteal", "tenacity", "move_speed",
    "attack_damage", "spell_power", "dodge", "kills",
    # дальность удара оружием и обзора (как далеко сущность замечает других)
    "attack_range", "vision_range",
    # псевдо-стат runtime: фактический урон последнего удара героя
    # (ctx.last_damage в sim; источник для heal {"pct": N, "of": "last_damage"})
    "last_damage",
}

# ctx-поля, доступные только как источник (value.of / scale.of), но не как цель op
CONTEXT_ONLY_STATS = {"hp_missing", "hp_missing_below_40", "kills", "last_damage", "hp_pct"}

# ресурсы: текущее значение меняют heal/drain/deal/set, максимум - стат max_<ресурс>
# (lua_content/effect_rules.lua -> resources); mod по ресурсу ничего бы не сделал
RESOURCE_STATS = {"hp", "mana", "stamina"}

from .damage import CERTAIN_FLAGS  # noqa: E402  (единый источник: true_damage/unavoidable/periodic)

FLAGS = {"no_crit", "silent", "iframe"} | set(CERTAIN_FLAGS)

# префиксы контекста цели/союзников (sim.target_ctx): enemy_hp_pct, ally_kills ...
TARGET_PREFIXES = ("enemy_", "ally_", "allies_", "source_")


def is_stat(name: str) -> bool:
    """Валидное имя стата/ctx-поля (включая префиксные enemy_*/ally_*)."""
    if not isinstance(name, str) or not name:
        return False
    if name.startswith("custom:"):
        return True
    for pfx in TARGET_PREFIXES:
        if name.startswith(pfx):
            name = name[len(pfx):]
            break
    return name in KNOWN_STATS or is_derived_stat(name) or name in registry_stats()


def is_derived_stat(name: str) -> bool:
    """Псевдо-стат, который считается от ctx (`hp_missing_below_<N>`...): только источник value.of / scale.of, писать в него нельзя.
    Определение семейства - ops.derived_ctx (одно место), здесь только вопрос «это оно?»."""
    from .ops import derived_ctx
    return derived_ctx(name) is not None


def registry_stats() -> set[str]:
    """Статы, объявленные в lua_content/effect_rules.lua (defaults): единственный реестр новых статов, без копии здесь."""
    from .runtime import rules
    return set(rules()["defaults"])


# ---------------------------------------------------------------- descriptors

@dataclass
class Value:
    """Value descriptor: flat | pct(+of) | ref."""
    flat: Optional[float] = None
    pct: Optional[float] = None       # процент (от `of`, иначе от op.stat)
    of: Optional[str] = None          # от какого стата брать pct
    ref: Optional[str] = None         # ссылка на поле контекста, "ctx.strength"

    def to_json(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        return d

    @staticmethod
    def from_json(d: dict) -> "Value":
        return Value(**{k: d.get(k) for k in ("flat", "pct", "of", "ref")})


@dataclass
class Scale:
    """Scale descriptor: base + floor(ctx[of]/every) * value * factor."""
    every: float
    of: str                            # псевдо-стат из ctx
    value: Optional[Value] = None      # что добавлять за шаг
    factor: float = 1.0
    cap: Optional[float] = None        # максимум шагов
    floor: Optional[float] = None      # минимум

    def to_json(self) -> dict:
        d = {"every": self.every, "of": self.of, "factor": self.factor}
        if self.value is not None:
            d["value"] = self.value.to_json()
        if self.cap is not None:
            d["cap"] = self.cap
        if self.floor is not None:
            d["floor"] = self.floor
        return {k: v for k, v in d.items() if v is not None}

    @staticmethod
    def from_json(d: dict) -> "Scale":
        v = d.get("value")
        return Scale(
            every=d["every"], of=d["of"],
            value=Value.from_json(v) if isinstance(v, dict) else None,
            factor=d.get("factor", 1.0),
            cap=d.get("cap"), floor=d.get("floor"),
        )


@dataclass
class Trigger:
    kind: str = "passive"              # passive | condition | event | applied
    event: Optional[str] = None        # для kind=event
    when: Optional[str] = None         # именованный предикат или выражение
    filter: Optional[str] = None       # доп. фильтр события
    owner_has: Optional[str] = None    # id родительского эффекта (sub-effect)
    cross: Optional[str] = None        # event=hp_cross: имя зоны (эффект с threshold)

    def to_json(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @staticmethod
    def from_json(d: dict) -> "Trigger":
        return Trigger(**{k: d.get(k) for k in
                          ("kind", "event", "when", "filter", "owner_has", "cross")})


# ---------------------------------------------------------------- Op

@dataclass
class Op:
    kind: str                                        # OP_KINDS
    target: str = "self"                             # TARGETS
    stat: Optional[str] = None                       # что трогаем (None для buff/deal)
    op: Optional[str] = None                         # OPS
    value: Optional[Value] = None
    scale: Optional[Scale] = None
    when: Optional[str] = None                       # условие на операцию
    fail: list = field(default_factory=list)         # Op[] при провале (drain)
    duration: Optional[dict] = None                  # Value/Scale dict (для buff)
    cooldown: Optional[dict] = None                  # Value dict (для buff)
    extend: Optional[dict] = None                    # {on, flat|pct} (для buff)
    buff_id: Optional[str] = None
    flags: list = field(default_factory=list)

    def to_json(self) -> dict:
        d: dict[str, Any] = {"kind": self.kind, "target": self.target}
        if self.stat:
            d["stat"] = self.stat
        if self.op:
            d["op"] = self.op
        if self.value:
            d["value"] = self.value.to_json()
        if self.scale:
            d["scale"] = self.scale.to_json()
        if self.when:
            d["when"] = self.when
        if self.fail:
            d["fail"] = [o.to_json() for o in self.fail]
        for k in ("duration", "cooldown", "extend", "buff_id"):
            v = getattr(self, k)
            if v:
                d[k] = v
        if self.flags:
            d["flags"] = list(self.flags)
        return d

    @staticmethod
    def from_json(d: dict) -> "Op":
        v = d.get("value")
        s = d.get("scale")
        return Op(
            kind=d["kind"], target=d.get("target", "self"),
            stat=d.get("stat"), op=d.get("op"),
            value=Value.from_json(v) if isinstance(v, dict) else None,
            scale=Scale.from_json(s) if isinstance(s, dict) else None,
            when=d.get("when"),
            fail=[Op.from_json(x) for x in d.get("fail", [])],
            duration=d.get("duration"), cooldown=d.get("cooldown"),
            extend=d.get("extend"), buff_id=d.get("buff_id"),
            flags=list(d.get("flags", [])),
        )


# ---------------------------------------------------------------- Effect

@dataclass
class Effect:
    id: str
    trigger: Trigger
    ops: list = field(default_factory=list)          # Op[]
    tags: list = field(default_factory=list)
    duration: Optional[dict] = None                  # Value/Scale dict, nil = пока триггер true
    cooldown: Optional[dict] = None
    stacks: Optional[dict] = None
    # Усиление ВСЕХ бонусов (mod add/sub) эффекта: пока `when` истинно,
    # множитель factor^floor(ctx[of] / every). Lost My Self: при HP = 1 бонусы
    # x2 за каждые 10% ниже 40% -> {when="ctx.hp <= 1", every=10,
    # of="hp_missing_below_40", factor=2}. Универсально - не поле под предмет.
    amplify: Optional[dict] = None
    # condition-эффект с порогом HP объявляет зону: при пересечении порога
    # шлётся событие hp_cross (trigger.cross = meta.name или id эффекта)
    threshold: Optional[float] = None
    meta: Optional[dict] = None                      # name/description/icon... для UI

    def to_json(self) -> dict:
        d: dict[str, Any] = {"id": self.id, "trigger": self.trigger.to_json(),
                             "ops": [o.to_json() for o in self.ops]}
        if self.tags:
            d["tags"] = list(self.tags)
        if self.threshold is not None:
            d["threshold"] = self.threshold
        for k in ("duration", "cooldown", "stacks", "amplify", "meta"):
            v = getattr(self, k)
            if v:
                d[k] = v
        return d

    @staticmethod
    def from_json(d: dict) -> "Effect":
        return Effect(
            id=d["id"],
            trigger=Trigger.from_json(d.get("trigger", {"kind": "passive"})),
            ops=[Op.from_json(o) for o in d.get("ops", [])],
            tags=list(d.get("tags", [])),
            duration=d.get("duration"), cooldown=d.get("cooldown"),
            stacks=d.get("stacks"), amplify=d.get("amplify"),
            threshold=d.get("threshold"), meta=d.get("meta"),
        )

    # -- convenience -----------------------------------------------------
    def dump(self, **kw) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, indent=2, **kw)
