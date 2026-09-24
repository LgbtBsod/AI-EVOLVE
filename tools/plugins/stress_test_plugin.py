"""
Stress Test Content Generator Plugin для Dev Probe
Генерирует тестовый контент для нагрузочного тестирования
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
import random
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class StressTestConfig:
    entity_count: int = 100
    item_count: int = 50
    event_count: int = 20
    npc_count: int = 30
    duration_seconds: int = 60


class StressTestContentGenerator:
    """
    Плагин для генерации большого количества тестового контента
    Для проверки производительности и стабильности
    """
    
    def __init__(self, probe_instance=None):
        self.probe = probe_instance
        self._generated_entities = []
        self._generated_items = []
        self._generated_events = []
        self._test_metrics = {
            "entities_spawned": 0,
            "items_created": 0,
            "events_triggered": 0,
            "generation_time_ms": 0
        }
        
    def generate_stress_test(self, config: StressTestConfig) -> Dict:
        """Сгенерировать полный набор тестового контента"""
        start_time = time.time()
        
        logger.info(f"Starting stress test generation: {config}")
        
        # Генерация сущностей
        entities = self._generate_entities(config.entity_count)
        
        # Генерация предметов
        items = self._generate_items(config.item_count)
        
        # Генерация событий
        events = self._generate_events(config.event_count)
        
        # Генерация NPC
        npcs = self._generate_npcs(config.npc_count)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        self._test_metrics = {
            "entities_spawned": len(entities),
            "items_created": len(items),
            "events_triggered": len(events),
            "npcs_spawned": len(npcs),
            "total_objects": len(entities) + len(items) + len(npcs),
            "generation_time_ms": elapsed_ms,
            "objects_per_second": (len(entities) + len(items) + len(npcs)) / (elapsed_ms / 1000) if elapsed_ms > 0 else 0
        }
        
        logger.info(f"Stress test generated: {self._test_metrics}")
        
        return {
            "config": config,
            "entities": entities,
            "items": items,
            "events": events,
            "npcs": npcs,
            "metrics": self._test_metrics
        }
    
    def _generate_entities(self, count: int) -> List[Dict]:
        """Сгенерировать множество сущностей"""
        entity_types = ["enemy", "ally", "neutral", "boss", "minion"]
        states = ["idle", "patrol", "combat", "fleeing", "dead"]
        
        entities = []
        for i in range(count):
            entity = {
                "id": f"stress_entity_{i}",
                "type": random.choice(entity_types),
                "x": random.randint(0, 1000),
                "y": random.randint(0, 1000),
                "hp": random.randint(10, 1000),
                "max_hp": random.randint(100, 1000),
                "damage": random.randint(5, 100),
                "state": random.choice(states),
                "level": random.randint(1, 50),
                "metadata": {
                    "stress_test": True,
                    "batch_id": i // 10
                }
            }
            entities.append(entity)
        
        self._generated_entities = entities
        return entities
    
    def _generate_items(self, count: int) -> List[Dict]:
        """Сгенерировать множество предметов"""
        rarities = ["common", "uncommon", "rare", "epic", "legendary"]
        item_types = ["weapon", "armor", "potion", "material", "quest"]
        
        items = []
        for i in range(count):
            rarity = random.choices(
                rarities, 
                weights=[50, 30, 15, 4, 1]
            )[0]
            
            item = {
                "id": f"stress_item_{i}",
                "name": f"Item_{rarity}_{i}",
                "type": random.choice(item_types),
                "rarity": rarity,
                "value": random.randint(1, 10000),
                "stats": {
                    "power": random.randint(1, 100) if rarity != "common" else 0,
                    "durability": random.randint(50, 200)
                },
                "metadata": {
                    "stress_test": True
                }
            }
            items.append(item)
        
        self._generated_items = items
        return items
    
    def _generate_events(self, count: int) -> List[Dict]:
        """Сгенерировать множество событий"""
        event_types = [
            "enemy_spawn", "item_drop", "quest_start", "quest_complete",
            "area_enter", "area_exit", "combat_start", "combat_end",
            "trade", "dialogue", "weather_change", "time_change"
        ]
        
        events = []
        for i in range(count):
            event = {
                "id": f"stress_event_{i}",
                "type": random.choice(event_types),
                "timestamp": time.time() - random.uniform(0, 3600),
                "data": {
                    "random_value": random.random(),
                    "random_int": random.randint(0, 1000)
                }
            }
            events.append(event)
        
        self._generated_events = events
        return events
    
    def _generate_npcs(self, count: int) -> List[Dict]:
        """Сгенерировать множество NPC"""
        npc_types = ["merchant", "quest_giver", "guard", "civilian", "trainer"]
        moods = ["friendly", "neutral", "hostile", "fearful"]
        
        npcs = []
        for i in range(count):
            npc = {
                "id": f"stress_npc_{i}",
                "type": random.choice(npc_types),
                "name": f"NPC_{i}",
                "x": random.randint(0, 1000),
                "y": random.randint(0, 1000),
                "mood": random.choice(moods),
                "inventory_size": random.randint(0, 20),
                "quests_available": random.randint(0, 3),
                "metadata": {
                    "stress_test": True
                }
            }
            npcs.append(npc)
        
        return npcs
    
    def get_metrics(self) -> Dict:
        """Получить метрики последней генерации"""
        return self._test_metrics.copy()
    
    def clear_generated(self):
        """Очистить сгенерированный контент"""
        self._generated_entities.clear()
        self._generated_items.clear()
        self._generated_events.clear()
        self._test_metrics = {
            "entities_spawned": 0,
            "items_created": 0,
            "events_triggered": 0,
            "generation_time_ms": 0
        }


# Self-test
if __name__ == "__main__":
    print("Testing Stress Test Content Generator...")
    
    generator = StressTestContentGenerator()
    
    # Small test
    config = StressTestConfig(
        entity_count=50,
        item_count=30,
        event_count=10,
        npc_count=20,
        duration_seconds=10
    )
    
    result = generator.generate_stress_test(config)
    metrics = generator.get_metrics()
    
    assert metrics["entities_spawned"] == 50
    assert metrics["items_created"] == 30
    assert metrics["events_triggered"] == 10
    assert metrics["npcs_spawned"] == 20
    assert metrics["generation_time_ms"] > 0
    
    print(f"✓ Generated {metrics['total_objects']} objects in {metrics['generation_time_ms']:.2f}ms")
    print(f"✓ Rate: {metrics['objects_per_second']:.0f} objects/sec")
    
    # Large stress test
    large_config = StressTestConfig(
        entity_count=500,
        item_count=300,
        event_count=100,
        npc_count=200
    )
    
    large_result = generator.generate_stress_test(large_config)
    large_metrics = generator.get_metrics()
    
    print(f"✓ Large test: {large_metrics['total_objects']} objects in {large_metrics['generation_time_ms']:.2f}ms")
    
    print("\n✅ Stress Test Content Generator Self-Test PASSED")
