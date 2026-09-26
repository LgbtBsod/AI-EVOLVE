"""Slice F2: the CONTROL family (hypnosis / command / possess / dominance / tame / temptation) as executable specs.

lua_content/corpus_abilities.lua rows with family = "control" run on EffectManager: applied, resisted, immune boss, expiry restore,
caster-death restore, permanent tame with a seeded roll, and two same-seed runs ending identically.
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
CONTROL = {k: a for k, a in ROWS.items() if a.get("family") == "control"}


def setup(seed=1, hero_hp=1000.0):
    mgr = EffectManager(world=World(), abilities=ROWS, rng=random.Random(seed))
    hero, enemy = Fighter(x=0.0, y=0.0, hp=hero_hp), Fighter(x=5.0, y=0.0, hp=500.0)
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters")
    return mgr, hero, enemy


def ctl(mgr, ent):
    return (mgr.state(ent).unit.external.get("control") or {}).get("rec")


def aggro(mgr, ent):
    return mgr.state(ent).unit.external.get("aggro") or {}


def test_every_control_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in CONTROL.values() if "corpus" in a} == {11, 13, 15, 20, 49, 51, 58, 60}
    for aid, ab in CONTROL.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


@pytest.mark.parametrize("aid,mode", [("corpus_tsukuyomi", "illusion:obey"), ("corpus_the_voice", "command:stand_still"),
                                      ("corpus_bloodbending", "controlled:puppet"), ("corpus_one_ring", "dominated:obey"),
                                      ("corpus_temptation", "tempted:follow")])
def test_control_is_applied_and_expires_restoring_everything(aid, mode):
    mgr, hero, enemy = setup()
    faction0 = mgr.state(enemy).faction
    assert mgr.cast(hero, aid, enemy).ok
    rec = ctl(mgr, enemy)
    assert rec and aggro(mgr, enemy)["aggro_mode"] == mode and aggro(mgr, enemy)["controller"] == rec["controller"]
    if rec["kind"] in ("possess", "dominance"):
        assert mgr.state(enemy).faction == "hero"
    mgr.update(rec["until"] + 0.1)
    assert ctl(mgr, enemy) is None and aggro(mgr, enemy) == {} and mgr.state(enemy).faction == faction0


def test_hypnosis_overrides_the_target_and_perception():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_tsukuyomi", enemy)
    assert aggro(mgr, enemy)["target"] == "caster" and aggro(mgr, enemy)["perception"] == "dream"


def test_condition_blocks_a_stronger_target():
    mgr, hero, enemy = setup(hero_hp=100.0)            # the enemy (500 max hp) is not inferior to the caster
    mgr.cast(hero, "corpus_one_ring", enemy)
    mgr.cast(hero, "corpus_parasite_strings", enemy)
    assert ctl(mgr, enemy) is None and mgr.state(enemy).faction == "monsters"


def test_resist_stat_and_boss_immunity():
    mgr, hero, enemy = setup()
    mgr.state(enemy).unit.base["status_resist_voice"] = 100.0
    mgr.cast(hero, "corpus_the_voice", enemy)
    assert ctl(mgr, enemy) is None
    mgr, hero, enemy = setup()
    mgr.state(enemy).unit.base["status_resist_control"] = 100.0     # generic resist covers every control kind
    mgr.cast(hero, "corpus_axii", enemy)
    assert ctl(mgr, enemy) is None
    mgr, hero, boss = setup()                                           # boss flag = an `immune` op with effect=control
    mgr.state(boss).unit.buffs["block:control"] = {"until": 1e18}
    mgr.cast(hero, "corpus_bloodbending", boss)
    assert ctl(mgr, boss) is None and mgr.state(boss).faction == "monsters"


def test_caster_death_restores_faction_and_aggro():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_parasite_strings", enemy)
    assert ctl(mgr, enemy) and mgr.state(enemy).faction == "hero"
    hero.health = 0.0
    mgr.update(0.1)
    assert ctl(mgr, enemy) is None and mgr.state(enemy).faction == "monsters" and aggro(mgr, enemy) == {}


def test_on_exit_runs_when_the_control_ends():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_parasite_strings", enemy)
    mgr.update(9.5)
    assert enemy.health == 500.0
    mgr.update(1.0)
    assert enemy.health == 495.0                                         # on_exit runs from the host's view: self = the released target


def test_new_control_replaces_the_old_and_restores_first():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_parasite_strings", enemy)
    mgr.cast(hero, "corpus_the_voice", enemy)
    assert ctl(mgr, enemy)["kind"] == "command" and mgr.state(enemy).faction == "monsters"
    mgr.update(5.0)
    assert ctl(mgr, enemy) is None and aggro(mgr, enemy) == {}


def _tame_run(seed):
    mgr, hero, enemy = setup(seed)
    out = []
    for _ in range(6):
        e = Fighter(x=5.0, y=0.0, hp=500.0)
        mgr.register(e, "monsters")
        mgr.cast(hero, "corpus_tame_beast", e)
        out.append(mgr.state(e).faction)
        mgr.update(1.0)
    return out, [mgr.state(s.entity).faction for s in mgr.states.values()]


def test_tame_is_permanent_and_deterministic_per_seed():
    a, b = _tame_run(3), _tame_run(3)
    assert a == b and "hero" in a[0] and "monsters" in a[0]              # chance 50: both outcomes occur within 6 casts
    mgr, hero, enemy = setup()
    mgr.state(enemy).unit.base["status_resist_tame"] = 100.0
    mgr.cast(hero, "corpus_tame_beast", enemy)
    assert mgr.state(enemy).faction == "monsters"


def test_tamed_stays_tamed_after_the_tamer_dies():
    mgr, hero, enemy = setup()
    for seed in range(20):
        mgr.rng = random.Random(seed)
        mgr.cast(hero, "corpus_tame_beast", enemy)
        if mgr.state(enemy).faction == "hero":
            break
    assert mgr.state(enemy).faction == "hero" and ctl(mgr, enemy) is None
    hero.health = 0.0
    mgr.update(50.0)
    assert mgr.state(enemy).faction == "hero"


def test_two_same_seed_runs_end_identically():
    def run():
        mgr, hero, enemy = setup(7)
        for aid in ("corpus_the_voice", "corpus_tame_beast", "corpus_tsukuyomi"):
            mgr.cast(hero, aid, enemy)
            mgr.update(3.0)
        return (mgr.state(enemy).faction, ctl(mgr, enemy) and ctl(mgr, enemy)["kind"], {k: v for k, v in aggro(mgr, enemy).items() if k != "controller"}, round(mgr.now, 3))
    assert run() == run()
