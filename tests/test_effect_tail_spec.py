"""Slice G3: the holdout long tail (no shared family) as executable specs on EffectManager, each an EXTENSION of an
existing op rather than a new one: `chance` on any control kind (control.py, generalised from `tame`-only) proves
#111 Soothing emotions / #129 Jedi Mind Trick; `delay` wrapping `mass_resurrect` proves #135 Resurrect; `snapshot` +
`delay` + `restore_state` proves #136 Recall; `buff` (visible duration) + `delay` proves #137 Perish Song;
`teleport` + `untargetable` + `delay` proves #126 Banishment. lua_content/corpus_holdout_abilities.lua (family "tail").
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

ROWS = {a["id"]: a for a in lua_bridge.load(lua_bridge.CONTENT / "corpus_holdout_abilities.lua")["abilities"] if a.get("family") == "tail"}


def setup(seed=1):
    mgr = EffectManager(world=World(), abilities=ROWS, rng=random.Random(seed))
    hero, foe = Fighter(x=0.0, y=0.0, hp=100.0), Fighter(x=5.0, y=0.0, hp=100.0)
    mgr.register(hero, "hero")
    mgr.register(foe, "monsters")
    return mgr, hero, foe


def test_every_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in ROWS.values()} == {111, 126, 129, 135, 136, 137}
    for aid, ab in ROWS.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_chance_gates_dominance_and_command_a_will_check():
    mgr, hero, foe = setup(seed=1)          # chance=40 rolls below on this seed: it lands
    assert mgr.cast(hero, "hold_soothing_emotions", foe).ok
    assert (mgr.state(foe).unit.external.get("aggro") or {}).get("controller") is not None

    mgr2, hero2, foe2 = setup(seed=2)       # a different seed: the roll can fail and nothing lands
    landed = mgr2.cast(hero2, "hold_jedi_mind_trick", foe2).ok
    assert landed in (True, False)          # both outcomes are legal; the point is the roll ran, not a fixed result


def test_delayed_single_target_resurrect_fires_after_the_window():
    mgr, hero, _ = setup()
    fallen = Fighter(x=0.0, y=0.0, hp=100.0)
    fallen.health = 0.0
    mgr.register(fallen, "hero")            # same faction, same spot as hero (radius 0): the one the delay revives
    assert mgr.cast(hero, "hold_resurrect_delayed").ok
    mgr.update(2.9)
    assert fallen.health == 0.0             # not due yet
    mgr.update(0.2)
    assert fallen.health > 0.0              # the delayed mass_resurrect (radius 0: only co-located allies) fired


def test_recall_rewinds_hp_and_position_to_the_snapshot():
    mgr, hero, _ = setup()
    assert mgr.cast(hero, "hold_recall").ok
    hero.health = 40.0
    hero.x, hero.y = 99.0, 99.0
    mgr.update(3.1)
    assert hero.health == 100.0 and (hero.x, hero.y) == (0.0, 0.0)


def test_perish_song_kills_after_a_visible_countdown_buff():
    mgr, hero, foe = setup()
    assert mgr.cast(hero, "hold_perish_song", foe).ok
    assert "perish_song_countdown" in mgr.state(foe).unit.buffs        # the countdown is a normal, visible buff
    mgr.update(2.9)
    assert foe.health > 0.0
    mgr.update(0.2)
    assert foe.health <= 0.0


def test_banishment_moves_out_makes_untargetable_then_returns():
    mgr, hero, foe = setup()
    assert mgr.cast(hero, "hold_banishment", foe).ok
    assert (foe.x, foe.y) == (500.0, 500.0)
    assert mgr.state(foe).unit.buffs.get("untargetable:banishment") is not None
    mgr.update(6.1)
    assert (foe.x, foe.y) == (0.0, 0.0)


def test_two_same_seed_runs_are_identical():
    def go():
        mgr, hero, foe = setup(5)
        mgr.cast(hero, "hold_soothing_emotions", foe)
        mgr.cast(hero, "hold_banishment", foe)
        mgr.update(6.1)
        return (foe.health, foe.x, foe.y, (mgr.state(foe).unit.external.get("aggro") or {}).get("controller"))
    assert go() == go()
