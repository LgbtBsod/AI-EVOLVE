"""Slice F1: FORM (stance/transform/timed_power_up) and MOVEMENT (dash/teleport/pull/push/swap) kinds as executable specs.

The rows of lua_content/corpus_abilities.lua run on EffectManager; the tests check positions, form replacement / revert, the
timed_power_up aftermath (on_exit) and that two runs with the same seed end identically.
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


def setup(seed=1, enemy_at=10.0, hp=100.0):
    mgr = EffectManager(world=World(), abilities=ROWS, rng=random.Random(seed))
    hero, enemy = Fighter(x=0.0, y=0.0, hp=hp), Fighter(x=enemy_at, y=0.0, hp=500.0)
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters")
    return mgr, hero, enemy


def walk(ops):
    for o in ops or []:
        yield o
        for key in ("on_enter", "on_exit", "stats", "fail"):
            yield from walk(o.get(key))


def forms(mgr, ent):
    return {g: r["id"] for g, r in mgr.state(ent).unit.external.get("forms", {}).items()}


def test_every_corpus_row_validates_and_is_marked():
    assert {a["corpus"] for a in ROWS.values() if "corpus" in a and a.get("family") != "control"} == {8, 9, 17, 23, 24, 27, 28, 36}
    for aid, ab in ROWS.items():
        for o in walk(ab["ops"]):
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


# ---------------------------------------------------------------- movement

def test_dash_moves_self_toward_target_and_stops_short():
    mgr, hero, enemy = setup()
    assert mgr.cast(hero, "corpus_rasengan", enemy).ok
    assert (hero.x, hero.y) == (6.0, 0.0) and enemy.health < 500.0           # distance 6 of 10, then the hit


def test_dash_never_passes_the_target():
    mgr, hero, enemy = setup(enemy_at=4.0)
    mgr.cast(hero, "corpus_guanyin_zero", enemy)
    assert hero.x == pytest.approx(2.5)                                      # stops 1.5 short of the target


def test_pull_and_push_move_the_target_along_the_axis():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_bungee_gum", enemy)
    assert enemy.x == pytest.approx(5.0) and "gum" in mgr.state(enemy).marks
    mgr.cast(hero, "corpus_gust", enemy)
    assert enemy.x == pytest.approx(9.0)


def test_teleport_behind_target_to_point_and_swap():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_instant_transmission", enemy)
    assert (hero.x, hero.y) == pytest.approx((11.5, 0.0))                    # behind the target, seen from the caster
    mgr.cast(hero, "corpus_blink_to")
    assert (hero.x, hero.y) == (20.0, 5.0)
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_shambles", enemy)
    assert (hero.x, enemy.x) == (10.0, 0.0)


def test_move_is_clamped_by_the_world_when_it_can():
    mgr, hero, enemy = setup()
    mgr.world.clamp_position = lambda x, y: (min(x, 8.0), y)
    mgr.cast(hero, "corpus_gust", enemy)
    assert enemy.x == 8.0


# ---------------------------------------------------------------- forms

def test_transform_applies_stats_and_reverts_at_expiry():
    mgr, hero, _ = setup()
    d0 = hero.speed
    assert mgr.cast(hero, "corpus_super_saiyan").ok
    assert forms(mgr, hero) == {"transform": "super_saiyan"} and hero.speed > d0
    mgr.update(39.0)
    assert forms(mgr, hero) and hero.speed > d0
    mgr.update(2.0)
    assert forms(mgr, hero) == {} and hero.speed == d0


def test_same_group_replaces_and_runs_on_exit_then_on_enter():
    mgr, hero, _ = setup(hp=100.0)
    mgr.cast(hero, "corpus_kurama_mode")
    st = mgr.state(hero)
    order = []
    orig = mgr._run_ops
    mgr._run_ops = lambda s, ops, *a, **k: (order.extend(o["kind"] + ":" + str(o.get("stat")) for o in ops), orig(s, ops, *a, **k))[1]
    forms_of = st.unit.external["forms"]
    forms_of["transform"]["on_exit"] = [{"kind": "heal", "target": "self", "stat": "hp", "value": {"flat": 1}}]
    mgr.cast(hero, {"id": "swap_form", "ops": [{"kind": "transform", "target": "self", "id": "other", "duration": {"flat": 5},
                                                "on_enter": [{"kind": "deal", "target": "self", "stat": "mana", "op": "sub",
                                                              "value": {"flat": 1}}]}]})
    assert forms(mgr, hero)["transform"] == "other"
    assert order[1:] == ["heal:hp", "deal:mana"]                                  # old on_exit first, then the new on_enter


def test_conflict_with_blocks_and_stance_group_is_exclusive():
    mgr, hero, _ = setup()
    mgr.cast(hero, "corpus_gear5")
    assert forms(mgr, hero) == {"gear": "gear_fifth", "transform": "sun_god", "power_up:gear5_rush": "gear5_rush"}
    mgr.cast(hero, "corpus_gear_second")                                     # gear_second conflicts with gear_fifth
    assert "gear2" not in forms(mgr, hero)
    mgr.cast(hero, {"id": "again", "ops": [{"kind": "stance", "target": "self", "id": "gear_x", "exclusive_group": "gear"}]})
    assert forms(mgr, hero)["gear"] == "gear_x"                              # replaced, not stacked


def test_timed_power_up_runs_its_aftermath_at_expiry():
    mgr, hero, _ = setup(hp=100.0)
    mgr.cast(hero, "corpus_kurama_mode")
    hp0 = hero.health
    mgr.update(29.0)
    assert hero.health == hp0 and "power_up:kurama_chakra" in forms(mgr, hero)
    mgr.update(2.0)
    assert "power_up:kurama_chakra" not in forms(mgr, hero) and hero.health == pytest.approx(hp0 - 5.0)


def test_form_ability_set_is_exposed_as_data():
    mgr, hero, _ = setup()
    mgr.cast(hero, "corpus_kurama_mode")
    assert mgr.form_abilities(hero) == {"add": ["kurama_bomb"], "remove": ["weapon_attack"]}
    mgr.update(31.0)
    assert mgr.form_abilities(hero) == {"add": [], "remove": []}


@pytest.mark.parametrize("script", ["corpus_rasengan", "corpus_bungee_gum", "corpus_instant_transmission", "corpus_super_saiyan"])
def test_deterministic_across_two_runs(script):
    def run():
        mgr, hero, enemy = setup(seed=7)
        mgr.cast(hero, script, enemy)
        mgr.update(20.0)
        return hero.x, hero.y, enemy.x, enemy.y, hero.health, enemy.health, forms(mgr, hero)

    assert run() == run()
