"""validate_op characterization: exact error strings over every op in lua_content/**/*.lua plus hand-made invalid ops.
Golden: tests/fixtures/validate_op_golden.json (regenerate only for an intended change: VALIDATE_OP_RECORD=1)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.effect_schema.validate import validate_op  # noqa: E402

GOLDEN = ROOT / "tests" / "fixtures" / "validate_op_golden.json"

HAND = [
    "x", None, {}, {"kind": "nope"}, {"kind": "mod", "target": "zzz", "stat": "attack", "value": 1},
    {"kind": "mod", "op": "bad", "stat": "attack", "value": 1}, {"kind": "mod", "stat": "zzz", "value": 1},
    {"kind": "mod", "value": 1}, {"kind": "heal", "value": 1}, {"kind": "mod", "stat": "hp", "value": 1},
    {"kind": "heal", "stat": "attack", "value": 1}, {"kind": "set", "stat": "attack", "value": 1},
    {"kind": "deal", "stat": "hp"}, {"kind": "mod", "stat": "attack", "value": 1, "flags": ["zz"]},
    {"kind": "mod", "stat": "attack", "value": 1, "extend": {"on": "zz"}},
    {"kind": "apply_effect"}, {"kind": "summon"}, {"kind": "move"}, {"kind": "move", "mode": "zz"},
    {"kind": "buff"}, {"kind": "extend"}, {"kind": "remove_buff"},
    {"kind": "deal", "stat": "hp", "value": 1, "target": "area", "center": "zz"},
    {"kind": "deal", "stat": "hp", "value": 1, "arc": 400}, {"kind": "deal", "stat": "hp", "value": 1, "target": "area", "arc": 90},
    {"kind": "deal", "stat": "hp", "value": 1, "arc": 0, "target": "area"},
    {"kind": "deal", "stat": "hp", "value": 1, "radius": "zz"}, {"kind": "deal", "stat": "hp", "value": 1, "radius": "attack"},
    {"kind": "deal", "stat": "hp", "value": 1, "affects": "zz"}, {"kind": "deal", "stat": "hp", "value": 1, "target": "area", "affects": "zz"},
    {"kind": "mod", "stat": "attack", "value": 1, "toward": "zz"}, {"kind": "mod", "stat": "attack", "value": 1, "toward": "source"},
    {"kind": "mod", "stat": "stealth", "value": 1, "toward": "source"},
    {"kind": "mod", "stat": "attack", "value": 1, "every": 1}, {"kind": "deal", "stat": "hp", "value": 1, "every": 1},
    {"kind": "deal", "stat": "hp", "value": 1, "every": 1, "duration": 3},
    {"kind": "deal", "stat": "hp", "value": 1, "when": "zz(("}, {"kind": "deal", "stat": "hp", "value": 1, "when": "hp < 5"},
    {"kind": "deal", "stat": "hp", "value": {}}, {"kind": "deal", "stat": "hp", "value": {"pct": 1, "of": "zz"}},
    {"kind": "deal", "stat": "hp", "value": {"flat": 1}}, {"kind": "deal", "stat": "hp", "scale": {}},
    {"kind": "deal", "stat": "hp", "scale": {"every": 0, "of": "zz"}}, {"kind": "deal", "stat": "hp", "scale": {"every": 2, "of": "attack"}},
    {"kind": "deal", "stat": "hp", "scale": {"every": 2}},
    {"kind": "deal", "stat": "hp", "value": 1, "fail": [{"kind": "zz"}, "q", {"kind": "buff"}]},
    {"kind": "mod", "stat": "custom:foo", "value": 1}, {"kind": "mod", "stat": "armor_pct_x", "value": 1},
]


def _walk(x, out):
    if isinstance(x, dict):
        if isinstance(x.get("ops"), list):
            out += [o for o in x["ops"] if isinstance(o, dict)]
        for v in x.values():
            _walk(v, out)
    elif isinstance(x, list):
        for v in x:
            _walk(v, out)


def _lua_ops():
    from lua_bridge import load
    ops: list = []
    for p in sorted((ROOT / "lua_content").rglob("*.lua")):
        try:
            _walk(load(str(p)), ops)
        except Exception:
            continue
    return ops


def _build():
    ops = _lua_ops() + HAND
    return {"n_lua": len(ops) - len(HAND),
            "cases": sorted([json.dumps(o, sort_keys=True, default=str), validate_op(o, "op", ["e1"])] for o in ops)}


def test_validate_op_matches_golden():
    got = _build()
    if os.environ.get("VALIDATE_OP_RECORD"):
        GOLDEN.write_text(json.dumps(got, ensure_ascii=False, indent=0), encoding="utf-8")
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert got["n_lua"] > 20
    assert got == want
