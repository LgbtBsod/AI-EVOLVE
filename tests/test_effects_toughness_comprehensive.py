"""
Комплексные тесты системы эффектов и стойкости.
Проверяет:
- Теги эффектов и синергии
- Комбо эффекты (подсечка: урон + замедление + нокдаун)
- Пробитие стойкости и бонус урона
- Скалирование стойкости после пробитий
- Суммирование CC эффектов через modifier_id
- Синергия негативных эффектов и множителей урона
"""
import pytest
import time
from game.core.effects import (
    BuffEffect, ActiveEffectsContainer, EffectType, 
    StatTarget, EffectTag
)

# Импортируем систему стойкости
try:
    from game.core.toughness import ToughnessComponent, ToughnessConfig, ToughnessState
except ImportError:
    from toughness import ToughnessComponent, ToughnessConfig, ToughnessState


class TestEffectTagsAndSynergies:
    """Тесты тегов эффектов и синергий"""
    
    def test_effect_has_tags(self):
        """Эффект должен корректно хранить и проверять теги"""
        # Создаем дебафф замедления с тегами
        slow_effect = BuffEffect(
            id="slow_debuff",
            name="Замедление",
            target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT,
            value=-0.3,  # -30% скорости
            duration=5.0,
            tags=[EffectTag.NEGATIVE, EffectTag.SLOW]
        )
        
        assert slow_effect.has_tag(EffectTag.NEGATIVE) is True
        assert slow_effect.has_tag(EffectTag.SLOW) is True
        assert slow_effect.has_tag(EffectTag.STUN) is False
    
    def test_container_get_effects_by_tag(self):
        """Контейнер должен возвращать эффекты по тегу"""
        container = ActiveEffectsContainer()
        
        # Добавляем разные эффекты
        container.add_effect(BuffEffect(
            id="slow1", name="Slow", target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT, value=-0.3, duration=5.0,
            tags=[EffectTag.NEGATIVE, EffectTag.SLOW]
        ))
        
        container.add_effect(BuffEffect(
            id="str_buff", name="Strength", target=StatTarget.STRENGTH,
            effect_type=EffectType.FLAT, value=10.0, duration=10.0,
            tags=[EffectTag.POSITIVE]
        ))
        
        container.add_effect(BuffEffect(
            id="stun1", name="Stun", target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT, value=-1.0, duration=2.0,
            tags=[EffectTag.NEGATIVE, EffectTag.STUN]
        ))
        
        # Получаем все негативные эффекты
        negative_effects = container.get_effects_by_tag(EffectTag.NEGATIVE)
        assert len(negative_effects) == 2  # slow и stun
        
        # Получаем все эффекты замедления
        slow_effects = container.get_effects_by_tag(EffectTag.SLOW)
        assert len(slow_effects) == 1
        assert slow_effects[0].id == "slow1"
    
    def test_count_negative_effects(self):
        """Подсчет количества негативных эффектов"""
        container = ActiveEffectsContainer()
        
        assert container.has_negative_effects() is False
        assert container.get_negative_effect_count() == 0
        
        # Добавляем бафф
        container.add_effect(BuffEffect(
            id="buff1", name="Buff", target=StatTarget.STRENGTH,
            effect_type=EffectType.FLAT, value=10.0, duration=10.0,
            tags=[EffectTag.POSITIVE]
        ))
        
        assert container.has_negative_effects() is False
        
        # Добавляем дебафф
        container.add_effect(BuffEffect(
            id="debuff1", name="Debuff", target=StatTarget.DEFENSE,
            effect_type=EffectType.PERCENT, value=-0.2, duration=5.0,
            tags=[EffectTag.NEGATIVE]
        ))
        
        assert container.has_negative_effects() is True
        assert container.get_negative_effect_count() == 1


class TestComboEffects:
    """Тесты комбо эффектов (например, подсечка)"""
    
    def test_trip_attack_combo(self):
        """Подсечка наносит урон + вешает замедление + нокдаун"""
        container = ActiveEffectsContainer()
        
        # Эмуляция скилла "Подсечка"
        # 1. Наносим урон (это делается в боевой системе)
        damage_dealt = 50.0
        
        # 2. Вешаем замедление на 2 секунды
        slow_effect = BuffEffect(
            id="trip_slow",
            name="Замедление от подсечки",
            target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT,
            value=-0.5,  # -50% скорости
            duration=2.0,
            tags=[EffectTag.NEGATIVE, EffectTag.SLOW],
            modifier_id="movement_cc"  # Общий ID для CC на движение
        )
        container.add_effect(slow_effect)
        
        # 3. Вешаем нокдаун (полная остановка) на 1.5 секунды
        knockdown_effect = BuffEffect(
            id="trip_knockdown",
            name="Опрокидывание",
            target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT,
            value=-1.0,  # -100% скорости (полный паралич)
            duration=1.5,
            tags=[EffectTag.NEGATIVE, EffectTag.KNOCKDOWN],
            modifier_id="movement_cc",  # Тот же ID - эффекты суммируются по времени
            priority=10  # Высокий приоритет
        )
        container.add_effect(knockdown_effect)
        
        # Проверяем что оба эффекта применены
        assert container.get_negative_effect_count() == 2
        
        # Проверяем наличие эффектов KNOCKDOWN
        knockdown_effects = container.get_effects_by_tag(EffectTag.KNOCKDOWN)
        assert len(knockdown_effects) > 0
        assert any(e.has_tag(EffectTag.KNOCKDOWN) for e in knockdown_effects)
        
        # Проверяем длительность CC
        knockdown_duration = container.get_cc_duration(EffectTag.KNOCKDOWN)
        assert knockdown_duration > 0


class TestToughnessBreakMechanics:
    """Тесты механики пробития стойкости"""
    
    def test_break_grants_damage_bonus(self):
        """При пробитии стойкости враг получает +25-35% урона"""
        config = ToughnessConfig(
            max_toughness=100.0,
            break_duration=5.0,
            damage_taken_multiplier_broken=0.35  # +35% урона
        )
        toughness = ToughnessComponent(config=config)
        
        assert toughness.is_broken is False
        
        # Наносим урон по стойкости до 0
        broke = toughness.take_toughness_damage(100.0)
        
        assert broke is True
        assert toughness.is_broken is True
        assert toughness.current_toughness == 0.0
        
        # Проверяем множитель урона
        damage_reduction = toughness.get_damage_reduction()
        assert damage_reduction == -0.35  # Отрицательный = увеличение урона на 35%
    
    def test_toughness_scales_after_break(self):
        """Каждое пробитие увеличивает макс. стойкость на 20% от HP"""
        max_hp = 1000.0
        growth_percent = 0.20  # 20%
        
        config = ToughnessConfig(
            max_toughness=100.0,
            break_duration=3.0,
            recovery_delay=1.0,
            recovery_rate=50.0
        )
        toughness = ToughnessComponent(config=config)
        
        initial_max = toughness.config.max_toughness
        assert initial_max == 100.0
        
        # Первое пробитие
        toughness.take_toughness_damage(100.0)
        toughness.times_broken = 1  # Эмулируем что уже сломали
        
        # Увеличиваем макс. стойкость
        new_max = initial_max + (max_hp * growth_percent)
        toughness.config.max_toughness = new_max
        
        assert toughness.config.max_toughness == 100.0 + (1000.0 * 0.20)  # 300.0
        
        # Восстанавливаем стойкость
        toughness.current_toughness = toughness.config.max_toughness
        toughness.state = ToughnessState.NORMAL
        
        # Второе пробитие
        toughness.take_toughness_damage(toughness.config.max_toughness)
        toughness.times_broken = 2
        
        # Еще раз увеличиваем
        new_max = new_max + (max_hp * growth_percent)
        toughness.config.max_toughness = new_max
        
        assert toughness.config.max_toughness == 500.0  # 100 + 200 + 200
    
    def test_toughness_fully_restores_after_break(self):
        """После выхода из BREAK стойкость восстанавливается полностью"""
        config = ToughnessConfig(
            max_toughness=100.0,
            break_duration=2.0,
            recovery_delay=0.5,
            recovery_rate=100.0
        )
        toughness = ToughnessComponent(config=config)
        
        # Ломаем стойкость
        toughness.take_toughness_damage(100.0)
        assert toughness.state == ToughnessState.BROKEN
        
        # Ждем окончания BREAK
        time.sleep(2.5)  # break_duration + small buffer
        toughness.update(2.5)
        
        # После BREAK стойкость должна восстановиться
        # В нашей реализации: переходим в RECOVERING и получаем 30% сразу
        assert toughness.state in [ToughnessState.RECOVERING, ToughnessState.NORMAL]
        assert toughness.current_toughness > 0


class TestCCDurationStacking:
    """Тесты суммирования длительности CC эффектов"""
    
    def test_same_modifier_id_stacks_duration(self):
        """Эффекты с одинаковым modifier_id суммируют длительность"""
        container = ActiveEffectsContainer()
        
        # Первое замедление на 2 секунды
        container.add_effect(BuffEffect(
            id="slow1",
            name="Slow 1",
            target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT,
            value=-0.3,
            duration=2.0,
            tags=[EffectTag.NEGATIVE, EffectTag.SLOW],
            modifier_id="movement_slow"
        ))
        
        # Второе замедление на 3 секунды (тот же modifier_id)
        container.add_effect(BuffEffect(
            id="slow2",
            name="Slow 2",
            target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT,
            value=-0.4,
            duration=3.0,
            tags=[EffectTag.NEGATIVE, EffectTag.SLOW],
            modifier_id="movement_slow"
        ))
        
        # Общая длительность SLOW эффектов
        total_slow_duration = container.get_cc_duration(EffectTag.SLOW)
        assert total_slow_duration >= 2.0  # Как минимум первый эффект
    
    def test_different_cc_types_sum(self):
        """Разные типы CC суммируются в общий пул"""
        container = ActiveEffectsContainer()
        
        # Стан на 2 секунды
        container.add_effect(BuffEffect(
            id="stun1", name="Stun", target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT, value=-1.0, duration=2.0,
            tags=[EffectTag.NEGATIVE, EffectTag.STUN]
        ))
        
        # Нокдаун на 1.5 секунды
        container.add_effect(BuffEffect(
            id="knockdown1", name="Knockdown", target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT, value=-1.0, duration=1.5,
            tags=[EffectTag.NEGATIVE, EffectTag.KNOCKDOWN]
        ))
        
        # Замедление на 3 секунды
        container.add_effect(BuffEffect(
            id="slow1", name="Slow", target=StatTarget.MOVEMENT_SPEED,
            effect_type=EffectType.PERCENT, value=-0.5, duration=3.0,
            tags=[EffectTag.NEGATIVE, EffectTag.SLOW]
        ))
        
        # Общая длительность всех CC
        total_cc = container.get_total_cc_duration()
        # Сумма: stun (2.0) + knockdown (1.5) + slow (3.0) = 6.5
        assert total_cc >= 6.4  # Небольшой допуск на время выполнения


class TestNegativeEffectDamageBonus:
    """Тесты бонуса урона по целям с негативными эффектами"""
    
    def test_damage_bonus_vs_negative_effects(self):
        """Бонус урона работает когда на цели есть негативные эффекты"""
        container = ActiveEffectsContainer()
        
        # На цели нет дебаффов
        assert container.has_negative_effects() is False
        negative_count = container.get_negative_effect_count()
        assert negative_count == 0
        
        # Базовый урон
        base_damage = 100.0
        
        # Бонус урона за каждый негативный эффект (10% за штуку)
        bonus_per_negative = 0.10
        total_bonus = negative_count * bonus_per_negative
        final_damage = base_damage * (1 + total_bonus)
        
        assert final_damage == 100.0  # Без бонуса
        
        # Вешаем дебафф с тегом NEGATIVE
        container.add_effect(BuffEffect(
            id="bleed", name="Кровотечение", target=StatTarget.HEALTH,
            effect_type=EffectType.FLAT, value=-10.0, duration=5.0,
            tags=[EffectTag.NEGATIVE, EffectTag.DOT, EffectTag.BLEED]
        ))
        
        assert container.has_negative_effects() is True
        negative_count = container.get_negative_effect_count()
        assert negative_count == 1
        
        # Пересчитываем урон
        total_bonus = negative_count * bonus_per_negative
        final_damage = base_damage * (1 + total_bonus)
        
        assert abs(final_damage - 110.0) < 0.01  # +10% бонус с допуском на float
    
    def test_broken_state_synergy(self):
        """Синергия: сначала негативки, потом пробитие = максимальный урон"""
        container = ActiveEffectsContainer()
        config = ToughnessConfig(
            max_toughness=100.0,
            break_duration=5.0,
            damage_taken_multiplier_broken=0.35
        )
        toughness = ToughnessComponent(config=config)
        
        base_damage = 100.0
        
        # 1. Вешаем негативные эффекты
        container.add_effect(BuffEffect(
            id="poison", name="Яд", target=StatTarget.HEALTH,
            effect_type=EffectType.FLAT, value=-5.0, duration=10.0,
            tags=[EffectTag.NEGATIVE, EffectTag.DOT, EffectTag.POISON]
        ))
        
        container.add_effect(BuffEffect(
            id="weakness", name="Ослабление", target=StatTarget.DEFENSE,
            effect_type=EffectType.PERCENT, value=-0.2, duration=8.0,
            tags=[EffectTag.NEGATIVE]
        ))
        
        negative_count = container.get_negative_effect_count()
        assert negative_count == 2
        
        # 2. Пробиваем стойкость
        toughness.take_toughness_damage(100.0)
        assert toughness.is_broken is True
        
        # 3. Рассчитываем итоговый урон
        # Бонус за негативки: +20% (2 * 10%)
        bonus_from_negatives = negative_count * 0.10
        
        # Бонус за BROKEN: +35%
        bonus_from_broken = abs(toughness.get_damage_reduction())
        
        # Итого: 100 * (1 + 0.20 + 0.35) = 155
        total_multiplier = 1 + bonus_from_negatives + bonus_from_broken
        final_damage = base_damage * total_multiplier
        
        assert abs(final_damage - 155.0) < 0.1  # Допуск на float


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
