"""Кузница предметов и itemcheck + семантика схемы, которую они выявили.

Выкованный предмет задействует всю схему (каждый стат, операцию, событие,
цель, флаг, форму значения, баффы, цепочки, amplify, hp_cross, ресурсы
hp/mana/stamina); itemcheck проверяет его от валидации до боя.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import lua_bridge  # noqa: E402
from tools.effect_schema import itemcheck  # noqa: E402
from tools.effect_schema.forge import PredGen, forge_item  # noqa: E402
from tools.effect_schema.lua_gen import render_item  # noqa: E402
from tools.effect_schema.sim import (EffectRuntime, PrediciationException, Unit, compile_pred,  # noqa: E402
                                     eval_pred)
from tools.effect_schema.validate import validate_item  # noqa: E402

BACKENDS = lua_bridge.available_backends()
needs_lua = pytest.mark.skipif(not BACKENDS, reason="no Lua backend (lupa / rust_core)")


def _checks(report):
    return {c.name: c for c in report.checks}


# ---------------------------------------------------------------- forge + itemcheck

@needs_lua
def test_coverage_item_passes_every_check_and_covers_the_whole_schema():
    report = itemcheck.check_item(forge_item(0, seed=0), pred_samples=60)
    assert report.ok, "\n".join(report.lines())
    cov = itemcheck.coverage(forge_item(0, seed=0))
    missing = {dim: sorted(a - u) for dim, (u, a) in cov.items() if a - u}
    assert missing == {}


@needs_lua
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_items_pass(seed):
    report = itemcheck.check_item(forge_item(120, seed=seed), pred_samples=40, seed=seed)
    assert report.ok, "\n".join(report.lines())


@needs_lua
@pytest.mark.parametrize("seed", [5, 6, 12, 15, 23])  # сиды, на которых раньше расходились Python и Lua
def test_hostile_conditions_agree_between_python_and_lua(seed):
    item = forge_item(80, seed=seed, hostile=True)
    lua = render_item({"name": "hostile"}, item["effects"])
    check = itemcheck.check_preds(item, lua, BACKENDS, samples=150, seed=seed)
    assert check.ok, check.findings[:5]


def test_forge_is_deterministic():
    assert forge_item(30, seed=4) == forge_item(30, seed=4)
    assert forge_item(30, seed=4) != forge_item(30, seed=5)


def test_pred_gen_produces_boolean_conditions():
    from tools.effect_schema.pred_lua import check_boolean
    import random
    gen = PredGen(random.Random(1))
    for _ in range(200):
        assert check_boolean(gen.cond(3)) == []


def test_itemcheck_reports_invariant_violations():
    # max_hp -> 0 через mod set: граница max_hp >= 1 из effect_rules.lua держит HP конечным
    item = {"name": "t", "effects": [{"id": "x", "trigger": {"kind": "passive"},
                                      "ops": [{"kind": "mod", "target": "self", "stat": "max_hp", "op": "set",
                                               "value": {"flat": 0}}]}]}
    _log, violations, summary = itemcheck.run_scenario(item)
    assert violations == [] and summary["max_hp"] == 1.0


# ---------------------------------------------------------------- Lua-compatible arithmetic

@needs_lua
@pytest.mark.parametrize("backend", BACKENDS)
def test_edge_arithmetic_matches_lua(backend):
    exprs = ["ctx.a % ctx.b > 0", "ctx.a % ctx.b == 0", "ctx.a / ctx.z > 0", "ctx.n / ctx.z < 0",
             "(ctx.n / ctx.z) ** 2.5 > 0", "(ctx.n / ctx.z) ** 3 < 0", "ctx.n ** 0.5 > 0", "ctx.n ** 0.5 != ctx.n ** 0.5",
             "ctx.z ** ctx.n > 1", "ctx.big ** ctx.big > 0", "floor(ctx.a / ctx.z) > 0", "ceil(ctx.n) == -8",
             "(ctx.z % ctx.nb) / ctx.one > 0", "ctx.one / (ctx.z % ctx.nb) > 0",
             "max(ctx.a / ctx.z, 1) > 5", "min(ctx.z / ctx.z, 1) < 5", "abs(ctx.n) >= 8"]
    effects = [{"id": f"e{i}", "trigger": {"kind": "condition", "when": e},
                "ops": [{"kind": "mod", "target": "self", "stat": "strength", "op": "add", "value": {"flat": 1}}]}
               for i, e in enumerate(exprs)]
    lua = render_item({"name": "edge"}, effects)
    ctxs = [{"a": 7.0, "b": -5.0, "z": 0.0, "n": -8.0, "nb": -5.0, "one": 1.0, "big": 1e300},
            {"a": -7.0, "b": 5.0, "z": -0.0, "n": -8.5, "nb": -3.0, "one": -1.0, "big": 10.0}]
    rows = lua_bridge.eval_preds(lua, ctxs, backend=backend)
    for ctx, row in zip(ctxs, rows):
        for e in exprs:
            assert row[e] == eval_pred(e, ctx), (e, ctx, row[e])


def test_compiled_predicates_stay_whitelisted_and_lazy():
    for bad in ["ctx.__class__", "max.__class__", "ctx.hp.real", "open('x')", "ctx.hp if 1 else 0", "[1][0] > 0"]:
        with pytest.raises(PrediciationException):
            compile_pred(bad)
    # and/or ленивые, как в Lua: неизвестное поле за ложной веткой не читается
    assert eval_pred("ctx.hp > 10 and ctx.unknown > 0", {"hp": 1.0}) is False
    with pytest.raises(PrediciationException):
        eval_pred("ctx.hp < 10 and ctx.unknown > 0", {"hp": 1.0})


def test_division_by_constant_zero_is_a_validation_error():
    item = {"effects": [{"id": "x", "trigger": {"kind": "condition", "when": "ctx.hp / 0 > 1"},
                         "ops": [{"kind": "mod", "target": "self", "stat": "strength", "op": "add", "value": {"flat": 1}}]}]}
    assert any("division by the constant 0" in e for e in validate_item(item))


# ---------------------------------------------------------------- resources: hp, mana, stamina

def _rt(effects, **hero_stats):
    hero = Unit("hero", max_hp=1000.0, **hero_stats)
    dummy = Unit("dummy", max_hp=5000.0)
    rt = EffectRuntime(hero, effects, enemy=dummy)
    rt.refresh_passives()
    return hero, dummy, rt


def test_stamina_is_a_resource_with_cost_fail_branch_and_regen():
    effects = [{"id": "dash", "trigger": {"kind": "event", "event": "use"}, "ops": [
        {"kind": "drain", "target": "self", "stat": "stamina", "op": "sub", "value": {"flat": 30},
         "fail": [{"kind": "deal", "target": "self", "stat": "hp", "op": "sub", "value": {"flat": 50}}]}]}]
    hero, _dummy, rt = _rt(effects, max_stamina=80, stamina_regen=5)
    for _ in range(2):
        rt.fire_event("use")
    assert hero.resource("stamina") == pytest.approx(20.0)
    rt.fire_event("use")                          # 30 > 20: стамины не хватает -> fail
    assert hero.resource("stamina") == pytest.approx(20.0) and hero.current_hp == pytest.approx(950.0)
    rt.tick(1.0, 2.0)                             # реген стамины 5/с
    assert hero.resource("stamina") == pytest.approx(30.0)
    assert hero.ctx()["stamina"] == pytest.approx(30.0) and hero.ctx()["max_stamina"] == 80.0


def test_mod_on_resource_is_rejected_and_max_drop_clamps_current():
    bad = {"effects": [{"id": "x", "trigger": {"kind": "passive"},
                        "ops": [{"kind": "mod", "target": "self", "stat": "stamina", "op": "add", "value": {"flat": 5}}]}]}
    assert any("resource 'stamina'" in e for e in validate_item(bad))
    shrink = [{"id": "x", "trigger": {"kind": "event", "event": "use"},
               "ops": [{"kind": "mod", "target": "self", "stat": "max_stamina", "op": "sub", "value": {"flat": 60}}]}]
    hero, _d, rt = _rt(shrink)
    rt.fire_event("use")
    assert hero.resource("stamina") == pytest.approx(40.0)


def test_negative_regen_kills_instead_of_negative_hp_and_heal_does_not_revive():
    hero, _d, rt = _rt([], hp_regen=-100)
    hero.current_hp = 50.0
    rt.tick(1.0, 1.0)
    assert hero.current_hp == 0.0 and not hero.alive
    hero.heal(500)
    assert hero.current_hp == 0.0 and not hero.alive


def test_enemy_mods_go_to_the_enemy_and_reset_on_respawn():
    effects = [{"id": "sunder", "trigger": {"kind": "event", "event": "attack_hit"},
                "ops": [{"kind": "mod", "target": "enemy", "stat": "defense", "op": "sub", "value": {"flat": 5}}]}]
    hero, dummy, rt = _rt(effects)
    rt.attack(0.0, base_damage=10)
    assert dummy._eff("defense") == -5.0 and hero._eff("defense") == 0.0
    rt.respawn_enemy()
    assert dummy._eff("defense") == 0.0


def test_effect_cooldown_and_applied_trigger():
    effects = [{"id": "proc", "cooldown": {"flat": 2}, "trigger": {"kind": "event", "event": "attack_hit"},
                "ops": [{"kind": "apply_effect", "target": "enemy", "buff_id": "burst"}]},
               {"id": "burst", "trigger": {"kind": "applied"},
                "ops": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 100}}]}]
    assert validate_item({"effects": effects}) == []
    _hero, dummy, rt = _rt(effects)
    for t in (0.0, 1.0, 2.5):
        rt.attack(t, base_damage=0)
    assert dummy.current_hp == pytest.approx(5000 - 2 * 100)  # t=1.0 - на кулдауне
    rt.fire_event("applied")  # applied не событие: сам по себе не срабатывает
    assert dummy.current_hp == pytest.approx(4800)


@needs_lua
def test_hp_cross_zone_survives_lua_and_named_predicate_is_real_in_lua():
    item = forge_item(0, seed=0)
    data = lua_bridge.load(render_item({"name": "f"}, item["effects"]))
    by_id = {e["id"]: e for e in data["effects"]}
    assert by_id["zone.half"]["threshold"] == 50
    assert by_id["zone.half.cross"]["trigger"]["cross"] == "Half HP"
    lua = render_item({"name": "n"}, [by_id["amp.low_hp"]])
    rows = lua_bridge.eval_preds(lua, [{"hp_pct": 30.0, "hp": 300.0}, {"hp_pct": 60.0, "hp": 600.0}])
    assert [r["low_hp_40"] for r in rows] == [True, False]


def test_all_numbers_in_conditions_are_float_in_both_languages():
    from tools.effect_schema.pred_lua import to_lua
    assert to_lua("min(40, ctx.x) % floor(ctx.y) > 1") == \
        "(math.min(40.0, ctx.x) % (math.floor(ctx.y) + 0.0)) > 1.0"
    assert eval_pred("min(40, ctx.x) % floor(ctx.y) > 1", {"x": 50.0, "y": 0.0}) is False  # nan, не ошибка
    assert not math.isnan(compile_pred("ctx.x ** 2")({"x": 3.0}) - 9.0)


@needs_lua
@pytest.mark.parametrize("backend", BACKENDS)
def test_huge_items_render_in_blocks(monkeypatch, backend):
    """Lua: не больше 131071 функций в одной функции; предмет на 100 тыс. эффектов
    упирался в этот лимит. Большие предметы пишутся блоками (здесь блок = 3 эффекта)."""
    from tools.effect_schema import lua_gen
    monkeypatch.setattr(lua_gen, "EFFECTS_PER_BLOCK", 3)
    item = forge_item(0, seed=2)
    lua = render_item({"name": "blocks"}, item["effects"])
    assert "лимит Lua 131071" in lua
    data = lua_bridge.load(lua, backend=backend)
    assert itemcheck._norm(data["effects"]) == itemcheck._norm(item["effects"])


def test_mod_without_op_adds():
    hero, _d, rt = _rt([{"id": "x", "trigger": {"kind": "passive"},
                         "ops": [{"kind": "mod", "target": "self", "stat": "strength", "op": None,
                                  "value": {"flat": 7}}]}])
    assert hero._eff("strength") == 7.0
