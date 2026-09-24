"""Мир из 80 уровней, прогрессия героя и врагов, перки характеристик."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects.abilities import load_abilities, load_bosses  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from src.gameplay import progression as prog  # noqa: E402
from src.gameplay.world import world_plan  # noqa: E402
from tests.test_effect_manager import FakeRng, Fighter  # noqa: E402


def test_world_has_80_levels_in_8_acts_with_bosses():
    plan = world_plan()
    assert plan.max_level == 80 and len(plan.acts) == 8
    assert [plan.act_for(lvl)["id"] for lvl in (1, 11, 21, 31, 41, 51, 61, 71)] == \
        ["midgard", "jotunheim", "svartalfheim", "vanaheim", "helheim", "limbo", "dis", "muspelheim"]
    for act in plan.acts:
        lo, hi = act["levels"]
        assert plan.info(hi).boss == act["boss"] and plan.info(lo + 4).boss_role == "miniboss"
        for enemy in act["enemies"] + act["elites"]:
            assert enemy in plan.bestiary, enemy
    info = plan.info(80)
    assert info.is_final and "Коцит" in info.name
    assert plan.final_sequence(80) == ["lucifer", "grey_cardinal", "knot_treasurer", "faceless_architect"]
    assert plan.info(76).name.endswith("Каина")


def test_bosses_have_10_to_20_skills_and_every_skill_is_an_ability():
    abilities = load_abilities()
    for boss in load_bosses().values():
        n = len(boss["skills"])
        assert (6 if boss["role"] == "miniboss" else 10) <= n <= 20, (boss["id"], n)
        assert all(s in abilities for s in boss["skills"])
    assert len(load_bosses()["lucifer"]["skills"]) == 20


def test_attribute_points_per_level():
    normal = prog.enemy_attributes("normal", 11, {"strength": 0.5, "vitality": 0.5})
    elite = prog.enemy_attributes("elite", 11, {"strength": 1.0})
    boss = prog.enemy_attributes("boss", 11, {})
    assert sum(normal.values()) == 100 and normal["strength"] == normal["vitality"] == 50
    assert sum(elite.values()) == 150
    assert boss["strength"] == boss["luck"] == 100                     # +10 к каждой за уровень


def test_enemy_level_grows_with_cycles_and_session_time():
    assert prog.enemy_level(5) == 5
    assert prog.enemy_level(5, cycle=2) == 5 + 40
    assert prog.enemy_level(5, session_seconds=11 * 60) == 7         # +1 за каждые 5 минут


def test_hero_spends_5_points_per_level_and_learns_from_close_calls():
    class Hero:
        attributes, attribute_points = {}, 10
    growth = prog.HeroGrowth("warrior")
    spent = growth.spend(Hero)
    assert sum(spent.values()) == 10 and Hero.attribute_points == 0
    assert Hero.attributes["strength"] >= Hero.attributes["endurance"]
    for _ in range(8):
        growth.note_close_call()
    Hero.attribute_points = 20
    spent = growth.spend(Hero)
    assert spent["vitality"] > spent.get("endurance", 0)             # раны -> живучесть


def test_xp_only_from_activities():
    assert prog.xp_for("chest") == 50 and prog.xp_for("trick_dodge") > 0 and prog.xp_for("idle") == 0


def test_attributes_drive_stats_and_unlock_perks():
    mgr = EffectManager(abilities=load_abilities(), rng=FakeRng(0.99))
    hero, enemy = Fighter(atk=20.0), Fighter(x=1.0, hp=500.0)
    hero.attributes = {"strength": 20, "vitality": 10, "endurance": 15, "agility": 15}
    mgr.register(hero, "hero")
    mgr.register(enemy, "monsters")
    assert hero.physical_damage == pytest.approx(20 + 20 * 0.6)     # сила -> урон
    assert hero.max_health == pytest.approx(100 + 20 * 1 + 10 * 6)  # сила и живучесть -> HP
    perks = prog.perk_effects(hero.attributes)
    names = {p["meta"]["name"] for p in perks}
    assert {"Прилив силы", "Стрейф", "Лёгкий шаг"} <= names and "Второй удар" not in names
    base_speed = hero.speed
    mgr.set_perks(hero, perks)
    mgr.update(0.1)                                                  # давно не били -> Лёгкий шаг
    assert hero.speed == pytest.approx(base_speed * 1.25)
    x0 = (hero.x, hero.y)
    mgr.cast(enemy, "weapon_attack", hero)                           # удар -> стрейф в сторону + уклонение
    assert (hero.x, hero.y) != x0
    assert any(src.startswith("perk.strafe") for _who, src, _i in mgr.state(hero).external)
    mgr.update(0.1)
    assert hero.speed == pytest.approx(base_speed)                   # только что били - без бонуса


def test_level_up_gives_points_not_hidden_stats():
    from src.entities.character import Character

    class Game:
        render = None
    hero = Character("t", Game(), is_player=True)
    hp = hero.max_health
    hero.add_experience(hero.experience_to_next_level)
    assert hero.level == 2 and hero.attribute_points == 5 and hero.max_health == hp
