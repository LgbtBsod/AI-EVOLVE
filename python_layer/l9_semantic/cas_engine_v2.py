"""
CAS Engine 2.0 - Conditional Advanced System
Поддержка сложных условий (PoE/Diablo style) и механик типа Sorrow of Berserk:
- if stat >= X then add Y
- if hp < 30% then crit_rate += 50%
- if enemy_has_debuff('burn') then damage *= 2.0
- Escalation mechanics (scaling with HP deficit)
- Safety Net (HP→1 + iframe)
- Kill Refresh (reset cooldowns on kill)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple, Set
from enum import Enum
import operator
import time

class ConditionType(Enum):
    STAT_GREATER = "stat_gte"
    STAT_LESS = "stat_lte"
    STAT_EQUAL = "stat_eq"
    HP_PERCENT_LESS = "hp_percent_lt"
    HP_PERCENT_GREATER = "hp_percent_gt"
    HAS_BUFF = "has_buff"
    HAS_DEBUFF = "has_debuff"
    EQUIPPED_ITEM = "has_item"
    MANA_PERCENT = "mana_percent_gt"
    HP_DEFICIT_PERCENT = "hp_deficit_pct"  # % недостающего HP
    
@dataclass
class Condition:
    type: ConditionType
    param: Any  # stat name, buff name, etc.
    value: float  # threshold value
    op: Callable = field(default=None)

    def __post_init__(self):
        if self.type == ConditionType.STAT_GREATER:
            self.op = operator.ge
        elif self.type == ConditionType.STAT_LESS:
            self.op = operator.le
        elif self.type == ConditionType.STAT_EQUAL:
            self.op = operator.eq
        elif self.type in [ConditionType.HP_PERCENT_LESS, ConditionType.HP_PERCENT_GREATER]:
            self.op = operator.lt if self.type == ConditionType.HP_PERCENT_LESS else operator.gt

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Проверка условия против контекста (статы, баффы, хп)"""
        if self.type == ConditionType.HAS_BUFF:
            return self.param in context.get('active_buffs', [])
        if self.type == ConditionType.HAS_DEBUFF:
            return self.param in context.get('active_debuffs', [])
        if self.type == ConditionType.EQUIPPED_ITEM:
            return self.param in context.get('equipped_items', [])
        
        current_val = context.get(self.param, 0)
        
        if self.type in [ConditionType.HP_PERCENT_LESS, ConditionType.HP_PERCENT_GREATER]:
            max_hp = context.get('max_hp', 1)
            cur_hp = context.get('current_hp', 1)
            percent = (cur_hp / max_hp) * 100 if max_hp > 0 else 0
            return self.op(percent, self.value)
            
        if self.type == ConditionType.HP_DEFICIT_PERCENT:
            max_hp = context.get('max_hp', 1)
            cur_hp = context.get('current_hp', 1)
            deficit_percent = ((max_hp - cur_hp) / max_hp) * 100 if max_hp > 0 else 0
            return self.op(deficit_percent, self.value)
            
        return self.op(current_val, self.value)

@dataclass
class EffectModifier:
    """Модификатор, применяемый если условие истинно"""
    target_stat: str
    operation: str    # 'add_flat', 'add_percent', 'multiply', 'set'
    value: float
    condition: Optional[Condition] = None
    scaling_per_deficit_pct: Optional[float] = None
    deficit_threshold: float = 10.0

    def apply(self, context: Dict[str, Any], current_value: float) -> float:
        if self.condition and not self.condition.evaluate(context):
            return current_value
            
        base_value = self.value
        
        if self.scaling_per_deficit_pct is not None:
            max_hp = context.get('max_hp', 1)
            cur_hp = context.get('current_hp', 1)
            deficit_percent = ((max_hp - cur_hp) / max_hp) * 100 if max_hp > 0 else 0
            thresholds_passed = int(deficit_percent / self.deficit_threshold)
            base_value += self.scaling_per_deficit_pct * thresholds_passed
        
        if self.operation == 'add_flat':
            return current_value + base_value
        elif self.operation == 'add_percent':
            return current_value * (1 + base_value / 100.0)
        elif self.operation == 'multiply':
            return current_value * base_value
        elif self.operation == 'set':
            return base_value
        return current_value

@dataclass
class ComplexEffect:
    """Сложный эффект с состоянием (Safety Net, Kill Refresh)"""
    name: str
    trigger_condition: Condition
    effects_on_trigger: List[Dict[str, Any]]
    is_active: bool = False
    last_trigger_time: float = 0.0
    cooldown: float = 30.0
    duration: float = 5.0
    sets_hp_to: Optional[float] = None
    grants_iframe: bool = False
    extends_on_kill: bool = False
    doubles_on_missing_hp: bool = False
    
    def can_trigger(self, context: Dict[str, Any]) -> bool:
        current_time = time.time()
        if current_time - self.last_trigger_time < self.cooldown:
            return False
        return self.trigger_condition.evaluate(context)
    
    def trigger(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.is_active = True
        self.last_trigger_time = time.time()
        
        changes = {'activated': True, 'effects': [], 'hp_set': None, 'iframe_granted': False}
        
        for effect in self.effects_on_trigger:
            changes['effects'].append(effect)
        
        if self.sets_hp_to is not None:
            changes['hp_set'] = self.sets_hp_to
            
        if self.grants_iframe:
            changes['iframe_granted'] = True
            if 'active_buffs' not in context:
                context['active_buffs'] = []
            context['active_buffs'].append('iframe_last_will')
        
        return changes
    
    def extend_duration(self, context: Dict[str, Any]):
        if self.is_active:
            self.last_trigger_time = time.time()
    
    def get_multiplier(self, context: Dict[str, Any]) -> float:
        if not self.doubles_on_missing_hp:
            return 1.0
        max_hp = context.get('max_hp', 1)
        cur_hp = context.get('current_hp', 1)
        missing_pct = ((max_hp - cur_hp) / max_hp) * 100 if max_hp > 0 else 0
        doublings = int(missing_pct / 10.0)
        return 2.0 ** doublings
    
    def deactivate_if_expired(self, context: Dict[str, Any]):
        if not self.is_active:
            return
        current_time = time.time()
        if current_time - self.last_trigger_time > self.duration:
            self.is_active = False
            if 'active_buffs' in context and 'iframe_last_will' in context['active_buffs']:
                context['active_buffs'].remove('iframe_last_will')

class CASSolver:
    """Решатель эффектов с поддержкой сложных механик"""
    
    def __init__(self):
        self.modifiers: List[EffectModifier] = []
        self.complex_effects: List[ComplexEffect] = []
        self.item_configs: Dict[str, Any] = {}

    def add_modifier(self, modifier: EffectModifier):
        self.modifiers.append(modifier)
    
    def add_complex_effect(self, effect: ComplexEffect):
        self.complex_effects.append(effect)
    
    def set_item_config(self, item_id: str, config: Dict[str, Any]):
        self.item_configs[item_id] = config

    def resolve_stat(self, stat_name: str, base_value: float, context: Dict[str, Any]) -> float:
        value = base_value
        
        flat_mods = [m for m in self.modifiers if m.target_stat == stat_name and m.operation == 'add_flat']
        pct_mods = [m for m in self.modifiers if m.target_stat == stat_name and m.operation == 'add_percent']
        mul_mods = [m for m in self.modifiers if m.target_stat == stat_name and m.operation == 'multiply']
        
        for mod in flat_mods:
            value = mod.apply(context, value)
        for mod in pct_mods:
            value = mod.apply(context, value)
        for mod in mul_mods:
            value = mod.apply(context, value)
            
        for effect in self.complex_effects:
            if effect.is_active:
                mult = effect.get_multiplier(context)
                for eff_data in effect.effects_on_trigger:
                    if eff_data.get('target_stat') == stat_name:
                        if eff_data['operation'] == 'add_percent':
                            value *= (1 + (eff_data['value'] * mult) / 100.0)
                        elif eff_data['operation'] == 'add_flat':
                            value += eff_data['value'] * mult
        
        return value
    
    def check_complex_triggers(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        activations = []
        for effect in self.complex_effects:
            if not effect.is_active and effect.can_trigger(context):
                changes = effect.trigger(context)
                activations.append({'effect_name': effect.name, 'changes': changes})
            elif effect.is_active:
                effect.deactivate_if_expired(context)
        return activations
    
    def on_kill_event(self, context: Dict[str, Any]) -> List[str]:
        extended = []
        for effect in self.complex_effects:
            if effect.is_active and effect.extends_on_kill:
                effect.extend_duration(context)
                extended.append(effect.name)
        return extended
    
    def calculate_blood_cost(self, context: Dict[str, Any], base_cost_pct: float = 0.5) -> Tuple[float, float]:
        max_hp = context.get('max_hp', 1)
        cur_hp = context.get('current_hp', 1)
        
        cost_pct = base_cost_pct
        damage_pct = base_cost_pct * 3
        
        hp_percent = (cur_hp / max_hp) * 100 if max_hp > 0 else 0
        
        if hp_percent < 40:
            deficit_below_40 = 40 - hp_percent
            thresholds = int(deficit_below_40 / 10)
            cost_pct += thresholds * 0.5
            damage_pct += thresholds * 1.5
        
        cost_hp = max_hp * (cost_pct / 100.0)
        damage = max_hp * (damage_pct / 100.0)
        
        return cost_hp, damage
    
    def get_debug_report(self, context: Dict[str, Any]) -> str:
        report = ["--- CAS Debug Report ---"]
        
        for i, mod in enumerate(self.modifiers):
            if mod.condition:
                passed = mod.condition.evaluate(context)
                status = "✅ PASS" if passed else "❌ FAIL"
                report.append(f"Mod #{i}: {mod.target_stat} [{mod.operation}] -> {status}")
        
        report.append("\n--- Complex Effects ---")
        for effect in self.complex_effects:
            status = "🟢 ACTIVE" if effect.is_active else "⚪ INACTIVE"
            report.append(f"{effect.name}: {status}")
            if effect.is_active:
                mult = effect.get_multiplier(context)
                report.append(f"   Multiplier: {mult}x")
                remaining = effect.duration - (time.time() - effect.last_trigger_time)
                report.append(f"   Time left: {remaining:.1f}s")
        
        return "\n".join(report)


def create_sorrow_of_berserk_config() -> Dict[str, Any]:
    """Конфигурация предмета Sorrow of Berserk"""
    return {
        'item_id': 'sorrow_of_berserk',
        'name': 'Sorrow of Berserk',
        'base_stats': {
            'max_hp_percent': 2000,
            'defense_percent': -80,
            'life_steal_percent': 20,
            'attack_speed_percent': 50,
        },
        'lost_my_self_buff': {
            'trigger_hp_percent': 40,
            'stats': {
                'strength_percent': 20,
                'stamina_percent': 10,
                'crit_rate_percent': 5,
                'crit_damage_percent': 10,
                'attack_speed_percent': 5,
            },
            'scaling_per_10pct_deficit': {
                'blood_cost_increase': 0.5,
                'blood_damage_increase': 1.5,
            }
        },
        'blood_attack': {
            'base_cost_percent': 0.5,
            'base_damage_percent': 1.5,
        },
        'safety_net': {
            'iframe_duration': 5.0,
            'cooldown': 30.0,
            'hp_set_value': 1,
        },
        'kill_refresh': {
            'extends_iframe': True,
            'extension_duration': 5.0,
        }
    }


def initialize_sorrow_of_berserk(solver: CASSolver):
    """Инициализация Sorrow of Berserk в решателе"""
    config = create_sorrow_of_berserk_config()
    solver.set_item_config('sorrow_of_berserk', config)
    
    lost_my_self_condition = Condition(
        type=ConditionType.HP_PERCENT_LESS,
        param='current_hp',
        value=40.0
    )
    
    for stat_name, stat_value in config['lost_my_self_buff']['stats'].items():
        modifier = EffectModifier(
            target_stat=stat_name,
            operation='add_percent',
            value=stat_value,
            condition=lost_my_self_condition,
            scaling_per_deficit_pct=config['lost_my_self_buff']['scaling_per_10pct_deficit'].get('blood_damage_increase', 0),
            deficit_threshold=10.0
        )
        solver.add_modifier(modifier)
    
    safety_net_condition = Condition(
        type=ConditionType.HP_PERCENT_LESS,
        param='current_hp',
        value=5.0
    )
    
    safety_net_effect = ComplexEffect(
        name='Last Will',
        trigger_condition=safety_net_condition,
        effects_on_trigger=[{'target_stat': 'iframe', 'operation': 'grant', 'value': 1}],
        cooldown=config['safety_net']['cooldown'],
        duration=config['safety_net']['iframe_duration'],
        sets_hp_to=config['safety_net']['hp_set_value'],
        grants_iframe=True,
        extends_on_kill=config['kill_refresh']['extends_iframe'],
        doubles_on_missing_hp=True
    )
    
    solver.add_complex_effect(safety_net_effect)
    
    return config
