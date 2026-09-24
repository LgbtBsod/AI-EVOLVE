"""Разум героя: сам замечает усиление на низком HP и учится, давить или отступать."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gameplay import hero_mind as hm  # noqa: E402
from src.effects.manager import HitInfo  # noqa: E402


class Hero:
    entity_id = "h"

    def __init__(self):
        self.health = self.max_health = 100.0
        self.physical_damage, self.attack_speed = 20.0, 1.0
        self.critical_chance, self.critical_damage, self.lifesteal = 0.1, 1.5, 0.0

    def is_alive(self):
        return self.health > 0


def episode(mind, hero, now, empowered, press_pays):
    """Один эпизод низкого HP; давить окупается (много урона, выжил) или убивает героя."""
    hero.health, hero.physical_damage = 100.0, 20.0
    mind.update(0.1, True, now)                               # база силы на полном HP
    hero.health = 25.0
    hero.physical_damage = 30.0 if empowered else 20.0
    mind.update(0.1, True, now + 0.1)
    stance = mind.stance
    if stance == "press" and not press_pays:
        hero.health = 0.0
        mind.note_hit(HitInfo("boss", "h", 25.0, killed=True), "h")
    else:
        mind.note_hit(HitInfo("h", "boss", 80.0 if stance == "press" else 5.0), "h")
        hero.health = 70.0
        mind.update(0.1, True, now + 1.0)
    return stance


def test_mind_notices_empowerment_and_learns_both_lessons(tmp_path):
    hero = Hero()
    mind = hm.HeroMind(hero, tmp_path / "mind.json", backend="python")
    now = 0.0
    for i in range(40):
        empowered = i % 2 == 0
        episode(mind, hero, now, empowered, press_pays=empowered)   # берсерк работает только усиленным
        now += 10.0
    assert mind.preferred("empowered") == "press"
    assert mind.preferred("plain") == "retreat"
    mind.save()
    again = hm.HeroMind(Hero(), tmp_path / "mind.json", backend="python")
    assert again.lessons() == mind.lessons() and again.episodes == 40


def test_press_stance_keeps_fighting_and_saves_potions_for_the_edge():
    class Brain:
        heal_at = 0.35
    hero, brain = Hero(), Brain()
    mind = hm.HeroMind(hero, None, backend="python", inventory_brain=brain)
    hero.health = 20.0
    assert mind.should_retreat()                               # без решения - осторожность
    mind._set_stance("press")
    assert not mind.should_retreat() and brain.heal_at == hm.HEAL_AT["press"]
