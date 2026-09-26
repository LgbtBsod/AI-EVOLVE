"""Slice F4: TRIGGER kinds (on_lethal / counter_delta / delay) as executable specs on EffectManager.

lua_content/corpus_abilities.lua rows with family = "trigger": a lethal hit survived once, charges exhausted, interceptor order,
kill/die events unchanged when nobody intercepts, delay at the exact game time, cancelled on caster death, same-seed determinism.
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
TRIG = {k: a for k, a in ROWS.items() if a.get("family") == "trigger"}
HIT = {"id": "t_hit", "trigger": "cast", "range": 50, "needs_target": True,
       "ops": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 100}, "flags": ["true_damage", "no_crit", "unavoidable"]}]}


def setup(seed=1):
    mgr = EffectManager(world=World(), abilities={**ROWS, "t_hit": HIT}, rng=random.Random(seed))
    hero, enemy = Fighter(x=0.0, y=0.0, hp=50.0), Fighter(x=5.0, y=0.0, hp=1000.0)
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters")
    events = []
    orig = mgr.emit
    mgr.emit = lambda e, ev, **kw: (events.append((ev, e.entity_id)), orig(e, ev, **kw))[1]
    return mgr, hero, enemy, events


def test_every_trigger_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in TRIG.values() if "corpus" in a} == {35, 59}
    for aid, ab in TRIG.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_lethal_hit_declined_still_kills_and_fires_events():
    mgr, hero, enemy, events = setup()
    assert mgr.cast(enemy, "t_hit", hero).ok
    assert hero.health <= 0 and ("die", hero.entity_id) in events and ("kill", enemy.entity_id) in events


def test_avatar_state_survives_one_lethal_hit_then_dies():
    mgr, hero, enemy, events = setup()
    assert mgr.cast(hero, "corpus_avatar_state").ok
    mgr.cast(enemy, "t_hit", hero)
    assert hero.health == 1.0 and not any(e[0] == "die" for e in events)
    assert mgr.state(hero).unit.external["triggers"]["lethal"]["avatar_guard"]["charges"] == 0
    assert "avatar" in {r["id"] for r in mgr.state(hero).unit.external["forms"].values()}   # the on_lethal ops ran
    mgr.cast(enemy, "t_hit", hero)
    assert hero.health <= 0 and ("die", hero.entity_id) in events


def test_god_hand_restores_and_resists_the_killing_type_for_twelve_lives():
    mgr, hero, enemy, events = setup()
    mgr.cast(hero, "corpus_god_hand")
    mgr.cast(enemy, "t_hit", hero)
    assert hero.health == hero.max_health and not any(e[0] == "die" for e in events)
    st = mgr.state(hero)
    assert st.unit.external["triggers"]["last_lethal"]["type"] and st.unit.external["triggers"]["lethal"]["god_hand"]["charges"] == 11
    assert st.unit.mods["defense"] == 5.0 and st.unit.mods["resist_physical"] == 60.0   # status ward + counter_delta


def test_interceptors_fire_by_priority_then_id_once_per_hit():
    mgr, hero, enemy, _ = setup()
    mgr.cast(hero, "corpus_last_stand_a")      # id ls_b priority 1, keep 5
    mgr.cast(hero, "corpus_last_stand_b")      # id ls_a priority 0, keep 1
    mgr.cast(enemy, "t_hit", hero)
    lethal = mgr.state(hero).unit.external["triggers"]["lethal"]
    assert hero.health == 1.0 and lethal["ls_a"]["charges"] == 0 and lethal["ls_b"]["charges"] == 1
    hero.health = 50.0
    mgr.cast(enemy, "t_hit", hero)
    assert hero.health == 5.0 and lethal["ls_b"]["charges"] == 0


def test_delay_fires_at_the_exact_game_time_and_not_before():
    mgr, hero, enemy, _ = setup()
    mgr.cast(hero, "corpus_delayed_blast", enemy)
    mgr.update(2.5)
    assert enemy.health == 1000.0
    mgr.update(0.5)                              # now == 3.0
    assert enemy.health == 960.0
    mgr.update(10.0)
    assert enemy.health == 960.0                 # once


def test_delay_is_cancelled_by_caster_death_unless_persist():
    for aid, expect in (("corpus_delayed_blast", 1000.0), ("corpus_delayed_blast_persist", 960.0)):
        mgr, hero, enemy, _ = setup()
        mgr.cast(hero, aid, enemy)
        mgr.cast(enemy, "t_hit", hero)
        assert hero.health <= 0
        mgr.update(3.0)
        assert enemy.health == expect, aid


def test_same_seed_runs_are_identical():
    def run():
        mgr, hero, enemy, events = setup(7)
        mgr.cast(hero, "corpus_god_hand")
        mgr.cast(hero, "corpus_delayed_blast", enemy)
        for _ in range(4):
            mgr.cast(enemy, "t_hit", hero)
            mgr.update(1.0)
        return hero.health, enemy.health, [e[0] for e in events]
    assert run() == run()
