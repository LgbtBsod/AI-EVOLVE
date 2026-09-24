"""Tests for Inventory Plugin."""

import pytest
from unittest.mock import MagicMock, patch

from ai_evolve.features.inventory.inventory_plugin import InventoryPlugin, Item, InventorySlot
from ai_evolve.core.event_system import EventSystem
from ai_evolve.db.database_core import DatabaseCore


class TestInventoryPlugin:
    """Тесты плагина инвентаря."""
    
    def test_plugin_initialization(self):
        """Тест инициализации плагина."""
        plugin = InventoryPlugin()
        
        assert plugin.name == "InventoryPlugin"
        assert "DatabaseCore" in plugin.dependencies
    
    def test_add_item_new_slot(self):
        """Тест добавления предмета в новый слот."""
        plugin = InventoryPlugin()
        entity_id = 1
        
        item_data = {
            "id": 1,
            "name": "Health Potion",
            "type": "consumable",
            "max_stack": 99
        }
        
        result = plugin.add_item(entity_id, item_data, quantity=5)
        
        assert result is True
        inventory = plugin.get_inventory(entity_id)
        assert len(inventory) == 1
        assert inventory[0]["quantity"] == 5
    
    def test_add_item_stacking(self):
        """Тест стакания предметов."""
        plugin = InventoryPlugin()
        entity_id = 1
        
        item_data = {
            "id": 1,
            "name": "Health Potion",
            "type": "consumable",
            "max_stack": 99
        }
        
        plugin.add_item(entity_id, item_data, quantity=10)
        plugin.add_item(entity_id, item_data, quantity=20)
        
        inventory = plugin.get_inventory(entity_id)
        assert len(inventory) == 1
        assert inventory[0]["quantity"] == 30
    
    def test_add_item_new_slot_on_stack_full(self):
        """Тест создания нового слота при полном стаке."""
        plugin = InventoryPlugin()
        entity_id = 1
        
        item_data = {
            "id": 1,
            "name": "Health Potion",
            "type": "consumable",
            "max_stack": 20
        }
        
        plugin.add_item(entity_id, item_data, quantity=25)
        
        inventory = plugin.get_inventory(entity_id)
        assert len(inventory) == 2
        assert inventory[0]["quantity"] == 20
        assert inventory[1]["quantity"] == 5
    
    def test_remove_item_at_slot(self):
        """Тест удаления предмета из слота."""
        plugin = InventoryPlugin()
        entity_id = 1
        
        item_data = {"id": 1, "name": "Sword", "type": "weapon"}
        plugin.add_item(entity_id, item_data)
        
        removed = plugin.remove_item_at_slot(entity_id, 0)
        
        assert removed is not None
        assert removed["name"] == "Sword"
        assert len(plugin.get_inventory(entity_id)) == 0
    
    def test_has_item_true(self):
        """Тест проверки наличия предмета (успех)."""
        plugin = InventoryPlugin()
        entity_id = 1
        
        item_data = {"id": 42, "name": "Key", "type": "quest"}
        plugin.add_item(entity_id, item_data, quantity=3)
        
        assert plugin.has_item(entity_id, 42, quantity=2) is True
    
    def test_has_item_false(self):
        """Тест проверки наличия предмета (неудача)."""
        plugin = InventoryPlugin()
        entity_id = 1
        
        item_data = {"id": 42, "name": "Key", "type": "quest"}
        plugin.add_item(entity_id, item_data, quantity=1)
        
        assert plugin.has_item(entity_id, 42, quantity=5) is False
    
    def test_clear_inventory(self):
        """Тест очистки инвентаря."""
        plugin = InventoryPlugin()
        entity_id = 1
        
        plugin.add_item(entity_id, {"id": 1, "name": "Item1"})
        plugin.add_item(entity_id, {"id": 2, "name": "Item2"})
        
        plugin.clear_inventory(entity_id)
        
        assert len(plugin.get_inventory(entity_id)) == 0
    
    def test_get_inventory_size(self):
        """Тест получения размера инвентаря."""
        plugin = InventoryPlugin()
        entity_id = 1
        
        plugin.add_item(entity_id, {"id": 1})
        plugin.add_item(entity_id, {"id": 2})
        plugin.add_item(entity_id, {"id": 3})
        
        assert plugin.get_inventory_size(entity_id) == 3
    
    def test_empty_entity_inventory(self):
        """Тест пустого инвентаря несуществующей сущности."""
        plugin = InventoryPlugin()
        
        inventory = plugin.get_inventory(999)
        assert inventory == {}
    
    def test_plugin_lifecycle(self):
        """Тест жизненного цикла плагина."""
        # Сбрасываем синглтон EventSystem
        EventSystem.reset_instance()
        
        plugin = InventoryPlugin()
        game_core = MagicMock()
        db_core = MagicMock()
        game_core.get_plugin.return_value = db_core
        
        # Инициализация
        result = plugin.on_init(game_core)
        assert result is True
        
        # Обновление (пустое)
        plugin.on_update(0.016)
        
        # Завершение
        plugin.on_shutdown()
