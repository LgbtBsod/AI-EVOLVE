"""Executable spec of docs/CC_PORT_SPEC.md S2: stack cap/refresh, cc_duration_mult, chance-resist, damage while CC'd, CC priority."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects import damage, statuses  # noqa: E402
from tests.test_statuses_spec import HP, ManagerHost, RuntimeHost  # noqa: E402

FLAGS = {"no_crit", "unavoidable"}


def setstat(h, who, key, value):
    """Stat on a game entity: `innate` survives refresh and is ADDED to the rules default (cc_*_mult 1.0 + value)."""
    st = h.mgr.state(who)
    st.innate[key] = value
    st.version += 1
    st.refresh(h.mgr.now)


def hit(h, amount=100.0):
    before = h.dummy.health
    h.mgr._damage(h.mgr.state(h.hero), h.mgr.state(h.dummy), amount, set(FLAGS), "t", ())
    return before - h.dummy.health


def test_stack_cap_and_refresh():
    h = ManagerHost()
    assert [h.apply("bleed") for _ in range(7)] == [1, 2, 3, 4, 5, 5, 5]          # cap 5
    h.advance(6)
    h.apply("bleed")                                                               # refresh: timer restarts at base 8 s
    lost = h.lost()
    h.advance(8)
    assert h.lost() - lost == pytest.approx(8 * (5 + 2 * 5))                       # 5 stacks: 5 + 2/stack, full 8 s again
    h.advance(3)
    assert h.apply("bleed") == 1                                                   # expired stacks are gone


def test_cc_duration_mult_default_neutral_and_scaled():
    h = ManagerHost()
    h.apply("freeze")
    assert h.blocked()
    h.advance(2)
    assert not h.blocked()                                                         # 2 s x 1.0
    g = ManagerHost()
    setstat(g, g.dummy, "cc_duration_mult", -0.5)
    g.apply("freeze")
    g.advance(1)
    assert not g.blocked()                                                         # 2 s x 0.5 = 1 s


@pytest.mark.parametrize("host_cls", [RuntimeHost, ManagerHost])
def test_cc_duration_mult_zero_is_immune(host_cls):
    h = host_cls()
    if host_cls is ManagerHost:
        setstat(h, h.dummy, "cc_duration_mult", -1.0)
    else:
        h.dummy.base["cc_duration_mult"] = 0.0   # runtime host: base is the value itself
    assert h.apply("stun") == 0
    assert h.apply("bleed") == 1                                                   # only CC rows are scaled


def test_duration_mult_does_not_touch_dots():
    h = ManagerHost()
    setstat(h, h.dummy, "cc_duration_mult", -1.0)
    h.apply("burn")
    h.advance(6)
    assert h.lost() == pytest.approx(6 * 11)


def test_chance_resist():
    h = ManagerHost()
    setstat(h, h.dummy, "status_resist_stun", 100)
    assert h.apply("stun") == 0
    g = ManagerHost()                          # FakeRng(0.99): 99 >= 50 -> not resisted
    setstat(g, g.dummy, "status_resist_stun", 50)
    assert g.apply("stun") == 1


def test_damage_while_cc_arithmetic():
    h = ManagerHost()
    free = hit(h)
    setstat(h, h.dummy, "cc_damage_flat", 10.0)
    setstat(h, h.dummy, "cc_damage_reduction", 25.0)
    assert hit(h) == pytest.approx(free)                                           # no CC: no reduction
    h.apply("stun")
    assert hit(h) == pytest.approx((free - 10.0) * 0.75)
    setstat(h, h.hero, "cc_damage_mult", 0.5)
    assert hit(h) == pytest.approx((free - 10.0) * 0.75 * 1.5)


def test_row_cc_damage_mult_and_defaults():
    h = ManagerHost()
    free = hit(h)
    h.apply("slow")
    assert hit(h) == pytest.approx(free)                                           # defaults 1.0 / 0: identical
    assert damage.cc_adjust(80.0, 0.0, 0.0, 1.0) == 80.0
    assert damage.cc_adjust(5.0, 10.0, 0.0, 2.0) == 0.0


def test_cc_priority_and_conditions():
    h = ManagerHost()
    tgt = h.dummy
    assert h.mgr.active_cc(tgt) is None
    h.apply("slow")
    h.apply("root")
    assert h.mgr.active_cc(tgt)["id"] == "root"
    h.apply("stun")
    assert h.mgr.active_cc(tgt)["id"] == "stun"
    h.apply("bleed")
    ctx = h.mgr._ctx(h.mgr.state(h.hero), h.mgr.state(tgt))
    assert ctx["has_cc"] == 1.0 and ctx["cc_is_stun"] == 1.0
    h.advance(2)                                                                   # stun (1.5 s) over, root (3 s) wins
    assert h.mgr.active_cc(tgt)["id"] == "root"
    assert statuses.cc_strongest(["slow", "knockdown", "micro_stun"]) == "knockdown"
    h.advance(3)
    assert h.mgr.active_cc(tgt) is None
    assert h.mgr._ctx(h.mgr.state(h.hero), h.mgr.state(tgt))["has_cc"] == 0.0
