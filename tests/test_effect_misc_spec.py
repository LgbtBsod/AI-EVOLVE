"""Slice F6a: the MIMIC family as executable specs on EffectManager (src/effects/mimic.py).

lua_content/corpus_abilities.lua rows with family = "mimic": fusion (damage = f(both payloads)), Heavenly Restriction (lift + trade + restore),
on_dispel (fires once), copied technique (usable, fidelity, expires), forged percept, control link (survives distance, breaks on a condition
or an op), erase (no death events, erase_immune), copied asset (works and expires); same-seed determinism.
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
MIMIC = {k: a for k, a in ROWS.items() if a.get("family") == "mimic"}
SLASH = {"id": "fire_slash", "trigger": "cast", "range": 999, "needs_target": True,
         "ops": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 12}, "flags": ["no_crit", "true_damage"]}]}


class SummonWorld(World):
    def __init__(self):
        super().__init__()
        self.made = []

    def spawn_summon(self, kind, x, y, faction, level, owner):
        f = Fighter(x=x, y=y, hp=50.0)
        f.summoned_by = owner
        self.made.append(f)
        return f


def setup(seed=1, enemy_x=5.0, techs=("fire_slash",), extra=None):
    mgr = EffectManager(world=SummonWorld(), abilities={**ROWS, "fire_slash": SLASH, **(extra or {})}, rng=random.Random(seed))
    hero, enemy = Fighter(x=0.0, y=0.0, hp=500.0), Fighter(x=enemy_x, y=0.0, hp=500.0)
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters", list(techs))
    return mgr, hero, enemy


def fuse(**kw):
    return {"id": "fz", "trigger": "cast", "range": 999, "needs_target": True,
            "ops": [{"kind": "fusion_strike", "target": "enemy", "flags": ["no_crit", "true_damage"], **kw}]}


def test_every_mimic_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in MIMIC.values() if "corpus" in a} == {2, 6, 7, 10, 15, 20, 29, 32}
    for aid, ab in MIMIC.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_fusion_strike_damage_is_a_function_of_both_payloads():
    mgr, hero, enemy = setup(extra={"a": fuse(parts=[{"value": {"flat": 4}}, {"value": {"flat": 5}}]),
                                    "b": fuse(parts=[{"value": {"flat": 4}}, {"value": {"flat": 9}}], mult=2),
                                    "c": fuse(parts=[{"value": {"flat": 4}}, {"value": {"flat": 5}}], merge="mul")})
    for aid, want in (("a", 9.0), ("b", 26.0), ("c", 20.0)):
        before = enemy.health
        mgr.cast(hero, aid, enemy)
        assert before - enemy.health == pytest.approx(want)
    before = enemy.health
    mgr.cast(hero, "corpus_hollow_purple", enemy)                 # the corpus row: (attack_damage 20 + 40) * 2, pays 20 mana
    assert hero.mana == 80.0 and before - enemy.health == pytest.approx(120.0)


def test_heavenly_restriction_lifts_trades_and_restores():
    mgr, hero, enemy = setup()
    unit = mgr.state(hero).unit
    base_atk, base_def = unit._eff("attack_damage"), unit._eff("defense")
    mgr.cast(hero, "corpus_heavenly_restriction")
    mgr.update(0.1)
    assert mgr.restriction_lifted(hero, "cursed_energy")
    assert unit._eff("attack_damage") > base_atk and unit._eff("defense") < base_def
    mgr.update(25.0)
    assert not mgr.restriction_lifted(hero, "cursed_energy")
    assert unit._eff("attack_damage") == pytest.approx(base_atk) and unit._eff("defense") == pytest.approx(base_def)


def test_on_dispel_fires_once_on_dispel():
    mgr, hero, enemy = setup()
    mgr.cast(hero, "corpus_shadow_clone")
    clone = mgr.world.made[0]
    hero.health = 100.0
    mgr.cast(hero, "corpus_dispel_clone", clone)
    assert clone.health <= 0 and hero.health == 115.0
    mgr.cast(hero, "corpus_dispel_clone", clone)                   # already gone: nothing fires again
    assert hero.health == 115.0


def test_on_dispel_fires_when_the_clone_is_killed_and_dispel_ignores_non_summons():
    kill = {"id": "t_kill", "trigger": "cast", "range": 999, "needs_target": True, "ops": [{"kind": "kill", "target": "enemy"}]}
    mgr, hero, enemy = setup(extra={"t_kill": kill})
    mgr.cast(hero, "corpus_shadow_clone")
    clone = mgr.world.made[0]
    hero.health = 100.0
    mgr.cast(hero, "corpus_dispel_clone", enemy)                   # not a summon: untouched
    assert enemy.health == 500.0
    mgr.cast(hero, "t_kill", clone)
    assert hero.health == 115.0


def test_copied_technique_is_usable_with_fidelity_then_expires():
    mgr, hero, enemy = setup()
    assert mgr.cast(hero, "corpus_sharingan_copy", enemy).ok
    assert mgr.state(hero).spells == ["fire_slash"]
    mgr.cast(hero, "corpus_use_copied", enemy)
    dealt = 500.0 - enemy.health
    full = {**ROWS["corpus_sharingan_copy"], "id": "full", "ops": [ROWS["corpus_sharingan_copy"]["ops"][0],
                                                                    {**ROWS["corpus_sharingan_copy"]["ops"][1], "fidelity": 1.0}]}
    mgr2, hero2, enemy2 = setup(extra={"full": full})
    mgr2.cast(hero2, "full", enemy2)
    mgr2.cast(hero2, "corpus_use_copied", enemy2)
    assert 0 < dealt < 500.0 - enemy2.health                        # fidelity 0.7 < 1.0
    mgr.update(31.0)
    assert mgr.state(hero).spells == []
    mgr.cast(hero, "corpus_use_copied", enemy)
    assert enemy.health == 500.0 - dealt                            # nothing left to use


def test_copy_technique_needs_the_technique_to_be_observed():
    blind = {"id": "t_blind", "trigger": "cast", "range": 999, "needs_target": True, "ops": [ROWS["corpus_sharingan_copy"]["ops"][1]]}
    mgr, hero, enemy = setup(extra={"t_blind": blind})
    mgr.cast(hero, "t_blind", enemy)
    assert mgr.state(hero).spells == []


def test_forged_percept_replaces_the_real_one_then_expires():
    look = {"id": "t_look", "trigger": "cast", "range": 999, "needs_target": True,
            "ops": [{"kind": "perceive", "target": "enemy", "duration": {"flat": 60}, "what": ["hp"]}]}
    mgr, hero, enemy = setup(extra={"t_look": look})
    mgr.cast(enemy, "t_look", hero)                                 # the victim-to-be watches the hero
    (facts,) = mgr.perceived(enemy).values()
    assert facts["hp"]["hp"] == 500.0
    mgr.cast(hero, "corpus_kyoka_forged", enemy)
    (facts,) = mgr.perceived(enemy).values()
    assert facts["hp"]["hp"] == 9999
    mgr.update(9.0)
    (facts,) = mgr.perceived(enemy).values()
    assert facts["hp"]["hp"] == 500.0


def _ctl(mgr, ent):
    return (mgr.state(ent).unit.external.get("control") or {}).get("rec")


def _weak(mgr, enemy):
    enemy.max_health = enemy.health = 100.0
    mgr.state(enemy).refresh(mgr.now)


def test_control_link_survives_distance_and_breaks_on_condition():
    mgr, hero, enemy = setup()
    _weak(mgr, enemy)
    assert mgr.cast(hero, "corpus_parasite_link", enemy).ok
    assert _ctl(mgr, enemy)["link"] and mgr.state(enemy).faction == "hero"
    enemy.x = 900.0
    mgr.update(120.0)                                              # far away, a long time: the link holds
    assert _ctl(mgr, enemy) is not None
    enemy.health = 10.0                                            # break_if hp < 20
    mgr.update(0.1)
    assert _ctl(mgr, enemy) is None and mgr.state(enemy).faction == "monsters"


def test_control_link_breaks_on_an_op_and_when_the_controller_dies():
    mgr, hero, enemy = setup()
    _weak(mgr, enemy)
    mgr.cast(hero, "corpus_parasite_link", enemy)
    mgr.cast(hero, "corpus_cut_link", enemy)
    mgr.update(0.1)
    assert _ctl(mgr, enemy) is None and mgr.state(enemy).faction == "monsters"
    mgr.state(hero).cooldowns.clear()
    mgr.cast(hero, "corpus_parasite_link", enemy)
    assert _ctl(mgr, enemy) is not None
    hero.health = 0.0
    mgr.update(0.1)
    assert _ctl(mgr, enemy) is None


def test_erase_leaves_no_death_events_and_respects_erase_immune():
    guard = {"id": "guard", "trigger": "cast", "ops": [{"kind": "on_lethal", "target": "self", "id": "g", "charges": 5, "restore": 100}]}
    mgr, hero, enemy = setup(extra={"guard": guard})
    seen = []
    mgr.register_event_handler(seen.append)
    mgr.cast(enemy, "guard")
    st = mgr.state(enemy)
    st.unit.external.setdefault("mimic", {})["dispel"] = {"owner": hero, "fired": False,
                                                          "ops": [{"kind": "heal", "target": "self", "stat": "hp", "value": {"flat": 50}}]}
    hero.health = 100.0
    st.unit.buffs["erase_immune"] = {"until": 1e18}
    mgr.cast(hero, "corpus_hakai", enemy)
    assert enemy.health == 500.0 and not getattr(enemy, "erased", False)      # immune
    st.unit.buffs.pop("erase_immune")
    mgr.state(hero).cooldowns.clear()
    mgr.cast(hero, "corpus_hakai", enemy)
    assert enemy.health <= 0 and enemy.erased and st.unit.external["erased"]
    assert hero.health == 100.0 and not [i for i in seen if getattr(i, "killed", False)]    # no kill / die, no on_lethal, no on_dispel
    mgr.op_restore_hp(st, 50.0)
    assert enemy.health <= 0                                        # cannot be revived


def test_copied_asset_works_then_expires():
    mgr, hero, enemy = setup()
    assert mgr.cast(hero, "corpus_ubw_copy", enemy).ok
    (new,) = [a for a in mgr.state(hero).abilities if "~copy" in a]
    assert mgr.cast(hero, new, enemy).ok and enemy.health == 488.0
    mgr.update(31.0)
    assert new not in mgr.state(hero).abilities and not mgr.cast(hero, new, enemy).ok


def test_same_seed_runs_are_identical():
    def run():
        mgr, hero, enemy = setup(seed=7)
        for cid in ("corpus_hollow_purple", "corpus_sharingan_copy", "corpus_use_copied", "corpus_shadow_clone", "corpus_ubw_copy"):
            mgr.cast(hero, cid, enemy)
            mgr.update(1.0)
        return enemy.health, hero.health, hero.mana, list(mgr.state(hero).spells), sorted(a.split(":")[0] for a in mgr.state(hero).abilities)
    assert run() == run()
