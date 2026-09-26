"""Slice F7: TIME and WORLD ops as executable specs on EffectManager (src/effects/timeworld.py).

lua_content/corpus_abilities.lua rows with family = "time": The World (exempt caster, frozen others for exactly the duration), Speed Force
(per-entity scale), Tsukuyomi (subjective ticks + settlement), Infinite Tsukuyomi (status on the world, persistent, removed at expiry),
Snap (deterministic sample + `rule` alias), Magnetism (pull / push signs). Scale 1.0 = today's timings bit for bit; same seed = same run.
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

from src.effects import timeworld  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from tests.test_effect_manager import Fighter, World  # noqa: E402
from tools.effect_schema.validate import validate_op  # noqa: E402

ROWS = {a["id"]: a for a in lua_bridge.load(lua_bridge.CONTENT / "corpus_abilities.lua")["abilities"]}
TIME = {k: a for k, a in ROWS.items() if a.get("family") == "time"}
NC = ["no_crit", "true_damage"]


def row(aid, ops, **kw):
    return {"id": aid, "trigger": "cast", "range": 999, "needs_target": any(o.get("target") == "enemy" for o in ops), "ops": ops, **kw}


def setup(seed=1, n=1, extra=None):
    mgr = EffectManager(world=World(), abilities={**ROWS, **(extra or {})}, rng=random.Random(seed))
    hero = Fighter(x=0.0, y=0.0, hp=5000.0)
    mgr.register(hero, "hero")
    foes = []
    for i in range(n):
        f = Fighter(x=5.0 + i, y=0.0, hp=5000.0)
        mgr.register(f, "monsters")
        foes.append(f)
    return mgr, hero, foes


def run(mgr, secs, dt=0.5):
    for _ in range(int(round(secs / dt))):
        mgr.update(dt)


def lost(e):
    return e.max_health - e.health


def stop_row(exempt):
    return row("s", [{"kind": "global_time_scale", "target": "world", "rate": 0, "duration": {"flat": 2}, "exempt": exempt}])


def test_every_time_row_validates_and_corpus_ids_are_marked():
    assert {a["corpus"] for a in TIME.values() if "corpus" in a} == {11, 13, 25, 38, 41, 43}
    for aid, ab in TIME.items():
        for o in ab["ops"]:
            assert validate_op(o, f"{aid}.{o['kind']}") == [], (aid, o)


def test_time_stop_freezes_others_for_exactly_the_duration_and_spares_the_caster():
    stop = row("stop", [TIME["corpus_the_world"]["ops"][0]])
    mgr, hero, (foe,) = setup(extra={"stop": stop})
    mgr.apply_status(foe, "burn", hero)
    mgr.apply_status(hero, "burn", hero)
    mgr.cast(hero, "stop", foe)
    assert mgr.world_time_scale() == 0.0 and mgr.time_scale(foe) == 0.0 and mgr.time_scale(hero) == 1.0
    run(mgr, 4.5)
    assert lost(foe) == 0.0 and lost(hero) > 0.0                    # the caster keeps ticking, the world does not
    run(mgr, 0.5)                                                    # t = 5.0: exactly the duration
    assert mgr.world_time_scale() == 1.0 and mgr.time_scale(foe) == 1.0
    run(mgr, 8.0)
    assert lost(foe) == pytest.approx(lost(hero))                    # a full burn each: nothing skipped, nothing doubled


def test_the_corpus_row_delayed_strike_lands_after_the_stop():
    mgr, hero, (foe,) = setup()
    mgr.cast(hero, "corpus_the_world", foe)
    run(mgr, 4.5)
    assert lost(foe) == 0.0
    run(mgr, 1.0)
    assert lost(foe) > 0.0


@pytest.mark.parametrize("who", ["tag", "faction", "id"])
def test_exempt_by_tag_faction_and_id(who):
    mgr, hero, (a, b) = setup(n=2)
    a.tags = ("free",)
    ex = {"tag": ["tag:free"], "faction": ["faction:monsters"], "id": [a.entity_id]}[who]
    mgr.abilities["s"] = stop_row(ex)
    mgr.cast(hero, "s", a)
    assert mgr.time_scale(a) == 1.0
    assert mgr.time_scale(b) == (1.0 if who == "faction" else 0.0)
    assert mgr.time_scale(hero) == 0.0


def burn_hp(rate=None, world_rate=None, secs=3.0):
    extra = {}
    if rate is not None:
        extra["t"] = row("t", [{"kind": "time_scale", "target": "self", "rate": rate, "duration": {"flat": 100}}])
    if world_rate is not None:
        extra["w"] = row("w", [{"kind": "global_time_scale", "target": "world", "rate": world_rate, "duration": {"flat": 100}}])
    mgr, hero, (foe,) = setup(extra=extra)
    mgr.apply_status(hero, "burn", hero)
    for aid in extra:
        mgr.cast(hero, aid, hero if aid == "t" else foe)
    run(mgr, secs, 0.25)
    return hero.health, mgr, hero


def test_scale_one_reproduces_todays_timings_bit_for_bit():
    base = burn_hp()[0]
    assert burn_hp(rate=1.0)[0] == base and burn_hp(world_rate=1.0)[0] == base


def test_per_entity_time_scale_speeds_up_and_slows_down_timers():
    base = burn_hp()[0]
    fast, mgr, hero = burn_hp(rate=2.0)
    slow = burn_hp(rate=0.5)[0]
    assert fast < base and slow > base                                # burn ticks 2x / 0.5x per real second
    assert 5000.0 - fast == pytest.approx(66.0, abs=1e-6)            # 3 s at x2 = the whole 6 s burn = 6 ticks of 8 + 3
    assert mgr.dt_for(hero, 1.0) == 2.0


def test_time_scale_is_bounded_and_expires():
    mgr, hero, _ = setup(extra={"t": row("t", [{"kind": "time_scale", "target": "self", "rate": 999, "duration": {"flat": 1}}])})
    mgr.cast(hero, "t", hero)
    assert mgr.time_scale(hero) == timeworld.MAX_SCALE
    run(mgr, 1.5)
    assert mgr.time_scale(hero) == 1.0 and not mgr._tw.active()


def test_subjective_time_runs_ticks_faster_then_settles_once():
    settle = [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 7}, "flags": NC}]
    ts = row("ts", [{"kind": "time_as_space", "target": "enemy", "mult": 4, "duration": {"flat": 1.5}, "settle": settle}])
    mgr, hero, (foe,) = setup(extra={"ts": ts})
    ctl, chero, (cfoe,) = setup()
    mgr.apply_status(foe, "burn", hero)
    ctl.apply_status(cfoe, "burn", chero)
    mgr.cast(hero, "ts", foe)
    run(mgr, 2.0, 0.25)
    run(ctl, 2.0, 0.25)
    assert lost(foe) > lost(cfoe) + 7.0 - 1e-6                        # extra ticks + the settlement
    run(mgr, 8.0, 0.25)
    run(ctl, 8.0, 0.25)
    assert lost(foe) == pytest.approx(lost(cfoe) + 7.0)               # settled exactly once, no double burn
    assert not mgr._tw.ents


def test_subjective_multiplier_is_capped():
    ts = row("ts", [{"kind": "time_as_space", "target": "enemy", "mult": 10 ** 6, "duration": {"flat": 1}}])
    mgr, hero, (foe,) = setup(extra={"ts": ts})
    mgr.cast(hero, "ts", foe)
    assert mgr._tw.ents[id(foe)]["subj"]["mult"] == timeworld.MAX_SUBJECTIVE


def test_status_on_the_world_hits_matches_newcomers_and_is_removed_at_expiry():
    op = dict(TIME["corpus_infinite_tsukuyomi_world"]["ops"][0], duration={"flat": 1.0})
    mgr, hero, (a,) = setup(extra={"w": row("w", [op])})
    mgr.cast(hero, "w")
    mgr.update(0.1)
    assert mgr.state(a).unit._eff("move_speed") < 5.0 and mgr.state(hero).unit._eff("move_speed") == 5.0   # the filter spares the hero
    assert "slow" in mgr.world_statuses()
    late = Fighter(x=9.0, hp=100.0)
    mgr.register(late, "monsters")
    mgr.update(0.1)
    assert mgr.state(late).unit._eff("move_speed") < 5.0                       # persistent: newcomers get it too
    run(mgr, 1.0, 0.1)
    assert mgr.world_statuses() == {}
    assert mgr.state(a).unit._eff("move_speed") == 5.0 and mgr.state(late).unit._eff("move_speed") == 5.0   # removed cleanly at expiry


def test_non_persistent_world_status_skips_newcomers():
    op = dict(TIME["corpus_infinite_tsukuyomi_world"]["ops"][0], persistent=False)
    mgr, hero, _ = setup(extra={"w": row("w", [op])})
    mgr.cast(hero, "w")
    late = Fighter(x=9.0, hp=100.0)
    mgr.register(late, "monsters")
    run(mgr, 0.5)
    assert mgr.state(late).unit._eff("move_speed") == 5.0


def test_polarity_pull_and_push_signs_select_by_tag():
    pull = row("pull", [TIME["corpus_magnetism"]["ops"][0]])
    push = row("push", [dict(TIME["corpus_magnetism"]["ops"][0], sign="repel")])
    mgr, hero, (metal, wood) = setup(n=2, extra={"pull": pull, "push": push})
    metal.tags, wood.tags = ("metal",), ()
    x0, w0 = metal.x, wood.x
    mgr.cast(hero, "pull")
    assert metal.x < x0 and wood.x == w0
    x1 = metal.x
    mgr.now += 20
    mgr.cast(hero, "push")
    assert metal.x > x1 and wood.x == w0


def test_polarity_by_stat_ignores_entities_without_it():
    mgr, hero, (a,) = setup(extra={"r": TIME["corpus_magnetism_repel"]})
    x0 = a.x
    mgr.cast(hero, "r")
    assert a.x == x0                                                   # no `polarity` stat on it: not selected


def snap(seed, n=10, spec=None):
    op = dict(TIME["corpus_snap"]["ops"][0], filter={"sample": spec or {"fraction": 0.5}})
    mgr, hero, foes = setup(seed=seed, n=n, extra={"snap": row("snap", [op, TIME["corpus_snap"]["ops"][1]])})
    mgr.cast(hero, "snap")
    return mgr, foes, [i for i, f in enumerate(foes) if getattr(f, "erased", False)]


def test_snap_erases_a_deterministic_half_and_the_rule_alias_runs():
    mgr, foes, gone = snap(3)
    assert len(gone) == 5 and all(foes[i].health <= 0 for i in gone)
    assert all(f.health > 0 for i, f in enumerate(foes) if i not in gone)
    assert len(mgr._rules) == 1                                        # `rule` = rule_override, bounded
    assert snap(3)[2] == gone                                          # same seed, same half
    assert len(snap(3, spec={"count": 3})[2]) == 3 and len(snap(3, n=3, spec={"count": 99})[2]) == 3


def test_sample_depends_on_seed_and_on_stable_order():
    picks = {tuple(snap(s)[2]) for s in range(1, 12)}
    assert len(picks) > 1


def test_sample_stream_is_named_unrelated_draws_do_not_shift_it():
    def second(extra_draws):
        mgr, foes, _ = snap(5)
        for _ in range(extra_draws):
            mgr.rng.random()
        alive = [f for f in foes if f.health > 0]
        return sorted(alive.index(e) for e in timeworld.sample(mgr, alive, {"count": 2}))
    assert second(0) == second(9)


def scenario(seed):
    mgr, hero, foes = setup(seed=seed, n=4, extra={"stop": row("stop", [TIME["corpus_the_world"]["ops"][0]])})
    for f in foes:
        mgr.apply_status(f, "burn", hero)
    mgr.cast(hero, "stop")
    run(mgr, 3.0)
    mgr.cast(hero, "corpus_snap")
    run(mgr, 8.0)
    return [round(f.health, 6) for f in [hero, *foes]], [getattr(f, "erased", False) for f in foes]


def test_same_seed_runs_are_identical():
    assert scenario(11) == scenario(11)


def test_idle_hook_is_never_entered_and_the_active_one_is_cheap(monkeypatch):
    mgr, hero, foes = setup(n=30)

    def boom(*a):
        raise AssertionError("entered with no time records")
    monkeypatch.setattr(timeworld, "_step_deltas", boom)
    run(mgr, 5.0, 0.1)
    monkeypatch.undo()
    mgr.abilities["t"] = row("t", [{"kind": "time_scale", "target": "self", "rate": 0.5, "duration": {"flat": 1000}}])
    mgr.cast(hero, "t", hero)
    t0 = time.perf_counter()
    for _ in range(300):
        mgr.update(0.05)
    assert time.perf_counter() - t0 < 5.0
