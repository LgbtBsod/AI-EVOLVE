"""
CAS Engine 2.0 - Conditional Advanced System
Интеграция с Training Room для тестирования сложных предметов

Примеры использования:
- Apocalypse Bringer: if strength >= 200 then damage += 100%
- Sorrow of Berserk: if hp < 35% then crit_damage += 200%
- Mana Shield: if mana >= 80% then spell_damage += 50%
"""

from python_layer.l9_semantic.cas_engine_v2 import (
    ConditionType, Condition, EffectModifier, CASSolver
)

def create_apocalypse_bringer() -> CASSolver:
    """
    Создает конфигурацию предмета Apocalypse Bringer:
    - +100% урона если сила >= 200
    - x1.5 урона если враг горит
    - +5% life leech если HP < 50%
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
    
    return solver

def create_sorrow_of_berserk() -> CASSolver:
    """
    Создает конфигурацию предмета Sorrow of Berserk:
    - +200% крит урона если HP < 35%
    - x3.0 весь урон если HP < 20%
    """
    solver = CASSolver()
    
    # Условие 1: HP < 35%
    hp35_cond = Condition(ConditionType.HP_PERCENT_LESS, None, 35)
    solver.add_modifier(EffectModifier('crit_damage', 'add_percent', 200, condition=hp35_cond))
    
    # Условие 2: HP < 20%
    hp20_cond = Condition(ConditionType.HP_PERCENT_LESS, None, 20)
    solver.add_modifier(EffectModifier('damage', 'multiply', 3.0, condition=hp20_cond))
    
    return solver

def create_mage_supremacy() -> CASSolver:
    """
    Создает конфигурацию для мага:
    - +50% урона заклинаний если мана >= 80%
    - +10% каст скорости если мана >= 90%
    """
    solver = CASSolver()
    
    # Условие 1: мана >= 80%
    mana80_cond = Condition(ConditionType.STAT_GREATER, 'mana_percent', 80)
    solver.add_modifier(EffectModifier('spell_damage', 'add_percent', 50, condition=mana80_cond))
    
    # Условие 2: мана >= 90%
    mana90_cond = Condition(ConditionType.STAT_GREATER, 'mana_percent', 90)
    solver.add_modifier(EffectModifier('cast_speed', 'add_percent', 10, condition=mana90_cond))
    
    return solver

def test_item_in_training_room(item_name: str, solver: CASSolver, context: dict):
    """
    Тестирует предмет в контексте тренировочной комнаты
    
    Args:
        item_name: Название предмета
        solver: CAS решатель с эффектами предмета
        context: Контекст (статы, HP, баффы и т.д.)
    
    Returns:
        dict с результатами теста
    """
    print(f"\n{'='*60}")
    print(f"🧪 Testing: {item_name}")
    print(f"{'='*60}")
    
    # Базовые статы
    base_stats = {
        'damage': 100,
        'crit_rate': 10,
        'crit_damage': 150,
        'spell_damage': 100,
        'cast_speed': 100,
        'life_leech': 0,
    }
    
    # Вычисляем итоговые статы
    final_stats = {}
    for stat_name, base_value in base_stats.items():
        final_stats[stat_name] = solver.resolve_stat(stat_name, base_value, context)
    
    # Печатаем результаты
    print(f"\n📊 Context:")
    for key, value in context.items():
        print(f"   {key}: {value}")
    
    print(f"\n📈 Results:")
    for stat_name, final_value in final_stats.items():
        base = base_stats[stat_name]
        if final_value != base:
            change = ((final_value / base) - 1) * 100 if base > 0 else final_value
            print(f"   {stat_name}: {base} → {final_value} ({change:+.1f}%)")
        else:
            print(f"   {stat_name}: {base} (unchanged)")
    
    # Отладочный отчет
    print(f"\n🔍 CAS Debug:")
    debug_lines = solver.get_debug_report(context).split('\n')[1:]  # Skip header
    for line in debug_lines:
        print(f"   {line}")
    
    return {
        'item': item_name,
        'context': context,
        'base_stats': base_stats,
        'final_stats': final_stats,
    }

if __name__ == '__main__':
    print("🎮 CAS Engine 2.0 - Training Room Integration Demo")
    print("="*60)
    
    # Тест 1: Apocalypse Bringer при идеальных условиях
    print("\n\n📦 Test 1: Apocalypse Bringer (All conditions met)")
    apoc_solver = create_apocalypse_bringer()
    context1 = {
        'strength': 250,
        'active_debuffs': ['burn'],
        'current_hp': 400,
        'max_hp': 1000,  # 40% HP
    }
    test_item_in_training_room("Apocalypse Bringer", apoc_solver, context1)
    
    # Тест 2: Apocalypse Bringer при плохих условиях
    print("\n\n📦 Test 2: Apocalypse Bringer (No conditions met)")
    context2 = {
        'strength': 100,
        'active_debuffs': [],
        'current_hp': 800,
        'max_hp': 1000,  # 80% HP
    }
    test_item_in_training_room("Apocalypse Bringer", apoc_solver, context2)
    
    # Тест 3: Sorrow of Berserk при низком HP
    print("\n\n📦 Test 3: Sorrow of Berserk (Low HP - both conditions)")
    sorrow_solver = create_sorrow_of_berserk()
    context3 = {
        'current_hp': 150,
        'max_hp': 1000,  # 15% HP
    }
    test_item_in_training_room("Sorrow of Berserk", sorrow_solver, context3)
    
    # Тест 4: Sorrow of Berserk при среднем HP
    print("\n\n📦 Test 4: Sorrow of Berserk (Medium HP - one condition)")
    context4 = {
        'current_hp': 300,
        'max_hp': 1000,  # 30% HP
    }
    test_item_in_training_room("Sorrow of Berserk", sorrow_solver, context4)
    
    # Тест 5: Mage Supremacy
    print("\n\n📦 Test 5: Mage Supremacy (High mana)")
    mage_solver = create_mage_supremacy()
    context5 = {
        'mana_percent': 95,
    }
    test_item_in_training_room("Mage Supremacy", mage_solver, context5)
    
    print("\n\n✅ All tests completed!")
    print("="*60)
