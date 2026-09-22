"""
Тесты для LootPlugin - системы генерации лута, сундуков и мимиков.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/workspace')

from ai_evolve.plugins.loot_plugin import (
    LootPlugin, LootGenerator, Item, Chest, 
    Rarity, ItemType, ItemStats
)
from ai_evolve.core.event_system import EventSystem


class TestItemStats:
    """Тесты для ItemStats."""
    
    def test_create_default_stats(self):
        stats = ItemStats()
        assert stats.damage == 0
        assert stats.armor == 0
        assert stats.crit_chance == 0.0
        assert stats.effects == []
    
    def test_to_dict(self):
        stats = ItemStats(damage=50, armor=30, crit_chance=0.25)
        data = stats.to_dict()
        
        assert data["damage"] == 50
        assert data["armor"] == 30
        assert data["crit_chance"] == 0.25
    
    def test_from_dict(self):
        data = {
            "damage": 100,
            "armor": 50,
            "health_bonus": 200,
            "crit_chance": 0.3,
            "effects": [{"type": "burn", "duration": 3.0}]
        }
        stats = ItemStats.from_dict(data)
        
        assert stats.damage == 100
        assert stats.armor == 50
        assert stats.health_bonus == 200
        assert stats.crit_chance == 0.3
        assert len(stats.effects) == 1


class TestItem:
    """Тесты для Item."""
    
    def test_create_item(self):
        stats = ItemStats(damage=50)
        item = Item(
            id="item_1",
            session_id="session_1",
            name="Меч",
            item_type=ItemType.WEAPON,
            rarity=Rarity.RARE,
            prefix="Легендарный",
            base="Меч",
            suffix="Огненной смерти",
            stats=stats
        )
        
        assert item.get_full_name() == "Легендарный Меч Огненной смерти"
        assert item.item_type == ItemType.WEAPON
        assert item.rarity == Rarity.RARE
    
    def test_get_quality_multiplier(self):
        common = Item(id="1", session_id="s", name="Test", item_type=ItemType.WEAPON, rarity=Rarity.COMMON)
        rare = Item(id="2", session_id="s", name="Test", item_type=ItemType.WEAPON, rarity=Rarity.RARE)
        epic = Item(id="3", session_id="s", name="Test", item_type=ItemType.WEAPON, rarity=Rarity.EPIC)
        legendary = Item(id="4", session_id="s", name="Test", item_type=ItemType.WEAPON, rarity=Rarity.LEGENDARY)
        
        assert common.get_quality_multiplier() == 1.0
        assert rare.get_quality_multiplier() == 2.5
        assert epic.get_quality_multiplier() == 5.0
        assert legendary.get_quality_multiplier() == 10.0
    
    def test_item_serialization(self):
        stats = ItemStats(damage=50)
        item = Item(
            id="item_1",
            session_id="session_1",
            name="Test Sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.RARE,
            stats=stats,
            value=100
        )
        
        # Сериализация
        data = item.to_dict()
        assert data["id"] == "item_1"
        assert data["session_id"] == "session_1"
        assert data["rarity"] == "rare"
        
        # Десериализация
        restored = Item.from_dict(data)
        assert restored.id == item.id
        assert restored.stats.damage == 50


class TestChest:
    """Тесты для Chest."""
    
    def test_create_chest(self):
        chest = Chest(
            id="chest_1",
            session_id="session_1",
            x=10.0, y=20.0, z=0.0
        )
        
        assert chest.id == "chest_1"
        assert not chest.is_mimic
        assert not chest.opened
        assert chest.loot_table == []
    
    def test_open_chest(self):
        chest = Chest(id="c1", session_id="s1", x=0, y=0, z=0)
        item = Item(id="i1", session_id="s1", name="Gold", item_type=ItemType.CONSUMABLE, rarity=Rarity.COMMON)
        chest.loot_table = [item]
        
        loot = chest.open()
        
        assert len(loot) == 1
        assert chest.opened
        assert chest.open() == []  # Повторное открытие не даёт лут


class TestLootGenerator:
    """Тесты для LootGenerator."""
    
    def test_create_generator(self):
        gen = LootGenerator("session_1", seed=42)
        assert gen.session_id == "session_1"
        assert gen.generated_items == {}
    
    def test_generate_common_item(self):
        gen = LootGenerator("session_1", seed=42)
        item = gen.generate_item(ItemType.WEAPON, Rarity.COMMON, level=1)
        
        assert item.item_type == ItemType.WEAPON
        assert item.rarity == Rarity.COMMON
        assert item.session_id == "session_1"
        # У обычных предметов нет префикса/суффикса
        assert item.prefix is None or item.suffix is None
    
    def test_generate_legendary_item(self):
        gen = LootGenerator("session_1", seed=42)
        item = gen.generate_item(ItemType.WEAPON, Rarity.LEGENDARY, level=10)
        
        assert item.rarity == Rarity.LEGENDARY
        assert item.prefix is not None  # У легендарок есть префикс
        assert item.post_suffix is not None  # И пост-суффикс
        assert len(item.stats.effects) >= 1  # И эффекты
    
    def test_generate_stats_scaling(self):
        gen = LootGenerator("session_1", seed=42)
        
        item_level_1 = gen.generate_item(ItemType.WEAPON, Rarity.COMMON, level=1)
        item_level_10 = gen.generate_item(ItemType.WEAPON, Rarity.COMMON, level=10)
        
        # Предметы высокого уровня должны быть сильнее
        assert item_level_10.stats.damage > item_level_1.stats.damage
    
    def test_generate_chest_loot(self):
        gen = LootGenerator("session_1", seed=42)
        loot = gen.generate_chest_loot(chest_level=5, is_mimic=False)
        
        assert len(loot) >= 2
        assert all(item.session_id == "session_1" for item in loot)
    
    def test_mimic_loot_quantity(self):
        gen = LootGenerator("session_1", seed=42)
        
        normal_loot = gen.generate_chest_loot(chest_level=5, is_mimic=False)
        mimic_loot = gen.generate_chest_loot(chest_level=5, is_mimic=True)
        
        # Мимики дают больше предметов
        assert len(mimic_loot) > len(normal_loot)
    
    def test_item_caching(self):
        gen = LootGenerator("session_1", seed=42)
        item = gen.generate_item(ItemType.WEAPON, Rarity.RARE, level=5)
        
        assert item.id in gen.generated_items
        assert gen.generated_items[item.id] == item


class TestLootPlugin:
    """Тесты для LootPlugin."""
    
    @pytest.fixture
    def plugin(self):
        """Создание плагина."""
        # Сброс синглтона EventSystem
        EventSystem.reset_instance()
        
        plugin = LootPlugin()
        return plugin
    
    @pytest.fixture
    def mock_game_core(self):
        """Моковый GameCore."""
        core = Mock()
        return core
    
    def test_plugin_initialization(self, plugin, mock_game_core):
        config = {"session_id": "test_session", "seed": 42}
        
        result = plugin.initialize(config, mock_game_core)
        
        assert result is True
        assert plugin.generator is not None
        assert plugin.generator.session_id == "test_session"
    
    def test_create_chest(self, plugin, mock_game_core):
        config = {"session_id": "test_session", "seed": 42}
        plugin.initialize(config, mock_game_core)
        
        chest = plugin.create_chest(x=10.0, y=20.0, z=0.0, level=5)
        
        assert chest is not None
        assert chest.x == 10.0
        assert chest.y == 20.0
        assert len(chest.loot_table) > 0
        assert chest.id in plugin.chests
    
    def test_create_mimic_chest(self, plugin, mock_game_core):
        config = {"session_id": "test_session", "seed": 42}
        plugin.initialize(config, mock_game_core)
        
        chest = plugin.create_chest(x=0, y=0, z=0, level=10, force_mimic=True)
        
        assert chest.is_mimic
        assert len(chest.loot_table) >= 5  # Мимики дают больше лута
    
    def test_open_chest_event(self, plugin, mock_game_core):
        config = {"session_id": "test_session", "seed": 42}
        plugin.initialize(config, mock_game_core)
        
        # Создаём сундук
        chest = plugin.create_chest(x=0, y=0, z=0, level=5)
        
        # Открываем через событие
        plugin._on_chest_open({
            "chest_id": chest.id,
            "player_id": "player_1",
            "player_level": 5
        })
        
        # Лут должен добавиться в инвентарь
        assert chest.session_id in plugin.player_inventory
        assert len(plugin.player_inventory[chest.session_id]) > 0
    
    def test_session_cleanup(self, plugin, mock_game_core):
        config = {"session_id": "test_session", "seed": 42}
        plugin.initialize(config, mock_game_core)
        
        # Создаём сундук
        chest = plugin.create_chest(x=0, y=0, z=0)
        
        # Завершаем сессию
        plugin._on_session_end({"session_id": "test_session"})
        
        # Сундук должен удалиться
        assert chest.id not in plugin.chests
        assert "test_session" not in plugin.player_inventory
    
    def test_shutdown(self, plugin, mock_game_core):
        config = {"session_id": "test_session"}
        plugin.initialize(config, mock_game_core)
        
        plugin.create_chest(x=0, y=0, z=0)
        
        plugin.shutdown()
        
        assert plugin.chests == {}
        assert plugin.player_inventory == {}
        assert plugin.generator is None


class TestLootIntegration:
    """Интеграционные тесты для системы лута."""
    
    def test_full_loot_cycle(self):
        """Полный цикл: создание сессии -> сундук -> открытие -> получение лута."""
        EventSystem.reset_instance()
        
        plugin = LootPlugin()
        config = {"session_id": "integration_test", "seed": 123}
        
        # Инициализация
        assert plugin.initialize(config, Mock())
        
        # Создание сундука
        chest = plugin.create_chest(x=50, y=50, z=0, level=10)
        assert chest is not None
        
        # Открытие
        plugin._on_chest_open({
            "chest_id": chest.id,
            "player_id": "hero",
            "player_level": 10
        })
        
        # Проверка получения лута
        assert chest.session_id in plugin.player_inventory
        loot = plugin.player_inventory[chest.session_id]
        assert len(loot) > 0
        
        # Завершение сессии
        plugin._on_session_end({"session_id": "integration_test"})
        
        # Очистка
        assert "integration_test" not in plugin.player_inventory
        
        plugin.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
