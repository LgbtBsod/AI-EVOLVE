"""Executable spec of Lost My Self (Sorrow of Berserk), from the game designer.

  - activates when hero HP < 40%;
  - +20% strength, +10% max stamina (stamina is a resource), +5% crit chance, +10% crit damage, +5% attack speed;
  - each attack spends 0.5% max HP and deals 1.5% max HP;
  - per each 10% of HP below 40%: attack cost +0.5% max HP, damage +1.5% max HP,
    hp regen +20, lifesteal +5%, crit chance +5%, crit damage +10%, attack speed +10%;
  - if the cost is higher than current HP: HP := 1 and the Last Will shield (iframe) for 5 s;
  - every kill under Last Will extends the shield by 5 s;
  - the shield from "HP -> 1" can be obtained again only once per 30 s;
  - at exactly 1 HP EVERY Lost My Self bonus is x2 per missing 10% step
    (3 steps -> x8); the condition is the 1 HP itself, a shield is NOT required
    (any other iframe/shield works) - designer's decision.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.effect_schema.catalog import get_template  # noqa: E402
from tools.effect_schema.lua_parse import parse_lua  # noqa: E402
from tools.effect_schema.sim import EffectRuntime, Unit  # noqa: E402

LUA_ITEM = ROOT / "lua_content" / "items" / "sorrow_of_berserk.lua"

MAX_HP = 10000.0
BASE = {"strength": 100.0, "max_stamina": 100.0, "crit_chance": 10.0, "crit_dmg": 50.0,
        "aspd": 1.0, "lifesteal": 0.0, "hp_regen": 0.0}
EFFECTS = ("lost_my_self", "lost_my_self.attack")


def _effects(source):
    """Спека гоняется по двум источникам: каталог шаблонов (Python) и
    контент предмета в Lua (lua_content/items/sorrow_of_berserk.lua)."""
    if source == "lua":
        return parse_lua(LUA_ITEM.read_text(encoding="utf-8"))["effects"]
    return [get_template(t).to_json() for t in EFFECTS]


@pytest.fixture(params=["catalog", "lua"])
def make(request):
    effects = _effects(request.param)

    def factory(hp_pct, dummy_hp=1e9):
        hero = Unit("hero", max_hp=MAX_HP, **BASE)
        hero.current_hp = MAX_HP * hp_pct / 100.0
        dummy = Unit("dummy", max_hp=dummy_hp)
        rt = EffectRuntime(hero, effects, enemy=dummy)
        rt.refresh_passives()
        return rt
    return factory


def bonus(rt, stat):
    return rt.owner.mods.get(stat, 0.0)


@pytest.mark.parametrize("hp_pct", [100, 50, 40])
def test_inactive_at_or_above_40(make, hp_pct):
    rt = make(hp_pct)
    assert all(abs(v) < 1e-9 for v in rt.owner.mods.values()), rt.owner.mods


def test_base_bonuses_below_40_without_full_step(make):
    rt = make(35)  # 5% below the threshold: no 10% step yet
    assert bonus(rt, "strength") == pytest.approx(20.0)     # +20% of 100
    assert bonus(rt, "max_stamina") == pytest.approx(10.0)  # +10% of 100
    assert bonus(rt, "crit_chance") == pytest.approx(5.0)   # +5 points
    assert bonus(rt, "crit_dmg") == pytest.approx(10.0)     # +10 points
    assert bonus(rt, "aspd") == pytest.approx(0.05)         # +5% of 1.0
    assert bonus(rt, "hp_regen") == pytest.approx(0.0)
    assert bonus(rt, "lifesteal") == pytest.approx(0.0)


def test_per_10_percent_steps(make):
    rt = make(15)  # 25% below the threshold: 2 full steps
    assert bonus(rt, "crit_chance") == pytest.approx(5 + 2 * 5)
    assert bonus(rt, "crit_dmg") == pytest.approx(10 + 2 * 10)
    assert bonus(rt, "aspd") == pytest.approx(0.05 + 2 * 0.10)
    assert bonus(rt, "hp_regen") == pytest.approx(2 * 20)
    assert bonus(rt, "lifesteal") == pytest.approx(2 * 5)
    assert bonus(rt, "strength") == pytest.approx(20.0)  # no per-step growth


@pytest.mark.parametrize("hp_pct,cost,dmg", [(35, 50, 150), (25, 100, 300), (15, 150, 450), (5, 200, 600)])
def test_attack_cost_and_damage(make, hp_pct, cost, dmg):
    rt = make(hp_pct)
    hp0, enemy0 = rt.owner.current_hp, rt.enemy.current_hp
    rt.attack(0.0, base_damage=0.0)
    assert hp0 - rt.owner.current_hp == pytest.approx(cost)
    assert enemy0 - rt.enemy.current_hp == pytest.approx(dmg)


def test_last_will_sets_hp_to_1_and_shields_for_5s(make):
    rt = make(1)  # 100 HP, cost at 3 steps = 200 > 100
    rt.attack(0.0, base_damage=0.0)
    assert rt.owner.current_hp == pytest.approx(1.0)
    assert "last_will" in rt.owner.buffs
    assert rt.owner.buffs["last_will"]["until"] == pytest.approx(5.0)


def test_last_will_is_an_iframe(make):
    rt = make(1)
    rt.attack(0.0, base_damage=0.0)
    rt.receive_damage(5000.0, 1.0)
    assert rt.owner.alive and rt.owner.current_hp == pytest.approx(1.0)


def test_kill_under_last_will_extends_shield_by_5s(make):
    rt = make(1, dummy_hp=500.0)
    rt.attack(0.0, base_damage=0.0)      # shield until 5, dummy takes 600 -> killed
    assert rt.owner.kills == 1
    assert rt.owner.buffs["last_will"]["until"] == pytest.approx(10.0)


def test_shield_has_30s_cooldown(make):
    rt = make(1)
    rt.attack(0.0, base_damage=0.0)      # shield #1 at t=0 (until 5)
    rt.tick(6.0, 0.0)                    # shield expired
    rt.owner.current_hp = 100.0
    rt.attack(6.0, base_damage=0.0)      # cost > hp again, but cooldown
    assert "last_will" not in rt.owner.buffs
    rt.owner.current_hp = 100.0
    rt.tick(31.0, 0.0)
    rt.attack(31.0, base_damage=0.0)     # 31 s after the first shield: allowed
    assert "last_will" in rt.owner.buffs


def test_bonuses_amplified_x2_per_step_at_1_hp(make):
    rt = make(1)
    rt.attack(0.0, base_damage=0.0)   # HP -> 1 (+ shield); 39.99% below 40 -> 3 steps -> x8
    rt.refresh_passives(1.0)
    assert bonus(rt, "strength") == pytest.approx(20.0 * 8)
    assert bonus(rt, "crit_chance") == pytest.approx((5 + 3 * 5) * 8)
    assert bonus(rt, "hp_regen") == pytest.approx(3 * 20 * 8)
    assert bonus(rt, "lifesteal") == pytest.approx(3 * 5 * 8)


def test_amplification_needs_1_hp_not_the_shield(make):
    rt = make(1)
    rt.owner.current_hp = 1.0         # 1 HP from anything else, no Last Will shield
    rt.refresh_passives(0.0)
    assert "last_will" not in rt.owner.buffs
    assert bonus(rt, "strength") == pytest.approx(20.0 * 8)
    rt.attack(0.0, base_damage=0.0)   # shield granted: still 1 HP -> still x8
    rt.refresh_passives(6.0)          # shield expired, HP still 1 -> still x8
    assert bonus(rt, "strength") == pytest.approx(20.0 * 8)
    rt.owner.current_hp = 2.0         # above 1 HP: back to normal size (same 3 steps)
    rt.refresh_passives(7.0)
    assert bonus(rt, "strength") == pytest.approx(20.0)
    assert bonus(rt, "hp_regen") == pytest.approx(3 * 20)


def test_lua_item_matches_catalog():
    """lua_content/items/sorrow_of_berserk.lua сгенерирован из каталога
    (ui_logic.to_lua) - при правке шаблона Lua надо перегенерировать."""
    import json
    lua, cat = _effects("lua"), _effects("catalog")
    norm = lambda e: json.loads(json.dumps(e), parse_int=float)
    assert [norm(e) for e in lua] == [norm(e) for e in cat]
