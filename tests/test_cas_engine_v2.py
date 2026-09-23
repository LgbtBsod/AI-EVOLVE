"""
Тесты для CAS Engine 2.0 (Conditional Advanced System)
Проверка условий в стиле PoE/Diablo/Dota 2
"""

import pytest
from python_layer.l9_semantic.cas_engine_v2 import (
    ConditionType, Condition, EffectModifier, CASSolver
)

class TestConditionTypes:
    """Тесты различных типов условий"""

    def test_stat_greater_condition(self):
        """if strength >= 100 then ..."""
        cond = Condition(ConditionType.STAT_GREATER, 'strength', 100)
        
        # Условие выполняется
        context = {'strength': 150}
        assert cond.evaluate(context) is True
        
        # Условие не выполняется
        context = {'strength': 50}
        assert cond.evaluate(context) is False
        
        # Граничное значение
        context = {'strength': 100}
        assert cond.evaluate(context) is True

    def test_hp_percent_low_condition(self):
        """if hp < 30% then crit_rate += 50%"""
        cond = Condition(ConditionType.HP_PERCENT_LESS, None, 30)
        
        # Низкое HP (25%)
        context = {'current_hp': 250, 'max_hp': 1000}
        assert cond.evaluate(context) is True
        
        # Высокое HP (80%)
        context = {'current_hp': 800, 'max_hp': 1000}
        assert cond.evaluate(context) is False
        
        # Граничное (30%)
        context = {'current_hp': 300, 'max_hp': 1000}
        assert cond.evaluate(context) is False  # strict less than

    def test_has_debuff_condition(self):
        """if enemy_has_debuff('burn') then damage *= 2"""
        cond = Condition(ConditionType.HAS_DEBUFF, 'burn', 0)
        
        context = {'active_debuffs': ['burn', 'slow']}
        assert cond.evaluate(context) is True
        
        context = {'active_debuffs': ['slow', 'freeze']}
        assert cond.evaluate(context) is False

    def test_has_buff_condition(self):
        """if has_buff('rally') then armor += 100"""
        cond = Condition(ConditionType.HAS_BUFF, 'rally', 0)
        
        context = {'active_buffs': ['rally', 'haste']}
        assert cond.evaluate(context) is True
        
        context = {'active_buffs': ['haste']}
        assert cond.evaluate(context) is False

    def test_equipped_item_condition(self):
        """if has_item('apocalypse_bringer') then ..."""
        cond = Condition(ConditionType.EQUIPPED_ITEM, 'apocalypse_bringer', 0)
        
        context = {'equipped_items': ['apocalypse_bringer', 'boots']}
        assert cond.evaluate(context) is True
        
        context = {'equipped_items': ['boots', 'gloves']}
        assert cond.evaluate(context) is False


class TestEffectModifiers:
    """Тесты модификаторов эффектов"""

    def test_flat_addition_no_condition(self):
        """+50 damage без условий"""
        mod = EffectModifier('damage', 'add_flat', 50)
        result = mod.apply({}, 100)
        assert result == 150

    def test_percent_addition_with_condition_pass(self):
        """if strength >= 100 then damage += 50%"""
        cond = Condition(ConditionType.STAT_GREATER, 'strength', 100)
        mod = EffectModifier('damage', 'add_percent', 50, condition=cond)
        
        context = {'strength': 150}
        result = mod.apply(context, 100)
        assert result == 150  # 100 * 1.5

    def test_percent_addition_with_condition_fail(self):
        """Условие не выполнено - модификатор не применяется"""
        cond = Condition(ConditionType.STAT_GREATER, 'strength', 100)
        mod = EffectModifier('damage', 'add_percent', 50, condition=cond)
        
        context = {'strength': 50}
        result = mod.apply(context, 100)
        assert result == 100  # осталось как было

    def test_hp_based_crit_bonus(self):
        """if hp < 30% then crit_rate += 50%"""
        cond = Condition(ConditionType.HP_PERCENT_LESS, None, 30)
        mod = EffectModifier('crit_rate', 'add_percent', 50, condition=cond)
        
        # Низкое HP - бонус работает
        context = {'current_hp': 250, 'max_hp': 1000}
        result = mod.apply(context, 10)  # base 10% crit
        assert result == 15  # 10 * 1.5
        
        # Высокое HP - бонус не работает
        context = {'current_hp': 800, 'max_hp': 1000}
        result = mod.apply(context, 10)
        assert result == 10

    def test_debuff_based_damage_multiplier(self):
        """if enemy_has_debuff('burn') then damage *= 2"""
        cond = Condition(ConditionType.HAS_DEBUFF, 'burn', 0)
        mod = EffectModifier('damage', 'multiply', 2.0, condition=cond)
        
        context = {'active_debuffs': ['burn']}
        result = mod.apply(context, 100)
        assert result == 200
        
        context = {'active_debuffs': []}
        result = mod.apply(context, 100)
        assert result == 100


class TestCASSolver:
    """Тесты решателя эффектов"""

    def test_multiple_modifiers_same_stat(self):
        """Несколько модификаторов на один стат"""
        solver = CASSolver()
        
        # +20 flat damage
        solver.add_modifier(EffectModifier('damage', 'add_flat', 20))
        # +50% damage if strength >= 100
        cond = Condition(ConditionType.STAT_GREATER, 'strength', 100)
        solver.add_modifier(EffectModifier('damage', 'add_percent', 50, condition=cond))
        
        context = {'strength': 150}
        result = solver.resolve_stat('damage', 100, context)
        
        # Сначала flat: 100 + 20 = 120
        # Потом percent: 120 * 1.5 = 180
        assert result == 180

    def test_conditional_chain(self):
        """Цепочка условий: low HP -> high crit -> massive damage"""
        solver = CASSolver()
        
        # if hp < 30% then crit_rate += 50%
        low_hp_cond = Condition(ConditionType.HP_PERCENT_LESS, None, 30)
        solver.add_modifier(EffectModifier('crit_rate', 'add_percent', 50, condition=low_hp_cond))
        
        # if crit_rate >= 50 then damage += 100%
        # (это потребует рекурсивного решения, упростим тест)
        
        context = {'current_hp': 200, 'max_hp': 1000}  # 20% HP
        crit_result = solver.resolve_stat('crit_rate', 10, context)
        assert crit_result == 15  # 10 * 1.5

    def test_debug_report(self):
        """Проверка отладочного отчета"""
        solver = CASSolver()
        
        cond_pass = Condition(ConditionType.STAT_GREATER, 'strength', 100)
        cond_fail = Condition(ConditionType.HP_PERCENT_LESS, None, 30)
        
        solver.add_modifier(EffectModifier('damage', 'add_flat', 50, condition=cond_pass))
        solver.add_modifier(EffectModifier('crit', 'add_percent', 20, condition=cond_fail))
        
        context = {'strength': 150, 'current_hp': 800, 'max_hp': 1000}
        report = solver.get_debug_report(context)
        
        assert "Mod #0" in report
        assert "✅ PASS" in report
        assert "Mod #1" in report
        assert "❌ FAIL" in report


class TestComplexScenarios:
    """Сложные сценарии в стиле PoE/Diablo билдов"""

    def test_apocalypse_bringer_effect(self):
        """
        Apocalypse Bringer (пример из игры):
        - if strength >= 200 then damage += 100%
        - if enemy_has_debuff('burn') then damage *= 1.5
        - if hp < 50% then life_leech += 5%
        """
        solver = CASSolver()
        
        # Условие 1: сила >= 200
        str_cond = Condition(ConditionType.STAT_GREATER, 'strength', 200)
        solver.add_modifier(EffectModifier('damage', 'add_percent', 100, condition=str_cond))
        
        # Условие 2: враг горит
        burn_cond = Condition(ConditionType.HAS_DEBUFF, 'burn', 0)
        solver.add_modifier(EffectModifier('damage', 'multiply', 1.5, condition=burn_cond))
        
        # Условие 3: низкое HP
        hp_cond = Condition(ConditionType.HP_PERCENT_LESS, None, 50)
        solver.add_modifier(EffectModifier('life_leech', 'add_flat', 5, condition=hp_cond))
        
        # Тестовый контекст: все условия выполняются
        context = {
            'strength': 250,
            'active_debuffs': ['burn'],
            'current_hp': 400,
            'max_hp': 1000  # 40% HP
        }
        
        damage = solver.resolve_stat('damage', 100, context)
        # Base 100 -> +100% (str) = 200 -> *1.5 (burn) = 300
        assert damage == 300
        
        leech = solver.resolve_stat('life_leech', 0, context)
        # Base 0 -> +5 (low hp) = 5
        assert leech == 5

    def test_sorrow_of_berserk_effect(self):
        """
        Sorrow of Berserk:
        - if hp < 35% then crit_damage += 200%
        - if hp < 20% then all_damage *= 3.0
        """
        solver = CASSolver()
        
        # Условие 1: HP < 35%
        hp35_cond = Condition(ConditionType.HP_PERCENT_LESS, None, 35)
        solver.add_modifier(EffectModifier('crit_damage', 'add_percent', 200, condition=hp35_cond))
        
        # Условие 2: HP < 20%
        hp20_cond = Condition(ConditionType.HP_PERCENT_LESS, None, 20)
        solver.add_modifier(EffectModifier('damage', 'multiply', 3.0, condition=hp20_cond))
        
        # Тест при 15% HP (оба условия работают)
        context = {'current_hp': 150, 'max_hp': 1000}
        
        crit_dmg = solver.resolve_stat('crit_damage', 150, context)
        # 150 * 3.0 = 450
        assert crit_dmg == 450
        
        dmg = solver.resolve_stat('damage', 100, context)
        # 100 * 3.0 = 300
        assert dmg == 300

    def test_mana_based_scaling(self):
        """
        Mage build:
        - if mana >= 80% then spell_damage += 50%
        """
        solver = CASSolver()
        
        # Для этого теста добавим новый тип условия
        # (в реальной реализации нужно добавить MANA_PERCENT в ConditionType)
        # Пока тестируем через stat_gte с вычисленным процентом
        mana_cond = Condition(ConditionType.STAT_GREATER, 'mana_percent', 80)
        solver.add_modifier(EffectModifier('spell_damage', 'add_percent', 50, condition=mana_cond))
        
        context = {'mana_percent': 90}
        result = solver.resolve_stat('spell_damage', 100, context)
        assert result == 150
        
        context = {'mana_percent': 50}
        result = solver.resolve_stat('spell_damage', 100, context)
        assert result == 100


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
