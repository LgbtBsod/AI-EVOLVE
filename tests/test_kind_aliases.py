"""Spec kind names (lua_content/kind_aliases.lua) run exactly like their canon twins; unknown kinds are still rejected."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from tools.effect_schema.validate import validate_op  # noqa: E402
from src.effects import ops as ops_mod  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from src.effects.ops import canonical_kind  # noqa: E402
from tests.test_effect_manager import FakeRng, Fighter, World  # noqa: E402

LUA = """return { abilities = { { id = "twin", cooldown = 1, range = 10, needs_target = true, tags = { "spell" }, ops = {
  { kind = "%s", target = "self", stat = "mana", value = { flat = 30 } },
  { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { flat = 15 } },
  { kind = "%s", target = "self", stat = "hp", value = { flat = 5 } } } } } }"""


def run(tmp_path, pay, heal):
    p = tmp_path / f"{pay}_{heal}.lua"
    p.write_text(LUA % (pay, heal), encoding="utf-8")
    ab = {a["id"]: a for a in lua_bridge.load(p)["abilities"]}
    mgr = EffectManager(world=World(), abilities=ab, rng=FakeRng())
    hero, enemy = Fighter(hp=50.0), Fighter(x=1.0, hp=100.0)
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters")
    res = mgr.cast(hero, "twin", enemy)
    return res.ok, hero.mana, hero.health, enemy.health


def test_spec_names_give_the_canon_result(tmp_path):
    canon, spec = run(tmp_path, "drain", "heal"), run(tmp_path, "consume", "restore")
    assert canon == spec and canon[0] and canon[1] == 70.0 and canon[3] == 85.0


def test_canonical_kind_and_from_json():
    assert canonical_kind("status") == "apply_effect" and canonical_kind("oath_binding") == "binding_vow"
    assert canonical_kind("remove_effect") == "remove_buff" and canonical_kind("use_learned") == "use_learned_technique"
    assert canonical_kind("deal") == "deal" and canonical_kind("debuff") == "debuff"    # canon and inexact: unchanged
    assert canonical_kind("dash") == "move"                                                # movement aliases are exact now


def test_validator_accepts_alias_and_rejects_unknown():
    assert validate_op({"kind": "consume", "stat": "mana", "value": {"flat": 1}}, "op") == \
        validate_op({"kind": "drain", "stat": "mana", "value": {"flat": 1}}, "op")
    assert validate_op({"kind": "dash", "target": "self"}, "op") == []                    # canonicalize_op injects mode=dash
    assert validate_op({"kind": "debuff", "target": "self"}, "op") == ["op: unknown kind 'debuff'"]
    assert validate_op({"kind": "no_such"}, "op") == ["op: unknown kind 'no_such'"]


def test_every_exact_alias_targets_a_handler():
    rows = lua_bridge.load(lua_bridge.CONTENT / "kind_aliases.lua")["aliases"]
    assert all(v["canon"] in ops_mod.OP_HANDLERS for v in rows.values())


def test_canonicalize_op_injects_implied_params_and_keeps_own_fields():
    from src.effects.ops import canonicalize_op
    op = {"kind": "dash", "distance": 4}
    out = canonicalize_op(op)
    assert out == {"kind": "move", "mode": "dash", "distance": 4} and op["kind"] == "dash"     # input untouched
    assert canonicalize_op({"kind": "push", "mode": "knockback"})["mode"] == "knockback"      # op's own field wins
    plain = {"kind": "deal"}
    assert canonicalize_op(plain) is plain
