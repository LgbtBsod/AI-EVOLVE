"""Executable spec of the statuses in lua_content/statuses/core_statuses.lua (docs/CC_PORT_SPEC.md S1).

Every status is applied by id to a dummy on BOTH hosts: EffectRuntime (training room) and EffectManager (game).
Legacy numbers are kept (bleed 5 + 2/stack ...); weaken = -10% damage dealt per stack, vulnerable = +10% damage
taken per stack (owner decision). Runtime does not expire timed mods on the dummy (a known host divergence,
APP_SPECIFICS row 5), so mod expiry is asserted on the manager only.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects import statuses  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from tests.test_effect_manager import Fighter, FakeRng, World  # noqa: E402
from tools.effect_schema.sim import EffectRuntime, Unit  # noqa: E402
from tools.effect_schema.validate import validate_op  # noqa: E402

DOTS = {  # id: (duration, base, per stack, cap)
    "bleed": (8, 5, 2, 5), "burn": (6, 8, 3, 3), "poison": (10, 4, 1.5, 6), "shock": (4, 3, 1.5, 4)}
HP = 1e6


class RuntimeHost:
    name = "runtime"

    def __init__(self):
        self.hero, self.dummy = Unit("hero", max_hp=HP), Unit("dummy", max_hp=HP)
        self.rt = EffectRuntime(self.hero, [], enemy=self.dummy)
        self.t = 0.0

    def apply(self, sid, stacks=1):
        return self.rt.apply_status(sid, self.t, stacks)

    def advance(self, seconds):
        for _ in range(int(round(seconds))):
            self.t += 1.0
            self.rt.tick(self.t, 1.0)

    def lost(self):
        return HP - self.dummy.current_hp

    def blocked(self):
        return "nullified" in self.dummy.buffs and self.dummy.buffs["nullified"]["until"] > self.t


class ManagerHost:
    name = "manager"

    def __init__(self):
        self.mgr = EffectManager(world=World(), abilities={}, rng=FakeRng(0.99))
        self.hero, self.dummy = Fighter(hp=HP), Fighter(x=1.0, hp=HP)
        self.mgr.register(self.hero, "hero")
        self.mgr.register(self.dummy, "monsters")

    def apply(self, sid, stacks=1):
        return self.mgr.apply_status(self.dummy, sid, self.hero, stacks)

    def advance(self, seconds):
        for _ in range(int(round(seconds))):
            self.mgr.update(1.0)

    def lost(self):
        return HP - self.dummy.health

    def blocked(self):
        b = self.mgr.state(self.dummy).unit.buffs.get("nullified")
        return bool(b) and b["until"] > self.mgr.now


@pytest.fixture(params=[RuntimeHost, ManagerHost], ids=["runtime", "manager"])
def host(request):
    return request.param()


def test_every_row_is_valid_schema():
    for sid, row in statuses.load_statuses().items():
        if row.get("alias") or sid in ("amaterasu", "tsukuyomi", "infinity"):   # planned kinds, see the file
            continue
        for i, o in enumerate(statuses.materialize(row, 1)):
            assert validate_op(o, f"{sid}.{i}") == []


def test_alias_and_unknown(host):
    assert statuses.get_status("disoriented")["id"] == "blind"
    with pytest.raises(KeyError):
        host.apply("no_such_status")


@pytest.mark.parametrize("sid", sorted(DOTS))
def test_dot_ticks_and_expires(host, sid):
    dur, base, per, _cap = DOTS[sid]
    assert host.apply(sid) == 1
    host.advance(dur)
    assert host.lost() == pytest.approx(dur * (base + per))       # a tick each second, the last one at `duration`
    host.advance(3)
    assert host.lost() == pytest.approx(dur * (base + per))       # expired: no more damage


def test_bleed_three_applications(host):
    for _ in range(3):
        host.apply("bleed")
    host.advance(8)
    assert host.lost() == pytest.approx(8 * (5 + 2 * 3))          # spec row 1: 5 + 2*3 per second for 8 s


@pytest.mark.parametrize("sid", sorted(DOTS))
def test_stack_cap(host, sid):
    dur, base, per, cap = DOTS[sid]
    assert host.apply(sid, stacks=cap + 5) == cap
    assert host.apply(sid) == cap
    host.advance(1)
    assert host.lost() == pytest.approx(base + per * cap)


def test_reapply_restarts_timer_without_double_dot(host):
    host.apply("burn")
    host.advance(4)
    before = host.lost()
    host.apply("burn")                                            # 2 stacks, timer back to 6 s
    host.advance(6)
    assert host.lost() - before == pytest.approx(6 * (8 + 3 * 2))
    host.advance(2)
    assert host.lost() - before == pytest.approx(6 * (8 + 3 * 2))


@pytest.mark.parametrize("sid,secs", [("stun", 1.5), ("freeze", 2), ("knockdown", 1.0)])
def test_cc_blocks_actions_then_expires(host, sid, secs):
    host.apply(sid)
    assert host.blocked()
    host.advance(2 if secs <= 2 else 3)
    assert not host.blocked()


def test_cc_priority_is_data_and_strongest_wins():
    want = {"stun": 5, "knockdown": 4, "micro_stun": 3, "root": 2, "disoriented": 1, "slow": 0}
    assert {k: statuses.cc_priority(k) for k in want} == want
    assert statuses.cc_priority("burn") is None
    assert statuses.cc_strongest(["slow", "root", "stun", "disoriented"]) == "stun"
    assert statuses.cc_strongest(["slow", "disoriented", "root"]) == "root"
    assert statuses.cc_strongest(["micro_stun", "knockdown"]) == "knockdown"
    assert statuses.cc_strongest(["burn"]) is None


def test_micro_stun_blocks_abilities_briefly(host):
    host.apply("micro_stun")
    assert host.blocked()
    host.advance(1)
    assert not host.blocked()


def test_chance_resist_full_and_rolled(host):
    unit = host.dummy if host.name == "runtime" else host.mgr.state(host.dummy).unit
    unit.base["status_resist_burn"] = 100.0
    assert host.apply("burn") == 0
    host.advance(2)
    assert host.lost() == 0
    if host.name == "manager":                       # a chance needs the rng: 0.99 -> not resisted, 0.0 -> resisted
        unit.base["status_resist_burn"] = 50.0
        assert host.apply("burn") == 1
        host.mgr.rng.value = 0.0
        assert host.apply("stun") == 1               # other statuses are unaffected
        unit.base["status_resist_burn"] = 50.0       # (pull() rebuilds base from the entity on refresh)
        assert host.apply("burn") == 0


def test_slow_and_root_on_move_speed():
    h = ManagerHost()
    speed = h.mgr.state(h.dummy).unit.stat("move_speed")
    h.apply("slow")
    assert h.mgr.state(h.dummy).unit.stat("move_speed") == pytest.approx(speed * 0.6)
    h.advance(4)                                                   # slow lasts 3 s
    assert h.mgr.state(h.dummy).unit.stat("move_speed") == pytest.approx(speed)
    h.apply("root")
    assert h.mgr.state(h.dummy).unit.stat("move_speed") == pytest.approx(0.0)
    h.advance(4)
    assert h.mgr.state(h.dummy).unit.stat("move_speed") == pytest.approx(speed)


def test_knockdown_pushes_target_away():
    h = ManagerHost()
    h.apply("knockdown")
    assert h.dummy.x == pytest.approx(1.0 + 1.5)


def _hit(mgr, src, dst):
    before = dst.health
    mgr._damage(mgr.state(src), mgr.state(dst), 100.0, set(), "spec", ())
    return before - dst.health


def test_vulnerable_raises_damage_taken_through_real_path():
    h = ManagerHost()
    assert _hit(h.mgr, h.hero, h.dummy) == pytest.approx(100.0)
    assert h.apply("vulnerable") == 1
    assert _hit(h.mgr, h.hero, h.dummy) == pytest.approx(110.0)
    assert h.apply("vulnerable", 5) == 2                           # cap 2
    assert _hit(h.mgr, h.hero, h.dummy) == pytest.approx(120.0)
    h.advance(5)                                                   # 4 s duration
    assert _hit(h.mgr, h.hero, h.dummy) == pytest.approx(100.0)


def test_weaken_lowers_damage_dealt_through_real_path():
    h = ManagerHost()
    assert _hit(h.mgr, h.dummy, h.hero) == pytest.approx(100.0)
    assert h.apply("weaken", 2) == 2
    assert _hit(h.mgr, h.dummy, h.hero) == pytest.approx(80.0)     # -10% per stack
    assert h.apply("weaken", 9) == 3                               # cap 3
    assert _hit(h.mgr, h.dummy, h.hero) == pytest.approx(70.0)
    h.advance(6)                                                   # 5 s duration
    assert _hit(h.mgr, h.dummy, h.hero) == pytest.approx(100.0)


def test_vulnerable_mod_on_runtime_host():
    h = RuntimeHost()
    h.apply("vulnerable", 2)
    assert h.dummy.mods.get("damage_taken") == pytest.approx(20.0)
