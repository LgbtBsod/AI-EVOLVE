"""
Advanced Condition-Action System (CAS) & Effect Manager
Supports declarative templates, complex conditions, and multi-threaded damage calculation.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Callable, Optional, Tuple
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CAS_Engine")

class StatType(Enum):
    FLAT = "flat"
    PERCENT = "percent"
    SCALING = "scaling"  # e.g., % of Max HP
    
class DamageType(Enum):
    PHYSICAL = "physical"
    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    VOID = "void"

class ConditionOperator(Enum):
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    EQ = "=="
    MOD = "%"  # Divisibility check

@dataclass
class Condition:
    """Declarative condition template"""
    stat: str  # e.g., "current_hp_percent", "enemy_resist_fire"
    operator: ConditionOperator
    value: float
    target: str = "self"  # self, enemy, global

@dataclass
class Action:
    """Declarative action template"""
    type: str  # "modify_stat", "apply_effect", "trigger_event"
    stat: Optional[str] = None
    value: float = 0.0
    stat_type: StatType = StatType.FLAT
    damage_type: Optional[DamageType] = None
    duration: float = 0.0  # 0 = permanent/passive

@dataclass
class EffectTemplate:
    """Complete effect definition (Item/Skill)"""
    id: str
    name: str
    conditions: List[Condition] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    is_active: bool = False  # True if triggered by event, False if passive aura

class CASManager:
    """
    Manages active effects, evaluates conditions, and executes actions.
    Thread-safe evaluation.
    """
    def __init__(self, max_workers: int = 4):
        self.active_effects: Dict[str, EffectTemplate] = {}
        self.entity_stats: Dict[str, float] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.lock = threading.Lock()

    def register_effect(self, effect: EffectTemplate):
        with self.lock:
            self.active_effects[effect.id] = effect
            logger.info(f"[CAS] Registered effect: {effect.name}")

    def update_stats(self, stats: Dict[str, float]):
        """Thread-safe stat update"""
        with self.lock:
            self.entity_stats.update(stats)

    def _evaluate_condition(self, cond: Condition, stats: Dict[str, float]) -> bool:
        val = stats.get(cond.stat, 0.0)
        if cond.operator == ConditionOperator.GT: return val > cond.value
        if cond.operator == ConditionOperator.LT: return val < cond.value
        if cond.operator == ConditionOperator.GTE: return val >= cond.value
        if cond.operator == ConditionOperator.LTE: return val <= cond.value
        if cond.operator == ConditionOperator.EQ: return val == cond.value
        if cond.operator == ConditionOperator.MOD: return val % cond.value == 0
        return False

    def evaluate_effects(self) -> List[Action]:
        """Evaluate all active effects and return valid actions"""
        valid_actions = []
        with self.lock:
            current_stats = self.entity_stats.copy()
        
        for eff in self.active_effects.values():
            # Check if ALL conditions are met
            if all(self._evaluate_condition(c, current_stats) for c in eff.conditions):
                valid_actions.extend(eff.actions)
        
        return valid_actions

    def apply_actions(self, actions: List[Action], target_stats: Dict[str, float]) -> Dict[str, float]:
        """Apply actions to stats (simulation)"""
        new_stats = target_stats.copy()
        for act in actions:
            if act.type == "modify_stat":
                if act.stat_type == StatType.FLAT:
                    new_stats[act.stat] = new_stats.get(act.stat, 0) + act.value
                elif act.stat_type == StatType.PERCENT:
                    base = new_stats.get(act.stat.replace('_percent', '_base'), 100)
                    new_stats[act.stat] = new_stats.get(act.stat, 0) + (base * act.value / 100.0)
                elif act.stat_type == StatType.SCALING:
                    # Special logic for scaling (e.g., % Max HP)
                    source_stat = act.stat.split('_from_')[-1] if '_from_' in act.stat else 'max_hp'
                    scale_val = new_stats.get(source_stat, 1000)
                    new_stats[act.stat] = new_stats.get(act.stat, 0) + (scale_val * act.value / 100.0)
        return new_stats

# -----------------------------------------------------------------------------
# ADVANCED DAMAGE CALCULATOR (Multi-threaded)
# -----------------------------------------------------------------------------

@dataclass
class DamageProfile:
    base_physical: float = 0.0
    base_elemental: Dict[DamageType, float] = field(default_factory=dict)
    
    flat_bonus_physical: float = 0.0
    flat_bonus_elemental: Dict[DamageType, float] = field(default_factory=dict)
    
    pct_bonus_physical: float = 0.0  # e.g., +20% phys dmg
    pct_bonus_elemental: Dict[DamageType, float] = field(default_factory=dict)
    
    scaling_from_stat: Dict[str, float] = field(default_factory=dict) # e.g., {"max_hp": 1.5} -> 1.5% of Max HP
    
    crit_chance: float = 0.0
    crit_mult: float = 2.0
    
    armor_pen_flat: float = 0.0
    armor_pen_percent: float = 0.0
    resist_pen_flat: float = 0.0
    resist_pen_percent: float = 0.0

@dataclass
class DefenseProfile:
    armor: float = 0.0
    resists: Dict[DamageType, float] = field(default_factory=dict) # e.g., {FIRE: 50.0}

class DamageCalculator:
    def __init__(self, workers: int = 3):
        # Thread 1: Aggregator, Thread 2: Phys Calc, Thread 3: Elem Calc
        self.executor = ThreadPoolExecutor(max_workers=workers)

    def calculate_damage(self, profile: DamageProfile, defense: DefenseProfile, is_crit: bool = False) -> Dict[str, float]:
        """
        Returns: { 'physical': dmg, 'fire': dmg, 'total': dmg }
        """
        futures = {
            'physical': self.executor.submit(self._calc_physical, profile, defense, is_crit),
        }
        
        for elem, val in profile.base_elemental.items():
            if val > 0 or any(profile.flat_bonus_elemental.get(elem, 0) > 0 for _ in [1]):
                futures[elem.name.lower()] = self.executor.submit(self._calc_elemental, profile, defense, elem, is_crit)
        
        results = {k: f.result() for k, f in futures.items()}
        results['total'] = sum(results.values())
        return results

    def _calc_physical(self, p: DamageProfile, d: DefenseProfile, is_crit: bool) -> float:
        # 1. Base + Flat
        raw = p.base_physical + p.flat_bonus_physical
        
        # 2. Scaling (e.g., % Max HP)
        for stat, pct in p.scaling_from_stat.items():
            # Assume we fetch stat value from context in real impl, here mock 1000
            stat_val = 1000.0 
            raw += stat_val * (pct / 100.0)
            
        # 3. Percent Bonus
        raw *= (1.0 + p.pct_bonus_physical / 100.0)
        
        # 4. Crit
        if is_crit: raw *= p.crit_mult
        
        # 5. Mitigation (Armor)
        effective_armor = max(0, d.armor * (1 - p.armor_pen_percent/100) - p.armor_pen_flat)
        mitigation = effective_armor / (effective_armor + 100) # Simple formula
        final = raw * (1 - mitigation)
        
        return max(0, final)

    def _calc_elemental(self, p: DamageProfile, d: DefenseProfile, elem: DamageType, is_crit: bool) -> float:
        raw = p.base_elemental.get(elem, 0) + p.flat_bonus_elemental.get(elem, 0)
        
        # Scaling
        for stat, pct in p.scaling_from_stat.items():
             stat_val = 1000.0
             raw += stat_val * (pct / 100.0) # Simplified: same scaling for all elems
        
        # Bonus %
        bonus = p.pct_bonus_elemental.get(elem, 0)
        # Add global elemental bonus if exists
        raw *= (1.0 + bonus / 100.0)
        
        if is_crit: raw *= p.crit_mult
        
        # Mitigation (Resist)
        enemy_resist = d.resists.get(elem, 0)
        effective_resist = max(-100, min(100, enemy_resist * (1 - p.resist_pen_percent/100) - p.resist_pen_flat))
        multiplier = 1 - (effective_resist / 100.0)
        
        return max(0, raw * multiplier)
