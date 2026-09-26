"""Slice F5: ZONES / auras / reality marbles / rule_override as executable specs on EffectManager (src/effects/zones.py).

lua_content/corpus_abilities.lua rows with family = "space": enter / exit fire once, tick order stable, affects filter, closed barrier,
guaranteed_hit, aura follows and nullifies (bypass flag), Room swap inside, expiry / owner death cleanup, bounded rule_override,
same-seed determinism, a performance guard.
"""
from __future__ import annotations

import random
import sys
import time
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
SPACE = {k: a for k, a in ROWS.items() if a.get("family") == "space"}
TRUE = ["true_damage", "no_crit"]


def hit_op(flags, v=10):
    return {"id": "t_hit", "trigger": "cast", "range": 999, "needs_target": True,
            "ops": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": v}, "flags": flags}]}


def setup(seed=1, extra=None, enemy_x=5.0):
    abilities = {**ROWS, "t_hit": hit_op(["no_crit"]), "t_bypass": hit_op(["no_crit", "bypass_infinity"]), **(extra or {})}
    mgr = EffectManager(world=World(), abilities=abilities, rng=random.Random(seed))
    hero, enemy = Fighter(x=0.0, y=0.0, hp=500.0), Fighter(x=enemy_x, y=0.0, hp=500.0)
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters")
    return mgr, hero, enemy


def zone_ability(**kw):
    return {"id": "z", "trigger": "cast", "ops": [{"kind": "zone", "target": "self", "id": "zz", "radius": 10, "affects": "enemies", **kw}]}


def dmg(v):
    return {"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": v}, "flags": TRUE}


def test_every_space_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in SPACE.values() if "corpus" in a} == {1, 3, 4, 16, 32}

    def walk(ops):
        for o in ops or []:
            yield o
            yield from walk(o.get("on_enter"))
            yield from walk((o.get("tick") or {}).get("ops"))
    for aid, ab in SPACE.items():
        for o in walk(ab["ops"]):
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_enter_and_exit_fire_once_per_crossing_and_affects_filters():
    mgr, hero, enemy = setup(extra={"z": zone_ability(on_enter=[dmg(1)], on_exit=[dmg(2)])}, enemy_x=50.0)
    mgr.cast(hero, "z")
    mgr.update(0.1)
    assert enemy.health == 500.0
    enemy.x = 5.0
    mgr.update(0.1)
    mgr.update(0.1)
    assert enemy.health == 499.0 and hero.health == 500.0        # once; the owner is not an enemy of himself
    enemy.x = 50.0
    mgr.update(0.1)
    mgr.update(0.1)
    assert enemy.health == 497.0


def test_tick_runs_every_period_in_member_id_order():
    mgr, hero, enemy = setup(extra={"z": zone_ability(tick={"every": {"flat": 1}, "ops": [dmg(1)]})})
    e2 = Fighter(x=-4.0, y=0.0, hp=500.0)
    mgr.register(e2, "monsters")
    order = []
    orig = mgr._damage
    mgr._damage = lambda st, tgt, *a, **k: (order.append(tgt.entity.entity_id), orig(st, tgt, *a, **k))[1]
    mgr.cast(hero, "z")
    for _ in range(4):
        mgr.update(0.5)
    assert enemy.health == 498.0 and e2.health == 498.0
    assert len(order) == 4 and order[:2] == order[2:] and order[:2] == sorted(order[:2])


def test_barrier_closed_traps_members_and_keeps_outsiders_out_but_not_the_owner():
    mgr, hero, enemy = setup(extra={"z": zone_ability(barrier="closed")})
    outsider = Fighter(x=30.0, y=0.0, hp=500.0)
    mgr.register(outsider, "monsters")
    mgr.cast(hero, "z")
    mgr.update(0.1)
    assert mgr.constrain_move(enemy, 25.0, 0.0)[0] < 10.0
    assert mgr.constrain_move(outsider, 2.0, 0.0)[0] > 10.0
    assert mgr.constrain_move(hero, 25.0, 0.0) == (25.0, 0.0)
    mgr._place(enemy, 40.0, 0.0)                                  # the seam of every `move` mode clamps too
    assert enemy.x < 10.0


def test_guaranteed_hit_beats_full_dodge_inside_and_only_inside():
    mgr, hero, enemy = setup(extra={"z": zone_ability(guaranteed_hit=True, affects="all")})
    enemy.dodge_chance = 1.0
    far, outer = Fighter(x=60.0, y=0.0, hp=500.0), Fighter(x=61.0, y=0.0, hp=500.0)
    far.dodge_chance = 1.0
    mgr.register(far, "monsters")
    mgr.register(outer, "hero")
    mgr.cast(hero, "z")
    mgr.update(0.1)
    for _ in range(20):
        mgr.cast(hero, "t_hit", enemy)
        mgr.cast(outer, "t_hit", far)
    assert enemy.health == 300.0                                  # inside: every hit lands although dodge_chance = 1
    assert far.health > 300.0                                     # outside the zone the dodge still works


def test_aura_follows_owner_and_nullifies_attackers_unless_bypass():
    mgr, hero, enemy = setup(enemy_x=2.0)
    mgr.cast(hero, "corpus_infinity")
    mgr.update(0.1)
    mgr.cast(enemy, "t_hit", hero)
    assert hero.health == 500.0                                   # nullified
    mgr.cast(enemy, "t_bypass", hero)
    assert hero.health == 490.0                                   # bypass_infinity flag
    hero.x, enemy.x = 100.0, 102.0                                # the aura follows the owner
    mgr.update(0.1)
    mgr.cast(enemy, "t_hit", hero)
    assert hero.health == 490.0
    enemy.x = 120.0                                               # attacker outside the radius: the aura does not stop it
    mgr.update(0.1)
    mgr.cast(enemy, "t_hit", hero)
    assert hero.health == 480.0


def test_room_swaps_any_two_members_only_inside_and_allowed_by_the_zone():
    mgr, hero, e1 = setup(enemy_x=3.0)
    e2 = Fighter(x=-6.0, y=0.0, hp=500.0)
    mgr.register(e2, "monsters")
    mgr.abilities["sw"] = {"id": "sw", "trigger": "cast", "range": 99, "needs_target": True,
                           "ops": [{"kind": "swap", "target": "enemy", "with": e2.entity_id}]}
    mgr.cast(hero, "sw", e1)
    assert (e1.x, e2.x) == (3.0, -6.0)                            # no Room yet: nothing happens
    mgr.cast(hero, "corpus_room")
    mgr.update(0.1)
    mgr.cast(hero, "sw", e1)
    assert (e1.x, e2.x) == (-6.0, 3.0)


@pytest.mark.parametrize("kill_owner", [False, True])
def test_expiry_and_owner_death_end_the_zone_cleanly(kill_owner):
    heal = {"kind": "heal", "target": "enemy", "stat": "hp", "value": {"flat": 5}}
    zab = zone_ability(duration={"flat": 3}, tick={"every": {"flat": 1}, "ops": [dmg(1)]}, barrier="closed", guaranteed_hit=True, on_exit=[heal])
    mgr, hero, enemy = setup(extra={"z": zab})
    mgr.cast(hero, "z")
    mgr.update(1.0)
    if kill_owner:
        hero.health = 0.0
    else:
        mgr.update(2.5)
    mgr.update(0.1)
    assert mgr._zones == []
    hp = enemy.health
    assert hp <= 500.0 and hp >= 497.0
    mgr.update(10.0)
    assert enemy.health == hp                                     # ticks stopped
    assert mgr.constrain_move(enemy, 99.0, 0.0) == (99.0, 0.0)    # barrier gone


def test_rule_override_is_bounded_and_restored():
    from src.effects import damage
    base = damage.config().consts
    ro = {"id": "ro", "trigger": "cast", "ops": [{"kind": "rule_override", "target": "self", "duration": {"flat": 2},
                                                  "rules": {"consts": {"min_damage": 50.0, "not_a_constant": 1}, "flags": ["no_crit", "bogus"]}}]}
    ro2 = {"id": "ro2", "trigger": "cast", "ops": [{"kind": "rule_override", "target": "self", "rules": {"consts": {"min_damage": 50.0}}}]}
    mgr, hero, enemy = setup(extra={"ro": ro, "ro2": ro2, "t_hit": hit_op([], 5)})
    mgr.cast(hero, "ro2")
    assert mgr._rules == []                                       # unbounded: refused
    mgr.cast(hero, "ro")
    assert mgr._rules[0]["consts"] == {"min_damage": 50.0} and mgr._rules[0]["flags"] == ["no_crit"]
    mgr.cast(hero, "t_hit", enemy)
    assert enemy.health == 450.0                                  # the raised floor applied
    mgr.update(2.5)
    assert mgr._rules == [] and damage.config().consts == base
    mgr.cast(hero, "t_hit", enemy)
    assert enemy.health == 445.0


def test_domain_shrine_and_ubw_rows_run():
    mgr, hero, enemy = setup()
    assert mgr.cast(hero, "corpus_domain_void").ok
    mgr.update(0.1)
    z = mgr._zones[0]
    assert z["id"] == "void" and z["barrier"] == "closed" and z["sure_hit"] and enemy.entity_id in z["members"]
    mgr.update(25.0)
    assert mgr._zones == []
    mgr2, hero2, enemy2 = setup()
    mgr2.cast(hero2, "corpus_malevolent_shrine")
    mgr2.update(1.0)
    mgr2.update(1.0)
    assert enemy2.health < 500.0 and len(mgr2._zones) == 2
    mgr3, hero3, enemy3 = setup()
    assert mgr3.cast(hero3, "corpus_unlimited_blade_works").ok
    mgr3.update(2.0)
    assert enemy3.health < 500.0


def test_zone_mod_changes_a_live_zone():
    mgr, hero, enemy = setup(extra={"z": zone_ability(), "zm": {"id": "zm", "trigger": "cast", "ops": [
        {"kind": "zone_mod", "target": "self", "id": "zz", "radius": 2, "barrier": "closed"}]}})
    mgr.cast(hero, "z")
    mgr.update(0.1)
    assert enemy.entity_id in mgr._zones[0]["members"]
    mgr.cast(hero, "zm")
    mgr.update(0.1)
    assert mgr._zones[0]["radius"] == 2.0 and mgr._zones[0]["barrier"] == "closed" and mgr._zones[0]["members"] == {}


def test_linked_zones_are_portals():
    a = {"id": "pa", "trigger": "cast", "ops": [{"kind": "zone", "target": "self", "id": "A", "radius": 3, "affects": "enemies", "link": "B"},
                                                 {"kind": "zone", "target": "self", "id": "B", "to": [40, 0], "radius": 3, "affects": "enemies", "link": "A"}]}
    mgr, hero, enemy = setup(extra={"pa": a}, enemy_x=50.0)
    mgr.cast(hero, "pa")
    mgr.update(0.1)
    enemy.x = 1.0                                                 # steps into A -> B's centre
    mgr.update(0.1)
    assert enemy.x == 40.0
    mgr.update(0.1)
    assert enemy.x == 40.0                                        # no bounce back


def test_same_seed_runs_are_identical():
    def run():
        mgr, hero, enemy = setup(7)
        mgr.cast(hero, "corpus_malevolent_shrine")
        for _ in range(12):
            mgr.cast(enemy, "t_hit", hero)
            mgr.update(0.5)
        return hero.health, enemy.health
    assert run() == run()


def test_performance_guard_200_members_600_frames():
    tick = {"every": {"flat": 1}, "ops": [{"kind": "mod", "target": "enemy", "stat": "defense", "op": "add", "value": {"flat": 0}}]}
    mgr, hero, _enemy = setup(extra={"z": zone_ability(radius=100, tick=tick)})
    for i in range(200):
        mgr.register(Fighter(x=float(i % 50), y=float(i // 50), hp=100.0), "monsters")
    mgr.cast(hero, "z")
    t0 = time.perf_counter()
    for _ in range(600):
        mgr.update(1 / 60)
    assert time.perf_counter() - t0 < 60.0
    assert len(mgr._zones[0]["members"]) >= 200
