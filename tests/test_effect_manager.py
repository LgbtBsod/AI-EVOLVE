"""Единый менеджер эффектов (src/effects/manager.py) и инвентарь на фейковых сущностях.

Удар оружием, навыки, зелья и эффекты предметов идут одним конвейером -
тесты проверяют конвейер без Panda3D.
"""
import math
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects.abilities import load_abilities  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from src.gameplay.inventory import Inventory, InventoryBrain  # noqa: E402
from src.gameplay.items import catalog  # noqa: E402


class FakeRng:
    """Без критов и уклонений (0.99), или с ними (0.0)."""

    def __init__(self, value=0.99):
        self.value = value

    def random(self):
        return self.value


class Fighter:
    _n = 0

    def __init__(self, x=0.0, y=0.0, hp=100.0, atk=20.0, defense=0.0, aspd=1.0, crit=0.05, dodge=0.0):
        Fighter._n += 1
        self.entity_id = f"f{Fighter._n}"
        self.x, self.y = x, y
        self.health = self.max_health = hp
        self.mana = self.max_mana = 100.0
        self.stamina = self.max_stamina = 100.0
        self.health_regen = self.mana_regen = self.stamina_regen = 0.0
        self.physical_damage, self.magical_damage = atk, 30.0
        self.defense, self.attack_speed = defense, aspd
        self.critical_chance, self.critical_damage, self.dodge_chance = crit, 1.5, dodge
        self.speed = 5.0
        self.level = 1

    def is_alive(self):
        return self.health > 0


class World:
    def __init__(self):
        self.summons = []

    def entities(self):
        return []

    def spawn_summon(self, kind, x, y, faction, level, owner):
        self.summons.append((kind, faction))


@pytest.fixture
def setup():
    def make(rng=0.99, **hero_kw):
        mgr = EffectManager(world=World(), abilities=load_abilities(), rng=FakeRng(rng))
        hero = Fighter(**hero_kw)
        enemy = Fighter(x=1.0, hp=200.0, atk=10.0)
        mgr.register(hero, "hero")
        mgr.register(enemy, "monsters")
        return mgr, hero, enemy
    return make


def items(*ids):
    cat = catalog()
    return [cat.get(i) for i in ids]


def test_weapon_attack_is_an_ability_with_cooldown_from_attack_speed(setup):
    mgr, hero, enemy = setup(atk=25.0, aspd=2.0)
    enemy.defense = 5.0
    r = mgr.cast(hero, "weapon_attack", enemy)
    assert r.ok and enemy.health == pytest.approx(200 - 20)
    assert mgr.cast(hero, "weapon_attack", enemy).reason == "cooldown"
    mgr.update(0.5)                                   # 1 / aspd = 0.5 s
    assert mgr.cast(hero, "weapon_attack", enemy).ok
    enemy.x = 10.0
    mgr.update(1.0)
    assert mgr.cast(hero, "weapon_attack", enemy).reason == "out of range"


def test_crit_dodge_and_hit_notifications(setup):
    mgr, hero, enemy = setup(rng=0.0, atk=20.0)       # всегда крит ... и всегда уклонение цели
    seen = []
    mgr.register_event_handler(seen.append)
    enemy.dodge_chance = 0.5
    mgr.cast(hero, "weapon_attack", enemy)
    assert seen[-1].is_dodged and enemy.health == 200
    enemy.dodge_chance = 0.0
    mgr.update(1.0)
    mgr.cast(hero, "weapon_attack", enemy)
    assert seen[-1].is_critical and enemy.health == pytest.approx(200 - 30)


def test_equipment_stats_and_on_hit_effect(setup):
    mgr, hero, enemy = setup(atk=20.0)
    mgr.equip(hero, items("vampire_fang"))
    assert hero.physical_damage == pytest.approx(26.0)            # +6 от клинка
    hero.health = 50.0
    mgr.cast(hero, "weapon_attack", enemy)
    assert enemy.health == pytest.approx(200 - 26)
    assert hero.health == pytest.approx(50 + 26 * 0.12)           # 12% урона - лечение
    mgr.equip(hero, [])
    assert hero.physical_damage == pytest.approx(20.0)            # снял - бонус ушёл


def test_potion_goes_through_the_same_pipeline(setup):
    mgr, hero, _enemy = setup(hp=200.0)
    hero.health = 50.0
    assert mgr.use_item(hero, catalog().get("health_potion"))
    assert hero.health == pytest.approx(50 + 0.35 * 200)


def test_lost_my_self_blood_price_and_last_will(setup):
    mgr, hero, enemy = setup(hp=1000.0, atk=20.0)
    mgr.equip(hero, items("sorrow_of_berserk"))
    hero.health = 100.0                                            # 10% HP: 3 шага ниже 40%
    mgr.update(0.2)
    assert hero.max_stamina == pytest.approx(110.0)                # +10% максимальной стамины
    mgr.cast(hero, "weapon_attack", enemy)
    # цена крови 0.5% + 3 x 0.5% = 20 HP; лайфстил Lost My Self 3 x 5 = 15% от 20 урона = +3
    assert hero.health == pytest.approx(100 - 1000 * 0.02 + 20 * 0.15)
    hero.health = 5.0                                              # цена выше HP -> 1 HP + щит
    mgr.update(1.5)
    mgr.cast(hero, "weapon_attack", enemy)
    assert hero.health == pytest.approx(1.0)
    before = hero.health
    mgr.cast(enemy, "weapon_attack", hero)
    assert hero.health == before                                   # iframe: урон не прошёл
    assert "last_will" in mgr.describe(hero)["buffs"]


def test_thorns_on_both_sides_do_not_loop(setup):
    mgr, hero, enemy = setup(atk=20.0)
    mgr.equip(hero, items("mantle_of_thorns"))
    mgr.equip(enemy, items("mantle_of_thorns"))
    mgr.cast(hero, "weapon_attack", enemy)
    assert enemy.health > 0 and hero.health < hero.max_health       # шипы вернули урон один раз


def test_poison_ticks_over_time(setup):
    mgr, hero, enemy = setup(atk=10.0)
    hero.x, enemy.x = 0.0, 1.5
    mgr.cast(hero, "stealth_strike", enemy)
    after_hit = enemy.health
    for _ in range(10):
        mgr.update(0.5)
    assert enemy.health == pytest.approx(after_hit - 5 * 4)        # 4 урона x 5 тиков


def test_area_is_friendly_fire_and_summon_uses_world(setup):
    mgr, hero, enemy = setup(atk=20.0)
    ally = Fighter(x=0.5)
    far = Fighter(x=30.0)
    enemy2 = Fighter(x=-1.0, hp=200.0)
    mgr.register(ally, "hero")
    mgr.register(far, "monsters")
    mgr.register(enemy2, "monsters")
    assert mgr.cast(hero, "cleave", enemy).ok                      # affects = others: всех, кроме себя
    assert enemy.health < 200 and enemy2.health < 200 and far.health == 100
    assert ally.health < 100 and hero.health == 100                # по-честному: свой тоже получил
    assert set(mgr.area_preview(hero, "fireball", enemy)) == {hero, ally, enemy, enemy2}
    mgr.cast(hero, "fireball", enemy)                              # огненный шар под ноги - и себе
    assert hero.health < 100
    mgr.cast(hero, {"id": "raise", "ops": [{"kind": "summon", "target": "self", "summon": "skeleton", "count": 2}]})
    assert mgr.world.summons == [("skeleton", "hero"), ("skeleton", "hero")]


def test_execute_revive_and_timed_debuff(setup):
    mgr, hero, enemy = setup(atk=20.0)
    mgr.equip(hero, items("executioner_axe", "venom_dagger")[:1])
    enemy.health = 20.0                                            # 10% < 12%: казнь на событии attack
    r = mgr.cast(hero, "weapon_attack", enemy)
    assert r.ok and enemy.health == 0 and hero.kills == 1
    mgr2, hero2, enemy2 = setup(atk=500.0)
    mgr2.equip(enemy2, items("phoenix_feather"))
    mgr2.cast(hero2, "weapon_attack", enemy2)
    assert enemy2.is_alive() and enemy2.health == pytest.approx(0.3 * 200)   # перо феникса
    mgr3, hero3, enemy3 = setup(atk=20.0)
    mgr3.equip(hero3, items("venom_dagger"))
    enemy3.defense = 4.0
    mgr3.cast(hero3, "weapon_attack", enemy3)
    assert enemy3.defense == pytest.approx(2.0)                   # -2 брони на 5 с
    for _ in range(12):
        mgr3.update(0.5)
    assert enemy3.defense == pytest.approx(4.0)


def test_inventory_brain_drinks_equips_and_reads_maps(setup):
    mgr, hero, _enemy = setup(hp=100.0)
    inv = Inventory(hero, on_change=lambda inv: mgr.equip(hero, inv.equipped.values()))
    cat = catalog()
    for item_id in ("health_potion", "iron_sword", "rusty_sword", "exit_map"):
        inv.add(cat.get(item_id))
    learned = []
    brain = InventoryBrain(inv, role="warrior")
    actions = [brain.update(0.1, lambda it: mgr.use_item(hero, it), learned.append) for _ in range(4)]
    assert "read:exit_map" in actions and learned[0].id == "exit_map"
    assert inv.equipped["weapon"].id == "iron_sword" and hero.physical_damage == pytest.approx(28.0)
    hero.health = 20.0
    assert brain.update(0.1, lambda it: mgr.use_item(hero, it)) == "potion:hp"
    assert hero.health == pytest.approx(55.0) and inv.count("health_potion") == 0


def test_every_game_item_and_ability_is_valid():
    from tools.effect_schema.validate import validate_item
    for item in catalog().items.values():
        assert validate_item({"effects": list(item.effects)}) == [], item.id
    for ab in load_abilities().values():
        assert validate_item({"effects": [{"id": ab["id"], "trigger": {"kind": "event", "event": "cast"},
                                            "ops": ab["ops"]}]}) == [], ab["id"]
