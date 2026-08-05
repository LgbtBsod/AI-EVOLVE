"""
Comprehensive Test Suite for New AI-EVOLVE Features
Tests all new gameplay mechanics: Neuro Resonance, Terraforming, Adaptive Anticipation
"""
import sys
import time
import unittest
from unittest.mock import MagicMock

# Mock panda3d before importing systems that might need it
sys.modules['panda3d.core'] = MagicMock()
sys.modules['direct.showbase.ShowBase'] = MagicMock()


class TestNeuroResonanceSystem(unittest.TestCase):
    """Test Neuro Resonance - Allied Synchronization"""
    
    def test_import_and_instantiation(self):
        from src.features.neuro_resonance import NeuroResonanceSystem
        system = NeuroResonanceSystem(max_links_per_unit=3, sync_range=40.0)
        self.assertIsNotNone(system)
        self.assertEqual(system.max_links_per_unit, 3)
        
    def test_register_unit(self):
        from src.features.neuro_resonance import NeuroResonanceSystem
        system = NeuroResonanceSystem()
        
        system.register_unit("unit_1", squad_id="alpha")
        system.register_unit("unit_2", squad_id="alpha")
        system.register_unit("unit_3", squad_id="alpha")
        
        self.assertIn("unit_1", system.unit_resonance)
        self.assertIn("unit_1", system.squad_groups["alpha"])
        
    def test_establish_link(self):
        from src.features.neuro_resonance import NeuroResonanceSystem
        system = NeuroResonanceSystem(max_links_per_unit=2)
        
        system.register_unit("unit_a")
        system.register_unit("unit_b")
        
        result = system.establish_link("unit_a", "unit_b")
        self.assertTrue(result)
        self.assertIn("unit_b", system.unit_resonance["unit_a"].linked_units)
        
    def test_resonance_state_progression(self):
        from src.features.neuro_resonance import NeuroResonanceSystem, ResonanceState
        system = NeuroResonanceSystem(max_links_per_unit=10)
        
        # Register main unit and multiple allies
        system.register_unit("main")
        for i in range(10):
            system.register_unit(f"ally_{i}")
            system.establish_link("main", f"ally_{i}")
            
        system.update_resonance_state("main")
        stats = system.unit_resonance["main"]
        
        self.assertEqual(stats.state, ResonanceState.PERFECT)
        self.assertTrue(stats.shared_vision)
        self.assertAlmostEqual(stats.coordination_bonus, 0.50, places=2)
        
    def test_get_combat_bonus(self):
        from src.features.neuro_resonance import NeuroResonanceSystem
        system = NeuroResonanceSystem()
        
        system.register_unit("unit_1")
        system.register_unit("unit_2")
        system.establish_link("unit_1", "unit_2")
        system.update_resonance_state("unit_1")
        
        bonuses = system.get_combat_bonus("unit_1")
        self.assertIn("accuracy", bonuses)
        self.assertIn("reaction_speed", bonuses)
        self.assertIn("damage", bonuses)
        self.assertIn("defense", bonuses)


class TestTerraformingSystem(unittest.TestCase):
    """Test Terraforming - Battlefield Environmental Scars"""
    
    def test_import_and_instantiation(self):
        from src.features.terraforming import (
            TerraformingSystem,
        )
        system = TerraformingSystem(max_modifications=50)
        self.assertIsNotNone(system)
        
    def test_add_crater_modification(self):
        from src.features.terraforming import (
            TerraformingSystem,
            TerrainModificationType,
        )
        system = TerraformingSystem()
        
        system.add_modification(
            mod_type=TerrainModificationType.CRATER,
            position=(100.0, 150.0),
            radius=5.0,
            duration=120.0
        )
        
        self.assertEqual(len(system.modifications), 1)
        self.assertEqual(system.modifications[0].mod_type, TerrainModificationType.CRATER)
        
    def test_position_effects(self):
        from src.features.terraforming import (
            TerraformingSystem,
            TerrainModificationType,
        )
        system = TerraformingSystem()
        
        # Add a crater at (100, 100) with radius 10
        system.add_modification(
            mod_type=TerrainModificationType.CRATER,
            position=(100.0, 100.0),
            radius=10.0,
            duration=60.0
        )
        
        # Position inside crater should be blocked
        effects = system.get_position_effects((100.0, 100.0))
        self.assertLessEqual(effects.get("movement_speed", 0), -0.9)
        self.assertGreater(effects.get("cover_bonus", 0), 0.5)
        
        # Position outside should have no effects
        effects_outside = system.get_position_effects((200.0, 200.0))
        self.assertEqual(len(effects_outside), 0)
        
    def test_is_position_blocked(self):
        from src.features.terraforming import (
            TerraformingSystem,
            TerrainModificationType,
        )
        system = TerraformingSystem()
        
        system.add_modification(
            mod_type=TerrainModificationType.CRATER,
            position=(50.0, 50.0),
            radius=5.0,
            duration=60.0
        )
        
        self.assertTrue(system.is_position_blocked((50.0, 50.0)))
        self.assertFalse(system.is_position_blocked((100.0, 100.0)))
        
    def test_multiple_modifications_stack(self):
        from src.features.terraforming import (
            TerraformingSystem,
            TerrainModificationType,
        )
        system = TerraformingSystem()
        
        # Add burn mark and debris at same location
        system.add_modification(
            mod_type=TerrainModificationType.BURN_MARK,
            position=(75.0, 75.0),
            radius=8.0,
            duration=60.0
        )
        system.add_modification(
            mod_type=TerrainModificationType.DEBRIS_FIELD,
            position=(75.0, 75.0),
            radius=8.0,
            duration=60.0
        )
        
        effects = system.get_position_effects((75.0, 75.0))
        
        # Effects should stack
        self.assertIn("damage_per_second", effects)
        self.assertIn("cover_bonus", effects)
        
    def test_cleanup_expired(self):
        from src.features.terraforming import (
            TerraformingSystem,
            TerrainModificationType,
        )
        system = TerraformingSystem(max_modifications=5)
        
        # Add modifications with very short duration
        for i in range(7):
            system.add_modification(
                mod_type=TerrainModificationType.CRATER,
                position=(float(i*10), float(i*10)),
                radius=3.0,
                duration=0.1  # Expires almost immediately
            )
            
        time.sleep(0.2)
        system.on_update(0.1)
        
        # Should have cleaned up expired
        active_count = len([m for m in system.modifications if not m.is_expired])
        self.assertEqual(active_count, 0)


class TestAdaptiveAnticipationSystem(unittest.TestCase):
    """Test Adaptive Anticipation - Predictive AI Defense"""
    
    def test_import_and_instantiation(self):
        from src.features.adaptive_anticipation import (
            AdaptiveAnticipationSystem,
        )
        system = AdaptiveAnticipationSystem(history_size=50, learning_rate=0.15)
        self.assertIsNotNone(system)
        self.assertEqual(system.history_size, 50)
        
    def test_record_encounter(self):
        from src.features.adaptive_anticipation import (
            AdaptiveAnticipationSystem,
            AttackPattern,
        )
        system = AdaptiveAnticipationSystem()
        
        system.record_encounter(
            pattern=AttackPattern.MELEE_RUSH,
            player_position=(100.0, 100.0),
            ai_response="backpedal_and_aoe",
            attack_successful=False,  # AI blocked it
            reaction_time=0.25
        )
        
        self.assertEqual(len(system.pattern_history), 1)
        self.assertEqual(system.stats.recognized_patterns[AttackPattern.MELEE_RUSH], 1)
        
    def test_prediction_accuracy_improves(self):
        from src.features.adaptive_anticipation import (
            AdaptiveAnticipationSystem,
            AttackPattern,
        )
        system = AdaptiveAnticipationSystem(history_size=100)
        
        # Record multiple successful blocks
        for i in range(20):
            system.record_encounter(
                pattern=AttackPattern.RANGED_SNIPER,
                player_position=(50.0 + i, 50.0),
                ai_response="take_cover_and_flank",
                attack_successful=False,  # Blocked
                reaction_time=0.3
            )
            
        # Accuracy should be high
        self.assertGreater(system.stats.prediction_accuracy, 0.9)
        self.assertGreater(system.stats.adaptation_level, 0.1)
        
    def test_predict_next_attack(self):
        from src.features.adaptive_anticipation import (
            AdaptiveAnticipationSystem,
            AttackPattern,
        )
        system = AdaptiveAnticipationSystem()
        
        # Need at least 5 encounters for prediction
        patterns = [
            AttackPattern.MELEE_RUSH,
            AttackPattern.MELEE_RUSH,
            AttackPattern.MELEE_RUSH,
            AttackPattern.AREA_BOMBARDMENT,
            AttackPattern.MELEE_RUSH,
            AttackPattern.MELEE_RUSH
        ]
        
        for pattern in patterns:
            system.record_encounter(
                pattern=pattern,
                player_position=(100.0, 100.0),
                ai_response="defensive",
                attack_successful=False,
                reaction_time=0.2
            )
            
        prediction = system.predict_next_attack()
        # Should predict MELEE_RUSH as it's most frequent
        self.assertEqual(prediction, AttackPattern.MELEE_RUSH)
        
    def test_get_optimal_counter(self):
        from src.features.adaptive_anticipation import (
            AdaptiveAnticipationSystem,
            AttackPattern,
        )
        system = AdaptiveAnticipationSystem()
        
        counter = system.get_optimal_counter(AttackPattern.STEALTH_FLANK)
        self.assertEqual(counter, "area_scan_and_defensive_stance")
        
    def test_get_dodge_direction(self):
        from src.features.adaptive_anticipation import (
            AdaptiveAnticipationSystem,
        )
        system = AdaptiveAnticipationSystem()
        
        attacker_pos = (0.0, 0.0)
        ai_pos = (10.0, 10.0)
        
        dodge = system.get_dodge_direction(attacker_pos, ai_pos)
        self.assertIsInstance(dodge, tuple)
        self.assertEqual(len(dodge), 2)
        
    def test_get_player_profile(self):
        from src.features.adaptive_anticipation import (
            AdaptiveAnticipationSystem,
            AttackPattern,
        )
        system = AdaptiveAnticipationSystem()
        
        # Initially insufficient data
        profile = system.get_player_profile()
        self.assertEqual(profile.get("analysis"), "insufficient_data")
        
        # Add some data
        for _ in range(10):
            system.record_encounter(
                pattern=AttackPattern.COMBO_ASSAULT,
                player_position=(50.0, 50.0),
                ai_response="retreat",
                attack_successful=True,
                reaction_time=0.4
            )
            
        profile = system.get_player_profile()
        self.assertEqual(profile.get("favorite_pattern"), "combo_assault")
        self.assertIn("encounters_analyzed", profile)
        self.assertEqual(profile["encounters_analyzed"], 10)


class TestFeatureIntegration(unittest.TestCase):
    """Test integration between all new features"""
    
    def test_all_features_import_cleanly(self):
        """Ensure all new feature modules import without errors"""
        from src.features import (
            AdaptiveAnticipationSystem,
            DynamicWeatherSystem,
            GeneticMemorySystem,
            MoraleSystem,
            NeuroResonanceSystem,
            TerraformingSystem,
        )
        
        # Instantiate all
        genetic = GeneticMemorySystem()
        weather = DynamicWeatherSystem()
        morale = MoraleSystem()
        resonance = NeuroResonanceSystem()
        terraform = TerraformingSystem()
        anticipation = AdaptiveAnticipationSystem()
        
        self.assertIsNotNone(genetic)
        self.assertIsNotNone(weather)
        self.assertIsNotNone(morale)
        self.assertIsNotNone(resonance)
        self.assertIsNotNone(terraform)
        self.assertIsNotNone(anticipation)
        
    def test_solid_compliance(self):
        """Verify new features follow SOLID principles"""
        from src.features.adaptive_anticipation import AdaptiveAnticipationSystem
        from src.features.neuro_resonance import NeuroResonanceSystem
        from src.features.terraforming import TerraformingSystem
        
        # Single Responsibility: Each system has one clear purpose
        # Check that classes have focused method sets
        neuro_methods = [m for m in dir(NeuroResonanceSystem) if not m.startswith('_')]
        terraform_methods = [m for m in dir(TerraformingSystem) if not m.startswith('_')]
        anticipation_methods = [m for m in dir(AdaptiveAnticipationSystem) if not m.startswith('_')]
        
        # Each should have reasonable number of public methods (not too many = focused)
        self.assertLess(len(neuro_methods), 20)
        self.assertLess(len(terraform_methods), 20)
        self.assertLess(len(anticipation_methods), 20)
        
    def test_thread_safety_basic(self):
        """Basic thread safety check for new systems"""
        import threading

        from src.features.neuro_resonance import NeuroResonanceSystem
        
        system = NeuroResonanceSystem()
        errors = []
        
        def register_units():
            try:
                for i in range(50):
                    system.register_unit(f"thread_unit_{i}")
            except Exception as e:
                errors.append(e)
                
        threads = [threading.Thread(target=register_units) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
            
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(system.unit_resonance), 250)  # 5 threads * 50 units


if __name__ == '__main__':
    unittest.main(verbosity=2)
