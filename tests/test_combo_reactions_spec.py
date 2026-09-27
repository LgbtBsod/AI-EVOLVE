"""Executable spec of docs/CC_PORT_SPEC.md S3: combo reactions (rows 12-16), existing ops only.

Game host only (EffectManager): reactions fire from `apply_status`, which `EffectRuntime` (training room) does
not implement (same host divergence noted for S1/S2, tests/test_statuses_spec.py). Pair reactions (melt,
superconduct, explosion) fire the instant the second status of the pair lands, before any DoT tick; same-type
reactions (hemorrhage, overload; owner decision Q5: KEEP, not blocked by the legacy A!=B rule) fire the instant
a status stacks to its own cap.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects.manager import MAX_EVENT_DEPTH  # noqa: E402
from tests.test_statuses_spec import ManagerHost  # noqa: E402


def book_stacks(h, status_id):
    return h.mgr._status_book.get((id(h.dummy), status_id), (0, 0.0))[0]


def test_melt_freeze_then_burn():
    h = ManagerHost()
    h.apply("freeze")
    assert h.blocked()
    h.apply("burn")
    assert h.lost() == pytest.approx(50)                       # true damage, before any burn tick
    assert not h.blocked()                                      # freeze purged
    assert book_stacks(h, "freeze") == 0
    assert h.mgr._depth == 0


def test_superconduct_freeze_then_shock():
    h = ManagerHost()
    h.apply("freeze")
    h.apply("shock")
    assert h.lost() == pytest.approx(80)
    assert not h.blocked()
    assert book_stacks(h, "freeze") == 0


def test_explosion_burn_then_poison_is_area_and_purges_poison():
    h = ManagerHost()
    h.apply("burn")
    h.apply("poison")
    assert h.lost() == pytest.approx(60)                        # true damage, before any DoT tick
    assert book_stacks(h, "poison") == 0                        # poison purged, burn kept ticking
    assert book_stacks(h, "burn") == 1


def test_hemorrhage_bleed_detonates_at_max_stacks():
    h = ManagerHost()
    for _ in range(4):
        h.apply("bleed")
    assert h.lost() == 0.0                                      # cap is 5: no detonate yet
    h.apply("bleed")
    assert h.lost() == pytest.approx(30)                        # 5th application hits the cap -> detonate


def test_overload_shock_detonates_at_max_stacks():
    h = ManagerHost()
    for _ in range(3):
        h.apply("shock")
    assert h.lost() == 0.0                                      # cap is 4
    h.apply("shock")
    assert h.lost() == pytest.approx(20)


def test_max_event_depth_still_bounds_reactions():
    h = ManagerHost()
    h.mgr._depth = MAX_EVENT_DEPTH
    h.apply("freeze")
    h.apply("burn")                                             # would melt, but depth is already at the cap
    assert h.lost() == 0.0
    h.mgr._depth = 0
