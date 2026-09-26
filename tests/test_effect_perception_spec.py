"""Slice F3: the PERCEPTION family (perceive / reveal / grant_vision / precognition / dodge) as executable specs.

lua_content/corpus_abilities.lua rows with family = "perception" run on EffectManager: information exposed as queryable data,
concealment revealed, vision mods change can_see, precognition warns/negates once per cooldown, expiry, same-seed determinism.
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

ROWS = {a["id"]: a for a in lua_bridge.load(lua_bridge.CONTENT / "corpus_abilities.lua")["abilities"]}
PERC = {k: a for k, a in ROWS.items() if a.get("family") == "perception"}
HIT = {"id": "t_hit", "trigger": "cast", "range": 50, "needs_target": True,
       "ops": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 10}, "flags": ["true_damage"]}]}
SWEEP = {"id": "t_sweep", "trigger": "cast", "ops": [{"kind": "deal", "target": "area", "radius": 20, "center": "self",
                                                       "affects": "enemies", "stat": "hp", "op": "sub", "value": {"flat": 10}}]}


def setup(seed=1, enemy_x=5.0):
    mgr = EffectManager(world=World(), abilities={**ROWS, "t_hit": HIT, "t_sweep": SWEEP}, rng=random.Random(seed))
    hero, enemy = Fighter(x=0.0, y=0.0, hp=1000.0), Fighter(x=enemy_x, y=0.0, hp=500.0)
    hero.vision_range = enemy.vision_range = 20.0
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters")
    return mgr, hero, enemy


def strike(mgr, attacker, victim):
    """One incoming hit on `victim`; returns the hp it lost."""
    before = victim.health
    assert mgr.cast(attacker, "t_hit", victim).ok
    return before - victim.health


def test_every_perception_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in PERC.values() if "corpus" in a} == {39, 50, 55}
    for aid, ab in PERC.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_perceive_exposes_data_for_the_duration_and_mutates_nothing():
    mgr, hero, enemy = setup()
    hp0 = enemy.health
    assert mgr.cast(hero, "corpus_prescience", enemy).ok
    seen = mgr.perceived(hero)
    (facts,) = seen.values()
    assert set(facts) == {"hp", "statuses", "intent"} and facts["hp"]["hp"] == hp0 and enemy.health == hp0
    mgr.update(15.5)
    assert mgr.perceived(hero) == {}


def test_perceive_all_and_selected_stats():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_shinigami_eyes", enemy)
    (facts,) = mgr.perceived(hero).values()
    assert set(facts) == {"hp", "stats", "statuses", "hidden", "intent"}
    mgr.cast(hero, "corpus_sharingan_watch", enemy)
    (facts,) = mgr.perceived(hero).values()
    assert set(facts) == {"stats", "intent"} and set(facts["stats"]) == {"attack", "defense"}


def test_perceive_shows_hidden_effects_and_statuses():
    mgr, hero, enemy = setup()
    mgr.state(enemy).unit.buffs["untargetable:all"] = {"until": 1e18}
    mgr.state(enemy).unit.buffs["burning"] = {"until": 1e18}
    mgr.cast(hero, "corpus_shinigami_eyes", enemy)
    (facts,) = mgr.perceived(hero).values()
    assert facts["hidden"]["untargetable"] == ["untargetable:all"] and facts["statuses"] == ["burning"]


def test_reveal_suppresses_untargetable_only_while_it_lasts_and_only_for_the_caster():
    mgr, hero, enemy = setup()
    mgr.state(enemy).unit.buffs["untargetable:all"] = {"until": 1e18}
    assert mgr.cast(hero, "t_sweep", enemy).ok and enemy.health == 500.0     # hidden: the sweep misses
    mgr.cast(hero, "corpus_shinigami_eyes", enemy)                           # reveal to = caster
    assert mgr.cast(hero, "t_sweep", enemy).ok and enemy.health == 490.0
    ally = Fighter(x=3.0, y=0.0, hp=100.0)
    mgr.register(ally, "hero")
    mgr.cast(ally, "t_sweep", enemy)
    assert enemy.health == 490.0                                             # revealed to the caster only: the ally still cannot target it
    mgr.update(30.5)
    mgr.cast(hero, "t_sweep", enemy)
    assert enemy.health == 490.0                                             # expired: hidden again


def test_spider_sense_reveals_the_zone_and_warns_once_per_cooldown():
    mgr, hero, enemy = setup()
    mgr.state(enemy).unit.buffs["untargetable:all"] = {"until": 1e18}
    assert mgr.cast(hero, "corpus_spider_sense", enemy).ok
    assert mgr.cast(hero, "t_sweep", enemy).ok and enemy.health == 490.0     # area reveal (everyone in 10u)
    assert strike(mgr, enemy, hero) == 0.0 and len(mgr.warnings(hero)) == 1  # first hit negated + warned
    assert strike(mgr, enemy, hero) == 10.0 and len(mgr.warnings(hero)) == 1  # inside the cooldown: lands, no second warning
    mgr.update(4.5)
    assert strike(mgr, enemy, hero) == 0.0 and len(mgr.warnings(hero)) == 2
    mgr.update(20.0)
    assert strike(mgr, enemy, hero) == 10.0 and len(mgr.warnings(hero)) == 2  # expired


def test_prescience_warns_without_negating():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_prescience", enemy)
    assert strike(mgr, enemy, hero) == 10.0
    (w,) = mgr.warnings(hero)
    assert w["from"] == enemy.entity_id


def test_dodge_alias_negates_without_a_warning():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_evade", None)
    assert strike(mgr, enemy, hero) == 0.0 and mgr.warnings(hero) == []
    assert strike(mgr, enemy, hero) == 10.0


def test_grant_vision_changes_can_see_and_expires():
    mgr, hero, enemy = setup(enemy_x=30.0)
    assert not mgr.can_see(hero, enemy)
    mgr.cast(hero, "corpus_far_sight", None)
    assert mgr.can_see(hero, enemy)
    mgr.update(10.5)
    assert not mgr.can_see(hero, enemy)


def test_reveal_cancels_stealth_circle_for_can_see():
    mgr, hero, enemy = setup(enemy_x=10.0)
    stealth = {"kind": "mod", "target": "enemy", "stat": "vision_range", "op": "add", "value": {"flat": -15}, "toward": "source",
               "duration": {"flat": 20}}
    mgr.abilities["t_stealth"] = {"id": "t_stealth", "trigger": "cast", "range": 50, "needs_target": True, "ops": [stealth]}
    mgr.cast(enemy, "t_stealth", hero)
    assert not mgr.can_see(hero, enemy)
    mgr.cast(hero, "corpus_shinigami_eyes", enemy)
    assert mgr.can_see(hero, enemy)


def _gae_run(seed):
    mgr, hero, enemy = setup(seed)
    out = []
    for _ in range(10):
        mgr.cast(hero, "corpus_gae_bolg_foresight", None)
        out.append(strike(mgr, enemy, hero))
        mgr.update(21.0)
    return out, len(mgr.warnings(hero))


def test_chance_precognition_is_seeded_and_both_outcomes_occur():
    a, b = _gae_run(5), _gae_run(5)
    assert a == b and set(a[0]) == {0.0, 10.0}


def test_two_same_seed_runs_end_identically():
    def run():
        mgr, hero, enemy = setup(7)
        for aid in ("corpus_spider_sense", "corpus_prescience", "corpus_shinigami_eyes"):
            mgr.cast(hero, aid, enemy)
            strike(mgr, enemy, hero)
            mgr.update(3.0)
        return hero.health, list(mgr.perceived(hero).values()), [w["t"] for w in mgr.warnings(hero)], round(mgr.now, 3)
    assert run() == run()
