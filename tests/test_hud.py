"""Панели HUD (src/ui/hud.py): чистые функции сбора данных - инвентарь, навыки/откаты, полные статы.

Само создание DirectGui-виджетов (create_hud/update_hud) требует запущенного Panda3D ShowBase
(окно/дисплей), которого нет в этом окружении - тестируются только функции, которые они вызывают.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects.abilities import load_abilities  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from src.gameplay.inventory import Inventory  # noqa: E402
from src.gameplay.items import catalog  # noqa: E402
from src.ui.hud import cooldowns_remaining, inventory_summary_lines, skills_summary_lines, stats_summary_lines  # noqa: E402


class Fighter:
    _n = 0

    def __init__(self):
        Fighter._n += 1
        self.entity_id = f"h{Fighter._n}"
        self.x, self.y = 0.0, 0.0
        self.health = self.max_health = 100.0
        self.mana = self.max_mana = 100.0
        self.stamina = self.max_stamina = 100.0
        self.health_regen = self.mana_regen = self.stamina_regen = 0.0
        self.physical_damage, self.magical_damage = 20.0, 30.0
        self.defense, self.attack_speed = 0.0, 1.0
        self.critical_chance, self.critical_damage, self.dodge_chance = 0.05, 1.5, 0.0
        self.speed = 5.0
        self.level = 1

    def is_alive(self):
        return self.health > 0


class World:
    def entities(self):
        return []


@pytest.fixture
def player():
    mgr = EffectManager(world=World(), abilities=load_abilities())
    hero = Fighter()
    mgr.register(hero, "hero")
    return mgr, hero


def test_inventory_summary_lines_empty_without_inventory():
    class NoInv:
        pass

    assert inventory_summary_lines(NoInv()) == []


def test_inventory_summary_lines_shape(player):
    _mgr, hero = player
    cat = catalog()
    hero.inventory = inv = Inventory(owner=hero, gold=42)
    item = next(iter(cat.items.values()))
    inv.add(item)
    lines = inventory_summary_lines(hero)
    assert any("42" in line for line in lines)
    assert any(item.name in line for line in lines)


def test_cooldowns_remaining_only_pending(player):
    mgr, hero = player
    st = hero.effect_state
    st.cooldowns["weapon_attack"] = mgr.now + 3.0
    st.cooldowns["ready_already"] = mgr.now - 1.0
    remaining = cooldowns_remaining(st, mgr.now)
    assert remaining == {"weapon_attack": 3.0}


def test_skills_summary_lines_lists_spells_and_cooldowns(player):
    mgr, hero = player
    st = hero.effect_state
    st.spells.append("fireball")
    st.cooldowns["fireball"] = mgr.now + 2.5
    lines = skills_summary_lines(hero, mgr.now)
    assert any("fireball" in line for line in lines)
    assert any("2.5" in line for line in lines)


def test_skills_summary_lines_empty_without_effect_state():
    class NoState:
        pass

    assert skills_summary_lines(NoState(), 0.0) == []


def test_stats_summary_lines_has_defense_and_move_speed(player):
    _mgr, hero = player
    lines = stats_summary_lines(hero)
    assert any(line.startswith("defense:") for line in lines)
    assert any(line.startswith("move_speed:") for line in lines)
