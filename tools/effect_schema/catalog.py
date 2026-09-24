"""Каталог шаблонов эффектов для билдера: id -> (название, ленивая фабрика Effect)."""

from __future__ import annotations

from .schema import Effect, Op, Value, Scale, Trigger


def _health_potion():
    return Effect(
        id="health_potion", tags=["consumable", "heal"],
        trigger=Trigger(kind="event", event="use"),
        ops=[Op(kind="heal", target="self", stat="hp", op="add",
                value=Value(flat=40))],
        meta={"name": "Health Potion", "description": "+40 HP instantly."},
    )


def _lost_my_self():
    sc = lambda v_pct=None, v_flat=None: Scale(
        every=10, of="hp_missing_below_40",
        value=Value(pct=v_pct) if v_pct is not None else Value(flat=v_flat))
    return Effect(
        id="lost_my_self", tags=["berserk", "passive"],
        trigger=Trigger(kind="condition", when="ctx.hp_pct < 40"),
        ops=[
            Op(kind="mod", target="self", stat="strength", op="add", value=Value(pct=20)),
            Op(kind="mod", target="self", stat="stamina", op="add", value=Value(pct=10)),
            Op(kind="mod", target="self", stat="crit_chance", op="add",
               value=Value(pct=5), scale=sc(v_pct=5)),
            Op(kind="mod", target="self", stat="crit_dmg", op="add",
               value=Value(pct=10), scale=sc(v_pct=10)),
            Op(kind="mod", target="self", stat="aspd", op="add",
               value=Value(pct=5), scale=sc(v_pct=10)),
            Op(kind="mod", target="self", stat="hp_regen", op="add",
               value=Value(flat=0), scale=sc(v_flat=20)),
            Op(kind="mod", target="self", stat="lifesteal", op="add",
               value=Value(pct=0), scale=sc(v_pct=5)),
        ],
        meta={"name": "Lost My Self",
              "description": "Below 40% HP: berserk power scaling with missing HP."},
    )


def _lost_my_self_attack():
    sc = lambda val: Scale(every=10, of="hp_missing_below_40", value=val)
    return Effect(
        id="lost_my_self.attack", tags=["berserk", "on_attack"],
        trigger=Trigger(kind="event", event="attack", owner_has="lost_my_self"),
        ops=[
            Op(kind="drain", target="self", stat="hp", op="sub",
               value=Value(pct=0.5, of="max_hp"),
               scale=sc(Value(pct=0.5, of="max_hp")),
               fail=[
                   Op(kind="set", target="self", stat="hp", op="set",
                      value=Value(flat=1)),
                   Op(kind="buff", target="self", buff_id="last_will",
                      duration={"base": 5,
                                "scale": {"every": 10, "of": "hp_missing_below_40",
                                          "value": {"flat": 5}, "factor": 2}},
                      cooldown={"flat": 30},
                      extend={"on": "kill", "flat": 5}),
               ]),
            Op(kind="deal", target="enemy", stat="hp", op="sub",
               value=Value(pct=1.5, of="max_hp"),
               scale=sc(Value(pct=1.5, of="max_hp"))),
        ],
        meta={"name": "Blood Price",
              "description": "Each attack costs 0.5% max HP and deals 1.5% max HP true damage; +0.5%/+1.5% per 10% HP below 40."},
    )


def _poison_dot():
    return Effect(
        id="venom_bite", tags=["debuff", "dot"],
        trigger=Trigger(kind="event", event="attack_hit"),
        ops=[Op(kind="apply_effect", target="enemy", buff_id="poison_stack")],
        meta={"name": "Venom Bite", "description": "Applies poison on hit."},
    )


def _last_will_buff():
    return Effect(
        id="last_will", tags=["shield", "survival"],
        trigger=Trigger(kind="passive"),
        duration={"flat": 5},
        ops=[Op(kind="mod", target="self", stat="defense", op="mul",
                value=Value(flat=2))],
        meta={"name": "Last Will", "description": "5s survival shield (iframe)."},
    )


# ---------------------------------------------------------------- built via builder form
#
# Эти предметы определены ЧЕРЕЗ ui_logic-формы (тот же путь, что и кнопки
# «Валидировать / Собрать Lua / Тест» в Flet-билдере) — dogfooding схемы.

def _form_effect(**kw):
    """Ленивая фабрика: форма билдера -> Effect (через общий UI-пайплайн)."""
    def make():
        from .ui_logic import effect_from_form
        return effect_from_form(kw)
    return make


_VAMPIRE_FORM = {
    "id": "vampires_fang", "tags": ["lifesteal", "weapon"],
    "trigger": {"kind": "event", "event": "attack_hit"},
    "ops": [
        # лifesteal = 8% ОТ ФАКТИЧЕСКОГО УРОНА последнего удара
        # (runtime-псевдостат ctx.last_damage), а не от текущего hp:
        # {"pct": 8} без "of" резолвился бы от "hp" (стат op) — 8% своего HP.
        {"kind": "heal", "target": "self", "stat": "hp", "op": "add",
         "value": {"pct": 8, "of": "last_damage"}, "flags": ["silent"]},
        {"kind": "mod", "target": "self", "stat": "strength", "op": "add",
         "value": {"flat": 5},
         "scale": {"every": 1, "of": "kills", "value": {"flat": 1}, "cap": 10}},
    ],
}

_MANTLE_FORM = {
    "id": "mantle_of_thorns", "tags": ["armor", "retaliation"],
    "trigger": {"kind": "event", "event": "take_damage"},
    "ops": [
        {"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub",
         "value": {"pct": 20, "of": "hp"}, "flags": ["no_crit"]},
    ],
}

_RAGE_FORM = {
    "id": "rage_tonic", "tags": ["consumable", "buff"],
    "trigger": {"kind": "event", "event": "use"},
    "ops": [
        {"kind": "buff", "target": "self", "buff_id": "enraged",
         "duration": {"base": 8,
                      "scale": {"every": 10, "of": "hp_missing_below_40",
                                "value": {"flat": 1}}},
         "cooldown": {"flat": 20}},
        {"kind": "drain", "target": "self", "stat": "hp", "op": "sub",
         "value": {"pct": 10},
         "fail": [{"kind": "set", "target": "self", "stat": "hp",
                   "op": "set", "value": {"flat": 1}}]},
    ],
}

_JUDGEMENT_FORM = {
    "id": "judgement", "tags": ["execute", "weapon"],
    "trigger": {"kind": "event", "event": "attack"},
    "ops": [
        # execute: добивание ниже 15% HP. Опциональный лifesteal-компонент
        # (см. шаблон reaper_kiss): heal {"pct": N, "of": "last_damage"} —
        # run_op("kill") фиксирует ctx.last_damage = фактический урон дobивания
        # ДО смерти цели, поэтому процент берётся от реального снятого HP.
        {"kind": "kill", "target": "enemy",
         "when": "ctx.enemy_hp_pct < 15"},
    ],
}

_REAPER_FORM = {
    "id": "reaper_kiss", "tags": ["execute", "lifesteal", "weapon"],
    "trigger": {"kind": "event", "event": "attack"},
    "ops": [
        {"kind": "kill", "target": "enemy",
         "when": "ctx.enemy_hp_pct < 20"},
        # 25% ОТ ФАКТИЧЕСКОГО УРОНА добиания (ctx.last_damage), а не от hp:
        # {"pct": 25} без "of" резолвился бы от stat op ("hp") — 25% своего HP.
        {"kind": "heal", "target": "self", "stat": "hp", "op": "add",
         "value": {"pct": 25, "of": "last_damage"}, "flags": ["silent"]},
    ],
}

_REbirth_FORM = {
    "id": "phoenix_feather", "tags": ["revive", "trinket"],
    "trigger": {"kind": "event", "event": "die"},
    "ops": [
        {"kind": "set", "target": "self", "stat": "hp", "op": "set",
         "value": {"pct": 30, "of": "max_hp"}},
        {"kind": "remove_buff", "target": "self", "buff_id": "enraged"},
    ],
}


CATALOG = {
    "health_potion": ("🧪 Health Potion (+40 HP)", _health_potion),
    "lost_my_self": ("😡 Lost My Self (berserk passive)", _lost_my_self),
    "lost_my_self.attack": ("🩸 Blood Price (drain+deal on attack)", _lost_my_self_attack),
    "venom_bite": ("🐍 Venom Bite (apply debuff)", _poison_dot),
    "last_will": ("🛡 Last Will (timed buff)", _last_will_buff),
    "vampires_fang": ("🦇 Vampire's Fang (lifesteal + kill scaling)",
                      _form_effect(**_VAMPIRE_FORM)),
    "mantle_of_thorns": ("🌵 Mantle of Thorns (retaliate on hit)",
                         _form_effect(**_MANTLE_FORM)),
    "rage_tonic": ("🔥 Rage Tonic (buff + HP cost)", _form_effect(**_RAGE_FORM)),
    "judgement": ("⚖️ Judgement (execute below 15%)", _form_effect(**_JUDGEMENT_FORM)),
    "reaper_kiss": ("💀 Reaper Kiss (execute + last_damage lifesteal)",
                    _form_effect(**_REAPER_FORM)),
    "phoenix_feather": ("🪶 Phoenix Feather (revive at 30% HP)",
                        _form_effect(**_REbirth_FORM)),
}


def get_template(tid: str) -> Effect:
    return CATALOG[tid][1]()


def template_names() -> dict:
    return {k: v[0] for k, v in CATALOG.items()}
