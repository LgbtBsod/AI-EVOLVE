"""S4 (docs/CC_PORT_SPEC.md 2.3 rows 17/19/21/22/25): toughness/break bar.

Executable spec, not a play scenario: build ops directly (op `toughness_damage`) against fake entities,
like tests/test_effect_manager.py. The feature flag (lua_content/toughness.lua `enabled`) is live by
default; each test monkeypatches `toughness.config()` explicitly (on with `ON_CONFIG`, or off) so it does
not depend on the file's current value.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects import toughness  # noqa: E402
from src.effects.abilities import load_abilities  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from tests.test_effect_manager import Fighter, FakeRng, World  # noqa: E402

ON_CONFIG = {
    "enabled": True,
    "base_by_class": {"player": 100, "npc": 50, "enemy": 800, "boss": 2000, "elite": 1500},
    "type_factor": {"physical": 1.0, "fire": 0.5},
    "break_duration": 5.0,
    "break_growth_pct": 5.0,
    "break_growth_cap_pct": 20.0,
}


def _mgr():
    mgr = EffectManager(world=World(), abilities=load_abilities(), rng=FakeRng(0.99))
    hero = Fighter()
    enemy = Fighter()
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters")
    return mgr, hero, enemy


def _hit(mgr, hero, enemy, amount, dtype=None):
    o = {"kind": "toughness_damage", "target": "enemy", "value": {"flat": amount}}
    if dtype:
        o["type"] = dtype
    from src.effects.ops import apply_op
    from src.effects.manager import OpCall
    st_h, st_e = mgr.state(hero), mgr.state(enemy)
    cx = OpCall(source=st_h, t=mgr.now, src="test", tags=(), ctx={}, hits=[])
    apply_op(mgr, cx, st_e, o)


def test_flag_off_is_inert(monkeypatch):
    """`enabled = false` (kill switch off): no toughness state appears, target never breaks."""
    monkeypatch.setattr(toughness, "config", lambda: {"enabled": False})
    assert toughness.enabled() is False
    mgr, hero, enemy = _mgr()
    _hit(mgr, hero, enemy, 999999)
    st_e = mgr.state(enemy)
    assert st_e.toughness is None
    assert st_e.toughness_break_until == 0.0


def test_break_at_zero_applies_broken_mod(monkeypatch):
    monkeypatch.setattr(toughness, "config", lambda: ON_CONFIG)
    mgr, hero, enemy = _mgr()
    st_e = mgr.state(enemy)
    _hit(mgr, hero, enemy, 1000)  # base is 800 -> breaks in one hit
    assert st_e.toughness == 0.0
    assert st_e.toughness_break_until > mgr.now
    assert st_e.unit._eff("broken") == 1.0


def test_type_factor_applied(monkeypatch):
    monkeypatch.setattr(toughness, "config", lambda: ON_CONFIG)
    mgr, hero, enemy = _mgr()
    st_e = mgr.state(enemy)
    _hit(mgr, hero, enemy, 100, dtype="fire")  # x0.5 -> 50 off an 800 base
    assert st_e.toughness == 750.0


def test_break_purges_cc_and_blocks_new_cc(monkeypatch):
    monkeypatch.setattr(toughness, "config", lambda: ON_CONFIG)
    mgr, hero, enemy = _mgr()
    st_e = mgr.state(enemy)
    mgr.apply_status(enemy, "stun", hero)
    from src.effects import statuses
    assert statuses.cc_ids(mgr._status_book, id(enemy), mgr.now)
    _hit(mgr, hero, enemy, 1000)  # breaks -> purges the stun
    assert not statuses.cc_ids(mgr._status_book, id(enemy), mgr.now)
    stacks = mgr.apply_status(enemy, "root", hero)  # row 25: new CC ignored while broken
    assert stacks == 0


def test_growth_capped_and_refill_on_exit(monkeypatch):
    monkeypatch.setattr(toughness, "config", lambda: ON_CONFIG)
    mgr, hero, enemy = _mgr()
    st_e = mgr.state(enemy)
    for _ in range(6):  # 6 breaks * 5% > the 20% cap
        _hit(mgr, hero, enemy, 1000)
        mgr.update(6.0)  # past break_duration -> refill, ready to break again
    assert st_e.toughness_growth_pct == 20.0
    assert st_e.toughness_max == 800.0 + 0.20 * enemy.max_health
    assert st_e.toughness == st_e.toughness_max
    assert st_e.toughness_break_until == 0.0
