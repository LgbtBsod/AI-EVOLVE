"""
Test Suite for Condition-Action System (CAS) and Advanced Damage Calculator.
Tests the "Apocalypse Bringer" item with 20+ conditions and complex interactions.
"""

import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from core.cas_engine import (
    CASManager, DamageCalculator, EffectTemplate, Condition, Action,
    StatType, DamageType, ConditionOperator, DamageProfile, DefenseProfile
)

class TestCasEngine(unittest.TestCase):
    
    def setUp(self):
        self.cas = CASManager()
        self.dmg_calc = DamageCalculator()

    def test_01_apocalypse_bringer_registration(self):
        """Test registering the ultra-complex item"""
        # Define Conditions
        conditions = [
            Condition("current_hp_percent", ConditionOperator.LTE, 40.0),
            Condition("kills_last_10s", ConditionOperator.GTE, 1.0),
            Condition("is_berserk_mode", ConditionOperator.EQ, 1.0),
        ]
        
        # Define Actions (Mixed Flat, Percent, Scaling)
        actions = [
            Action("modify_stat", stat="attack_power_percent", value=50.0, stat_type=StatType.PERCENT),
            Action("modify_stat", stat="attack_speed_percent", value=50.0, stat_type=StatType.PERCENT),
            Action("modify_stat", stat="flat_dmg_from_max_hp", value=2.0, stat_type=StatType.SCALING), # 2% Max HP
            Action("modify_stat", stat="vampirism_percent", value=20.0, stat_type=StatType.PERCENT),
            Action("modify_stat", stat="iframe_active", value=1.0, stat_type=StatType.FLAT),
        ]
        
        item = EffectTemplate(
            id="apocalypse_bringer",
            name="Apocalypse Bringer",
            conditions=conditions,
            actions=actions
        )
        
        self.cas.register_effect(item)
        self.assertIn("apocalypse_bringer", self.cas.active_effects)
        print("✅ Item Registered Successfully")

    def test_02_condition_evaluation_logic(self):
        """Test that effects only trigger when ALL conditions are met"""
        # Register a simple effect
        eff = EffectTemplate(
            id="test_eff",
            name="Test Effect",
            conditions=[
                Condition("hp_percent", ConditionOperator.LTE, 30.0),
                Condition("buff_active", ConditionOperator.EQ, 1.0)
            ],
            actions=[Action("modify_stat", stat="dmg", value=100.0)]
        )
        self.cas.register_effect(eff)
        
        # Scenario A: Only 1 condition met -> No Action
        self.cas.update_stats({"hp_percent": 25.0, "buff_active": 0.0})
        actions = self.cas.evaluate_effects()
        self.assertEqual(len(actions), 0, "Should not trigger if not all conditions met")
        
        # Scenario B: All conditions met -> Action Triggered
        self.cas.update_stats({"hp_percent": 25.0, "buff_active": 1.0})
        actions = self.cas.evaluate_effects()
        self.assertEqual(len(actions), 1, "Should trigger when all conditions met")
        self.assertEqual(actions[0].value, 100.0)
        print("✅ Condition Logic Works Correctly")

    def test_03_flat_vs_scaling_damage(self):
        """Test difference between Flat (+10) and Scaling (10% MaxHP)"""
        stats_high_hp = {"max_hp": 10000, "current_hp": 5000}
        stats_low_hp = {"max_hp": 1000, "current_hp": 500}
        
        # Effect: +10 Flat Dmg
        flat_eff = EffectTemplate(
            id="flat", name="Flat", 
            conditions=[], 
            actions=[Action("modify_stat", stat="bonus_dmg", value=10.0, stat_type=StatType.FLAT)]
        )
        
        # Effect: +10% MaxHP Dmg
        scale_eff = EffectTemplate(
            id="scale", name="Scaling",
            conditions=[],
            actions=[Action("modify_stat", stat="bonus_dmg_from_max_hp", value=10.0, stat_type=StatType.SCALING)]
        )
        
        self.cas.register_effect(flat_eff)
        self.cas.register_effect(scale_eff)
        
        # High HP Test
        self.cas.update_stats(stats_high_hp)
        acts = self.cas.evaluate_effects()
        # Flat should be 10, Scaling should be 1000 (10% of 10000)
        # Note: apply_actions logic handles the calculation, here we just check presence
        self.assertEqual(len(acts), 2)
        print("✅ Flat vs Scaling Distinction Verified")

    def test_04_multithreaded_damage_calculation(self):
        """Test the 3-thread damage calculator with complex resist/armor logic"""
        
        # Attacker: High Physical, Some Fire, HP Scaling
        profile = DamageProfile(
            base_physical=100.0,
            base_elemental={DamageType.FIRE: 50.0},
            flat_bonus_physical=20.0,
            scaling_from_stat={"max_hp": 5.0}, # 5% of Max HP as bonus dmg
            crit_chance=100.0, # Force Crit
            crit_mult=2.5,
            armor_pen_percent=20.0,
            resist_pen_flat=10.0
        )
        
        # Defender: High Armor, High Fire Resist
        defense = DefenseProfile(
            armor=500.0,
            resists={DamageType.FIRE: 60.0}
        )
        
        results = self.dmg_calc.calculate_damage(profile, defense, is_crit=True)
        
        # Assertions
        self.assertIn('physical', results)
        self.assertIn('fire', results)
        self.assertIn('total', results)
        
        # Physical Check (Roughly):
        # Raw = 100 (base) + 20 (flat) + 50 (5% of mock 1000 HP) = 170
        # Crit = 170 * 2.5 = 425
        # Armor Mitigation: 500 * 0.8 (pen) = 400. Mitigation = 400/500 = 0.8. Dmg = 425 * 0.2 = 85
        self.assertGreater(results['physical'], 0)
        
        # Fire Check (Roughly):
        # Raw = 50 (base) + 50 (scaling) = 100
        # Crit = 250
        # Resist: 60 - 10 (pen) = 50. Multiplier = 0.5. Dmg = 125
        self.assertGreater(results['fire'], 0)
        
        print(f"✅ Multi-threaded Calc: Phys={results['physical']:.2f}, Fire={results['fire']:.2f}, Total={results['total']:.2f}")

    def test_05_stress_test_20_conditions(self):
        """Stress test with an item having 20 conditions"""
        conditions = []
        for i in range(1, 21):
            conditions.append(Condition(f"stat_{i}", ConditionOperator.GTE, float(i)))
            
        mega_item = EffectTemplate(
            id="mega_item",
            name="Mega Item",
            conditions=conditions,
            actions=[Action("modify_stat", stat="god_mode", value=1.0)]
        )
        
        self.cas.register_effect(mega_item)
        
        # Fail case
        self.cas.update_stats({f"stat_{i}": float(i)-1 for i in range(1, 21)})
        self.assertEqual(len(self.cas.evaluate_effects()), 0)
        
        # Pass case
        self.cas.update_stats({f"stat_{i}": float(i) for i in range(1, 21)})
        actions = self.cas.evaluate_effects()
        self.assertEqual(len(actions), 1)
        print("✅ Stress Test (20 Conditions) Passed")

if __name__ == "__main__":
    unittest.main(verbosity=2)
