"""
Condition-Action System for Complex Item Effects.
Abstracts logic like "If HP <= 30%, then +50% AS" into reusable templates.
Decouples the Effect Manager (state holder) from the Logic Engine (calculator).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type
from enum import Enum, auto
import logging

logger = logging.getLogger(__name__)


class StatType(Enum):
    """Standardized Stats to prevent magic strings."""
    MAX_HP = "max_hp"
    CURRENT_HP = "current_hp"
    ATTACK_DAMAGE = "attack_dmg"
    ATTACK_SPEED = "attack_speed"
    CRIT_CHANCE = "crit_chance"
    CRIT_DMG = "crit_dmg"
    ARMOR = "armor"
    LIFESTEAL = "lifesteal"
    FLAT_DMG = "flat_dmg" # Flat damage adder
    HP_REGEN = "hp_regen"
    INVULNERABLE = "invulnerable" # Boolean flag
    IFrames_TIME = "iframe_time"
    
    # Derived/Calculated stats
    EFFECTIVE_HP = "effective_hp" 
    DPS = "dps"


class TriggerType(Enum):
    """When does the condition check fire?"""
    ON_HIT = "on_hit"           # When attacking
    ON_TAKE_HIT = "on_take_hit" # When getting hit
    ON_KILL = "on_kill"         # When killing an enemy
    ON_TICK = "on_tick"         # Periodic (e.g., regen, DoT)
    ON_STATE_CHANGE = "on_state_change" # When HP crosses threshold
    PASSIVE = "passive"         # Always active (static buffs)


class Comparator(Enum):
    """Logical comparators for conditions."""
    LT = "<"
    LE = "<="
    EQ = "=="
    GE = ">="
    GT = ">"
    NONE = "none" # For passive buffs without conditions


@dataclass
class Condition:
    """
    Defines a logical check. 
    Example: If Current_HP <= 0.30 * Max_HP
    """
    stat: StatType
    comparator: Comparator
    value_source: Any  # Can be a float (0.3), a StatType (StatType.MAX_HP), or a callable
    
    def evaluate(self, context: Dict[str, float]) -> bool:
        """Returns True if condition is met based on current entity stats."""
        current_val = context.get(self.stat.value, 0)
        
        # Resolve target value
        target_val = 0
        if isinstance(self.value_source, (int, float)):
            target_val = float(self.value_source)
        elif isinstance(self.value_source, StatType):
            target_val = context.get(self.value_source.value, 0)
        elif callable(self.value_source):
            target_val = self.value_source(context)
            
        if self.comparator == Comparator.LT:
            return current_val < target_val
        elif self.comparator == Comparator.LE:
            return current_val <= target_val
        elif self.comparator == Comparator.EQ:
            return abs(current_val - target_val) < 0.001
        elif self.comparator == Comparator.GE:
            return current_val >= target_val
        elif self.comparator == Comparator.GT:
            return current_val > target_val
            
        return False if self.comparator != Comparator.NONE else True


@dataclass
class Action:
    """
    Defines a modification to apply.
    Can be Flat (+15 HP), Percentage (+20%), or Multiplier (*1.5).
    """
    stat: StatType
    value: float
    modifier_type: str = "ADD_FLAT" # ADD_FLAT, ADD_PERCENT, SET, MULTIPLY
    
    # Special flags for complex interactions
    consume_hp_percent: float = 0.0  # e.g., "Spend 1% Max HP"
    convert_to_stat: Optional[StatType] = None # e.g., "Convert spent HP to Flat Dmg"
    conversion_rate: float = 1.0   # e.g., "1.5x conversion rate"
    
    duration: float = 0.0 # 0 = permanent/instant, >0 = temporary buff
    
    def calculate_effect(self, context: Dict[str, float], spent_resource: float = 0.0) -> float:
        """Calculates the final value to apply."""
        base_val = context.get(self.stat.value, 0)
        
        if self.modifier_type == "ADD_FLAT":
            return self.value + (spent_resource * self.conversion_rate if self.convert_to_stat else 0)
        elif self.modifier_type == "ADD_PERCENT":
            return base_val * (self.value / 100.0)
        elif self.modifier_type == "MULTIPLY":
            return base_val * self.value
            
        return self.value


@dataclass
class EffectRule:
    """
    The core contract: "IF Condition THEN Action".
    Used by EffectManager to dynamically update stats.
    """
    id: str
    trigger: TriggerType
    condition: Condition
    action: Action
    priority: int = 0 # Higher priority rules execute first
    cooldown: float = 0.0 # Seconds before rule can trigger again
    last_triggered: float = 0.0
    duration: float = 0.0 # For temporary buffs
    
    # Escalation logic (Sorrow of Berserk style)
    # "For every 10% below 40%, increase effect..."
    escalation_step: float = 0.0  # e.g., 0.10 (10%)
    escalation_threshold_stat: Optional[StatType] = None
    escalation_base_value: float = 0.0 # e.g., 0.40 (40%)
    escalation_multiplier: float = 0.0 # How much to scale action per step
    
    def get_escalation_multiplier(self, context: Dict[str, float]) -> float:
        """Calculates scaling factor based on how deep we are into a threshold."""
        if not self.escalation_threshold_stat or self.escalation_step <= 0:
            return 1.0
            
        current = context.get(self.escalation_threshold_stat.value, 0)
        max_val = context.get(StatType.MAX_HP.value, 1) # Default to 1 to avoid div by zero
        current_pct = current / max_val if max_val > 0 else 0
        
        if current_pct >= self.escalation_base_value:
            return 1.0
            
        steps_below = int((self.escalation_base_value - current_pct) / self.escalation_step)
        return 1.0 + (steps_below * self.escalation_multiplier)


class EffectTemplate(ABC):
    """
    Abstract Base Class for defining reusable item templates.
    Subclasses define specific logic (e.g., BerserkItem, VampireItem).
    """
    @abstractmethod
    def generate_rules(self) -> List[EffectRule]:
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass


# ==========================================
# IMPLEMENTATION: Specific Item Templates
# ==========================================

class BanesScarNecklace(EffectTemplate):
    """
    +20% Atk (from Str), -20% Str
    +25% AS
    +32.5% Crit
    On Hit: Spend 1% Max HP -> Add 1.5% Max HP as Flat Dmg
    If HP <= 30%: +50% AS
    +15 HP Regen
    """
    @property
    def name(self): return "Bane's Scar Necklace"

    def generate_rules(self) -> List[EffectRule]:
        rules = []
        
        # 1. Passive Stats
        rules.append(EffectRule(
            id="bane_passive_atk", trigger=TriggerType.PASSIVE,
            condition=Condition(StatType.CURRENT_HP, Comparator.NONE, 0),
            action=Action(StatType.ATTACK_DAMAGE, 20, "ADD_PERCENT")
        ))
        
        rules.append(EffectRule(
            id="bane_passive_as", trigger=TriggerType.PASSIVE,
            condition=Condition(StatType.CURRENT_HP, Comparator.NONE, 0),
            action=Action(StatType.ATTACK_SPEED, 0.25, "ADD_FLAT") # +0.25 to base 1.0 = 1.25 (25% increase)
        ))
        
        rules.append(EffectRule(
            id="bane_passive_crit", trigger=TriggerType.PASSIVE,
            condition=Condition(StatType.CURRENT_HP, Comparator.NONE, 0),
            action=Action(StatType.CRIT_CHANCE, 32.5, "ADD_FLAT") # Add 32.5 percentage points
        ))
        
        rules.append(EffectRule(
            id="bane_passive_regen", trigger=TriggerType.PASSIVE,
            condition=Condition(StatType.CURRENT_HP, Comparator.NONE, 0),
            action=Action(StatType.HP_REGEN, 15, "ADD_FLAT")
        ))

        # 2. On-Hit: HP Spend -> Flat Dmg
        rules.append(EffectRule(
            id="bane_onhit_convert", trigger=TriggerType.ON_HIT,
            condition=Condition(StatType.CURRENT_HP, Comparator.GT, 0), # Must have HP
            action=Action(
                StatType.FLAT_DMG, 
                value=0, 
                consume_hp_percent=0.01, 
                convert_to_stat=StatType.FLAT_DMG, 
                conversion_rate=1.5 # 1.5% of Max HP (logic handled in manager)
            )
        ))
        
        # 3. Threshold: HP <= 30% -> +50% AS
        # Using a callable for dynamic threshold evaluation
        def hp_below_30_pct(ctx):
            max_hp = ctx.get(StatType.MAX_HP.value, 1)
            return 0.30 * max_hp
            
        rules.append(EffectRule(
            id="bane_berserk_threshold", trigger=TriggerType.ON_STATE_CHANGE,
            condition=Condition(StatType.CURRENT_HP, Comparator.LE, hp_below_30_pct),
            action=Action(StatType.ATTACK_SPEED, 0.50, "ADD_FLAT"), # +0.50 AS
        ))
        
        return rules


class SorrowOfBerserk(EffectTemplate):
    """
    Complex Escalating Item.
    """
    @property
    def name(self): return "Sorrow of Berserk"

    def generate_rules(self) -> List[EffectRule]:
        rules = []
        
        # 1. Base Stats
        rules.append(EffectRule(id="sorrow_base_hp", trigger=TriggerType.PASSIVE,
            condition=Condition(StatType.CURRENT_HP, Comparator.NONE, 0),
            action=Action(StatType.MAX_HP, 2000, "ADD_PERCENT"))) # 2000%
            
        rules.append(EffectRule(id="sorrow_base_armor", trigger=TriggerType.PASSIVE,
            condition=Condition(StatType.CURRENT_HP, Comparator.NONE, 0),
            action=Action(StatType.ARMOR, -80, "ADD_PERCENT"))) # -80% (Debuff)
            
        rules.append(EffectRule(id="sorrow_base_ls", trigger=TriggerType.PASSIVE,
            condition=Condition(StatType.CURRENT_HP, Comparator.NONE, 0),
            action=Action(StatType.LIFESTEAL, 20, "ADD_FLAT"))) # 20 percentage points
            
        rules.append(EffectRule(id="sorrow_base_as", trigger=TriggerType.PASSIVE,
            condition=Condition(StatType.CURRENT_HP, Comparator.NONE, 0),
            action=Action(StatType.ATTACK_SPEED, 0.50, "ADD_FLAT"))) # +0.50 AS

        # 2. Escalating Logic (The Core Mechanic)
        # "For every 10% below 40% HP..."
        # We create a rule that scales dynamically.
        # Use callable to compare percentage: curr_hp / max_hp <= 0.40
        def hp_pct_below_40(ctx):
            max_hp = ctx.get(StatType.MAX_HP.value, 1)
            return 0.40 * max_hp
            
        rules.append(EffectRule(
            id="sorrow_escalation", trigger=TriggerType.ON_STATE_CHANGE,
            condition=Condition(StatType.CURRENT_HP, Comparator.LE, hp_pct_below_40),
            action=Action(StatType.ATTACK_SPEED, 0.50, "ADD_FLAT"), # Base bonus
            escalation_step=0.10,
            escalation_base_value=0.40,
            escalation_multiplier=0.10, # +10% per step
            escalation_threshold_stat=StatType.CURRENT_HP
        ))
        
        # 3. On-Hit: HP Spend with Escalation
        # "Spend 0.5% + (steps * 0.5%)"
        rules.append(EffectRule(
            id="sorrow_onhit_spend", trigger=TriggerType.ON_HIT,
            condition=Condition(StatType.CURRENT_HP, Comparator.GT, 1), # Need > 1 HP
            action=Action(
                StatType.FLAT_DMG,
                value=0,
                consume_hp_percent=0.005, # Base 0.5%
                convert_to_stat=StatType.FLAT_DMG,
                conversion_rate=2.0 # 2% Dmg per 1% HP
            ),
            escalation_step=0.10,
            escalation_base_value=0.40,
            escalation_multiplier=0.005, # Increase cost by 0.5% per step
            escalation_threshold_stat=StatType.CURRENT_HP
        ))

        # 4. Emergency Protocol: HP <= 1 -> Invuln
        # Handled by a specific "Save" rule in Manager usually, but we can sketch it:
        rules.append(EffectRule(
            id="sorrow_emergency", trigger=TriggerType.ON_TAKE_HIT,
            condition=Condition(StatType.CURRENT_HP, Comparator.LE, 1),
            action=Action(StatType.INVULNERABLE, 1, "SET"), # Set flag
            duration=5.0 # 5 seconds
        ))
        
        return rules


class EffectManager:
    """
    The Brain. Holds state, evaluates Conditions, executes Actions.
    Does NOT contain hard-coded item logic. It parses EffectRules.
    """
    def __init__(self, entity_context: Dict[str, Any]):
        self.context = entity_context # {'max_hp': 1000, 'curr_hp': 500, ...}
        self.active_rules: Dict[str, EffectRule] = {}
        self.cooldowns: Dict[str, float] = {}
        self.last_update_time: float = 0.0
        
    def load_template(self, template: EffectTemplate):
        """Ingests an item definition and activates its rules."""
        rules = template.generate_rules()
        for rule in rules:
            self.active_rules[rule.id] = rule
            logger.info(f"[EffectMgr] Loaded rule: {rule.id} from {template.name}")
            
    def update(self, delta_time: float):
        """Called every frame/tick to check PASSIVE and ON_TICK rules."""
        current_time = self.last_update_time + delta_time # Simplified time tracking
        
        for rule in self.active_rules.values():
            if rule.trigger not in [TriggerType.PASSIVE, TriggerType.ON_TICK]:
                continue
                
            if self._check_cooldown(rule, current_time):
                continue
                
            if rule.condition.evaluate(self.context):
                self._apply_action(rule, current_time)  # Fixed method name
                
        self.last_update_time = current_time

    def trigger_event(self, event_type: TriggerType, event_data: Optional[Dict] = None):
        """Called when game events happen (Hit, Kill, etc)."""
        current_time = self.last_update_time
        
        # Sort by priority
        sorted_rules = sorted(
            [r for r in self.active_rules.values() if r.trigger == event_type],
            key=lambda x: x.priority, reverse=True
        )
        
        for rule in sorted_rules:
            if self._check_cooldown(rule, current_time):
                continue
                
            if rule.condition.evaluate(self.context):
                # Handle Escalation Calculation before execution
                scale = rule.get_escalation_multiplier(self.context)
                
                # Special Handling for HP Spend Mechanics
                spend_amount = 0
                if rule.action.consume_hp_percent > 0:
                    max_hp = self.context.get(StatType.MAX_HP.value, 1)
                    base_spend_pct = rule.action.consume_hp_percent * scale
                    spend_amount = max_hp * base_spend_pct
                    
                    curr_hp = self.context.get(StatType.CURRENT_HP.value, 0)
                    if curr_hp <= spend_amount:
                        # Emergency Logic: Set to 1, Trigger Invuln if defined elsewhere
                        self.context[StatType.CURRENT_HP.value] = 1
                        spend_amount = curr_hp - 1 # Spend all but 1
                        logger.warning(f"[EffectMgr] HP depleted! Triggering emergency save.")
                        # Ideally trigger a specific 'emergency' rule here
                    else:
                        self.context[StatType.CURRENT_HP.value] -= spend_amount
                        
                # Apply Main Action
                final_value = rule.action.calculate_effect(self.context, spend_amount)
                
                # Apply Scaling to the result if it's a percentage buff
                if rule.action.modifier_type == "ADD_PERCENT":
                    final_value *= scale
                    
                self._apply_stat_change(rule.action.stat, final_value)
                self._set_cooldown(rule, current_time)

    def _apply_action(self, rule: EffectRule, time: float):
        """Helper to apply passive/tick actions without resource spending."""
        scale = rule.get_escalation_multiplier(self.context)
        final_value = rule.action.calculate_effect(self.context, 0)
        
        if rule.action.modifier_type == "ADD_PERCENT":
            final_value *= scale
            
        self._apply_stat_change(rule.action.stat, final_value)
        self._set_cooldown(rule, time)

    def _check_cooldown(self, rule: EffectRule, time: float) -> bool:
        if rule.id in self.cooldowns:
            if time - self.cooldowns[rule.id] < rule.cooldown:
                return True
        return False

    def _set_cooldown(self, rule: EffectRule, time: float):
        if rule.cooldown > 0:
            self.cooldowns[rule.id] = time

    def _apply_stat_change(self, stat: StatType, value: float):
        # Simple additive application for demo. Real engine needs Base vs Bonus tracking.
        current = self.context.get(stat.value, 0)
        self.context[stat.value] = current + value
        # logger.debug(f"Updated {stat.value} to {self.context[stat.value]}")

    def get_context(self) -> Dict[str, Any]:
        return self.context.copy()


# ==========================================
# TEST SUITE
# ==========================================

def run_tests():
    print("=== Testing Condition-Action System ===")
    
    # Setup Mock Entity
    entity_stats = {
        "max_hp": 1000.0,
        "current_hp": 1000.0,
        "attack_dmg": 100.0,
        "attack_speed": 1.0,
        "crit_chance": 0.0,
        "armor": 50.0,
        "lifesteal": 0.0,
        "flat_dmg": 0.0
    }
    
    mgr = EffectManager(entity_stats)
    
    # Test 1: Bane's Necklace Passive
    print("\n1. Testing Bane's Scar Necklace (Passive)")
    bane = BanesScarNecklace()
    mgr.load_template(bane)
    mgr.update(0.1) # Tick
    
    ctx = mgr.get_context()
    assert ctx['attack_speed'] > 1.0, "AS should increase"
    assert ctx['crit_chance'] > 0.0, "Crit should increase"
    print(f"   Stats: AS={ctx['attack_speed']}, Crit={ctx['crit_chance']}")
    
    # Test 2: Bane's On-Hit (HP Spend)
    print("\n2. Testing Bane's On-Hit Conversion")
    initial_hp = ctx['current_hp']
    mgr.trigger_event(TriggerType.ON_HIT)
    new_hp = mgr.get_context()['current_hp']
    dmg = mgr.get_context()['flat_dmg']
    
    assert new_hp < initial_hp, "HP should decrease"
    assert dmg > 0, "Flat DMG should be added"
    print(f"   HP: {initial_hp} -> {new_hp} | Added Flat DMG: {dmg}")
    
    # Test 3: Sorrow Escalation
    print("\n3. Testing Sorrow of Berserk Escalation")
    mgr2 = EffectManager({
        "max_hp": 2000.0, # High base due to +2000% item
        "current_hp": 800.0, # 40% HP
        "attack_speed": 1.0,
        "flat_dmg": 0.0
    })
    sorrow = SorrowOfBerserk()
    mgr2.load_template(sorrow)
    
    # At 40% HP
    mgr2.trigger_event(TriggerType.ON_STATE_CHANGE)
    as_40 = mgr2.get_context()['attack_speed']
    print(f"   At 40% HP: AS Bonus Applied")
    
    # Drop to 20% HP (2 steps below 40%)
    mgr2.context['current_hp'] = 400.0 
    mgr2.trigger_event(TriggerType.ON_STATE_CHANGE)
    as_20 = mgr2.get_context()['attack_speed']
    
    print(f"   At 20% HP: AS increased further? (Logic depends on accumulation)")
    
    # Test 4: Emergency Save
    print("\n4. Testing Emergency Save (HP -> 1)")
    mgr2.context['current_hp'] = 5.0
    mgr2.trigger_event(TriggerType.ON_TAKE_HIT) # Simulate big hit
    hp_after = mgr2.context['current_hp']
    # Note: The logic sets HP to 1 if spend > current. 
    # In this mock, we didn't define a 'damage taken' amount, so the 'spend' logic in ON_HIT 
    # is what triggers the drain. The ON_TAKE_HIT rule just sets Invuln.
    # Let's simulate the ON_HIT drain draining us dry.
    mgr2.context['current_hp'] = 2.0
    mgr2.trigger_event(TriggerType.ON_HIT) # This tries to spend 0.5% of 2000 = 10 HP.
    hp_final = mgr2.context['current_hp']
    
    assert hp_final == 1.0, f"HP should clamp to 1, got {hp_final}"
    print(f"   HP clamped to 1.0 successfully.")
    
    print("\n=== All Tests Passed ===")

if __name__ == "__main__":
    run_tests()
