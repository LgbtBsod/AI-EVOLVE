"""Slice G1b: SOCIAL ops and RESOURCE POOLS as executable specs on EffectManager (src/effects/social.py).

lua_content/corpus_holdout_abilities.lua (family "social"): Zero's speech / Paragon persuasion (reputation tiers fire ops), Broker a ceasefire
(diplomacy), Loan with interest (contract + a debt tick), Pewter burn (fuel_consume + crash), Bardic Inspiration / Waterfowl Dance / Smite (pools).
Caps, tiers and pools are data in effect_rules.lua `social`.
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

from src.effects import social  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from tests.test_effect_manager import Fighter, World  # noqa: E402
from tools.effect_schema.validate import validate_op  # noqa: E402

ROWS = {a["id"]: a for a in lua_bridge.load(lua_bridge.CONTENT / "corpus_holdout_abilities.lua")["abilities"] if a.get("family") == "social"}


def row(aid, ops, **kw):
    return {"id": aid, "trigger": "cast", "range": 999, "needs_target": any(o.get("target") == "enemy" for o in ops), "ops": ops, **kw}


def setup(seed=1, extra=None):
    mgr = EffectManager(world=World(), abilities={**ROWS, **(extra or {})}, rng=random.Random(seed))
    hero, foe = Fighter(x=0.0, y=0.0, hp=100.0), Fighter(x=5.0, y=0.0, hp=100.0)
    mgr.register(hero, "hero")
    mgr.register(foe, "monsters")
    return mgr, hero, foe


def run(mgr, secs, dt=0.5):
    for _ in range(int(round(secs / dt))):
        mgr.update(dt)


def eff(mgr, e, stat):
    st = mgr.state(e)
    st.refresh(mgr.now)
    return st.unit._eff(stat)


def test_every_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in ROWS.values()} == {108, 110, 127, 140, 142, 145, 154, 155}
    for aid, ab in ROWS.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_zero_speech_crossing_the_revered_tier_fires_its_op_once():
    mgr, hero, foe = setup()
    assert mgr.cast(hero, "hold_zero_speech", foe).ok
    st = mgr.state(hero)
    assert social.standing(st, "citizens") == 60.0 and social.tier_id(st, "citizens") == "revered"
    assert mgr.state(foe).unit.external["aggro"]["faction"] == "hero"      # the F2 set_faction seam
    mgr.state(foe).unit.external["aggro"]["faction"] = "monsters"
    st.cooldowns.clear()
    mgr.cast(hero, "hold_zero_speech", foe)                    # already revered: no new entry, so no re-fire
    assert mgr.state(foe).unit.external["aggro"]["faction"] == "monsters" and social.standing(st, "citizens") == 100.0


def test_reputation_is_clamped_and_gate_refuses_below_the_tier():
    mgr, hero, foe = setup()
    mgr.abilities["rep"] = row("rep", [{"kind": "reputation", "target": "enemy", "faction": "f", "delta": 500}])
    mgr.abilities["gated"] = row("gated", [{"kind": "reputation", "target": "enemy", "faction": "g", "delta": 5, "gate": "friendly"}])
    st = mgr.state(hero)
    mgr.cast(hero, "rep", foe)
    assert social.standing(st, "f") == 60.0                # max_delta
    mgr.cast(hero, "gated", foe)
    assert social.standing(st, "g") == 0.0 and mgr.soc_state().log[-1]["refused"].startswith("reputation:gate")


def test_paragon_persuasion_threshold_opens_a_ceasefire_that_expires():
    mgr, hero, foe = setup()
    assert mgr.cast(hero, "hold_paragon_persuasion", foe).ok
    assert social.relation(mgr, "hero", "monsters") == "ceasefire"
    assert mgr.state(foe).unit.external["aggro"]["aggro_mode"] == "passive"
    run(mgr, 21)
    assert social.relation(mgr, "hero", "monsters") is None
    assert "aggro" not in mgr.state(foe).unit.external


def test_diplomacy_alliance_merges_and_restores_factions_and_costs_mana():
    mgr, hero, foe = setup()
    mgr.abilities["ally"] = row("ally", [{"kind": "diplomacy", "target": "enemy", "relation": "alliance", "duration": {"flat": 5}}])
    mana = mgr.op_resource(mgr.state(hero), "mana")
    assert mgr.cast(hero, "ally", foe).ok
    assert mgr.state(foe).faction == "hero" and mgr.op_resource(mgr.state(hero), "mana") == mana - 20
    run(mgr, 6)
    assert mgr.state(foe).faction == "monsters"
    mgr.abilities["bad"] = row("bad", [{"kind": "diplomacy", "target": "enemy", "relation": "conquest", "duration": {"flat": 5}}])
    mgr.cast(hero, "bad", foe)
    assert mgr.soc_state().log[-1]["refused"] == "diplomacy:conquest"


def test_broker_ceasefire_duration_is_capped():
    mgr, hero, foe = setup()
    mgr.abilities["long"] = row("long", [{"kind": "diplomacy", "target": "enemy", "relation": "war", "duration": {"flat": 9999}}])
    mgr.cast(hero, "long", foe)
    assert mgr.soc_state().treaties[0]["until"] - mgr.now == 120


def test_loan_debt_grows_by_a_periodic_tick_and_breach_penalises_the_debtor():
    mgr, hero, foe = setup()
    assert mgr.cast(hero, "hold_loan_interest", foe).ok
    fst = mgr.state(foe)
    assert social.debt_of(fst, "loan") == 100.0
    run(mgr, 5)
    assert social.debt_of(fst, "loan") == pytest.approx(110.0)
    run(mgr, 5)
    assert social.debt_of(fst, "loan") == pytest.approx(121.0)
    d0 = eff(mgr, foe, "defense")
    run(mgr, 11)
    assert not mgr.soc_state().contracts and mgr.soc_state().log[-1]["closed"] == "expired_unpaid"
    assert eff(mgr, foe, "defense") == d0 - 5


def test_settling_the_debt_fulfils_the_contract_and_interest_is_capped():
    mgr, hero, foe = setup()
    mgr.abilities["settle"] = row("settle", [{"kind": "contract", "target": "enemy", "action": "settle", "id": "loan"}])
    mgr.cast(hero, "hold_loan_interest", foe)
    fst = mgr.state(foe)
    run(mgr, 5)
    mgr.cast(hero, "settle", foe)                               # pays min(debt, mana): the loan gave 100 mana (capped by max_mana)
    assert social.debt_of(fst, "loan") < 110.0
    mgr.abilities["huge"] = row("huge", [{"kind": "contract", "target": "enemy", "id": "h", "principal": 100, "duration": {"flat": 200},
                                          "interest": {"rate": 5.0, "every": 1}}])
    mgr.cast(hero, "huge", foe)
    run(mgr, 20)
    assert social.debt_of(fst, "h") == 300.0


def test_pewter_burn_drains_then_crashes_and_debt_fires_the_debt_effect():
    mgr, hero, _ = setup()
    st = mgr.state(hero)
    a0 = eff(mgr, hero, "attack_damage")
    assert mgr.cast(hero, "hold_pewter_burn").ok
    assert eff(mgr, hero, "attack_damage") == pytest.approx(a0 + 10)
    run(mgr, 4)
    assert social.pool(mgr, st, "pewter")["v"] == pytest.approx(60.0, abs=11.0)
    run(mgr, 5)
    assert not mgr.soc_state().burns
    assert eff(mgr, hero, "attack_damage") == pytest.approx(a0 - 6)        # the crash once the boost ended
    mgr.abilities["hard"] = row("hard", [{"kind": "fuel_consume", "target": "self", "pool": "pewter", "rate": 20, "duration": {"flat": 30}}])
    social.pool(mgr, st, "pewter")["v"] = 30.0
    d0 = eff(mgr, hero, "defense")
    mgr.cast(hero, "hard")
    run(mgr, 5)
    assert social.pool(mgr, st, "pewter")["debt"] > 0 and eff(mgr, hero, "defense") == d0 - 3
    run(mgr, 30)
    assert not mgr.soc_state().burns and social.pool(mgr, st, "pewter")["debt"] <= 40.0


def test_pool_without_allow_debt_refuses_and_regen_repays_debt_first():
    mgr, hero, foe = setup()
    st = mgr.state(hero)
    mgr.abilities["insp"] = row("insp", [{"kind": "fuel_consume", "target": "enemy", "pool": "inspiration", "amount": 1,
                                          "then": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 9}}]}])
    social.pool(mgr, st, "inspiration")                    # starts empty (start = 0)
    hp = foe.health
    mgr.cast(hero, "insp", foe)
    assert foe.health == hp and mgr.soc_state().log[-1]["refused"] == "fuel:inspiration"
    p = social.pool(mgr, st, "warp")
    p["v"], p["debt"] = 0.0, 2.0
    run(mgr, 8)                                            # regen 0.5/s: the debt first, the rest into the pool
    assert p["debt"] == 0.0 and p["v"] == pytest.approx(2.0, abs=0.3)


def test_bardic_inspiration_grants_dice_and_use_rolls_seeded_dice():
    def go(seed):
        mgr, hero, _ = setup(seed, {"roll": row("roll", [{"kind": "pool", "target": "self", "pool": "inspiration", "action": "use", "count": 5,
                                                          "die": True, "stat": "attack_damage", "duration": {"flat": 5}}])})
        mgr.cast(hero, "hold_bardic_inspiration")
        st = mgr.state(hero)
        assert social.pool(mgr, st, "inspiration")["v"] == 2.0
        mgr.cast(hero, "roll")
        return social.pool(mgr, st, "inspiration")["v"], list(st.unit.external["dice"])
    left, dice = go(3)
    assert left == 0.0 and len(dice) == 2 and all(1 <= d <= 6 for d in dice)
    assert go(3) == (left, dice)


def test_waterfowl_dance_heals_per_counted_hit_and_smite_perils_roll_on_the_seed():
    mgr, hero, foe = setup()
    hero.health = 50.0
    assert mgr.cast(hero, "hold_waterfowl_dance", foe).ok
    assert foe.health == 100.0 - 16.0 and hero.health == 50.0 + 8.0
    assert social.pool(mgr, mgr.state(hero), "lifesteal_hits")["v"] == 0.0

    def smite(seed):
        m, h, f = setup(seed)
        m.cast(h, "hold_smite", f)
        return f.health, h.health
    out = smite(1)
    assert out[0] == 70.0 and smite(1) == out              # 15 > 10 warp: overdraw into debt, deterministic peril roll
    assert {smite(s)[1] for s in range(12)} == {100.0, 85.0}


def test_two_same_seed_runs_are_identical():
    def go():
        mgr, hero, foe = setup(5)
        for aid in ("hold_zero_speech", "hold_loan_interest", "hold_pewter_burn", "hold_smite"):
            mgr.cast(hero, aid, foe)
            run(mgr, 3)
        return (foe.health, hero.health, dict(mgr.state(hero).unit.external.get("reputation") or {}), social.debt_of(mgr.state(foe), "loan"))
    assert go() == go()
