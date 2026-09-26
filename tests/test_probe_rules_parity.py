"""Parity: hypotheses()/forecast() (Lua rules + tools/probe_rules.py evaluator) reproduce, byte for byte,
the outputs of the original if/elif code frozen in tests/fixtures/probe_rules_golden.json
(48 cases: synthetic ones that hit every rule and branch + 3 recorded runs)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import probe_analysis as pa  # noqa: E402
import probe_rules  # noqa: E402

GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "probe_rules_golden.json").read_text(encoding="utf-8"))


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False)


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_outputs_identical(case):
    hyp = pa.hypotheses(case["samples"], case["events"], dict(case["ctx"]))
    fc = pa.forecast(case["samples"], case["events"], dict(case["ctx"]))
    assert _dump(hyp) == _dump(case["hyp"])
    assert _dump(fc) == _dump(case["fc"])
    assert pa.format_hypotheses(hyp, 3) == case["fmt_h"]
    assert pa.format_forecast(fc) == case["fmt_f"]


def test_every_rule_is_covered_by_the_golden():
    ids = {r["id"] for r in probe_rules.rules_table()["hypotheses"]}
    assert ids <= {h["id"] for c in GOLDEN for h in c["hyp"]}


def test_evaluator_conditions():
    facts = {"a": 3, "b": 0, "n": None}
    hold = probe_rules.holds
    assert hold({"m": "a", "op": "ge", "v": 3}, facts, {})
    assert not hold({"m": "n", "op": "gt", "v": 1}, facts, {})
    assert not hold({"m": ["a", "b"], "op": "gt", "v": 0}, facts, {})  # /0 -> None -> false
    assert hold({"any": [{"m": "b", "op": "truthy"}, {"m": "n", "op": "isnone"}]}, facts, {})
    assert hold({"m": "a", "op": "gt", "v": "$lim"}, facts, {"lim": 2})


def test_snapshot_equals_lua():
    lua_bridge = pytest.importorskip("lua_bridge")
    try:
        lua = lua_bridge.load(probe_rules.RULES_PATH)
    except RuntimeError:
        pytest.skip("no Lua backend")
    snap = json.loads(probe_rules.SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert snap == lua, "regenerate: python tools/probe_rules.py"
