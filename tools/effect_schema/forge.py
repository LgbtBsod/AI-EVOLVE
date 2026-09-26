"""Кузница предметов: генератор предметов для стресс-проверки всей схемы.

forge_item() собирает предмет, который задействует ВСЁ, что умеет Effect
Schema: каждый изменяемый стат с каждой операцией (add/sub/mul/div/set/
min/max) и каждой формой значения (flat, pct, pct of, ref), scale с cap/
floor/factor, все события, все цели, все флаги, баффы с длительностью,
кулдауном, продлением и iframe, extend/remove_buff/apply_effect-цепочки,
kill, owner_has, amplify (when и while_buff), зону hp_cross, ресурсы hp,
mana и stamina, кулдаун эффекта. Сверху - N случайных эффектов со сложными
условиями получения (цепочки сравнений, and/or, арифметика, max/min/floor/
ceil/abs, %, **).

hostile=True снимает ограничения генератора условий (деление на выражения,
возведение в любую степень): так itemcheck ищет расхождения Python и Lua.

Результат детерминирован по seed. Проверка - itemcheck.check_item().
"""
from __future__ import annotations

import random
from typing import Optional

from .schema import CONTEXT_ONLY_STATS, EVENTS, FLAGS, KNOWN_STATS, OPS, RESOURCE_STATS, TARGETS

WRITABLE = sorted(KNOWN_STATS - CONTEXT_ONLY_STATS - RESOURCE_STATS)
RESOURCES = sorted(RESOURCE_STATS)
# поля контекста, которые видят условия и value.of/ref (sim.EffectRuntime.context)
CTX_OWN = WRITABLE + RESOURCES + ["hp_pct", "hp_missing", "hp_missing_below_40", "kills"]
CTX_FIELDS = CTX_OWN + ["enemy_hp", "enemy_max_hp", "enemy_hp_pct", "enemy_defense", "last_damage"]
_CMP = ["<", "<=", ">", ">=", "==", "!="]


# ---------------------------------------------------------------- conditions

class PredGen:
    """Случайные булевы условия на языке схемы (sim.eval_pred / pred_lua.to_lua)."""

    def __init__(self, rng: random.Random, hostile: bool = False):
        self.rng = rng
        self.hostile = hostile

    def _const(self) -> str:
        r = self.rng
        v = r.choice([0, 1, 2, 3, 5, 10, 25, 40, 50, 100, 250, 1000]) if r.random() < 0.7 \
            else round(r.uniform(-50, 500), 2)
        return repr(v)

    def _field(self) -> str:
        return "ctx." + self.rng.choice(CTX_FIELDS)

    def num(self, depth: int = 2) -> str:
        r = self.rng
        if depth <= 0 or r.random() < 0.3:
            return self._field() if r.random() < 0.7 else self._const()
        a, b = self.num(depth - 1), self.num(depth - 1)
        if b in ("0", "0.0"):  # деление на литерал 0 валидатор отвергает; на выражение - можно
            b = self._field()
        pick = r.randrange(9)
        if pick <= 2:
            return f"({a} {r.choice('+-*')} {b})"
        if pick == 3:  # деление: в «мирном» режиме - на ненулевую константу
            return f"({a} / {b})" if self.hostile else f"({a} / {r.choice([2, 3, 4, 10, 0.5])})"
        if pick == 4:
            return f"({a} % {b})" if self.hostile else f"({a} % {r.choice([2, 3, 7, 10])})"
        if pick == 5:
            return f"({a} ** {b})" if self.hostile else f"(abs({a}) ** {r.choice([0.5, 2])})"
        if pick == 6:
            return f"{r.choice(['max', 'min'])}({a}, {b})"
        if pick == 7:
            return f"{r.choice(['floor', 'ceil', 'abs'])}({a})"
        return f"(-{a})"

    def cond(self, depth: int = 2) -> str:
        r = self.rng
        if depth <= 0 or r.random() < 0.45:
            if r.random() < 0.2:  # цепочка сравнений: a < b <= c
                return f"{self.num(1)} {r.choice(['<', '<='])} {self.num(1)} {r.choice(['<', '<='])} {self.num(1)}"
            return f"{self.num(depth)} {r.choice(_CMP)} {self.num(depth)}"
        parts = [self.cond(depth - 1) for _ in range(r.randint(2, 3))]
        return "(" + f" {r.choice(['and', 'or'])} ".join(parts) + ")"


# ---------------------------------------------------------------- op builders

def _value(form: int, stat: str, rng: random.Random) -> dict:
    """0: flat, 1: pct (своего стата), 2: pct of другого поля, 3: ref."""
    if form == 0:
        return {"flat": round(rng.uniform(1, 20), 2)}
    if form == 1:
        return {"pct": round(rng.uniform(1, 15), 2)}
    if form == 2:
        return {"pct": round(rng.uniform(0.5, 5), 2), "of": rng.choice(CTX_OWN)}
    return {"ref": "ctx." + rng.choice([f for f in CTX_OWN if f != stat])}


def _mod(stat: str, op: str, form: int, rng: random.Random, target: str = "self") -> dict:
    o = {"kind": "mod", "target": target, "stat": stat, "op": op}
    if op in ("mul", "div"):
        o["value"] = {"flat": round(rng.uniform(1.01, 1.25), 3)}
    elif op in ("set", "min", "max"):
        o["value"] = {"flat": round(rng.uniform(1, 200), 2)} if form % 2 == 0 else {"ref": "ctx." + stat}
    else:
        o["value"] = _value(form, stat, rng)
        if form == 1:
            o["scale"] = {"every": rng.choice([5, 10, 20]), "of": rng.choice(["hp_missing_below_40", "kills", "hp_missing"]),
                          "value": {"flat": round(rng.uniform(0.5, 5), 2)}, "factor": rng.choice([1, 1.5, 2]),
                          "cap": rng.choice([3, 5, 10]), "floor": 0}
    return o


# ---------------------------------------------------------------- coverage block

def coverage_effects(rng: random.Random, preds: PredGen) -> list[dict]:
    """Детерминированный блок: каждая часть схемы хотя бы один раз."""
    effs: list[dict] = []
    # 1) каждый стат x каждая операция x формы значения; passive и condition по очереди
    for i, stat in enumerate(WRITABLE):
        ops = [_mod(stat, op, (i + j) % 4, rng) for j, op in enumerate(sorted(OPS))]
        trigger = {"kind": "passive"} if i % 2 == 0 else {"kind": "condition", "when": preds.cond(2)}
        effs.append({"id": f"stat.{stat}", "tags": ["forge", "stat"], "trigger": trigger, "ops": ops})

    # 2) каждое событие: ресурсы hp/mana, урон, дебафф врага, условие на операцию
    targets = sorted(TARGETS)
    for k, event in enumerate(sorted(EVENTS)):
        res = RESOURCES[k % len(RESOURCES)]  # hp / mana / stamina по очереди
        ops = [
            {"kind": "heal", "target": "self", "stat": "hp", "op": "add", "value": {"pct": 1, "of": "max_hp"}},
            {"kind": "drain", "target": "self", "stat": res, "op": "sub", "value": {"flat": 15},
             "fail": [{"kind": "heal", "target": "self", "stat": res, "op": "add", "value": {"pct": 50, "of": f"max_{res}"}}]},
            {"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"pct": 2, "of": "enemy_max_hp"},
             "when": preds.cond(1), "flags": [sorted(FLAGS)[k % len(FLAGS)]]},
            {"kind": "deal", "target": "enemy", "stat": RESOURCES[(k + 1) % len(RESOURCES)], "op": "sub",
             "value": {"flat": 5}},
            {"kind": "mod", "target": "enemy", "stat": "defense", "op": "sub", "value": {"flat": 1}},
            {"kind": "mod", "target": targets[k % len(targets)], "stat": WRITABLE[k % len(WRITABLE)],
             "op": "add", "value": {"flat": 1}},
        ]
        effs.append({"id": f"event.{event}", "tags": ["forge", "event"],
                     "trigger": {"kind": "event", "event": event, "filter": preds.cond(2)}, "ops": ops})

    # 3) баффы: iframe-щит (длительность, кулдаун, продление за kill), ярость со scale-длительностью
    effs.append({"id": "buff.grant", "tags": ["forge", "buff"], "trigger": {"kind": "event", "event": "use"}, "ops": [
        {"kind": "buff", "target": "self", "buff_id": "forge_shield", "flags": ["iframe"],
         "duration": {"flat": 3}, "cooldown": {"flat": 5}, "extend": {"on": "kill", "flat": 1}},
        {"kind": "buff", "target": "self", "buff_id": "forge_rage",
         "duration": {"base": 2, "scale": {"every": 10, "of": "hp_missing_below_40", "value": {"flat": 1}, "cap": 3}}},
        {"kind": "set", "target": "self", "stat": "mana", "op": "set", "value": {"pct": 50, "of": "max_mana"}},
        {"kind": "set", "target": "self", "stat": "stamina", "op": "set", "value": {"pct": 75, "of": "max_stamina"}},
    ]})
    effs.append({"id": "buff.extend", "tags": ["forge", "buff"], "trigger": {"kind": "event", "event": "kill"},
                 "ops": [{"kind": "extend", "target": "self", "buff_id": "forge_rage", "extend": {"on": "kill", "flat": 2}}]})
    effs.append({"id": "buff.remove", "tags": ["forge", "buff"], "trigger": {"kind": "event", "event": "take_damage"},
                 "ops": [{"kind": "remove_buff", "target": "self", "buff_id": "forge_rage", "when": "ctx.hp_pct < 20"}]})

    # 4) цепочка apply_effect: attack_hit -> chain.b -> chain.c (applied - только через apply_effect)
    effs.append({"id": "chain.a", "tags": ["forge", "chain"], "trigger": {"kind": "event", "event": "attack_hit"},
                 "ops": [{"kind": "apply_effect", "target": "enemy", "buff_id": "chain.b"}]})
    effs.append({"id": "chain.b", "tags": ["forge", "chain"], "trigger": {"kind": "applied"},
                 "ops": [{"kind": "apply_effect", "target": "enemy", "buff_id": "chain.c"},
                         {"kind": "mod", "target": "enemy", "stat": "defense", "op": "sub", "value": {"flat": 2}}]})
    effs.append({"id": "chain.c", "tags": ["forge", "chain"], "trigger": {"kind": "applied"},
                 "ops": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 3},
                          "flags": ["true_damage"]}]})

    # 4b) по площади, призыв, урон и лечение со временем (менеджер эффектов игры)
    effs.append({"id": "area.nova", "tags": ["forge", "area"], "trigger": {"kind": "event", "event": "cast"},
                 "ops": [{"kind": "deal", "target": "area", "radius": 4, "center": "self", "stat": "hp", "op": "sub",
                          "value": {"pct": 80, "of": "spell_power"}},
                         {"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 2},
                          "every": 1, "duration": {"flat": 3}, "flags": ["true_damage"]},
                         {"kind": "heal", "target": "self", "stat": "hp", "op": "add", "value": {"flat": 3},
                          "every": 1, "duration": {"flat": 3}},
                         {"kind": "summon", "target": "self", "summon": "skeleton", "count": 2},
                         {"kind": "move", "target": "enemy", "mode": "knockback", "distance": 3}]})

    # 5) казнь, owner_has, кулдаун эффекта
    effs.append({"id": "execute", "tags": ["forge"], "trigger": {"kind": "event", "event": "attack"},
                 "ops": [{"kind": "kill", "target": "enemy", "when": "ctx.enemy_hp_pct < 10"}]})
    effs.append({"id": "sub.strength", "tags": ["forge"], "cooldown": {"flat": 1},
                 "trigger": {"kind": "event", "event": "attack", "owner_has": "stat.strength"},
                 "ops": [{"kind": "deal", "target": "source", "stat": "hp", "op": "sub", "value": {"flat": 1}}]})

    # 6) amplify по условию и пока активен бафф; именованное условие из effect_rules.lua
    effs.append({"id": "amp.low_hp", "tags": ["forge", "amplify"],
                 "trigger": {"kind": "condition", "when": "low_hp_40"},
                 "amplify": {"when": "ctx.hp <= 1", "every": 10, "of": "hp_missing_below_40", "factor": 2},
                 "ops": [{"kind": "mod", "target": "self", "stat": "strength", "op": "add", "value": {"pct": 20}},
                         {"kind": "mod", "target": "self", "stat": "crit_chance", "op": "add", "value": {"flat": 5},
                          "scale": {"every": 10, "of": "hp_missing_below_40", "value": {"flat": 5}}}]})
    effs.append({"id": "amp.rage", "tags": ["forge", "amplify"], "trigger": {"kind": "passive"},
                 "amplify": {"while_buff": "forge_rage", "every": 1, "of": "kills", "factor": 1.1},
                 "ops": [{"kind": "mod", "target": "self", "stat": "aspd", "op": "add", "value": {"flat": 0.1}}]})

    # 7) зона hp_cross и реакция на пересечение
    effs.append({"id": "zone.half", "tags": ["forge", "zone"], "threshold": 50,
                 "meta": {"name": "Half HP"},
                 "trigger": {"kind": "condition", "when": "ctx.hp_pct < 50"},
                 "ops": [{"kind": "mod", "target": "self", "stat": "defense", "op": "add", "value": {"flat": 10}}]})
    effs.append({"id": "zone.half.cross", "tags": ["forge", "zone"],
                 "trigger": {"kind": "event", "event": "hp_cross", "cross": "Half HP"},
                 "ops": [{"kind": "heal", "target": "ally", "stat": "hp", "op": "add", "value": {"flat": 25}}]})
    return effs + primitive_effects()


def primitive_effects() -> list[dict]:
    """Примитивы боя (аудит Сукуна / Годжо / Тоджи) и Махораги: каждый kind схемы, что не покрыт блоком выше, ровно в
    одном эффекте-группе. Поля - как читают обработчики src/effects/ops.py; события подобраны так, чтобы метка ставилась
    раньше взрыва, а колесо шло от адаптации к истинной форме."""
    def ev(eid: str, event: str, ops: list, tag: str) -> dict:
        return {"id": eid, "tags": ["forge", tag], "trigger": {"kind": "event", "event": event}, "ops": ops}

    dur = lambda s: {"flat": s}  # noqa: E731
    true_form = {"kind": "trigger_true_form", "target": "self",
                 "ops": [{"kind": "mod", "target": "self", "stat": "strength", "op": "mul", "value": {"flat": 1.5}}]}
    return [
        # защита: резист типа, иммунитет (тип урона / действие), запрет действия, поглощение, невыбираемость
        ev("prim.guard", "take_damage", [
            {"kind": "resist", "target": "self", "damage_type": "fire", "value": {"flat": 10}, "duration": dur(4)},
            {"kind": "immune", "target": "self", "damage_type": "poison", "duration": dur(2)},
            {"kind": "immune", "target": "self", "effect": "heal_mana", "duration": dur(2)},
            {"kind": "block", "target": "enemy", "stat": "cursed_technique", "duration": dur(2)},
            {"kind": "absorb_damage", "target": "self", "value": {"pct": 50, "of": "last_damage"}, "window": dur(1)},
            {"kind": "untargetable", "target": "self", "by": ["six_eyes", "divination"], "duration": dur(1)},
        ], "combat"),
        # метка и её взрыв (метка ставится на attack_hit, взрывается на crit / kill)
        ev("prim.mark", "attack_hit", [
            {"kind": "mark", "target": "enemy", "mark_id": "forge_mark", "value": {"flat": 1}, "duration": dur(8),
             "max_stacks": 5}], "combat"),
        ev("prim.detonate", "crit", [
            {"kind": "detonate", "target": "enemy", "mark_id": "forge_mark", "value": {"flat": 4}}], "combat"),
        # срыв сил цели: отмена, прерывание техники, разрыв связи, снятие эффектов
        ev("prim.disrupt", "dodge", [
            {"kind": "nullify", "target": "enemy", "what": ["abilities"], "duration": dur(2)},
            {"kind": "cancel_technique", "target": "enemy", "duration": dur(1)},
            {"kind": "sever", "target": "enemy", "what": "soul_body_link", "duration": dur(2)},
            {"kind": "purge", "target": "enemy", "filter": {"kind": "buff", "tag": "iframe"}},
        ], "combat"),
        # обет: цена платится сразу, награда живёт пока действует метка
        ev("prim.vow", "combat_start", [
            {"kind": "binding_vow", "target": "self", "vow_id": "forge_vow", "duration": dur(5),
             "cost": [{"kind": "drain", "target": "self", "stat": "hp", "op": "sub", "value": {"flat": 10}}],
             "gain": [{"kind": "mod", "target": "self", "stat": "strength", "op": "add", "value": {"flat": 5}}]}], "combat"),
        # кража и применение техники
        ev("prim.learn", "use", [
            {"kind": "learn", "target": "self", "ability_id": "forge_technique"},
            {"kind": "use_learned_technique", "target": "self", "pick": "last", "tech_target": "enemy",
             "value": {"flat": 5}, "adapt_damage": {"flat": 20}}], "adapt"),
        # адаптация Махораги: наблюдение, порог, память, сброс
        ev("prim.adapt", "attack", [
            {"kind": "observe_phenomenon", "target": "self", "damage_type": "fire", "threshold": {"hits": 2}},
            {"kind": "register_phenomenon", "target": "self", "memory_key": "fire:forge_technique"},
            {"kind": "adapt", "target": "self", "phenomenon": {"damage_type": "physical"}, "threshold": {"hits": 1},
             "on_adapt": [{"kind": "heal", "target": "self", "stat": "hp", "op": "add", "value": {"flat": 5}}]},
            {"kind": "unadapt", "target": "self", "memory_key": "fire:forge_technique"}], "adapt"),
        ev("prim.reset", "combat_end", [{"kind": "reset_adaptation", "target": "self"}], "adapt"),
        # фракция и агро
        ev("prim.aggro", "tick", [
            {"kind": "set_faction", "target": "self", "faction": "feral"},
            {"kind": "set_aggro", "target": "self", "aggro_mode": "threat_first"},
            {"kind": "set_targeting", "target": "self",
             "targeting": {"mode": "lowest_hp", "switch_on": "damage", "switch_interval": 3}},
            {"kind": "retarget", "target": "self", "target_ref": "dummy"},
            {"kind": "clear_aggro", "target": "self"}], "aggro"),
        # колесо и эскалация; на wheel_max колесо само зовёт trigger_true_form
        ev("prim.wheel", "kill", [
            {"kind": "rotate_wheel", "target": "self", "wheel_delta": 3},
            {"kind": "display_wheel", "target": "self", "mode": "golden"},
            {"kind": "halt_wheel", "target": "self"},
            {"kind": "escalate", "target": "self", "escalation_delta": 2},
            {"kind": "deescalate", "target": "self", "escalation_delta": 1},
            true_form], "wheel"),
    ]


# ---------------------------------------------------------------- random block

def random_effect(idx: int, rng: random.Random, preds: PredGen) -> dict:
    kind = rng.choice(["passive", "condition", "condition", "event", "event", "event"])
    trigger: dict = {"kind": kind}
    if kind == "condition":
        trigger["when"] = preds.cond(rng.randint(1, 3))
    elif kind == "event":
        trigger["event"] = rng.choice(sorted(EVENTS))
        if rng.random() < 0.7:
            trigger["filter"] = preds.cond(rng.randint(1, 3))
    ops = []
    for _ in range(rng.randint(1, 4)):
        stat = rng.choice(WRITABLE)
        if kind != "event" or rng.random() < 0.5:
            o = _mod(stat, rng.choice(sorted(OPS)), rng.randrange(4), rng, rng.choice(["self", "self", "enemy"]))
        else:
            res = rng.choice(RESOURCES)
            o = {"kind": rng.choice(["heal", "deal", "drain"]), "target": rng.choice(["self", "enemy"]),
                 "stat": res, "op": "add", "value": {"pct": round(rng.uniform(0.5, 5), 2), "of": "max_" + res}}
            if o["kind"] == "drain":
                o["fail"] = [{"kind": "heal", "target": "self", "stat": res, "op": "add", "value": {"flat": 1}}]
        if rng.random() < 0.3:
            o["when"] = preds.cond(1)
        ops.append(o)
    ef = {"id": f"rnd.{idx}", "tags": ["forge", "random"], "trigger": trigger, "ops": ops}
    if kind != "event" and rng.random() < 0.1:
        ef["amplify"] = {"when": preds.cond(1), "every": rng.choice([5, 10]), "of": "hp_missing_below_40",
                         "factor": rng.choice([1.5, 2])}
    return ef


def forge_item(random_effects: int = 0, seed: int = 0, hostile: bool = False,
               name: Optional[str] = None) -> dict:
    """Предмет: блок покрытия схемы + random_effects случайных эффектов."""
    rng = random.Random(seed)
    preds = PredGen(rng, hostile=hostile)
    effects = coverage_effects(rng, preds) + [random_effect(i, rng, preds) for i in range(random_effects)]
    return {"name": name or f"Forged Item (seed {seed}, {len(effects)} effects)",
            "description": "Generated by tools/effect_schema/forge.py to exercise the whole effect schema.",
            "effects": effects}
