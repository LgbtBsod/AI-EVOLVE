#!/usr/bin/env python3
"""
Test Suite for Training Room & Mannequin System
Проверка работоспособности системы тестирования предметов
"""

import unittest
import sys
import json
from pathlib import Path

sys.path.insert(0, '/workspace/src')
sys.path.insert(0, '/workspace/tools')

from training_room import (
    TrainingRoom, Mannequin, MannequinConfig, MannequinType,
    TestScenario, TestResult
)
from features.advanced_items import (
    create_banes_scar_necklace, create_sorrow_of_berserk
)
from core.cas_engine import DamageType


class TestMannequin(unittest.TestCase):
    """Тесты манекена"""
    
    def setUp(self):
        self.config = MannequinConfig(
            name="Test Dummy",
            mannequin_type=MannequinType.DUMMY,
            max_hp=10000.0,
            defense=100.0
        )
        self.mannequin = Mannequin(self.config)
        
    def test_mannequin_creation(self):
        """Создание манекена"""
        self.assertEqual(self.mannequin.config.name, "Test Dummy")
        self.assertEqual(self.mannequin.current_hp, 10000.0)
        self.assertTrue(self.mannequin.is_alive())
        
    def test_take_damage_with_defense(self):
        """Получение урона с учётом защиты"""
        self.mannequin.take_damage(500.0, DamageType.PHYSICAL, "player")
        # Урон должен быть снижен на defense (100)
        expected_damage = max(1.0, 500.0 - 100.0)
        self.assertEqual(self.mannequin.damage_taken["player"], expected_damage)
        self.assertEqual(self.mannequin.current_hp, 10000.0 - expected_damage)
        
    def test_take_damage_with_resistance(self):
        """Получение урона с учётом сопротивлений"""
        config = MannequinConfig(
            name="Resist Dummy",
            mannequin_type=MannequinType.TANK,
            max_hp=10000.0,
            resistances={DamageType.FIRE: 50.0}  # 50% resistance
        )
        mannequin = Mannequin(config)
        
        mannequin.take_damage(1000.0, DamageType.FIRE, "mage")
        # 50% resistance
        expected_damage = 1000.0 * 0.5
        self.assertEqual(mannequin.damage_taken["mage"], expected_damage)
        
    def test_reset(self):
        """Сброс манекена"""
        self.mannequin.take_damage(5000.0, DamageType.PHYSICAL, "player")
        self.mannequin.reset()
        self.assertEqual(self.mannequin.current_hp, 10000.0)
        self.assertEqual(len(self.mannequin.hit_log), 0)
        
    def test_get_stats_summary(self):
        """Получение агрегированной статистики"""
        self.mannequin.take_damage(100.0, DamageType.PHYSICAL, "p1", is_crit=False, timestamp=1.0)
        self.mannequin.take_damage(200.0, DamageType.PHYSICAL, "p1", is_crit=True, timestamp=2.0)
        
        summary = self.mannequin.get_stats_summary()
        self.assertEqual(summary['hits'], 2)
        self.assertEqual(summary['crit_count'], 1)
        self.assertEqual(summary['crit_rate'], 50.0)


class TestTrainingRoom(unittest.TestCase):
    """Тесты Training Room"""
    
    def setUp(self):
        self.room = TrainingRoom(output_dir="/tmp/training_room_test")
        
    def test_create_mannequins(self):
        """Создание различных типов манекенов"""
        self.room.create_mannequin("dummy", MannequinType.DUMMY)
        self.room.create_mannequin("tank", MannequinType.TANK)
        self.room.create_mannequin("boss", MannequinType.BOSS)
        
        self.assertIn("dummy", self.room.mannequins)
        self.assertIn("tank", self.room.mannequins)
        self.assertIn("boss", self.room.mannequins)
        
        # Проверка HP
        self.assertEqual(self.room.mannequins["dummy"].config.max_hp, 100000.0)
        self.assertEqual(self.room.mannequins["tank"].config.max_hp, 50000.0)
        self.assertEqual(self.room.mannequins["boss"].config.max_hp, 500000.0)
        
    def test_run_dps_test(self):
        """Запуск DPS теста"""
        self.room.create_mannequin("target", MannequinType.DUMMY)
        
        scenario = TestScenario(
            name="test_dps",
            description="Test DPS scenario",
            duration_seconds=5.0,
            attacks_per_second=2.0
        )
        self.room.setup_test_scenario(scenario)
        
        items = [create_banes_scar_necklace()]
        result = self.room.run_dps_test(items, "target")
        
        # Проверка результатов
        self.assertGreater(result.dps, 0)
        self.assertGreater(result.total_hits, 0)
        self.assertEqual(result.scenario_name, "test_dps")
        
    def test_compare_items(self):
        """Сравнение наборов предметов"""
        self.room.create_mannequin("target_dummy", MannequinType.DUMMY)
        
        comparison = self.room.compare_items(
            item_sets={
                'set_a': [create_banes_scar_necklace()],
                'set_b': [create_sorrow_of_berserk()]
            },
            mannequin_name="target_dummy",
            duration=3.0
        )
        
        self.assertIn('tested_sets', comparison)
        self.assertIn('best_dps', comparison)
        self.assertIn('comparison_table', comparison)
        self.assertEqual(len(comparison['tested_sets']), 2)
        
    def test_export_report(self):
        """Экспорт отчёта в JSON"""
        self.room.create_mannequin("target", MannequinType.DUMMY)
        
        scenario = TestScenario(name="export_test", description="Test")
        self.room.setup_test_scenario(scenario)
        
        items = [create_banes_scar_necklace()]
        result = self.room.run_dps_test(items, "target")
        
        report_path = self.room.export_report(result, "test_export.json")
        
        self.assertTrue(report_path.exists())
        
        # Проверка содержимого
        with open(report_path) as f:
            data = json.load(f)
            
        self.assertIn('metadata', data)
        self.assertIn('summary', data)
        self.assertEqual(data['summary']['dps'], result.dps)


class TestLuaConfigIntegration(unittest.TestCase):
    """Тесты интеграции с Lua конфигурацией"""
    
    def test_lua_config_exists(self):
        """Проверка существования Lua конфигов"""
        lua_path = Path('/workspace/lua_content/training_room/mannequins.lua')
        self.assertTrue(lua_path.exists())
        
    def test_lua_config_content(self):
        """Проверка содержимого Lua конфига"""
        lua_path = Path('/workspace/lua_content/training_room/mannequins.lua')
        content = lua_path.read_text()
        
        self.assertIn('mannequins', content)
        self.assertIn('scenarios', content)
        self.assertIn('item_sets', content)
        self.assertIn('dummy', content)
        self.assertIn('tank', content)


class TestRecommendations(unittest.TestCase):
    """Тесты генерации рекомендаций"""
    
    def setUp(self):
        self.room = TrainingRoom(output_dir="/tmp/training_room_test")
        
    def test_low_crit_recommendation(self):
        """Рекомендация при низком крите"""
        result = TestResult(
            scenario_name="test",
            total_damage=1000.0,
            dps=100.0,
            total_hits=10,
            crit_count=0,
            crit_rate=0.0,
            average_hit=100.0
        )
        
        recs = self.room._generate_recommendations(result, None)
        self.assertTrue(any("crit" in r.lower() for r in recs))
        
    def test_high_crit_recommendation(self):
        """Рекомендация при высоком крите"""
        from training_room import Mannequin, MannequinConfig, MannequinType
        
        config = MannequinConfig("test", MannequinType.DUMMY)
        mannequin = Mannequin(config)
        
        # Добавляем много критов
        for i in range(10):
            mannequin.hit_log.append({'is_crit': True, 'final_damage': 100})
            
        recs = self.room._generate_recommendations(None, mannequin)
        self.assertTrue(any("high crit" in r.lower() for r in recs))


if __name__ == "__main__":
    print("\n" + "="*60)
    print("TRAINING ROOM TEST SUITE")
    print("="*60 + "\n")
    
    unittest.main(verbosity=2)
