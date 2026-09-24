"""The damage pipeline (docs/DAMAGE_PIPELINE.md): Python twin semantics, Rust-vs-twin parity, the neutral guard.

`AI_EVOLVE_DAMAGE=python` forces the twin everywhere (the Rust-only tests then skip); Rust tests skip when the built
rust_core has no `resolve_hit`.
"""
from __future__ import annotations

import random
import re
import struct
from array import array
from pathlib import Path

import pytest

from src.effects import damage as dmg
from src.effects.damage import F_BROKEN, F_CERTAIN, F_NO_CRIT, F_TRUE, NAN, Outcome

ROOT = Path(__file__).resolve().parents[1]
NEUTRAL = dict(amount=10.0, flags=0.0, accuracy=0.0, evasion=0.0, dodge=0.0, block_chance=0.0, block_bonus=0.0,
               crit_chance=0.0, crit_mult=1.5, type_mod=0.0, resist=0.0, resist_pen=0.0, armor=0.0,
               pen_pct=0.0, pen_flat=0.0, taken=0.0)
CFG = dmg.config_from_data()          # built-in copy of lua_content/damage.lua
CONSTS = CFG.consts
rust = pytest.mark.skipif(not dmg._RUST_OK, reason="rust_core has no damage kernel")


def params(**kw) -> tuple:
    bad = set(kw) - set(NEUTRAL)
    assert not bad, bad
    return tuple({**NEUTRAL, **kw}[f] for f in dmg.PARAMS)


def hit(rolls=(NAN,) * 5, consts=CONSTS, **kw) -> Outcome:
    """The kernel on a hit with the given overrides and rolls (dodge, crit ... default: not drawn)."""
    return dmg.resolve_hit_py(params(**kw), rolls, consts)


def roll(*, acc=NAN, dodge=1.0, block=NAN, crit=1.0, var=NAN) -> tuple:
    return (acc, dodge, block, crit, var)


class Dice:
    """rng that replays given numbers and records how many were drawn."""

    def __init__(self, *values):
        self.values, self.drawn = list(values), []

    def random(self):
        self.drawn.append(self.values.pop(0) if self.values else 0.5)
        return self.drawn[-1]


# ---------------------------------------------------------------- hand-made stage cases

def test_neutral_hit_is_max_one_amount_minus_armor():
    o = hit(roll(), amount=20.0, armor=3.0)
    assert (o.need, o.hit, o.dodged, o.blocked, o.crit) == (0, 1, 0, 0, 0)
    assert o.damage_before == 20.0 and o.armor_reduced == 3.0 and o.final == 17.0
    assert o.resisted == 0.0 and o.blocked_amount == 0.0 and o.armor_ignored == 0.0


def test_min_damage_floor_and_true_damage_skips_it():
    assert hit(roll(), amount=5.0, armor=1000.0).final == 1.0
    o = hit(roll(), amount=0.4, armor=1000.0, flags=F_TRUE | F_CERTAIN | F_NO_CRIT)
    assert o.final == 0.4 and o.armor_reduced == 0.0          # true damage: no armor, no floor
    r = hit(roll(), amount=100.0, armor=1000.0, resist=25.0, flags=F_TRUE | F_CERTAIN | F_NO_CRIT)
    assert r.final == 75.0 and r.resisted == 25.0             # ... but a poison DoT is still resisted


def test_crit_multiplies_before_armor():
    o = hit(roll(crit=0.0), amount=10.0, crit_chance=0.5, crit_mult=2.0, armor=5.0)
    assert o.crit == 1 and o.damage_before == 20.0 and o.final == 15.0
    assert hit(roll(crit=0.5), amount=10.0, crit_chance=0.5, crit_mult=2.0, armor=5.0).crit == 0   # roll < chance


def test_negative_armor_adds_damage_as_before():
    assert hit(roll(), amount=10.0, armor=-3.0).final == 13.0


def test_penetration_pct_and_flat_floor_at_zero():
    assert hit(roll(), amount=20.0, armor=10.0, pen_pct=50.0).final == 15.0          # armor 10 -> 5
    assert hit(roll(), amount=20.0, armor=10.0, pen_flat=4.0).final == 14.0          # armor 10 -> 6
    o = hit(roll(), amount=20.0, armor=10.0, pen_pct=50.0, pen_flat=20.0)            # would be -15: floored at 0
    assert o.final == 20.0 and o.armor_ignored == 10.0
    assert hit(roll(), amount=20.0, armor=-4.0, pen_pct=100.0, pen_flat=9.0).final == 24.0   # negative armor stays


def test_percent_armor_curve_is_a_lua_choice():
    percent = dmg.config_from_data({"constants": {"armor": {"curve": "percent", "k": 100}}}).consts
    o = hit(roll(), consts=percent, amount=100.0, armor=100.0)
    assert o.final == 50.0 and o.armor_reduced == 50.0                                # k / (k + armor)


def test_resistance_percent_penetration_clamp_and_immunity():
    assert hit(roll(), amount=100.0, resist=25.0).final == 75.0
    assert hit(roll(), amount=100.0, resist=25.0).resisted == 25.0
    assert hit(roll(), amount=100.0, resist=50.0, resist_pen=20.0).final == 70.0       # 50 - 20 = 30
    assert hit(roll(), amount=100.0, resist=50.0, resist_pen=80.0).final == 100.0      # penetration stops at 0
    assert hit(roll(), amount=100.0, resist=99.0).final == pytest.approx(10.0)                       # capped at resist.max = 90
    assert hit(roll(), amount=100.0, resist=-50.0).final == 150.0                      # vulnerability
    o = hit(roll(), amount=100.0, resist=100.0, resist_pen=100.0)                      # immune: no min damage
    assert o.final == 0.0 and o.resisted == 100.0


def test_block_roll_reduces_and_adds_to_the_lua_reduction():
    o = hit(roll(block=0.1), amount=100.0, block_chance=25.0)
    assert o.blocked == 1 and o.blocked_amount == 50.0 and o.final == 50.0
    o = hit(roll(block=0.1), amount=100.0, block_chance=25.0, block_bonus=30.0)
    assert o.final == pytest.approx(20.0)
    assert hit(roll(block=0.25), amount=100.0, block_chance=25.0).blocked == 0        # roll < chance/100
    assert hit(roll(block=0.0), amount=100.0, block_chance=25.0, flags=F_TRUE | F_CERTAIN).blocked == 0


def test_dodge_roll_and_accuracy_vs_evasion():
    o = hit(roll(dodge=0.1), dodge=0.2)
    assert (o.hit, o.dodged, o.final) == (1, 1, 0.0)
    assert hit(roll(dodge=0.2), dodge=0.2).dodged == 0
    # 100 - 30 = 70 % to hit: roll .69 hits, .71 misses; more accuracy than evasion cannot exceed 100 %
    assert hit(roll(acc=0.69), evasion=30.0).hit == 1
    assert hit(roll(acc=0.71), evasion=30.0).hit == 0
    assert hit(roll(), accuracy=50.0).need == 0                                        # cannot miss: no roll asked
    assert hit(roll(acc=0.04), evasion=200.0).hit == 1                                 # never below hit.min = 5 %
    assert hit(roll(acc=0.06), evasion=200.0).hit == 0


def test_final_modifiers_taken_and_broken():
    assert hit(roll(), amount=100.0, taken=20.0).final == 120.0
    assert hit(roll(), amount=100.0, flags=F_BROKEN).final == pytest.approx(115.0)
    assert hit(roll(), amount=100.0, taken=-200.0).final == 1.0                        # multiplier floors at 0, then min 1


def test_type_modifier_and_variance():
    assert hit(roll(), amount=100.0, type_mod=25.0).final == 125.0
    assert hit(roll(), amount=100.0, type_mod=-150.0).final == 1.0
    var = dmg.config_from_data({"constants": {"variance": 0.2}}).consts
    assert hit(roll(var=0.5), consts=var, amount=100.0).final == pytest.approx(100.0)
    assert hit(roll(var=1.0), consts=var, amount=100.0).final == pytest.approx(120.0)
    assert hit(roll(var=0.0), consts=var, amount=100.0).final == pytest.approx(80.0)


def test_stage_amounts_add_up():
    o = hit(roll(block=0.0, crit=0.0), amount=100.0, crit_chance=1.0, crit_mult=2.0, armor=20.0, resist=25.0,
            block_chance=50.0, type_mod=10.0)
    assert o.damage_before == 100.0 * 1.1 * 2.0
    assert o.armor_reduced == 20.0 and o.resisted == pytest.approx((220.0 - 20.0) * 0.25)
    assert o.final == pytest.approx(o.damage_before - o.armor_reduced - o.resisted - o.blocked_amount)


# ---------------------------------------------------------------- the roll order (docs/DAMAGE_PIPELINE.md)

def drawn(rolls: list, **kw) -> list:
    dice = Dice(*rolls)
    dmg.roll_hit(params(**kw), dice, CONSTS, backend="python")
    return dice.drawn


def test_neutral_hit_draws_dodge_then_crit_like_before():
    assert drawn([0.9, 0.9]) == [0.9, 0.9]
    d = Dice(0.3, 0.7)
    dmg.roll_hit(params(dodge=0.5, crit_chance=0.9), d, CONSTS, backend="python")     # dodge drawn first
    assert d.drawn == [0.3]                                                            # dodged: no crit draw


def test_certain_and_no_crit_flags_skip_draws():
    assert drawn([], flags=F_CERTAIN | F_NO_CRIT) == []                               # periodic
    assert drawn([0.4], flags=F_CERTAIN) == [0.4]                                     # unavoidable: crit only
    assert drawn([0.4], flags=F_NO_CRIT) == [0.4]                                     # no_crit: dodge only


def test_extra_draws_only_for_non_neutral_stats():
    assert len(drawn([0.5] * 5)) == 2
    assert len(drawn([0.5] * 5, block_chance=10.0)) == 3
    assert len(drawn([0.5] * 5, evasion=10.0)) == 3
    assert len(drawn([0.5] * 5, accuracy=10.0)) == 2                                  # cannot miss anyway
    var = dmg.config_from_data({"constants": {"variance": 0.1}}).consts
    dice = Dice()
    dmg.roll_hit(params(), dice, var, backend="python")
    assert len(dice.drawn) == 3
    order = Dice(0.5, 0.5, 0.5, 0.5, 0.5)
    dmg.roll_hit(params(evasion=10.0, block_chance=10.0), order, var, backend="python")
    assert len(order.drawn) == 5                                                       # accuracy, dodge, block, crit, variance


def test_kernel_asks_for_rolls_in_stage_order():
    seen = []
    p = params(evasion=10.0, block_chance=10.0)
    rolls = [NAN] * 5
    while True:
        o = dmg.resolve_hit_py(p, rolls, CONSTS)
        if not o.need:
            break
        seen.append(o.need - 1)
        rolls[o.need - 1] = 0.5
    assert seen == [dmg.R_ACCURACY, dmg.R_DODGE, dmg.R_BLOCK, dmg.R_CRIT]


# ---------------------------------------------------------------- neutral == today's formula

def legacy(amount, crit, crit_mult, defense, true=False):
    """EffectManager._damage before the pipeline: crit x, then max(1, x - defense) unless true damage."""
    if crit:
        amount *= crit_mult
    return amount if true else max(1.0, amount - defense)


def test_neutral_defaults_equal_the_legacy_formula_on_a_table():
    rng = random.Random(7)
    table = [(a, c, m, d, t) for a in (0.3, 1.0, 5.5, 12.0, 47.25, 1e6) for c in (False, True)
             for m in (1.0, 1.5, 2.25) for d in (-4.0, 0.0, 0.5, 3.0, 9.0, 55.5, 1e9) for t in (False, True)]
    table += [(rng.uniform(0.1, 300), rng.random() < 0.3, rng.uniform(1, 4), rng.uniform(-5, 80), rng.random() < 0.2)
              for _ in range(2000)]
    for amount, crit, mult, defense, true in table:
        flags = (F_TRUE | F_CERTAIN) if true else 0
        o = hit(roll(crit=0.0 if crit else 1.0), amount=amount, crit_chance=0.5, crit_mult=mult, armor=defense,
                flags=float(flags))
        assert o.final == legacy(amount, crit, mult, defense, true), (amount, crit, mult, defense, true)
        assert (o.hit, o.dodged, o.blocked, o.crit) == (1, 0, 0, int(crit))


# ---------------------------------------------------------------- properties (seeded random)

def rand_case(rng: random.Random) -> dict:
    return dict(amount=rng.uniform(1, 200), armor=rng.uniform(-10, 120), pen_pct=rng.choice([0, rng.uniform(0, 100)]),
                pen_flat=rng.choice([0, rng.uniform(0, 30)]), resist=rng.choice([0, rng.uniform(-60, 95)]),
                resist_pen=rng.choice([0, rng.uniform(0, 60)]), taken=rng.choice([0, rng.uniform(-50, 100)]),
                type_mod=rng.choice([0, rng.uniform(-50, 100)]), block_bonus=rng.choice([0, rng.uniform(0, 40)]))


FULL_ROLLS = (0.5, 0.5, 0.0, 0.5, 0.5)      # hits, no dodge, blocked when block_chance > 0


def test_more_armor_never_more_damage_more_penetration_never_less():
    rng = random.Random(11)
    for _ in range(600):
        kw = rand_case(rng)
        base = hit(FULL_ROLLS, **kw).final
        more_armor = hit(FULL_ROLLS, **{**kw, "armor": kw["armor"] + rng.uniform(0.1, 30)}).final
        more_pen = hit(FULL_ROLLS, **{**kw, "pen_pct": min(100.0, kw["pen_pct"] + 10), "pen_flat": kw["pen_flat"] + 2}).final
        assert more_armor <= base + 1e-9 and more_pen >= base - 1e-9, kw


def test_more_resist_less_damage_and_immunity_is_zero():
    rng = random.Random(12)
    for _ in range(400):
        kw = rand_case(rng)
        lo, hi = sorted((rng.uniform(-60, 99), rng.uniform(-60, 99)))
        a = hit(FULL_ROLLS, **{**kw, "resist": lo}).final
        b = hit(FULL_ROLLS, **{**kw, "resist": hi}).final
        assert b <= a + 1e-9, (kw, lo, hi)
        assert hit(FULL_ROLLS, **{**kw, "resist": 100.0, "resist_pen": 100.0}).final == 0.0


def test_block_reduces_and_evasion_accuracy_edges():
    rng = random.Random(13)
    for _ in range(300):
        kw = rand_case(rng)
        plain = hit(FULL_ROLLS, **kw)
        blocked = hit(FULL_ROLLS, **{**kw, "block_chance": 50.0})
        assert blocked.blocked == 1 and blocked.final <= plain.final + 1e-9
    assert hit(roll(acc=0.0), evasion=500.0).hit == 1         # a roll under the 5 % floor always hits
    assert hit(roll(acc=0.0499), evasion=500.0).hit == 1 and hit(roll(acc=0.05), evasion=500.0).hit == 0
    for acc_roll in (0.0, 0.3, 0.99):
        assert hit(roll(acc=acc_roll), accuracy=100.0, evasion=0.0).hit == 1
    seq = [hit(roll(acc=0.5), evasion=e).hit for e in (0, 10, 30, 49, 50, 51, 90)]
    assert seq == sorted(seq, reverse=True)                    # more evasion never hits more often


# ---------------------------------------------------------------- Lua data

def test_builtin_config_equals_damage_lua():
    from src.content import lua_bridge
    from_lua = dmg.load_config(lua_bridge.CONTENT / "damage.lua")
    assert from_lua == CFG
    assert dmg.config().types[0] == dmg.config().default_type == "physical"


def test_lua_constants_change_results(tmp_path):
    src = (ROOT / "lua_content" / "damage.lua").read_text(encoding="utf-8")
    tuned = tmp_path / "damage.lua"
    tuned.write_text(re.sub(r"min_damage = 1\.0", "min_damage = 3.0", src)
                     .replace('curve = "subtractive"', 'curve = "percent"')
                     .replace("block = { reduction = 50 }", "block = { reduction = 80 }"), encoding="utf-8")
    cfg = dmg.load_config(tuned)
    assert cfg.consts != CONSTS
    assert hit(roll(), consts=CONSTS, amount=5.0, armor=1000.0).final == 1.0
    assert hit(roll(), consts=cfg.consts, amount=5.0, armor=1000.0).final == 3.0       # min_damage
    assert hit(roll(), consts=cfg.consts, amount=100.0, armor=100.0).final == 50.0     # percent curve
    assert hit(roll(block=0.0), consts=cfg.consts, amount=100.0, block_chance=90.0).final == pytest.approx(20.0)   # block 80 %


def test_bad_lua_values_are_refused():
    with pytest.raises(ValueError):
        dmg.config_from_data({"constants": {"armor": {"curve": "bogus"}}})
    with pytest.raises(ValueError):
        dmg.config_from_data({"default_type": "plasma"})


def test_damage_type_comes_from_tags():
    assert dmg.damage_type(("attack", "fire", "ice"), CFG) == "fire"
    assert dmg.damage_type(("attack", "skill"), CFG) == "physical"
    assert dmg.damage_type((), CFG) == "physical"


def test_batch_twin_matches_single_calls():
    rng = random.Random(5)
    cols = [[] for _ in dmg.PARAMS]
    roll_cols = [[] for _ in range(dmg.ROLLS)]
    singles = []
    for _ in range(50):
        p = params(**rand_case(rng))
        r = tuple(rng.random() for _ in range(dmg.ROLLS))
        singles.append(dmg.resolve_hit_py(p, r, CONSTS))
        for col, v in zip(cols, p, strict=True):
            col.append(v)
        for col, v in zip(roll_cols, r, strict=True):
            col.append(v)
    out = dmg.resolve_hits_py(cols, roll_cols, CONSTS)
    for i, single in enumerate(singles):
        assert tuple(col[i] for col in out) == tuple(float(v) for v in single)


def bits(x: float) -> bytes:
    return struct.pack("<d", x)


def same_outcome(a: Outcome, b: Outcome) -> bool:
    return all(bits(float(x)) == bits(float(y)) for x, y in zip(a, b, strict=True))



# ---------------------------------------------------------------- Rust kernel == Python twin, bit for bit

def _pick(rng, *options):
    return rng.choice(options)


def random_params(rng: random.Random) -> tuple:
    return (
        _pick(rng, rng.uniform(0.1, 500), rng.uniform(0.1, 500), 0.3, 1.0, 0.0, 1e9),               # amount
        float(rng.randrange(16)),                                                                    # flags
        _pick(rng, 0.0, rng.uniform(-50, 80), 100.0),                                                # accuracy
        _pick(rng, 0.0, rng.uniform(0, 200), 30.0),                                                  # evasion
        _pick(rng, 0.0, rng.uniform(0, 0.9), 1.0),                                                   # dodge
        _pick(rng, 0.0, rng.uniform(0, 100), 100.0),                                                 # block_chance
        _pick(rng, 0.0, rng.uniform(0, 60)),                                                         # block_bonus
        _pick(rng, 0.0, rng.uniform(0, 1), 1.0),                                                     # crit_chance
        _pick(rng, 1.5, rng.uniform(1, 4), 2.0),                                                     # crit_mult
        _pick(rng, 0.0, rng.uniform(-80, 300)),                                                      # type_mod
        _pick(rng, 0.0, rng.uniform(-150, 130), 100.0, 90.0, -100.0),                                # resist
        _pick(rng, 0.0, rng.uniform(0, 120)),                                                        # resist_pen
        _pick(rng, 0.0, rng.uniform(-20, 200), 3.0, 1e9, -7.5),                                      # armor
        _pick(rng, 0.0, rng.uniform(-10, 120), 100.0),                                               # pen_pct
        _pick(rng, 0.0, rng.uniform(-5, 60)),                                                        # pen_flat
        _pick(rng, 0.0, rng.uniform(-150, 300)),                                                     # taken
    )


def random_rolls(rng: random.Random) -> tuple:
    return tuple(NAN if rng.random() < 0.2 else _pick(rng, rng.random(), rng.random(), 0.0, 0.5, 1 - 2 ** -53)
                 for _ in range(dmg.ROLLS))


CONST_VARIANTS = [
    CONSTS,
    dmg.config_from_data({"constants": {"armor": {"curve": "percent", "k": 80}, "variance": 0.25}}).consts,
    dmg.config_from_data({"constants": {"hit": {"base": 90, "min": 10, "max": 95}, "min_damage": 0.0,
                                        "broken": 1.5, "block": {"reduction": 75},
                                        "resist": {"min": -50, "max": 60, "immune_at": 95}}}).consts,
]


@rust
def test_rust_kernel_equals_the_twin_on_20000_random_hits():
    rng = random.Random(20240924)
    bad = []
    for i in range(20000):
        p, r, c = random_params(rng), random_rolls(rng), CONST_VARIANTS[i % len(CONST_VARIANTS)]
        a, b = dmg.resolve_hit_py(p, r, c), dmg.resolve_hit(p, r, c, backend="rust")
        if not same_outcome(a, b):
            bad.append((p, r, c, a, b))
    assert not bad, f"{len(bad)} mismatches, first: {bad[0]}"


@rust
def test_rust_batch_equals_the_twin_batch_and_single_calls():
    rng = random.Random(77)
    n = 20000
    rows = [random_params(rng) for _ in range(n)]
    rolls = [random_rolls(rng) for _ in range(n)]
    pcols = [array("d", col) for col in zip(*rows, strict=True)]
    rcols = [array("d", col) for col in zip(*rolls, strict=True)]
    for consts in CONST_VARIANTS:
        fast = dmg.resolve_hits(pcols, rcols, consts, backend="rust")
        slow = dmg.resolve_hits(pcols, rcols, consts, backend="python")
        assert [c.tobytes() for c in fast] == [c.tobytes() for c in slow]
        for i in range(0, n, 997):
            assert tuple(col[i] for col in fast) == tuple(float(v) for v in
                                                          dmg.resolve_hit_py(rows[i], rolls[i], consts))


@rust
def test_rust_batch_rejects_bad_shapes():
    with pytest.raises(ValueError):
        dmg.resolve_hits([array("d", [1.0])] * 3, [array("d", [1.0])] * 5, CONSTS, backend="rust")
    with pytest.raises(ValueError):
        dmg._rc.resolve_hit([1.0] * 3, [NAN] * 5, list(CONSTS))
    with pytest.raises(ValueError):
        dmg._rc.resolve_hit(list(params()), [NAN] * 4, list(CONSTS))


@rust
def test_driver_draws_the_same_dice_on_both_backends():
    rng = random.Random(3)
    for i in range(3000):
        p, c = random_params(rng), CONST_VARIANTS[i % len(CONST_VARIANTS)]
        dice_a, dice_b = random.Random(i), random.Random(i)
        rec_a, rec_b = Dice(), Dice()
        rec_a.random = lambda d=dice_a, r=rec_a: r.drawn.append(d.random()) or r.drawn[-1]
        rec_b.random = lambda d=dice_b, r=rec_b: r.drawn.append(d.random()) or r.drawn[-1]
        a = dmg.roll_hit(p, rec_a, c, backend="python")
        b = dmg.roll_hit(p, rec_b, c, backend="rust")
        assert same_outcome(a, b) and rec_a.drawn == rec_b.drawn, p


def test_dispatch_and_forced_twin(monkeypatch):
    assert "python" in dmg.available_backends()
    with pytest.raises(ValueError):
        dmg.resolve_hit(params(), roll(), CONSTS, backend="fortran")
    monkeypatch.setattr(dmg, "BACKEND", "python")
    assert dmg.resolve_hit(params(amount=5.0, armor=1.0), roll(), CONSTS) == hit(roll(), amount=5.0, armor=1.0)
    monkeypatch.setattr(dmg, "_RUST_OK", False)
    with pytest.raises(RuntimeError):
        dmg.resolve_hit(params(), roll(), CONSTS, backend="rust")


# ---------------------------------------------------------------- wired into EffectManager (the live `deal` path)

import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from src.content import lua_bridge  # noqa: E402
from src.effects import runtime  # noqa: E402
from src.effects.abilities import load_abilities  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402

needs_lua = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")


class CountingRng:
    """Constant rolls; counts draws."""

    def __init__(self, value=0.99):
        self.value, self.calls = value, 0

    def random(self):
        self.calls += 1
        return self.value


class Fighter:
    _n = 0

    def __init__(self, x=0.0, hp=200.0, atk=25.0, defense=0.0, crit=0.0, dodge=0.0, **innate):
        Fighter._n += 1
        self.entity_id = f"dmg{Fighter._n}"
        self.x, self.y = x, 0.0
        self.health = self.max_health = hp
        self.mana = self.max_mana = 100.0
        self.stamina = self.max_stamina = 100.0
        self.health_regen = self.mana_regen = self.stamina_regen = 0.0
        self.physical_damage, self.magical_damage = atk, 30.0
        self.defense, self.attack_speed = defense, 1.0
        self.critical_chance, self.critical_damage, self.dodge_chance = crit, 1.5, dodge
        self.speed, self.level = 5.0, 1
        if innate:
            self.innate_stats = innate          # what the bestiary `stats` becomes (world.make_enemy)

    def is_alive(self):
        return self.health > 0


class NoWorld:
    def entities(self):
        return []

    def spawn_summon(self, *_a):
        return None


def duel(rng=0.99, hero=None, foe=None):
    """(manager, hero, foe, hits): the hero has no crit, the foe 200 HP; every HitInfo lands in `hits`."""
    mgr = EffectManager(world=NoWorld(), abilities=load_abilities(), rng=CountingRng(rng))
    hero, foe = hero or Fighter(), foe or Fighter(x=1.0)
    mgr.register(hero, "hero")
    mgr.register(foe, "monsters")
    hits = []
    mgr.register_event_handler(hits.append)
    return mgr, hero, foe, hits


@needs_lua
def test_manager_neutral_hit_is_the_old_formula_and_draws_dodge_then_crit():
    mgr, hero, foe, hits = duel(foe=Fighter(x=1.0, defense=5.0))
    assert mgr.cast(hero, "weapon_attack", foe).ok
    assert foe.health == pytest.approx(200 - 20)
    assert mgr.rng.calls == 2                                        # dodge, crit - no extra draw for the new stages
    h = hits[0]
    assert (h.damage, h.armor_reduced, h.resisted, h.blocked_amount, h.missed, h.blocked) == (20.0, 5.0, 0.0, 0.0, False, False)
    assert h.hit_type == "physical" and h.landed and not h.invulnerable


@needs_lua
def test_registered_stats_have_defaults_bounds_and_validate():
    r = runtime.rules()
    for stat in ("accuracy", "evasion", "penetration_pct", "penetration_flat", "resist_pen", "block_chance",
                 "block_reduction", "damage_taken", "broken", "resist_fire", "damage_ice"):
        assert r["defaults"][stat] == 0, stat
    assert r["bounds"]["resist_fire"] == {"min": -100, "max": 100} and r["bounds"]["evasion"]["max"] == 95
    from src.effects.schema import is_stat
    assert is_stat("resist_holy") and is_stat("enemy_resist_holy") and is_stat("penetration_flat")
    assert not is_stat("resist_plasma")
    u = runtime.Unit("t")
    u.mods["resist_fire"] = 250.0
    assert u._eff("resist_fire") == 100.0                            # the registry bound clamps the stat


def _hit_with(rng=0.99, **kw):
    """The first HitInfo of a weapon attack; f_<stat> = target stat, h_<stat> = attacker stat (bestiary-style `stats`)."""
    foe_stats = {k[2:]: v for k, v in kw.items() if k.startswith("f_")}
    hero_stats = {k[2:]: v for k, v in kw.items() if k.startswith("h_")}
    mgr, hero, foe, hits = duel(rng=rng, hero=Fighter(**hero_stats), foe=Fighter(x=1.0, defense=5.0, **foe_stats))
    mgr.cast(hero, "weapon_attack", foe)
    return hits[0]


@needs_lua
def test_resistance_penetration_and_block_change_the_hit_in_the_expected_direction():
    assert _hit_with().damage == 20.0
    res = _hit_with(f_resist_physical=25)
    assert res.damage == pytest.approx(15.0) and res.resisted == pytest.approx(5.0)            # (25 - 5) x 0.75
    assert _hit_with(f_resist_physical=25, h_resist_pen=100).damage == 20.0                    # penetration undoes it
    pen = _hit_with(h_penetration_flat=3)
    assert pen.damage == 23.0 and pen.armor_ignored == 3.0
    assert _hit_with(h_penetration_pct=100).damage == 25.0
    blk = _hit_with(f_block_chance=50, rng=0.1)                # roll .1 < 50 %: blocked (no crit, no dodge chance)
    assert blk.blocked and blk.damage == pytest.approx(10.0) and blk.blocked_amount == pytest.approx(10.0)
    assert not _hit_with(f_block_chance=50, rng=0.9).blocked
    assert _hit_with(f_damage_taken=50).damage == pytest.approx(30.0)
    assert _hit_with(f_broken=1).damage == pytest.approx(23.0)                                 # 20 x 1.15
    assert _hit_with(h_damage_physical=20).damage == pytest.approx(25.0)                       # 25 x 1.2 - 5


@needs_lua
def test_accuracy_versus_evasion_misses_and_is_not_a_dodge():
    mgr, hero, foe, hits = duel(rng=0.6, foe=Fighter(x=1.0, evasion=50))
    assert mgr.cast(hero, "weapon_attack", foe).ok
    h = hits[0]
    assert h.missed and not h.is_dodged and not h.landed and h.damage == 0.0 and foe.health == 200.0
    mgr, hero, foe, hits = duel(rng=0.6, hero=Fighter(accuracy=20), foe=Fighter(x=1.0, evasion=50))
    mgr.cast(hero, "weapon_attack", foe)
    assert hits[0].landed and foe.health < 200.0                   # 100 + 20 - 50 = 70 % > .6


def _fireball(**foe_stats):
    """(manager, foe, the fire hits that landed on the foe); the area also burns the caster (friendly fire), skipped here."""
    mgr, hero, foe, hits = duel(foe=Fighter(x=1.0, **foe_stats))
    assert mgr.cast(hero, "fireball", foe).ok
    return mgr, foe, [h for h in hits if h.target == foe.entity_id]


@needs_lua
def test_a_tagged_ability_deals_that_type_and_its_dot_keeps_it():
    _mgr, _foe, plain = _fireball()
    assert plain[0].hit_type == "fire" and plain[0].damage == pytest.approx(36.0)             # 120 % of spell_power 30
    mgr, foe, hits = _fireball(resist_fire=50)
    assert hits[0].damage == pytest.approx(18.0) and hits[0].resisted == pytest.approx(18.0)
    dot = mgr.state(foe).periodic[0]
    assert "type:fire" in dot["flags"]
    hp = foe.health
    mgr.update(1.01)
    assert hp - foe.health == pytest.approx(4.5 * 0.5)                                         # 15 % of 30 = 4.5, resisted 50 %


@needs_lua
def test_immunity_takes_everything_and_ignores_the_min_damage_floor():
    _mgr, foe, hits = _fireball(resist_fire=100)
    assert hits[0].damage == 0.0 and foe.health == 200.0 and hits[0].resisted > 0


@needs_lua
def test_invulnerability_is_not_a_block():
    mgr, hero, foe, hits = duel()
    mgr.state(foe).unit.buffs["shield"] = {"until": 1e9, "flags": ["iframe"]}
    mgr.cast(hero, "weapon_attack", foe)
    assert hits[0].invulnerable and not hits[0].blocked and foe.health == 200.0


@needs_lua
def test_lua_constants_and_type_defaults_reach_the_live_hit(tmp_path, monkeypatch):
    src = (ROOT / "lua_content" / "damage.lua").read_text(encoding="utf-8")
    tuned = tmp_path / "damage.lua"
    tuned.write_text(src.replace('{ id = "fire",      resist = 0, mod = 0 }', '{ id = "fire",      resist = 40, mod = 0 }')
                     .replace("min_damage = 1.0", "min_damage = 5.0"), encoding="utf-8")
    monkeypatch.setenv(dmg.LUA_ENV, str(tuned))
    dmg.config.cache_clear()
    runtime.rules.cache_clear()
    try:
        assert runtime.rules()["defaults"]["resist_fire"] == 40                                # a per-type default
        _mgr, _foe, hits = _fireball()
        assert hits[0].damage == pytest.approx(36.0 * 0.6)                                     # every unit resists fire 40 %
        mgr, hero, foe, hits = duel(foe=Fighter(x=1.0, defense=1000.0))
        mgr.cast(hero, "weapon_attack", foe)
        assert hits[0].damage == 5.0                                                          # the tuned min_damage
    finally:
        monkeypatch.undo()
        dmg.config.cache_clear()
        runtime.rules.cache_clear()
    assert runtime.rules()["defaults"]["resist_fire"] == 0


sys.path.insert(0, str(ROOT / "tools"))


def test_event_fields_reach_the_combat_analysis():
    import probe_analysis as analysis
    ev = [{"t": 0.0, "source": "h", "target": "g", "damage": 10.0, "critical": False, "dodged": False, "type": "physical",
           "armor": 9.0, "resisted": 4.0, "blocked": True, "guarded": 10.0},
          {"t": 1.0, "source": "g", "target": "h", "damage": 0.0, "critical": False, "dodged": True, "missed": True},
          {"t": 2.0, "source": "g", "target": "h", "damage": 5.0, "critical": False, "dodged": False, "armor": 8.0,
           "resisted": 0.0, "pierced": 3.0}]
    s = analysis.combat_stats(ev, "h")
    assert (s["hits"], s["dodges"], s["misses"], s["blocks"], s["resisted"], s["armored"], s["pierced"]) == \
        (2, 1, 1, 1, 4.0, 17.0, 3.0)


@pytest.mark.skipif(importlib.util.find_spec("panda3d") is None, reason="Panda3D not installed")
def test_golem_scenario_events_show_resist_block_and_pierce(tmp_path):
    """The live game: the golem shard (bestiary stats) - every hero hit on it is resisted 30 %, blocked hits are cut
    50 %, every golem hit pierces 3 armor points of the hero."""
    out = tmp_path / "golem"
    env = {**os.environ, "AI_EVOLVE_PROBE_DB": str(tmp_path / "probe.sqlite")}
    proc = subprocess.run([sys.executable, "tools/agent_play.py", "--seed", "21", "--out", str(out),
                           "spawn enemy golem_shard x3; until kills>=3 or dead max 60"],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert "RESULT status=OK" in proc.stdout, proc.stdout + proc.stderr
    events = [json.loads(line) for line in (out / "combat.jsonl").read_text(encoding="utf-8").splitlines()]
    on_golem = [e for e in events if e["target_type"] == "golem_shard" and not e["dodged"]]
    on_hero = [e for e in events if e["target_type"] == "hero" and not e["dodged"]]
    assert on_golem and on_hero
    plain = [e for e in on_golem if not e.get("blocked") and e["damage"] > 0]
    assert plain and all(e["resisted"] > 0 for e in plain)
    # resisted / (damage + resisted) = 30 % on a hit that was not cut by the golem's remaining HP (a killing hit is)
    ratios = [e["resisted"] / (e["damage"] + e["resisted"]) for e in plain]
    assert all(r >= 0.27 for r in ratios) and sum(abs(r - 0.30) < 0.03 for r in ratios) >= 0.6 * len(ratios), ratios
    guarded = [e for e in on_golem if e.get("blocked")]
    assert guarded and all(e["guarded"] > 0 for e in guarded)
    assert all(e["pierced"] == 3.0 for e in on_hero)                # penetration_flat 3 of the golem
    assert "blocks=" in proc.stdout and "resisted=" in proc.stdout and "pierced=" in proc.stdout


def test_spawn_grammar_takes_a_bestiary_type():
    from agent_play import ScriptError, parse_script
    cmds = parse_script("spawn enemy golem_shard x2; spawn enemy")
    assert cmds[0][1] == {"key": "1", "times": 2, "what": "enemy", "enemy": "golem_shard"}
    assert cmds[1][1] == {"key": "1", "times": 1, "what": "enemy"}                              # untyped: as before
    for bad in ("spawn enemy dragon_of_doom", "spawn trap golem_shard", "spawn enemy a b"):
        with pytest.raises(ScriptError):
            parse_script(bad)
