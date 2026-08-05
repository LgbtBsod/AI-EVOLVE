"""
Comprehensive Test Suite for New Features
Tests Genetic Memory, Dynamic Weather, and Morale Systems.
"""
import os
import sys
import unittest
from unittest.mock import Mock

# Add src to path correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

class TestGeneticMemory(unittest.TestCase):
    def test_memory_recording(self):
        """Test that significant milestones are recorded."""
        from src.features.genetic_memory import GeneticMemorySystem
        
        system = GeneticMemorySystem(max_memories=5)
        system.on_start()
        
        # Record a success
        system.record_milestone("ancestor_1", "fireball", 0.85, ["combat", "magic"])
        
        self.assertEqual(len(system.memory_pool), 1)
        self.assertEqual(system.memory_pool[0].skill_name, "fireball")
        self.assertEqual(system.memory_pool[0].potency, 0.85)
        
    def test_memory_threshold(self):
        """Test that low success rates are not recorded."""
        from src.features.genetic_memory import GeneticMemorySystem
        
        system = GeneticMemorySystem()
        system.on_start()
        
        # Should not record (below 0.7 threshold)
        system.record_milestone("ancestor_2", "weak_attack", 0.5, ["combat"])
        
        self.assertEqual(len(system.memory_pool), 0)
        
    def test_echo_trigger(self):
        """Test ancestral echo activation."""
        from src.features.genetic_memory import GeneticMemorySystem
        
        system = GeneticMemorySystem()
        system.on_start()
        
        # Record strong memory
        system.record_milestone("ancient_hero", "sword_mastery", 0.95, ["combat", "melee"])
        
        # Create mock entity
        mock_entity = Mock()
        mock_entity.id = "descendant_1"
        
        # Trigger echo with matching context
        bonus = system.trigger_echo(mock_entity, ["combat", "arena"])
        
        self.assertIsNotNone(bonus)
        self.assertEqual(bonus["skill"], "sword_mastery")
        self.assertIn("Echo of ancient_hero", bonus["message"])
        
    def test_memory_limit(self):
        """Test oldest memories are removed when limit exceeded."""
        from src.features.genetic_memory import GeneticMemorySystem
        
        system = GeneticMemorySystem(max_memories=3)
        system.on_start()
        
        # Add 4 memories
        for i in range(4):
            system.record_milestone(f"ancestor_{i}", f"skill_{i}", 0.8, ["test"])
            
        self.assertEqual(len(system.memory_pool), 3)
        # Oldest (ancestor_0) should be removed
        self.assertEqual(system.memory_pool[0].ancestor_id, "ancestor_1")


class TestDynamicWeather(unittest.TestCase):
    def test_weather_change(self):
        """Test weather transitions."""
        from src.features.dynamic_weather import DynamicWeatherSystem, WeatherType
        
        system = DynamicWeatherSystem()
        system.on_start()
        
        self.assertEqual(system.current_weather.weather_type, WeatherType.CLEAR)
        
        # Simulate time passing
        system.next_weather_duration = 0.1  # Force change soon
        system.on_update(0.2)
        
        # Weather should have changed
        self.assertNotEqual(system.current_weather.weather_type, WeatherType.CLEAR)
        
    def test_environmental_bonuses(self):
        """Test unit bonuses based on weather."""
        from src.features.dynamic_weather import DynamicWeatherSystem, WeatherType
        
        system = DynamicWeatherSystem()
        system.on_start()
        
        # Force fog
        system._change_weather(WeatherType.FOG)
        
        # Stealth unit should get bonus
        bonuses = system.get_environmental_bonus(["stealth_unit", "archer"])
        self.assertIn("stealth", bonuses)
        self.assertEqual(bonuses["stealth"], 0.5)
        
        # Non-stealth unit gets nothing
        bonuses = system.get_environmental_bonus(["warrior"])
        self.assertEqual(len(bonuses), 0)
        
    def test_storm_effects(self):
        """Test storm penalties and bonuses."""
        from src.features.dynamic_weather import DynamicWeatherSystem, WeatherType
        
        system = DynamicWeatherSystem()
        system.on_start()
        system._change_weather(WeatherType.STORM)
        
        # Electric attack bonus
        bonuses = system.get_environmental_bonus(["electric_attack", "mage"])
        self.assertIn("damage", bonuses)
        self.assertEqual(bonuses["damage"], 0.3)
        
        # Heavy armor penalty (via rain profile logic - simplified test)
        # In full implementation, storm would also apply mud effects


class TestMoraleSystem(unittest.TestCase):
    def test_morale_states(self):
        """Test morale state transitions."""
        from src.features.morale_system import MoraleState, MoraleSystem
        
        system = MoraleSystem()
        system.on_start()
        system.register_unit("unit_1", base_morale=80.0)
        
        stats = system.unit_morale["unit_1"]
        self.assertEqual(stats.state, MoraleState.NORMAL)
        
        # Boost to heroic
        system.apply_morale_change("unit_1", 15.0, "victory")
        self.assertEqual(system.unit_morale["unit_1"].state, MoraleState.HEROIC)
        
        # Drop to panicked
        system.apply_morale_change("unit_1", -80.0, "ambush")
        self.assertEqual(system.unit_morale["unit_1"].state, MoraleState.PANICKED)
        
    def test_performance_modifier(self):
        """Test combat performance modifiers."""
        from src.features.morale_system import MoraleSystem
        
        system = MoraleSystem()
        system.on_start()
        system.register_unit("hero", base_morale=95.0)
        
        modifier = system.get_performance_modifier("hero")
        self.assertEqual(modifier, 0.3)  # Heroic bonus
        
        system.apply_morale_change("hero", -60.0, "defeat")
        modifier = system.get_performance_modifier("hero")
        self.assertLess(modifier, 0)  # Now negative
        
    def test_flee_behavior(self):
        """Test flee decision based on morale."""
        from src.features.morale_system import MoraleSystem
        
        system = MoraleSystem()
        system.on_start()
        system.register_unit("coward", base_morale=10.0)
        
        self.assertTrue(system.should_flee("coward"))
        
        system.apply_morale_change("coward", 50.0, "pep_talk")
        self.assertFalse(system.should_flee("coward"))
        
    def test_passive_decay(self):
        """Test passive morale decay over time."""
        from src.features.morale_system import MoraleState, MoraleSystem
        
        system = MoraleSystem()
        system.on_start()
        system.register_unit("soldier", base_morale=40.0)  # Low normal
        
        # Simulate time passing (decay when wavering or lower)
        system.apply_morale_change("soldier", -10.0, "tiredness")  # Now wavering
        self.assertEqual(system.unit_morale["soldier"].state, MoraleState.WAVERING)
        
        # Update should cause decay
        system.on_update(10.0)  # 10 seconds
        
        # Should have decayed further
        current = system.unit_morale["soldier"].current_morale
        self.assertLess(current, 30.0)


class TestIntegration(unittest.TestCase):
    def test_combined_systems(self):
        """Test all systems working together."""
        from src.features.dynamic_weather import DynamicWeatherSystem, WeatherType
        from src.features.genetic_memory import GeneticMemorySystem
        from src.features.morale_system import MoraleState, MoraleSystem
        
        # Initialize all
        memory_sys = GeneticMemorySystem()
        weather_sys = DynamicWeatherSystem()
        morale_sys = MoraleSystem()
        
        memory_sys.on_start()
        weather_sys.on_start()
        morale_sys.on_start()
        
        # Scenario: Unit fights in storm, achieves victory
        unit_id = "champion"
        morale_sys.register_unit(unit_id, base_morale=70.0)
        
        # Storm active
        weather_sys._change_weather(WeatherType.STORM)
        
        # Unit wins despite storm (impressive)
        memory_sys.record_milestone(unit_id, "storm_victory", 0.9, ["combat", "storm", "lightning"])
        
        # Morale boost
        morale_sys.apply_morale_change(unit_id, 20.0, "victory_in_storm")
        
        # Verify states
        self.assertEqual(morale_sys.unit_morale[unit_id].state, MoraleState.HEROIC)
        self.assertEqual(len(memory_sys.memory_pool), 1)
        self.assertEqual(weather_sys.current_weather.weather_type, WeatherType.STORM)
        
        # Future descendant might get echo
        mock_descendant = Mock()
        mock_descendant.id = "heir"
        echo = memory_sys.trigger_echo(mock_descendant, ["combat", "storm"])
        self.assertIsNotNone(echo)


if __name__ == '__main__':
    print("=" * 60)
    print("RUNNING COMPREHENSIVE FEATURE TESTS")
    print("=" * 60)
    
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print(f"TESTS RUN: {result.testsRun}")
    print(f"FAILURES: {len(result.failures)}")
    print(f"ERRORS: {len(result.errors)}")
    print(f"SUCCESS: {result.wasSuccessful()}")
    print("=" * 60)
    
    if result.wasSuccessful():
        print("\n✅ ALL NEW FEATURES WORKING CORRECTLY!")
    else:
        print("\n❌ SOME TESTS FAILED - REVIEW ABOVE")
        
    sys.exit(0 if result.wasSuccessful() else 1)
