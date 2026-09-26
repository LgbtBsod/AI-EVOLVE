"""Stacked timed `mod` ops on one stat must equal a recompute from the LIVE set, whatever expires first (EffectManager)."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.effects.manager import EffectManager  # noqa: E402
from tests.test_effect_manager import Fighter, World  # noqa: E402

STAT = "move_speed"


def _mod(aid, op, val, dur):
    o = {"kind": "mod", "target": "self", "stat": STAT, "op": op, "value": {"flat": val}, "duration": dur}
    return {"id": aid, "trigger": "cast", "range": 999, "needs_target": False, "ops": [o]}


def _setup(*rows):
    mgr = EffectManager(world=World(), abilities={r["id"]: r for r in rows}, rng=random.Random(1))
    hero = Fighter(x=0.0, y=0.0, hp=100.0)
    mgr.register(hero, "hero")
    return mgr, hero


def _eff(mgr, hero):
    st = mgr.state(hero)
    st.refresh(mgr.now)
    return st.unit._eff(STAT)


def _to(mgr, t):
    while mgr.now < t - 1e-9:
        mgr.update(0.5)


def _base():
    mgr, hero = _setup()
    return _eff(mgr, hero)


def test_mul_mul_short_expires_first():
    b = _base()
    mgr, hero = _setup(_mod("a", "mul", 2.0, 20), _mod("b", "mul", 1.5, 10))
    mgr.cast(hero, "a"); mgr.cast(hero, "b")
    assert _eff(mgr, hero) == pytest.approx(b * 3.0)
    _to(mgr, 11)
    assert _eff(mgr, hero) == pytest.approx(b * 2.0)
    _to(mgr, 21)
    assert _eff(mgr, hero) == pytest.approx(b)


def test_mul_mul_long_expires_first():
    b = _base()
    mgr, hero = _setup(_mod("a", "mul", 2.0, 10), _mod("b", "mul", 1.5, 20))
    mgr.cast(hero, "a"); mgr.cast(hero, "b")
    assert _eff(mgr, hero) == pytest.approx(b * 3.0)
    _to(mgr, 11)
    assert _eff(mgr, hero) == pytest.approx(b * 1.5)
    _to(mgr, 21)
    assert _eff(mgr, hero) == pytest.approx(b)


def test_add_and_mul_mixed():
    b = _base()
    mgr, hero = _setup(_mod("a", "add", 3.0, 10), _mod("m", "mul", 2.0, 20))
    mgr.cast(hero, "a"); mgr.cast(hero, "m")
    assert _eff(mgr, hero) == pytest.approx((b + 3.0) * 2.0)      # order of casting: add, then mul
    _to(mgr, 11)
    assert _eff(mgr, hero) == pytest.approx(b * 2.0)
    _to(mgr, 21)
    assert _eff(mgr, hero) == pytest.approx(b)


def test_refresh_same_buff_does_not_stack():
    b = _base()
    mgr, hero = _setup(_mod("m", "mul", 2.0, 10))
    mgr.cast(hero, "m"); _to(mgr, 5); mgr.cast(hero, "m")
    assert _eff(mgr, hero) == pytest.approx(b * 2.0)
    _to(mgr, 16)
    assert _eff(mgr, hero) == pytest.approx(b)
