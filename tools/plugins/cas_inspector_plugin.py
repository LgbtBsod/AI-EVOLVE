"""
Dev Probe Plugin: CAS Inspector
Allows AI agents and developers to inspect, modify, and test Condition-Action effects in real-time.
"""

import time
import json
from typing import Dict, List, Any, Optional
from dataclasses import asdict
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from core.cas_engine import CASManager, EffectTemplate, Condition, Action, StatType, DamageType, ConditionOperator

class CASInspectorPlugin:
    """
    Dev Probe Plugin for inspecting and manipulating the Condition-Action System.
    Features:
    - List all active effects
    - Inspect specific effect conditions/actions
    - Simulate stat changes to see what triggers
    - Add/Remove effects dynamically
    - Export/Import effect templates (JSON)
    """
    
    def __init__(self, probe_instance, cas_manager: Optional[CASManager] = None):
        self.probe = probe_instance
        self.cas = cas_manager or CASManager()
        self.name = "CASInspectorPlugin"
        self.version = "1.0.0"
        self.enabled = True
        
        # Metrics
        self.evaluations_count = 0
        self.last_evaluation_time = 0.0
        
    def register(self):
        """Register with Dev Probe"""
        if self.probe:
            self.probe.register_plugin(self)
        print(f"[{self.name}] v{self.version} registered")
        
    def list_effects(self) -> List[Dict[str, Any]]:
        """Return list of all registered effects"""
        effects = []
        for eff_id, eff in self.cas.active_effects.items():
            effects.append({
                "id": eff.id,
                "name": eff.name,
                "condition_count": len(eff.conditions),
                "action_count": len(eff.actions),
                "is_active": eff.is_active
            })
        return effects
    
    def inspect_effect(self, effect_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a specific effect"""
        eff = self.cas.active_effects.get(effect_id)
        if not eff:
            return None
            
        return {
            "id": eff.id,
            "name": eff.name,
            "conditions": [
                {"stat": c.stat, "op": c.operator.value, "value": c.value, "target": c.target}
                for c in eff.conditions
            ],
            "actions": [
                {"type": a.type, "stat": a.stat, "value": a.value, "stat_type": a.stat_type.value}
                for a in eff.actions
            ]
        }
    
    def simulate_trigger(self, effect_id: str, test_stats: Dict[str, float]) -> Dict[str, Any]:
        """
        Simulate stats to see if an effect would trigger.
        Returns which conditions pass/fail.
        """
        eff = self.cas.active_effects.get(effect_id)
        if not eff:
            return {"error": "Effect not found"}
            
        results = {
            "effect_id": effect_id,
            "all_conditions_met": True,
            "condition_results": [],
            "would_trigger_actions": []
        }
        
        for cond in eff.conditions:
            val = test_stats.get(cond.stat, 0.0)
            passed = self.cas._evaluate_condition(cond, test_stats)
            results["condition_results"].append({
                "stat": cond.stat,
                "operator": cond.operator.value,
                "required": cond.value,
                "actual": val,
                "passed": passed
            })
            if not passed:
                results["all_conditions_met"] = False
                
        if results["all_conditions_met"]:
            results["would_trigger_actions"] = [
                {"type": a.type, "stat": a.stat, "value": a.value}
                for a in eff.actions
            ]
            
        return results
    
    def add_effect_from_json(self, json_str: str) -> bool:
        """Dynamically add an effect from JSON definition"""
        try:
            data = json.loads(json_str)
            
            conditions = [
                Condition(
                    stat=c["stat"],
                    operator=ConditionOperator(c["operator"]),
                    value=c["value"],
                    target=c.get("target", "self")
                )
                for c in data.get("conditions", [])
            ]
            
            actions = [
                Action(
                    type=a["type"],
                    stat=a.get("stat"),
                    value=a.get("value", 0.0),
                    stat_type=StatType(a.get("stat_type", "flat")),
                    duration=a.get("duration", 0.0)
                )
                for a in data.get("actions", [])
            ]
            
            effect = EffectTemplate(
                id=data["id"],
                name=data["name"],
                conditions=conditions,
                actions=actions,
                is_active=data.get("is_active", False)
            )
            
            self.cas.register_effect(effect)
            return True
        except Exception as e:
            print(f"[{self.name}] Error adding effect: {e}")
            return False
    
    def export_effects(self) -> str:
        """Export all effects as JSON"""
        export_data = []
        for eff in self.cas.active_effects.values():
            export_data.append({
                "id": eff.id,
                "name": eff.name,
                "is_active": eff.is_active,
                "conditions": [
                    {"stat": c.stat, "operator": c.operator.value, "value": c.value, "target": c.target}
                    for c in eff.conditions
                ],
                "actions": [
                    {"type": a.type, "stat": a.stat, "value": a.value, "stat_type": a.stat_type.value}
                    for a in eff.actions
                ]
            })
        return json.dumps(export_data, indent=2)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Return plugin metrics"""
        return {
            "plugin_name": self.name,
            "version": self.version,
            "active_effects_count": len(self.cas.active_effects),
            "evaluations_performed": self.evaluations_count,
            "last_evaluation_ms": self.last_evaluation_time
        }
    
    def run_evaluation_benchmark(self, iterations: int = 1000) -> float:
        """Benchmark condition evaluation speed"""
        start = time.perf_counter()
        
        test_stats = {
            "hp_percent": 25.0,
            "attack_power": 150.0,
            "buff_active": 1.0
        }
        
        for _ in range(iterations):
            self.cas.update_stats(test_stats)
            self.cas.evaluate_effects()
            self.evaluations_count += 1
            
        end = time.perf_counter()
        self.last_evaluation_time = (end - start) * 1000  # ms
        return self.last_evaluation_time


# Example Usage for AI Agents
if __name__ == "__main__":
    # Mock probe instance
    class MockProbe:
        def register_plugin(self, plugin): pass
    
    plugin = CASInspectorPlugin(MockProbe())
    
    # Add Apocalypse Bringer via JSON
    apocalypse_json = '''
    {
        "id": "apocalypse_test",
        "name": "Apocalypse Bringer (Test)",
        "conditions": [
            {"stat": "hp_percent", "operator": "<=", "value": 40.0},
            {"stat": "kills", "operator": ">=", "value": 5.0}
        ],
        "actions": [
            {"type": "modify_stat", "stat": "dmg_percent", "value": 50.0, "stat_type": "percent"},
            {"type": "modify_stat", "stat": "bonus_from_hp", "value": 2.0, "stat_type": "scaling"}
        ]
    }
    '''
    
    plugin.add_effect_from_json(apocalypse_json)
    
    # Simulate trigger
    result = plugin.simulate_trigger("apocalypse_test", {"hp_percent": 35.0, "kills": 10.0})
    print("Simulation Result:", json.dumps(result, indent=2))
    
    # Benchmark
    ms = plugin.run_evaluation_benchmark(10000)
    print(f"Benchmark: {ms:.2f}ms for 10k evaluations ({10000/(ms/1000):.0f} evals/sec)")
