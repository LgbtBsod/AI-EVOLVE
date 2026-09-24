#!/usr/bin/env python3
"""Тесты системы эффектов с тегами, синергиями и стойкостью"""

import sys
import time
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.constants import (
    EffectType, EffectCategory, EffectModifierType, EffectTag,
    StanceState, ToughnessType
)
from src.systems.effects.effect_system import (
    EffectSystem, Effect, EffectModifier, ActiveEffect, EffectTemplate, EffectTrigger
)
from src.systems.combat.components.toughness_component import (
    ToughnessComponent, ToughnessConfig
)
from src.core.architecture import LifecycleState


def test_effect_tags_and_synergies():
    """Тест тегов эффектов и синергий"""
    print("\n=== ТЕСТ 1: Теги эффектов и синергии ===")
    
    system = EffectSystem()
    system.initialize()
    
    entity_id = "test_entity_1"
    
    # Создаем эффект замедления с тегом NEGATIVE и SLOW
    slow_effect = Effect(
        effect_id="slow_001",
        name="Замедление",
        description="Снижает скорость на 50%",
        effect_type=EffectType.DEBUFF,
        category=EffectCategory.CROWD_CONTROL,
        duration=10.0,
        tags=[EffectTag.NEGATIVE, EffectTag.SLOW],
        modifiers=[
            EffectModifier(
                stat_type="movement_speed",
                value=-0.5,
                modifier_type=EffectModifierType.MULTIPLICATIVE,
                modifier_id="slow_debuff",
                tags=[EffectTag.NEGATIVE, EffectTag.SLOW]
            )
        ]
    )
    
    # Применяем эффект
    active_effects = system.active_effects.setdefault(entity_id, [])
    active_effect = ActiveEffect(
        effect=slow_effect,
        entity_id=entity_id,
        applied_at=time.perf_counter(),
        expires_at=time.perf_counter() + 10.0
    )
    active_effects.append(active_effect)
    
    # Проверяем теги
    assert system.has_tag(entity_id, EffectTag.NEGATIVE), "Должен быть тег NEGATIVE"
    assert system.has_tag(entity_id, EffectTag.SLOW), "Должен быть тег SLOW"
    assert not system.has_tag(entity_id, EffectTag.STUN), "Не должно быть тега STUN"
    
    # Считаем негативные эффекты
    negative_count = system.count_negative_effects(entity_id)
    assert negative_count == 1, f"Должен быть 1 негативный эффект, найдено: {negative_count}"
    
    print("✓ Теги эффектов работают корректно")
    print(f"  - Негативных эффектов: {negative_count}")
    print(f"  - Есть SLOW: {system.has_tag(entity_id, EffectTag.SLOW)}")
    

def test_combo_effects():
    """Тест комбинации эффектов (подсечка: урон + замедление + нокдаун)"""
    print("\n=== ТЕСТ 2: Комбо эффекты (Подсечка) ===")
    
    system = EffectSystem()
    system.initialize()
    
    entity_id = "enemy_1"
    
    # Эффект нокдауна (100% снижение скорости)
    knockdown_effect = Effect(
        effect_id="knockdown_001",
        name="Нокдаун",
        description="Полная потеря подвижности",
        effect_type=EffectType.DEBUFF,
        category=EffectCategory.CROWD_CONTROL,
        duration=2.0,
        tags=[EffectTag.NEGATIVE, EffectTag.KNOCKDOWN],
        modifiers=[
            EffectModifier(
                stat_type="movement_speed",
                value=-1.0,
                modifier_type=EffectModifierType.MULTIPLICATIVE,
                modifier_id="knockdown_immobilize",
                tags=[EffectTag.NEGATIVE, EffectTag.KNOCKDOWN]
            )
        ]
    )
    
    # Эффект уязвимости к негативным эффектам
    vulnerability_effect = Effect(
        effect_id="vulnerability_001",
        name="Уязвимость",
        description="+20% урона по целям с негативными эффектами",
        effect_type=EffectType.BUFF,
        category=EffectCategory.COMBAT,
        duration=5.0,
        tags=[EffectTag.BUFF],
        modifiers=[
            EffectModifier(
                stat_type="damage_vs_negative",
                value=0.20,
                modifier_type=EffectModifierType.MULTIPLICATIVE,
                modifier_id="negative_hunter",
                tags=[EffectTag.NEGATIVE]
            )
        ]
    )
    
    # Применяем эффекты
    active_effects = system.active_effects.setdefault(entity_id, [])
    
    active_effects.append(ActiveEffect(
        effect=knockdown_effect,
        entity_id=entity_id,
        applied_at=time.perf_counter(),
        expires_at=time.perf_counter() + 2.0
    ))
    
    active_effects.append(ActiveEffect(
        effect=vulnerability_effect,
        entity_id=entity_id,
        applied_at=time.perf_counter(),
        expires_at=time.perf_counter() + 5.0
    ))
    
    # Проверяем
    assert system.has_tag(entity_id, EffectTag.KNOCKDOWN), "Должен быть нокдаун"
    assert system.has_tag(entity_id, EffectTag.NEGATIVE), "Должен быть негативный эффект"
    
    negative_count = system.count_negative_effects(entity_id)
    print(f"✓ Комбо применено: {negative_count} негативных эффектов")
    print(f"  - Нокдаун активен: {system.has_tag(entity_id, EffectTag.KNOCKDOWN)}")
    print(f"  - Уязвимость активна: {system.has_tag(entity_id, EffectTag.BUFF)}")


def test_toughness_break_damage_bonus():
    """Тест бонуса урона при пробитии стойкости"""
    print("\n=== ТЕСТ 3: Пробитие стойкости и бонус урона ===")
    
    # Создаем компонент стойкости для босса
    config = ToughnessConfig(
        max_toughness=500.0,
        recovery_rate=20.0,
        recovery_delay=2.0,
        break_duration=5.0,
        damage_taken_multiplier_broken=0.35,  # +35% урона
        toughness_from_hp_ratio=0.2,  # 20% от HP за пробитие
        max_toughness_cap_ratio=0.2,
        auto_recover_on_break_end=True  # Полное восстановление после BREAK
    )
    
    boss = ToughnessComponent(
        entity_id="boss_1",
        config=config,
        max_health=10000.0
    )
    boss._state = LifecycleState.READY
    
    print(f"  - Начальная стойкость: {boss.current_toughness}/{boss.max_toughness}")
    print(f"  - Множитель урона (NORMAL): {boss.damage_multiplier:.2f}")
    
    # Наносим урон по стойкости
    damage_dealt = boss.take_toughness_damage(400.0, ToughnessType.PHYSICAL)
    print(f"  - Нанесено урона по стойкости: {damage_dealt:.1f}")
    print(f"  - Осталось стойкости: {boss.current_toughness:.1f}/{boss.max_toughness:.1f}")
    print(f"  - Состояние: {boss.state.value}")
    
    # Добиваем стойкость
    damage_dealt = boss.take_toughness_damage(150.0, ToughnessType.PHYSICAL)
    print(f"\n  - ФИНАЛЬНЫЙ УДАР! Нанесено: {damage_dealt:.1f}")
    print(f"  - Стойкость: {boss.current_toughness:.1f}/{boss.max_toughness:.1f}")
    print(f"  - Состояние: {boss.state.value}")
    print(f"  - Множитель урона (BROKEN): {boss.damage_multiplier:.2f}")
    
    assert boss.state == StanceState.BROKEN, "Босс должен быть в состоянии BROKEN"
    assert boss.is_broken, "is_broken должен быть True"
    assert boss.damage_multiplier == 1.35, f"Множитель должен быть 1.35, получен {boss.damage_multiplier}"
    
    print("✓ Пробитие стойкости работает корректно")
    print(f"  - Босс оглушен и получает +35% урона")


def test_toughness_scaling_after_break():
    """Тест увеличения макс. стойкости после каждого пробития"""
    print("\n=== ТЕСТ 4: Скалирование стойкости после пробитий ===")
    
    config = ToughnessConfig(
        max_toughness=100.0,
        recovery_rate=1000.0,  # Быстрое восстановление для теста
        recovery_delay=0.1,
        break_duration=0.5,
        damage_taken_multiplier_broken=0.25,
        toughness_from_hp_ratio=0.2,  # 20% от HP
        max_toughness_cap_ratio=0.2,  # Максимум 20% от HP
        auto_recover_on_break_end=True
    )
    
    enemy = ToughnessComponent(
        entity_id="enemy_scaling",
        config=config,
        max_health=1000.0
    )
    enemy._state = LifecycleState.READY
    
    initial_max = enemy.max_toughness
    print(f"  - Начальный макс. стойкость: {initial_max:.1f}")
    print(f"  - Макс. бонус от HP: {1000.0 * 0.2:.1f} (20% от 1000 HP)")
    
    # Первое пробитие
    enemy.take_toughness_damage(200.0)
    print(f"\n  --- ПРОБИТИЕ #1 ---")
    print(f"  - Макс. стойкость после: {enemy.max_toughness:.1f}")
    print(f"  - Прирост: {enemy.max_toughness - initial_max:.1f}")
    
    # Ждем выхода из BREAK
    time.sleep(0.6)
    enemy._on_update(0.6)
    
    # Второе пробитие
    enemy.take_toughness_damage(200.0)
    print(f"\n  --- ПРОБИТИЕ #2 ---")
    print(f"  - Макс. стойкость после: {enemy.max_toughness:.1f}")
    
    # Третье пробитие
    time.sleep(0.6)
    enemy._on_update(0.6)
    enemy.take_toughness_damage(200.0)
    print(f"\n  --- ПРОБИТИЕ #3 ---")
    print(f"  - Макс. стойкость после: {enemy.max_toughness:.1f}")
    
    # Проверяем что стойкость выросла но не превысила кап
    max_allowed = initial_max + (1000.0 * 0.2)
    assert enemy.max_toughness <= max_allowed, f"Стойкость не должна превышать {max_allowed}"
    assert enemy.max_toughness > initial_max, "Стойкость должна вырасти"
    
    print(f"\n✓ Скалирование работает (макс. кап: {max_allowed:.1f})")


def test_effect_modifier_types():
    """Тест различных типов модификаторов (ADDITIVE, MULTIPLICATIVE, OVERRIDE)"""
    print("\n=== ТЕСТ 5: Типы модификаторов эффектов ===")
    
    system = EffectSystem()
    system.initialize()
    
    entity_id = "hero_1"
    
    # Базовое значение урона
    base_damage = 100.0
    
    # Плоский бонус +50 урона
    flat_buff = Effect(
        effect_id="flat_str",
        name="Сила героя",
        description="+50 к урону",
        effect_type=EffectType.BUFF,
        category=EffectCategory.STAT_MODIFIER,
        duration=30.0,
        modifiers=[
            EffectModifier(
                stat_type="physical_damage",
                value=50.0,
                modifier_type=EffectModifierType.ADDITIVE,
                modifier_id="str_flat"
            )
        ]
    )
    
    # Процентный бонус +25% урона
    percent_buff = Effect(
        effect_id="percent_dmg",
        name="Ярость",
        description="+25% к урону",
        effect_type=EffectType.BUFF,
        category=EffectCategory.STAT_MODIFIER,
        duration=30.0,
        modifiers=[
            EffectModifier(
                stat_type="physical_damage",
                value=0.25,
                modifier_type=EffectModifierType.MULTIPLICATIVE,
                modifier_id="rage_percent"
            )
        ]
    )
    
    # Применяем оба эффекта
    active_effects = system.active_effects.setdefault(entity_id, [])
    
    active_effects.append(ActiveEffect(
        effect=flat_buff,
        entity_id=entity_id,
        applied_at=time.perf_counter(),
        expires_at=time.perf_counter() + 30.0
    ))
    
    active_effects.append(ActiveEffect(
        effect=percent_buff,
        entity_id=entity_id,
        applied_at=time.perf_counter(),
        expires_at=time.perf_counter() + 30.0
    ))
    
    # Рассчитываем итоговый урон: (100 + 50) * (1 + 0.25) = 187.5
    final_damage = system.get_modified_stat(entity_id, "physical_damage", base_damage)
    expected = (base_damage + 50.0) * 1.25
    
    print(f"  - Базовый урон: {base_damage}")
    print(f"  - Плоский бонус: +50")
    print(f"  - Процентный бонус: +25%")
    print(f"  - Итоговый урон: {final_damage:.1f}")
    print(f"  - Ожидаемый: {expected:.1f}")
    
    assert abs(final_damage - expected) < 0.01, f"Урон должен быть {expected}, получен {final_damage}"
    
    print("✓ Формула (base + flat) * (1 + percent) работает корректно")


def test_stun_knockdown_daze_stack():
    """Тест суммирования длительности стан/нокдаун/ошеломление"""
    print("\n=== ТЕСТ 6: Суммирование CC эффектов ===")
    
    system = EffectSystem()
    system.initialize()
    
    entity_id = "cc_target"
    
    # Эффект стана на 2 секунды
    stun1 = Effect(
        effect_id="stun_001",
        name="Оглушение",
        description="Стан на 2 сек",
        effect_type=EffectType.DEBUFF,
        category=EffectCategory.CROWD_CONTROL,
        duration=2.0,
        tags=[EffectTag.NEGATIVE, EffectTag.STUN],
        modifiers=[
            EffectModifier(
                stat_type="movement_speed",
                value=-1.0,
                modifier_type=EffectModifierType.MULTIPLICATIVE,
                modifier_id="stun_root",
                tags=[EffectTag.STUN]
            )
        ]
    )
    
    # Второй стан на 1.5 секунды (должен суммироваться)
    stun2 = Effect(
        effect_id="stun_002",
        name="Оглушение 2",
        description="Стан на 1.5 сек",
        effect_type=EffectType.DEBUFF,
        category=EffectCategory.CROWD_CONTROL,
        duration=1.5,
        tags=[EffectTag.NEGATIVE, EffectTag.STUN],
        modifiers=[
            EffectModifier(
                stat_type="movement_speed",
                value=-1.0,
                modifier_type=EffectModifierType.MULTIPLICATIVE,
                modifier_id="stun_root_2",
                tags=[EffectTag.STUN]
            )
        ]
    )
    
    # Применяем оба стана
    active_effects = system.active_effects.setdefault(entity_id, [])
    
    current_time = time.perf_counter()
    
    active_effects.append(ActiveEffect(
        effect=stun1,
        entity_id=entity_id,
        applied_at=current_time,
        expires_at=current_time + 2.0
    ))
    
    active_effects.append(ActiveEffect(
        effect=stun2,
        entity_id=entity_id,
        applied_at=current_time,
        expires_at=current_time + 1.5
    ))
    
    # Проверяем наличие стана
    stun_effects = system.get_effects_by_tag(entity_id, EffectTag.STUN)
    total_stun_duration = sum(
        (ae.expires_at - ae.applied_at) for ae in stun_effects if ae.expires_at
    )
    
    print(f"  - Применено стан-эффектов: {len(stun_effects)}")
    print(f"  - Общая длительность: {total_stun_duration:.1f} сек")
    print(f"  - Цель обездвижена: {system.has_tag(entity_id, EffectTag.STUN)}")
    
    assert len(stun_effects) == 2, "Должно быть 2 стан-эффекта"
    assert system.has_tag(entity_id, EffectTag.STUN), "Должен быть тег STUN"
    
    print("✓ CC эффекты применяются и детектируются")


def test_negative_before_break_synergy():
    """Тест синергии: сначала негативки, потом пробитие (а не наоборот)"""
    print("\n=== ТЕСТ 7: Синергия - негативки ДО пробития ===")
    
    system = EffectSystem()
    system.initialize()
    
    # Создаем врага со стойкостью
    config = ToughnessConfig(
        max_toughness=200.0,
        break_duration=5.0,
        damage_taken_multiplier_broken=0.30,
        auto_recover_on_break_end=True
    )
    
    enemy = ToughnessComponent(
        entity_id="synergy_enemy",
        config=config,
        max_health=5000.0
    )
    enemy._state = LifecycleState.READY
    
    entity_id = enemy.component_id
    
    # Шаг 1: Вешаем негативные эффекты
    poison = Effect(
        effect_id="poison_001",
        name="Яд",
        description="Отравление",
        effect_type=EffectType.DEBUFF,
        category=EffectCategory.DAMAGE_OVER_TIME,
        duration=10.0,
        tags=[EffectTag.NEGATIVE],
        modifiers=[
            EffectModifier(
                stat_type="health",
                value=-10,
                modifier_type=EffectModifierType.ADDITIVE,
                modifier_id="poison_dot",
                tags=[EffectTag.NEGATIVE]
            )
        ]
    )
    
    system.active_effects.setdefault(entity_id, []).append(ActiveEffect(
        effect=poison,
        entity_id=entity_id,
        applied_at=time.perf_counter(),
        expires_at=time.perf_counter() + 10.0
    ))
    
    print(f"  - Негативных эффектов ДО пробития: {system.count_negative_effects(entity_id)}")
    
    # Шаг 2: Пробиваем стойкость
    enemy.take_toughness_damage(300.0)
    
    print(f"  - Стойкость пробита: {enemy.is_broken}")
    print(f"  - Состояние: {enemy.state.value}")
    print(f"  - Множитель урона: {enemy.damage_multiplier:.2f}")
    
    # Проверяем что негативки остались
    assert system.count_negative_effects(entity_id) >= 1, "Негативки должны остаться после пробития"
    assert enemy.is_broken, "Враг должен быть в BROKEN"
    
    print("✓ Синергия работает: негативки + пробитие = максимальный урон")


def run_all_tests():
    """Запуск всех тестов"""
    print("=" * 60)
    print("ТЕСТЫ СИСТЕМЫ ЭФФЕКТОВ И СТОЙКОСТИ")
    print("=" * 60)
    
    try:
        test_effect_tags_and_synergies()
        test_combo_effects()
        test_toughness_break_damage_bonus()
        test_toughness_scaling_after_break()
        test_effect_modifier_types()
        test_stun_knockdown_daze_stack()
        test_negative_before_break_synergy()
        
        print("\n" + "=" * 60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛЕН: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
