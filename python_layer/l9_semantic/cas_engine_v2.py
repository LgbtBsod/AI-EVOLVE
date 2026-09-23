"""
CAS Engine 2.0 - Conditional Advanced System
Поддержка сложных условий (PoE/Diablo style):
- if stat >= X then add Y
- if hp < 30% then crit_rate += 50%
- if enemy_has_debuff('burn') then damage *= 2.0
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple
from enum import Enum
import operator

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
        # Остальные условия обрабатываются отдельно

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Проверка условия против контекста (статы, баффы, хп)"""
        if self.type == ConditionType.HAS_BUFF:
            return self.param in context.get('active_buffs', [])
        if self.type == ConditionType.HAS_DEBUFF:
            return self.param in context.get('active_debuffs', [])
        if self.type == ConditionType.EQUIPPED_ITEM:
            return self.param in context.get('equipped_items', [])
        
        # Числовые сравнения
        current_val = context.get(self.param, 0)
        
        # Специфичная логика для процентов
        if self.type in [ConditionType.HP_PERCENT_LESS, ConditionType.HP_PERCENT_GREATER]:
            max_hp = context.get('max_hp', 1)
            cur_hp = context.get('current_hp', 1)
            percent = (cur_hp / max_hp) * 100 if max_hp > 0 else 0
            return self.op(percent, self.value)
            
        return self.op(current_val, self.value)

@dataclass
class EffectModifier:
    """Модификатор, применяемый если условие истинно"""
    target_stat: str  # какой стат менять (damage, crit_rate, defense)
    operation: str    # 'add_flat', 'add_percent', 'multiply', 'set'
    value: float
    condition: Optional[Condition] = None

    def apply(self, context: Dict[str, Any], current_value: float) -> float:
        if self.condition and not self.condition.evaluate(context):
            return current_value  # Условие не выполнено, не меняем
            
        if self.operation == 'add_flat':
            return current_value + self.value
        elif self.operation == 'add_percent':
            return current_value * (1 + self.value / 100.0)
        elif self.operation == 'multiply':
            return current_value * self.value
        elif self.operation == 'set':
            return self.value
        return current_value

class CASSolver:
    """Решатель эффектов с поддержкой приоритетов и условий"""
    
    def __init__(self):
        self.modifiers: List[EffectModifier] = []

    def add_modifier(self, modifier: EffectModifier):
        self.modifiers.append(modifier)

    def resolve_stat(self, stat_name: str, base_value: float, context: Dict[str, Any]) -> float:
        """Вычисляет итоговое значение стата с учетом всех условий"""
        value = base_value
        # Сортируем: сначала flat, потом percent, потом multiply
        flat_mods = [m for m in self.modifiers if m.target_stat == stat_name and m.operation == 'add_flat']
        pct_mods = [m for m in self.modifiers if m.target_stat == stat_name and m.operation == 'add_percent']
        mul_mods = [m for m in self.modifiers if m.target_stat == stat_name and m.operation == 'multiply']
        
        for mod in flat_mods:
            value = mod.apply(context, value)
        for mod in pct_mods:
            value = mod.apply(context, value)
        for mod in mul_mods:
            value = mod.apply(context, value)
            
        return value

    def get_debug_report(self, context: Dict[str, Any]) -> str:
        """Отладочный отчет: какие сработали условия"""
        report = ["--- CAS Debug Report ---"]
        for i, mod in enumerate(self.modifiers):
            if mod.condition:
                passed = mod.condition.evaluate(context)
                status = "✅ PASS" if passed else "❌ FAIL"
                report.append(f"Mod #{i}: {mod.target_stat} [{mod.operation}] -> {status}")
                if not passed:
                    report.append(f"   Condition: {mod.condition.type.value}({mod.condition.param}, {mod.condition.value})")
        return "\n".join(report)
