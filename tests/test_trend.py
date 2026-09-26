"""qa.py trend: synthetic history - one slow check and one flipping check are flagged, a noisy-but-stable one is not."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from qa_plugins import trend  # noqa: E402

CFG = trend.trend_cfg({})


def rows(name, durs, statuses=None):
    return [{"name": name, "dur": d, "status": (statuses or ["ok"] * len(durs))[i]} for i, d in enumerate(durs)]


def test_slow_check_flagged_after_three_confirmations():
    lines = trend.trend_lines(rows("slow", [2.0] * 15 + [4.0, 4.1, 4.2]), CFG)
    assert len(lines) == 1 and "slow" in lines[0] and "dur=+" in lines[0]


def test_single_spike_is_not_flagged():
    assert trend.trend_lines(rows("spike", [2.0] * 17 + [9.0]), CFG) == []


def test_flipping_check_flagged():
    st = ["ok", "fail"] * 6
    lines = trend.trend_lines(rows("flip", [1.0] * 12, st), CFG)
    assert len(lines) == 1 and "flips=" in lines[0]


def test_noisy_but_stable_not_flagged():
    durs = [1.0, 1.6, 0.8, 1.4, 1.1, 1.5, 0.9, 1.3, 1.0, 1.5, 0.9, 1.2, 1.4, 1.0, 1.3]
    assert trend.trend_lines(rows("noisy", durs), CFG) == []


def test_short_history_skipped():
    assert trend.trend_lines(rows("new", [1.0, 1.0, 9.0, 9.0, 9.0]), CFG) == []
