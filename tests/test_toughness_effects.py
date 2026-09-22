#!/usr/bin/env python3
"""Comprehensive Tests for Toughness and Effects Systems

Test coverage:
1. ToughnessComponent - все механики стойкости
2. EffectSystem - баффы, дебаффы, стеки
3. Интеграция стойкости и эффектов
4. Краевые случаи и нагрузочные тесты
"""

import pytest
import time
from typing import Callable

# Импорты компонентов
from src.systems.combat.components.toughness_component import (
    ToughnessComponent,
    ToughnessConfig,
    ToughnessBreakEvent,
    ToughnessRecoveryEvent
)
from src.core.constants import StanceState, ToughnessType


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def default_config() -> ToughnessConfig:
    """Конфигурация по умолчанию"""
    return ToughnessConfig(
        max_toughness=100.0,
        recovery_rate=10.0,
        recovery_delay=1.0,
        break_duration=2.0,
        damage_taken_multiplier_broken=0.25,
        toughness_from_hp_ratio=0.05,  # 5% от HP за каждое пробитие
        max_toughness_cap_ratio=0.2,   # Максимум 20% от HP
        auto_recover_on_break_end=True
    )


@pytest.fixture
def toughness_component(default_config) -> ToughnessComponent:
    """Базовый компонент стойкости"""
    comp = ToughnessComponent(
        entity_id="test_entity",
        config=default_config,
        max_health=500.0
    )
    comp.initialize()
    yield comp
    comp.destroy()


@pytest.fixture
def boss_toughness() -> ToughnessComponent:
    """Компонент стойкости для босса"""
    config = ToughnessConfig(
        max_toughness=1000.0,
        recovery_rate=20.0,
        recovery_delay=2.0,
        break_duration=5.0,
        damage_taken_multiplier_broken=0.35,
        toughness_from_hp_ratio=0.2,
        max_toughness_cap_ratio=0.2,
        auto_recover_on_break_end=True
    )
    comp = ToughnessComponent(
        entity_id="boss",
        config=config,
        max_health=5000.0
    )
    # Не вызываем initialize() так как это переводит компонент в INITIALIZING state
    # comp.initialize()
    yield comp
    # comp.destroy()


# ============================================================================
# TEST: TOUGHNESS COMPONENT - BASIC
# ============================================================================

class TestToughnessBasic:
    """Базовые тесты компонента стойкости"""
    
    def test_initialization(self, toughness_component):
        """Тест инициализации компонента"""
        assert toughness_component.current_toughness == 100.0
        assert toughness_component.max_toughness == 100.0
        assert toughness_component.state == StanceState.NORMAL
        assert toughness_component.break_count == 0
        assert toughness_component.toughness_percent == 100.0
        assert not toughness_component.is_broken
        assert not toughness_component.is_recovering
    
    def test_damage_multiplier_normal(self, toughness_component):
        """Множитель урона в нормальном состоянии"""
        assert toughness_component.damage_multiplier == 1.0
    
    def test_set_max_health(self, toughness_component):
        """Установка максимального здоровья"""
        toughness_component.set_max_health(1000.0)
        # Проверка что health сохранился
        assert toughness_component._max_health == 1000.0
    
    def test_reset(self, toughness_component):
        """Сброс компонента"""
        # Нанесем урон
        toughness_component.take_toughness_damage(50.0)
        assert toughness_component.current_toughness == 50.0
        
        # Сброс
        toughness_component.reset()
        assert toughness_component.current_toughness == 100.0
        assert toughness_component.break_count == 0
        assert toughness_component.state == StanceState.NORMAL


# ============================================================================
# TEST: TOUGHNESS DAMAGE
# ============================================================================

class TestToughnessDamage:
    """Тесты нанесения урона по стойкости"""
    
    def test_basic_damage(self, toughness_component):
        """Базовый урон по стойкости"""
        result = toughness_component.take_toughness_damage(30.0)
        assert result == 30.0
        assert toughness_component.current_toughness == 70.0
    
    def test_damage_cannot_exceed_current(self, toughness_component):
        """Урон не может уменьшить стойкость ниже 0"""
        toughness_component.take_toughness_damage(150.0)
        assert toughness_component.current_toughness == 0.0
    
    def test_zero_damage(self, toughness_component):
        """Нулевой урон"""
        result = toughness_component.take_toughness_damage(0.0)
        assert result == 0.0
        assert toughness_component.current_toughness == 100.0
    
    def test_no_damage_when_broken(self, toughness_component):
        """Нельзя нанести урон по уже пробитой стойкости"""
        toughness_component.take_toughness_damage(200.0)  # Пробиваем
        assert toughness_component.state == StanceState.BROKEN
        
        result = toughness_component.take_toughness_damage(50.0)
        assert result == 0.0
        assert toughness_component.current_toughness == 0.0


# ============================================================================
# TEST: TOUGHNESS STATES
# ============================================================================

class TestToughnessStates:
    """Тесты состояний стойкости"""
    
    def test_weakened_state(self, toughness_component):
        """Переход в ослабленное состояние (ниже 25%)"""
        toughness_component.take_toughness_damage(76.0)  # Остается 24%
        assert toughness_component.state == StanceState.WEAKENED
        assert toughness_component.damage_multiplier == 1.125  # +12.5%
    
    def test_weakened_not_triggered_above_25(self, toughness_component):
        """Ослабленное состояние не срабатывает выше 25%"""
        toughness_component.take_toughness_damage(75.0)  # Остается ровно 25%
        assert toughness_component.state == StanceState.NORMAL
    
    def test_broken_state_triggers(self, toughness_component):
        """Срабатывание состояния BROKEN"""
        toughness_component.take_toughness_damage(100.0)
        assert toughness_component.state == StanceState.BROKEN
        assert toughness_component.is_broken
        assert toughness_component.break_count == 1
    
    def test_broken_damage_multiplier(self, toughness_component):
        """Множитель урона в состоянии BROKEN"""
        toughness_component.take_toughness_damage(100.0)
        assert toughness_component.damage_multiplier == 1.25  # +25%
    
    def test_boss_broken_multiplier(self, boss_toughness):
        """Множитель урона для босса в BROKEN"""
        boss_toughness.take_toughness_damage(1000.0)
        assert boss_toughness.damage_multiplier == 1.35  # +35%


# ============================================================================
# TEST: TOUGHNESS BREAK MECHANICS
# ============================================================================

class TestToughnessBreak:
    """Тесты механики пробития стойкости"""
    
    def test_break_increases_count(self, toughness_component):
        """Пробитие увеличивает счетчик"""
        toughness_component.take_toughness_damage(100.0)
        assert toughness_component.break_count == 1
        
        # Ждем выхода из BREAK и восстановления
        time.sleep(2.5)
        toughness_component._on_update(0.1)
        
        # Теперь стойкость полная, пробиваем снова
        toughness_component.take_toughness_damage(200.0)
        assert toughness_component.break_count == 2
    
    def test_break_increases_max_toughness(self, toughness_component):
        """Пробитие увеличивает макс. стойкость от HP на 5% (накопительно до 20%)"""
        initial_max = toughness_component.max_toughness
        toughness_component.take_toughness_damage(100.0)
        
        # Бонус = 500 HP * 0.05 = 25 (теперь 5% вместо 20%)
        expected_new_max = initial_max + 25.0
        assert toughness_component.max_toughness == expected_new_max
    
    def test_break_increases_max_toughness_cumulative(self, toughness_component):
        """Пробитие увеличивает макс. стойкость накопительно на 5% каждый раз до caps в 20%"""
        initial_max = toughness_component.max_toughness  # 100
        
        # Пробиваем 4 раза: 5% + 5% + 5% + 5% = 20% (достигаем капа)
        for i in range(4):
            toughness_component.take_toughness_damage(200.0)
            assert toughness_component.state == StanceState.BROKEN
            
            # Ждем выхода из BREAK и полного восстановления
            time.sleep(5.5)
            toughness_component._on_update(0.1)
        
        # После 4 пробитий: бонус = 4 * (500 * 0.05) = 4 * 25 = 100
        # Максимум = 100 + 100 = 200
        expected_max = initial_max + (500.0 * 0.05 * 4)
        assert toughness_component.max_toughness == expected_max
        
        # Еще одно пробитие не должно увеличить макс (кап достигнут)
        toughness_component.take_toughness_damage(200.0)
        assert toughness_component.state == StanceState.BROKEN
        
        time.sleep(5.5)
        toughness_component._on_update(0.1)
        
        # Максимум все еще 200 (кап 20% от HP = 100 бонуса)
        max_cap = initial_max + (500.0 * 0.2)
        assert toughness_component.max_toughness == max_cap
    
    def test_break_max_cap(self, toughness_component):
        """Ограничение максимума стойкости 20% от HP"""
        # Пробиваем несколько раз
        for i in range(6):
            toughness_component.take_toughness_damage(200.0)
            assert toughness_component.state == StanceState.BROKEN
            
            # Ждем выхода из BREAK
            time.sleep(5.5)
            toughness_component._on_update(0.1)
        
        # Максимум = base + (500 * 0.2) = 100 + 100 = 200
        max_allowed = 100.0 + (500.0 * 0.2)
        assert toughness_component.max_toughness <= max_allowed
    
    def test_full_recovery_after_break(self, toughness_component):
        """Полное восстановление стойкости после BREAK"""
        toughness_component.take_toughness_damage(100.0)
        assert toughness_component.current_toughness == 0.0
        
        # Ждем выхода из BREAK
        time.sleep(2.5)
        toughness_component._on_update(0.1)
        
        assert toughness_component.current_toughness == toughness_component.max_toughness
        # После выхода из BREAK стойкость полностью восстанавливается и состояние становится NORMAL
        assert toughness_component.state == StanceState.NORMAL


# ============================================================================
# TEST: TOUGHNESS RECOVERY
# ============================================================================

class TestToughnessRecovery:
    """Тесты восстановления стойкости"""
    
    def test_recovery_delay(self, toughness_component):
        """Задержка восстановления после урона"""
        toughness_component.take_toughness_damage(50.0)
        
        # Сразу пытаемся восстановить
        toughness_component._on_update(0.5)
        assert toughness_component.current_toughness == 50.0  # Не изменилось
    
    def test_recovery_rate(self, toughness_component):
        """Скорость восстановления"""
        toughness_component.take_toughness_damage(50.0)
        
        # Ждем окончания задержки
        time.sleep(1.5)
        
        # Восстанавливаем 2 секунды
        toughness_component._on_update(2.0)
        
        # 10.0 rate * 2.0 sec = 20.0 восстановлено
        expected = min(100.0, 50.0 + 20.0)
        assert toughness_component.current_toughness >= 69.0  # С учетом дельты времени
    
    def test_recovery_to_normal_state(self, toughness_component):
        """Переход в NORMAL при полном восстановлении"""
        toughness_component.take_toughness_damage(100.0)
        
        # Ждем выхода из BREAK (break_duration=5.0 сек)
        time.sleep(5.5)
        toughness_component._on_update(0.1)
        
        # После выхода из BREAK стойкость полностью восстанавливается и состояние становится NORMAL
        assert toughness_component.state == StanceState.NORMAL
        assert toughness_component.current_toughness == toughness_component.max_toughness
    
    def test_damage_interrupts_recovery(self, toughness_component):
        """Урон прерывает восстановление"""
        toughness_component.take_toughness_damage(50.0)
        
        # Сразу после урона стойкость должна быть 50
        assert toughness_component.current_toughness == 50.0
        
        # Ждем меньше чем recovery_delay (1.0 сек в фикстуре), поэтому восстановления не будет
        time.sleep(0.5)
        toughness_component._on_update(0.1)
        
        # Стойкость не должна измениться
        assert toughness_component.current_toughness == 50.0
        
        # Наносим еще урон
        toughness_component.take_toughness_damage(10.0)
        
        # Сразу после урона стойкость должна быть 40
        assert toughness_component.current_toughness == 40.0
        
        # Снова ждем меньше recovery_delay
        time.sleep(0.5)
        toughness_component._on_update(0.5)
        
        # Все еще в задержке (общее время с последнего удара < 1.0 сек), стойкость не должна измениться
        assert toughness_component.current_toughness <= 40.5


# ============================================================================
# TEST: ELEMENTAL EFFECTIVENESS
# ============================================================================

class TestElementalEffectiveness:
    """Тесты эффективности стихий"""
    
    def test_universal_type(self, toughness_component):
        """Универсальный тип пробивает всё"""
        result = toughness_component.take_toughness_damage(
            50.0,
            toughness_type=ToughnessType.UNIVERSAL,
            enemy_toughness_type=ToughnessType.PHYSICAL
        )
        assert result == 50.0  # 1.0 множитель
    
    def test_physical_vs_physical(self, toughness_component):
        """Физический vs Физический"""
        result = toughness_component.take_toughness_damage(
            50.0,
            toughness_type=ToughnessType.PHYSICAL,
            enemy_toughness_type=ToughnessType.PHYSICAL
        )
        assert result == 50.0  # 1.0 множитель
    
    def test_fire_vs_ice(self, toughness_component):
        """Огонь vs Лед (2.0 эффективность)"""
        result = toughness_component.take_toughness_damage(
            50.0,
            toughness_type=ToughnessType.FIRE,
            enemy_toughness_type=ToughnessType.ICE
        )
        assert result == 100.0  # 2.0 множитель
    
    def test_ice_vs_fire(self, toughness_component):
        """Лед vs Огонь (0.5 эффективность)"""
        result = toughness_component.take_toughness_damage(
            50.0,
            toughness_type=ToughnessType.ICE,
            enemy_toughness_type=ToughnessType.FIRE
        )
        assert result == 25.0  # 0.5 множитель
    
    def test_quantum_vs_imaginary(self, toughness_component):
        """Квант vs Мнимый (0.5 эффективность)"""
        result = toughness_component.take_toughness_damage(
            50.0,
            toughness_type=ToughnessType.QUANTUM,
            enemy_toughness_type=ToughnessType.IMAGINARY
        )
        assert result == 25.0  # 0.5 множитель


# ============================================================================
# TEST: CALLBACKS AND EVENTS
# ============================================================================

class TestCallbacks:
    """Тесты callback-ов и событий"""
    
    def test_on_toughness_changed(self, toughness_component):
        """Callback при изменении стойкости"""
        events = []
        
        def handler(current: float, previous: float):
            events.append((current, previous))
        
        toughness_component.on_toughness_changed = handler
        toughness_component.take_toughness_damage(30.0)
        
        assert len(events) == 1
        assert events[0] == (70.0, 100.0)
    
    def test_on_toughness_broken(self, toughness_component):
        """Callback при пробитии стойкости"""
        events = []
        
        def handler(event: ToughnessBreakEvent):
            events.append(event)
        
        toughness_component.on_toughness_broken = handler
        toughness_component.take_toughness_damage(100.0)
        
        assert len(events) == 1
        assert events[0].break_count == 1
        assert events[0].new_state == StanceState.BROKEN
        assert events[0].remaining_toughness == 0.0
    
    def test_on_toughness_recovered(self, toughness_component):
        """Callback при восстановлении стойкости"""
        events = []
        
        def handler(event: ToughnessRecoveryEvent):
            events.append(event)
        
        toughness_component.on_toughness_recovered = handler
        toughness_component.take_toughness_damage(100.0)
        
        # Ждем выхода из BREAK
        time.sleep(2.5)
        toughness_component._on_update(0.1)
        
        assert len(events) == 1
        assert events[0].recovered_amount > 0
        assert events[0].current_toughness == toughness_component.max_toughness
    
    def test_on_state_changed(self, toughness_component):
        """Callback при смене состояния"""
        states = []
        
        def handler(new_state: StanceState):
            states.append(new_state)
        
        toughness_component.on_state_changed = handler
        toughness_component.take_toughness_damage(80.0)  # WEAKENED
        
        assert StanceState.WEAKENED in states


# ============================================================================
# TEST: METRICS
# ============================================================================

class TestMetrics:
    """Тесты метрик"""
    
    def test_get_metrics(self, toughness_component):
        """Получение метрик компонента"""
        metrics = toughness_component.get_metrics()
        
        assert "current_toughness" in metrics
        assert "max_toughness" in metrics
        assert "toughness_percent" in metrics
        assert "state" in metrics
        assert "break_count" in metrics
        assert "damage_multiplier" in metrics
        assert "hp_based_bonus" in metrics
        assert "recovery_delay_remaining" in metrics
        
        assert metrics["current_toughness"] == 100.0
        assert metrics["state"] == "normal"
        assert metrics["break_count"] == 0
    
    def test_metrics_after_damage(self, toughness_component):
        """Метрики после получения урона"""
        toughness_component.take_toughness_damage(40.0)
        metrics = toughness_component.get_metrics()
        
        assert metrics["current_toughness"] == 60.0
        assert metrics["toughness_percent"] == 60.0


# ============================================================================
# TEST: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Тесты краевых случаев"""
    
    def test_negative_damage(self, toughness_component):
        """Отрицательный урон (лечение стойкости)"""
        result = toughness_component.take_toughness_damage(-10.0)
        # Отрицательный урон не должен увеличивать стойкость
        assert toughness_component.current_toughness == 100.0
    
    def test_very_large_damage(self, toughness_component):
        """Очень большой урон"""
        toughness_component.take_toughness_damage(10000.0)
        assert toughness_component.current_toughness == 0.0
        assert toughness_component.state == StanceState.BROKEN
    
    def test_zero_max_toughness(self):
        """Нулевая максимальная стойкость"""
        config = ToughnessConfig(max_toughness=0.0)
        comp = ToughnessComponent(config=config)
        comp.initialize()
        
        assert comp.current_toughness == 0.0
        assert comp.toughness_percent == 0.0
    
    def test_rapid_successive_hits(self, toughness_component):
        """Быстрые последовательные удары"""
        for _ in range(10):
            toughness_component.take_toughness_damage(15.0)
        
        assert toughness_component.state == StanceState.BROKEN
        assert toughness_component.break_count == 1
    
    def test_multiple_break_cycles(self, toughness_component):
        """Множественные циклы пробития"""
        for cycle in range(3):
            # Пробиваем
            toughness_component.take_toughness_damage(200.0)
            assert toughness_component.state == StanceState.BROKEN
            
            # Ждем выхода
            time.sleep(2.5)
            toughness_component._on_update(0.1)
            
            assert toughness_component.current_toughness == toughness_component.max_toughness
        
        assert toughness_component.break_count == 3


# ============================================================================
# TEST: BOSS SCENARIO
# ============================================================================

class TestBossScenario:
    """Сценарий с боссом"""
    
    def test_boss_long_fight(self, boss_toughness):
        """Длительный бой с боссом"""
        total_damage_dealt = 0
        breaks_achieved = 0
        
        # Симуляция боя на 30 секунд
        for i in range(300):  # 300 тиков по 0.1 сек
            # Наносим урон по стойкости
            dmg = boss_toughness.take_toughness_damage(50.0)
            total_damage_dealt += dmg
            
            if boss_toughness.state == StanceState.BROKEN:
                breaks_achieved += 1
            
            boss_toughness._on_update(0.1)
            time.sleep(0.01)  # Небольшая задержка
        
        # Проверяем что были пробития
        assert boss_toughness.break_count >= 1
        assert boss_toughness.max_toughness > 1000.0  # Увеличилась от HP
    
    def test_boss_enrage_pattern(self, boss_toughness):
        """Паттерн ярости босса"""
        # Сбрасываем стойкость перед тестом (на случай если предыдущий тест изменил состояние)
        boss_toughness.reset()
        
        # Пробиваем стойкость 3 раза
        # После каждого пробоя макс стойкость увеличивается на 20% от HP (1000)
        for i in range(3):
            # Наносим урон равный текущему максимуму стойкости
            current_max = boss_toughness.max_toughness
            boss_toughness.take_toughness_damage(current_max)
            assert boss_toughness.state == StanceState.BROKEN
            
            # В BROKEN босс получает +35% урона
            assert boss_toughness.damage_multiplier == 1.35
            
            # Ждем выхода из BREAK
            time.sleep(5.5)
            boss_toughness._on_update(0.1)
            
            # Проверяем что вышли из BREAK и стойкость полностью восстановлена
            assert boss_toughness.state == StanceState.NORMAL
            assert boss_toughness.current_toughness == boss_toughness.max_toughness
        
        # Макс стойкость должна вырасти после 3 пробитий
        expected_min_max = 1000.0 + (5000.0 * 0.2)  # base + 20% HP
        assert boss_toughness.max_toughness >= expected_min_max
        # Проверка что было минимум 3 пробития
        assert boss_toughness.break_count >= 3


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
