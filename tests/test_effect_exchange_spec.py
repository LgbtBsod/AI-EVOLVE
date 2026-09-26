"""Slice G1a: BOUNDED exchange ops as executable specs on EffectManager (src/effects/exchange.py).

lua_content/corpus_holdout_abilities.lua (blind holdout ids 101-160): equal exchange / forge / dream fold (create_ex_nihilo), Resurrect / Garden (mass_resurrect),
Healing weave (status_mod), Doom (debuff), Avatar State (unbounded), Priori Incantatem (copy_last_cast + read), Skill Hunter (steal), Balefire (time_erase),
Age of Stars (change_tier). Whitelists and caps are data in effect_rules.lua `exchange`.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects import exchange, statecraft  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from tests.test_effect_manager import Fighter, World  # noqa: E402
from tools.effect_schema.validate import validate_op  # noqa: E402

ROWS = {a["id"]: a for a in lua_bridge.load(lua_bridge.CONTENT / "corpus_holdout_abilities.lua")["abilities"]}
ZAP = {"id": "zap", "trigger": "cast", "range": 999, "needs_target": True,
       "ops": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 10}}]}


def row(aid, ops, **kw):
    return {"id": aid, "trigger": "cast", "range": 999, "needs_target": any(o.get("target") == "enemy" for o in ops), "ops": ops, **kw}


def setup(seed=1, extra=None):
    mgr = EffectManager(world=World(), abilities={**ROWS, "zap": ZAP, **(extra or {})}, rng=random.Random(seed))
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


def created(hero_st):
    return hero_st.unit.external.get("created", [])


def test_every_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in ROWS.values()} == {101, 114, 116, 119, 132, 134, 135, 141, 143, 146, 150, 159, 160}
    for aid, ab in ROWS.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_create_pays_the_recipe_cost_exactly_and_records_the_product():
    mgr, hero, _ = setup()
    assert mgr.cast(hero, "hold_forge_weapon").ok
    assert hero.stamina == 75.0 and hero.mana == 100.0                           # stamina, not mana, pays the forge
    mgr.cast(hero, "hold_equal_exchange")
    mgr.cast(hero, "hold_dream_fold")
    assert hero.mana == 30.0
    assert [c["id"] for c in created(mgr.state(hero))] == ["iron_sword", "transmuted_blade", "dream_bridge"]


def test_unknown_recipe_is_refused_and_short_pay_creates_nothing():
    mgr, hero, _ = setup(extra={"bad": row("bad", [{"kind": "create_ex_nihilo", "target": "self", "recipe": "unmake_reality"}]),
                                "pile": row("pile", [{"kind": "create_ex_nihilo", "target": "self", "recipe": "familiar", "count": 9}])})
    mgr.cast(hero, "bad")
    assert hero.mana == 100.0 and created(mgr.state(hero)) == [] and mgr._sc.log[-1]["refused"] == "create:unmake_reality"
    mgr.cast(hero, "pile")                                                       # count clamped to max_count 2 -> 2 x 20 mana
    assert hero.mana == 60.0 and len(created(mgr.state(hero))) == 2
    hero.mana = 10.0
    mgr.cast(hero, "hold_dream_fold")
    assert hero.mana == 10.0 and len(created(mgr.state(hero))) == 2


def dead_allies(mgr, n, faction="hero", x=3.0):
    out = []
    for i in range(n):
        a = Fighter(x=x + i, y=0.0, hp=100.0)
        mgr.register(a, faction)
        mgr._set_health(mgr.state(a), 0.0)
        out.append(a)
    return out


def test_mass_resurrect_is_capped_clamped_and_pays_once():
    mgr, hero, foe = setup()
    allies = dead_allies(mgr, 5)
    mgr._set_health(mgr.state(foe), 0.0)                                         # a dead ENEMY is not revived
    assert mgr.cast(hero, "hold_garden_of_avalon").ok
    assert [a.health for a in allies] == [60.0, 60.0, 60.0, 0.0, 0.0] and foe.health == 0.0      # pct 100 clamped to 60, cap 3
    assert hero.mana == 50.0
    mgr.cast(hero, "hold_resurrect")                                             # the rest (radius 10, pct 40)
    assert [a.health for a in allies[3:]] == [40.0, 40.0] and hero.mana == 0.0


def test_mass_resurrect_respects_radius_and_refuses_when_nobody_or_no_mana():
    mgr, hero, _ = setup()
    far = dead_allies(mgr, 1, x=99.0)
    mgr.cast(hero, "hold_garden_of_avalon")
    assert far[0].health == 0.0 and hero.mana == 100.0 and mgr._sc.log[-1]["refused"] == "mass_resurrect"
    near = dead_allies(mgr, 1)
    hero.mana = 10.0
    mgr.cast(hero, "hold_garden_of_avalon")
    assert near[0].health == 0.0 and hero.mana == 10.0


def test_status_mod_changes_an_active_status_and_refuses_an_inactive_one():
    mgr, hero, foe = setup()
    mgr.cast(hero, "hold_healing_weave", foe)
    assert mgr._sc.log[-1]["refused"] == "status_mod:burn"                       # nothing active: no change
    run(mgr, 9.0)                                                                # the weave cooldown (8 s)
    mgr.apply_status(foe, "burn", hero)
    st = mgr.state(foe)
    p0, until0 = st.periodic[0]["amount"], mgr._status_book[(id(foe), "burn")][1]
    mgr.cast(hero, "hold_healing_weave", foe)
    assert st.periodic[0]["amount"] == pytest.approx(p0 * 0.5)
    assert mgr._status_book[(id(foe), "burn")][1] == pytest.approx(mgr.now + (until0 - mgr.now) * 0.5)


def test_status_mod_is_clamped_by_the_rules():
    mgr, hero, foe = setup(extra={"big": row("big", [{"kind": "status_mod", "target": "enemy", "status": "burn", "duration_mult": 50, "potency_mult": 50}])})
    mgr.apply_status(foe, "burn", hero)
    p0, until0 = mgr.state(foe).periodic[0]["amount"], mgr._status_book[(id(foe), "burn")][1]
    mgr.cast(hero, "big", foe)
    assert mgr.state(foe).periodic[0]["amount"] == pytest.approx(p0 * 2.0)
    assert mgr._status_book[(id(foe), "burn")][1] == pytest.approx(mgr.now + (until0 - mgr.now) * 2.0)


def test_debuff_lowers_a_stat_for_its_duration_only():
    mgr, hero, foe = setup()
    base = eff(mgr, foe, "defense")
    mgr.cast(hero, "hold_doom", foe)
    assert eff(mgr, foe, "defense") == base - 6.0
    run(mgr, 11.0)
    assert eff(mgr, foe, "defense") == base


def test_unbounded_lifts_the_cap_within_the_data_bound_and_restores():
    mgr, hero, _ = setup(extra={"cap": row("cap", [{"kind": "unbounded", "target": "self", "stat": "max_hp", "mult": 9}])})
    base = eff(mgr, hero, "attack_damage")
    mgr.cast(hero, "hold_avatar_state")
    assert eff(mgr, hero, "attack_damage") == pytest.approx(base * 3.0)         # mult 9 clamped to the rule cap 3.0
    run(mgr, 21.0)
    assert eff(mgr, hero, "attack_damage") == pytest.approx(base)
    mgr.cast(hero, "cap")                                                        # a stat not on the whitelist is refused
    assert mgr._sc.log[-1]["refused"] == "unbounded:max_hp"


def test_copy_last_cast_replays_the_targets_last_cast_and_read_exposes_its_data():
    mgr, hero, foe = setup()
    mgr.cast(foe, "zap", hero)
    assert hero.health == 90.0
    mgr.cast(hero, "hold_priori_incantatem", foe)
    assert foe.health == 90.0                                                    # the same 10 damage, cast BY the hero
    rec = next(iter(mgr.state(hero).unit.external["perception"]["read"].values()))
    assert rec["data"]["last_cast"] == "zap"


def test_copy_last_cast_refuses_without_a_record_and_never_copies_itself():
    mgr, hero, foe = setup()
    mgr.cast(hero, "hold_priori_incantatem", foe)                                # foe never cast
    assert mgr._sc.log[-1]["refused"] == "copy_last_cast"
    mgr.cast(foe, "hold_priori_incantatem", hero)                                # foe's own last cast is a copy_last_cast row: refused
    assert foe.health == 100.0 and hero.health == 100.0


def test_read_returns_only_the_requested_fields():
    mgr, hero, foe = setup()
    mgr.state(foe).abilities.append("wand_strike")
    mgr.cast(hero, "hold_dream_extraction", foe)
    rec = next(iter(mgr.state(hero).unit.external["perception"]["read"].values()))
    assert set(rec["data"]) == {"name", "abilities"} and rec["data"]["abilities"] == ["wand_strike"]


def test_steal_moves_the_grant_with_a_fidelity_and_a_cost():
    mgr, hero, foe = setup(extra={"low": row("low", [{"kind": "steal", "target": "enemy", "technique": "wand_strike", "fidelity": 0.01}])})
    mgr.state(foe).abilities.append("wand_strike")
    mgr.cast(hero, "hold_skill_hunter", foe)
    assert "wand_strike" not in mgr.state(foe).abilities and "wand_strike" in mgr.state(hero).spells
    assert mgr.state(hero).unit.external["mimic"]["learned"]["wand_strike"]["fidelity"] == 0.8 and hero.mana == 70.0
    run(mgr, 11.0)
    mgr.cast(hero, "hold_skill_hunter", foe)                                     # nothing left to take: no cost
    assert hero.mana == 70.0 and mgr._sc.log[-1]["refused"] == "steal:wand_strike"
    mgr.state(foe).abilities.append("wand_strike")
    mgr.cast(hero, "low", foe)
    assert mgr.state(hero).unit.external["mimic"]["learned"]["wand_strike"]["fidelity"] == 0.25      # min_fidelity floor


def test_time_erase_reverts_the_window_then_erases_and_falls_back_to_plain_erase():
    mgr, hero, foe = setup()
    mgr.state(foe).unit.external["memo"] = "before"
    mgr.snapshot("self", entity=foe, sid="pre")
    mgr.state(foe).unit.external["memo"] = "after"
    run(mgr, 2.0)
    mgr.cast(hero, "hold_balefire", foe)
    ext = mgr.state(foe).unit.external
    assert ext["memo"] == "before" and ext["erased"] and foe.health <= 0
    mgr2, hero2, foe2 = setup()
    mgr2.state(foe2).unit.external["memo"] = "before"
    mgr2.snapshot("self", entity=foe2, sid="pre")
    mgr2.state(foe2).unit.external["memo"] = "after"
    run(mgr2, 8.0)                                                               # snapshot older than window 6: plain erase
    mgr2.cast(hero2, "hold_balefire", foe2)
    assert mgr2.state(foe2).unit.external["memo"] == "after" and mgr2.state(foe2).unit.external["erased"]


def test_change_tier_applies_replaces_and_clamps_stat_mods():
    mgr, hero, _ = setup(extra={"to_dusk": row("to_dusk", [{"kind": "change_tier", "target": "self", "track": "stars", "to": "dusk"}]),
                                "nope": row("nope", [{"kind": "change_tier", "target": "self", "track": "no_such_track"}])})
    d0, a0 = eff(mgr, hero, "defense"), eff(mgr, hero, "attack_damage")
    seen = []
    for _ in range(4):
        mgr.cast(hero, "hold_age_of_stars")
        mgr.now += 25.0
        seen.append((eff(mgr, hero, "defense") - d0, eff(mgr, hero, "attack_damage") - a0))
    assert seen == [(2.0, 0.0), (5.0, 0.0), (9.0, 4.0), (9.0, 4.0)]              # replaced, not stacked; clamped at the last tier
    mgr.cast(hero, "to_dusk")
    assert eff(mgr, hero, "defense") - d0 == 2.0 and eff(mgr, hero, "attack_damage") == a0
    mgr.cast(hero, "nope")
    assert mgr.state(hero).unit.external["tiers"] == {"stars": 0}


def script(seed):
    mgr, hero, foe = setup(seed)
    dead_allies(mgr, 2)
    mgr.state(foe).abilities.append("wand_strike")
    mgr.apply_status(foe, "burn", hero)
    for aid, tgt in (("zap", hero), ("hold_priori_incantatem", foe), ("hold_skill_hunter", foe), ("hold_resurrect", None),
                     ("hold_forge_weapon", None), ("hold_age_of_stars", None), ("hold_balefire", foe)):
        mgr.cast(foe if aid == "zap" else hero, aid, tgt)
        run(mgr, 1.0)
    img = statecraft.state_image(mgr, "world", mgr.state(hero))
    out = json.dumps({"ents": list(img["ents"].values()), "mgr": img["mgr"], "created": created(mgr.state(hero)), "log": mgr._sc.log}, sort_keys=True, default=str)
    return re.sub(r"f\d+", "fN", out)                                             # Fighter ids are a process-wide counter


def test_two_same_seed_runs_are_identical():
    assert script(3) == script(3)


def test_handler_table_is_the_documented_set():
    assert set(exchange.EXCHANGE_HANDLERS) == {"create_ex_nihilo", "mass_resurrect", "status_mod", "debuff", "unbounded", "copy_last_cast",
                                               "read", "steal", "learn_technique", "time_erase", "change_tier"}
