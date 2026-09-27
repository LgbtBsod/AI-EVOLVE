"""Slice G2: the generic op precondition (`requires` / `cost`, src/effects/gate.py) and the bounded interrupt window, as
executable specs on EffectManager. lua_content/corpus_holdout_abilities.lua (family "gate"): Bloodbending (moon phase),
Erasure (eye contact), Founding Titan (ancestry), Water regeneration (terrain), Attack Titan (self-injury cost), Fireball
(sphere area), Counterspell (interrupt a matching cast). Every unmodeled world condition (moon/ancestry/terrain/eye-contact)
is a boolean flag stat on the caster's `innate` (survives `EntityState.refresh`, unlike a raw `unit.base` write); the stat
cache is turned off on entities that flip such a flag mid-test so the next cast actually re-pulls it.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects.manager import EffectManager  # noqa: E402
from tests.test_effect_manager import Fighter, World  # noqa: E402
from tools.effect_schema.validate import validate_op  # noqa: E402

ROWS = {a["id"]: a for a in lua_bridge.load(lua_bridge.CONTENT / "corpus_holdout_abilities.lua")["abilities"] if a.get("family") == "gate"}


def row(aid, ops, **kw):
    return {"id": aid, "trigger": "cast", "range": 999, "needs_target": any(o.get("target") == "enemy" for o in ops), "ops": ops, **kw}


def setup(seed=1, extra=None):
    mgr = EffectManager(world=World(), abilities={**ROWS, **(extra or {})}, rng=random.Random(seed))
    hero, foe = Fighter(x=0.0, y=0.0, hp=100.0), Fighter(x=5.0, y=0.0, hp=100.0)
    mgr.register(hero, "hero")
    mgr.register(foe, "monsters")
    mgr.state(hero).stat_cache = mgr.state(foe).stat_cache = False   # a test flips a flag stat mid-run and re-casts
    return mgr, hero, foe


def flag(mgr, entity, name, value=1.0):
    mgr.state(entity).innate[name] = value


def test_every_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in ROWS.values()} == {104, 106, 107, 120, 122, 123, 146, 148}
    for aid, ab in ROWS.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_requires_blocks_without_the_flag_and_lands_with_it():
    mgr, hero, foe = setup()
    assert mgr.cast(hero, "hold_bloodbending", foe).ok
    assert "aggro" not in mgr.state(foe).unit.external          # no moon: the command never lands
    flag(mgr, hero, "moon_phase")
    mgr.state(hero).cooldowns.clear()
    assert mgr.cast(hero, "hold_bloodbending", foe).ok
    assert mgr.state(foe).unit.external["aggro"]["aggro_mode"] == "command:obey"


def test_eye_contact_and_ancestry_gate_the_same_way():
    mgr, hero, foe = setup()
    mgr.cast(hero, "hold_erasure", foe)
    assert not mgr.state(foe).unit.buffs
    flag(mgr, hero, "eye_contact")
    mgr.state(hero).cooldowns.clear()
    assert mgr.cast(hero, "hold_erasure", foe).ok

    mgr2, hero2, foe2 = setup()
    mgr2.state(hero2).stat_cache = False
    mgr2.cast(hero2, "hold_founding_titan", foe2)
    assert "aggro" not in mgr2.state(foe2).unit.external
    flag(mgr2, hero2, "ancestry")
    mgr2.state(hero2).cooldowns.clear()
    assert mgr2.cast(hero2, "hold_founding_titan", foe2).ok
    assert mgr2.state(foe2).unit.external["aggro"]["aggro_mode"] == "command:obey"


def test_terrain_gate_and_near_death_trigger():
    mgr, hero, _ = setup()
    hp0 = hero.health
    mgr.cast(hero, "hold_water_regeneration")
    assert hero.health == hp0                     # not near water: refused, no heal
    flag(mgr, hero, "near_water")
    mgr.state(hero).cooldowns.clear()
    assert mgr.cast(hero, "hold_water_regeneration").ok
    assert hero.health == pytest.approx(min(100.0, hp0 + 30.0))

    mgr2, hero2, _ = setup()
    mgr2.cast(hero2, "hold_avatar_state_gated")
    a0 = mgr2.state(hero2).unit._eff("attack_damage")
    flag(mgr2, hero2, "near_death")
    mgr2.state(hero2).cooldowns.clear()
    assert mgr2.cast(hero2, "hold_avatar_state_gated").ok
    assert mgr2.state(hero2).unit._eff("attack_damage") > a0


def test_self_injury_cost_is_paid_and_a_short_pay_refuses():
    mgr, hero, _ = setup()
    hero.health = 10.0
    mgr.cast(hero, "hold_attack_titan")
    assert hero.health == 10.0                       # 10 hp cannot pay a 15 hp cost: refused, nothing paid
    hero.health = 100.0
    mgr.state(hero).cooldowns.clear()
    assert mgr.cast(hero, "hold_attack_titan").ok
    assert hero.health == 85.0


def test_fireball_sphere_hits_everyone_in_radius_of_the_target():
    mgr, hero, foe = setup()
    bystander = Fighter(x=6.0, y=0.0, hp=100.0)
    mgr.register(bystander, "monsters")
    assert mgr.cast(hero, "hold_fireball", foe).ok
    assert foe.health == 100.0 - 28.0 and bystander.health == 100.0 - 28.0


def test_counterspell_arms_a_window_that_nullifies_one_matching_cast():
    mgr, hero, foe = setup()
    mgr.abilities["bolt"] = row("bolt", [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 10}}], tags=("spell",))
    assert mgr.cast(hero, "hold_counterspell").ok
    assert mgr.cast(foe, "bolt", hero).ok
    assert hero.health == 100.0                       # the interrupt window nullified the bolt
    mgr.state(foe).cooldowns.clear()
    assert mgr.cast(foe, "bolt", hero).ok
    assert hero.health == 90.0                         # charge spent: the second bolt lands


def test_two_same_seed_runs_are_identical():
    def go():
        mgr, hero, foe = setup(5)
        for name in ("moon_phase", "eye_contact", "ancestry", "near_water", "near_death"):
            flag(mgr, hero, name)
        for aid in ("hold_bloodbending", "hold_erasure", "hold_founding_titan", "hold_water_regeneration", "hold_fireball"):
            mgr.cast(hero, aid, foe)
        return (foe.health, hero.health, (mgr.state(foe).unit.external.get("aggro") or {}).get("aggro_mode"))
    assert go() == go()
