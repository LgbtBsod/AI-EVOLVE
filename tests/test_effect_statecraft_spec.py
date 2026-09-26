"""Slice F8: STATE ops as executable specs on EffectManager (src/effects/statecraft.py).

lua_content/corpus_abilities.lua rows with family = "state": Horcruxes (snapshot + on_lethal restore + respawn at an anchor), Dormammu (time_loop with
carried memory), Death Note (write / rename / wish, kill.cause), Expelliarmus (confiscate). Forward-only: a restore puts a saved state back.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects import statecraft  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from tests.test_effect_manager import Fighter, World  # noqa: E402
from tools.effect_schema.validate import validate_op  # noqa: E402

ROWS = {a["id"]: a for a in lua_bridge.load(lua_bridge.CONTENT / "corpus_abilities.lua")["abilities"]}
STATE = {k: a for k, a in ROWS.items() if a.get("family") == "state"}
KILL = {"id": "k", "trigger": "cast", "range": 999, "needs_target": True, "ops": [{"kind": "kill", "target": "enemy"}]}


def row(aid, ops, **kw):
    return {"id": aid, "trigger": "cast", "range": 999, "needs_target": any(o.get("target") == "enemy" for o in ops), "ops": ops, **kw}


def setup(seed=1, extra=None, hp=500.0):
    mgr = EffectManager(world=World(), abilities={**ROWS, "k": KILL, **(extra or {})}, rng=random.Random(seed))
    hero = Fighter(x=0.0, y=0.0, hp=hp)
    foe = Fighter(x=5.0, y=0.0, hp=hp)
    mgr.register(hero, "hero")
    mgr.register(foe, "monsters")
    return mgr, hero, foe


def run(mgr, secs, dt=0.5):
    for _ in range(int(round(secs / dt))):
        mgr.update(dt)


def fingerprint(mgr):
    img = statecraft.state_image(mgr, "world", next(iter(mgr.states.values())))
    return json.dumps({"ents": img["ents"], "mgr": img["mgr"]}, sort_keys=True)


def test_every_state_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in STATE.values()} == {37, 44, 46, 54}
    for aid, ab in STATE.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_snapshot_restore_is_bit_exact_through_json_and_restores_rng_delays_and_zones():
    delay = row("z", [{"kind": "delay", "target": "self", "after": {"flat": 30}, "ops": [{"kind": "heal", "stat": "hp", "value": {"flat": 1}}]},
                      {"kind": "zone", "target": "self", "id": "zz", "radius": 5, "duration": {"flat": 60}}])
    mgr, hero, foe = setup(extra={"z": delay})
    mgr.apply_status(foe, "burn", hero)
    mgr.cast(hero, "z")
    run(mgr, 3.0)
    img = json.loads(json.dumps(mgr.snapshot("world", sid="a")))
    before = fingerprint(mgr)
    run(mgr, 5.0)
    hero.health, hero.x = 1.0, 99.0
    mgr.rng.random()
    assert fingerprint(mgr) != before
    rep = mgr.restore(img)
    assert rep["missing"] == [] and fingerprint(mgr) == before
    assert len(mgr._delayed) == 1 and len(mgr._zones) == 1


def test_two_runs_from_a_restore_are_identical():
    mgr, hero, foe = setup()
    mgr.apply_status(foe, "burn", hero)
    run(mgr, 2.0)
    mgr.snapshot("world", sid="s")
    run(mgr, 6.0)
    first = (fingerprint(mgr), foe.health, mgr.rng.random())
    mgr.restore("s")
    run(mgr, 6.0)
    assert (fingerprint(mgr), foe.health, mgr.rng.random()) == first


def test_restore_reconciles_entities_that_no_longer_exist():
    mgr, hero, foe = setup()
    mgr.snapshot("world", sid="w")
    mgr.unregister(foe)
    rep = mgr.restore("w")
    assert rep["missing"] == [statecraft.eid_of(foe)] and rep["restored"] == [statecraft.eid_of(hero)]


def test_ring_is_bounded_and_same_id_replaces():
    mgr, hero, _ = setup()
    for i in range(20):
        mgr.snapshot("self", entity=hero, sid=f"s{i}")
    mgr.snapshot("self", entity=hero, sid="s19")
    ring = mgr._sc.rings[f"entity:{statecraft.eid_of(hero)}"]
    assert len(ring) == statecraft.cfg()["ring"] and [i["id"] for i in ring].count("s19") == 1


def test_horcrux_respawns_at_the_anchor_once_and_the_charge_is_spent():
    mgr, hero, foe = setup(hp=100.0)
    mgr.cast(hero, "corpus_horcrux")
    mgr.cast(foe, "k", hero)
    assert hero.health > 0 and (hero.x, hero.y) == (40.0, 40.0)         # restored to the saved state and placed at the anchor
    mgr.cast(foe, "k", hero)
    assert hero.health <= 0                                             # the one charge is consumed: the second hit is lethal


def test_time_loop_restores_n_times_and_the_memory_survives():
    mgr, hero, foe = setup(hp=100.0)
    mgr.cast(hero, "corpus_time_loop")
    mgr.state(hero).unit.external.setdefault("memory", {})["insight"] = 0
    for n in range(1, 4):
        mgr.state(hero).unit.external["memory"]["insight"] = n * 10
        mgr.cast(foe, "k", hero)
        assert hero.health <= 0
        mgr.update(0.5)
        assert hero.health == hero.max_health and mgr.now < 2.0          # rewound to the cast moment, then forward again
        assert mgr.state(hero).unit.external["memory"]["insight"] == n * 10 and mgr.state(hero).unit.external["memory"]["loop_count"] == n
    mgr.cast(foe, "k", hero)
    mgr.update(0.5)
    assert hero.health <= 0 and not mgr._sc.loops                        # the loops are used up: the death stands


def test_write_executes_at_the_exact_time_with_its_cause_and_can_be_cancelled():
    mgr, hero, foe = setup()
    mgr.cast(hero, "corpus_death_note", foe)
    assert statecraft.name_of(mgr.state(foe)) == "target_one"
    run(mgr, 39.5)
    assert foe.health > 0
    mgr.update(0.5)                                                      # t = 40.0
    assert foe.health <= 0 and mgr.state(foe).unit.external["death"] == {"cause": "heart_attack", "t": 40.0}
    cancel = row("c", [{"kind": "write", "target": "self", "id": "note", "cancel": True}])
    mgr2, hero2, foe2 = setup(extra={"c": cancel})
    mgr2.cast(hero2, "corpus_death_note", foe2)
    mgr2.cast(hero2, "c")
    run(mgr2, 45.0)
    assert foe2.health > 0


def test_write_finds_the_target_by_its_current_name():
    extra = {"w": row("w", [{"kind": "write", "target": "enemy", "name": "ghost", "after": {"flat": 2}}]),
             "r": row("r", [{"kind": "rename", "target": "enemy", "name": "ghost"}])}
    mgr, hero, foe = setup(extra=extra)
    mgr.cast(hero, "w", foe)
    mgr.cast(hero, "r", foe)
    run(mgr, 2.0)
    assert foe.health <= 0 and mgr.state(foe).unit.external["death"]["cause"] == "written"


def test_wish_only_from_the_whitelist_with_cost_and_cooldown():
    extra = {"h": row("h", [{"kind": "wish", "target": "self", "outcome": "heal", "amount": 9999}]),
             "bad": row("bad", [{"kind": "wish", "target": "self", "outcome": "rewrite_reality"}])}
    mgr, hero, foe = setup(extra=extra)
    cap = statecraft.cfg()["wish"]["heal"]
    hero.health = 50.0
    mgr.cast(hero, "bad")
    assert mgr.state(hero).resource("mana") == 100.0 and hero.health == 50.0   # refused: nothing paid, nothing changed
    mgr.cast(hero, "h")
    assert hero.health == pytest.approx(50.0 + cap["max"], abs=1.0)            # clamped by the whitelist row
    assert mgr.state(hero).resource("mana") == pytest.approx(100.0 - cap["cost"]["amount"], abs=1.0)
    hero.health = 50.0
    mgr.cast(hero, "h")
    assert hero.health == 50.0                                                 # cooldown
    run(mgr, cap["cooldown"] + 1)
    mgr.state(hero).unit.pools["mana"] = 100.0
    mgr.cast(hero, "h")
    assert hero.health > 50.0


def test_confiscate_moves_the_grant():
    mgr, hero, foe = setup()
    mgr.state(foe).abilities.append("wand_strike")
    mgr.cast(hero, "corpus_expelliarmus", foe)
    assert "wand_strike" not in mgr.state(foe).abilities and "wand_strike" in mgr.state(hero).abilities
    assert mgr.state(hero).unit.external["grants"][0]["id"] == "wand_strike"


def test_state_rewind_alias_resolves_to_restore_state():
    rows = lua_bridge.load(lua_bridge.CONTENT / "kind_aliases.lua")["aliases"]
    assert rows["state_rewind"]["canon"] == "restore_state" and rows["state_rewind"]["exact"]


def test_snapshot_is_cheap_and_small():
    mgr, hero, foe = setup()
    for i in range(30):
        mgr.register(Fighter(x=float(i), y=1.0, hp=100.0), "monsters")
    t0 = time.perf_counter()
    img = mgr.snapshot("world")
    text = json.dumps(img)
    mgr.restore(img)
    assert time.perf_counter() - t0 < 1.0 and len(text) < 400_000
