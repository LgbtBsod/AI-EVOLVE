"""
Тесты для CAS Effect System v3.0

Проверяют:
1. Регистрацию эффектов и подписок
2. Активацию/деактивацию по событиям
3. Скалирование бонусов от HP
4. Blood Cost механику
5. Safety Net (Last Will) триггер
6. Iframe и cooldown
7. Kill Refresh механику
8. Агрегацию статов от нескольких эффектов
"""

import pytest
import time
from python_layer.l9_semantic.cas_effect_system import (
    EventType, Event, CASSubscriptionManager, EffectManager,
    EffectState, SorrowLostMySelfEffect, BaseEffect
)


class TestCASSubscriptionManager:
    """Тесты менеджера подписок CAS"""
    
    def test_subscribe_and_emit(self):
        """Проверка базовой подписки и получения событий"""
        manager = CASSubscriptionManager()
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        def condition(event):
            return True
        
        sub = manager.subscribe(
            effect_id="test_effect",
            event_types={EventType.HP_PERCENT_CHANGED},
            condition_callback=condition,
            handler_callback=handler
        )
        
        event = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="test",
            data={"hp_percent": 0.5}
        )
        
        manager.emit(event)
        
        assert len(received_events) == 1
        assert received_events[0].data["hp_percent"] == 0.5
    
    def test_unsubscribe(self):
        """Проверка отписки от событий"""
        manager = CASSubscriptionManager()
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        sub = manager.subscribe(
            effect_id="test_effect",
            event_types={EventType.HP_PERCENT_CHANGED},
            condition_callback=lambda e: True,
            handler_callback=handler
        )
        
        manager.unsubscribe(sub)
        
        event = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="test",
            data={"hp_percent": 0.5}
        )
        
        manager.emit(event)
        
        assert len(received_events) == 0
    
    def test_condition_filtering(self):
        """Проверка фильтрации событий через condition callback"""
        manager = CASSubscriptionManager()
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        def condition(event):
            return event.data.get("hp_percent", 1.0) < 0.3
        
        manager.subscribe(
            effect_id="test_effect",
            event_types={EventType.HP_PERCENT_CHANGED},
            condition_callback=condition,
            handler_callback=handler
        )
        
        # Событие с HP=50% - не пройдёт
        event_high = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="test",
            data={"hp_percent": 0.5}
        )
        manager.emit(event_high)
        
        # Событие с HP=20% - пройдёт
        event_low = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="test",
            data={"hp_percent": 0.2}
        )
        manager.emit(event_low)
        
        assert len(received_events) == 1
        assert received_events[0].data["hp_percent"] == 0.2


class TestEffectManager:
    """Тесты менеджера эффектов"""
    
    def test_register_effect(self):
        """Проверка регистрации эффекта"""
        cas_manager = CASSubscriptionManager()
        effect_manager = EffectManager("player_1", cas_manager)
        
        effect = SorrowLostMySelfEffect("player_1")
        effect_manager.register_effect(effect)
        
        # ID теперь включает счётчик: player_1_sorrow_lost_my_self_1
        assert len(effect_manager.effects) == 1
        assert any("player_1_sorrow_lost_my_self" in key for key in effect_manager.effects.keys())
        assert effect.subscription is not None
    
    def test_activate_deactivate_effect(self):
        """Проверка активации и деактивации"""
        cas_manager = CASSubscriptionManager()
        effect_manager = EffectManager("player_1", cas_manager)
        
        effect = SorrowLostMySelfEffect("player_1")
        effect_manager.register_effect(effect)
        
        event = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="test",
            data={"hp_percent": 0.3}
        )
        
        activated = effect_manager.activate_effect(effect.effect_id, event)
        assert activated is True
        assert effect.state == EffectState.ACTIVE
        
        effect_manager.deactivate_effect(effect.effect_id, "test")
        assert effect.state == EffectState.INACTIVE
    
    def test_aggregate_stats(self):
        """Проверка агрегации статов от нескольких эффектов"""
        cas_manager = CASSubscriptionManager()
        effect_manager = EffectManager("player_1", cas_manager)
        
        effect1 = SorrowLostMySelfEffect("player_1")
        effect_manager.register_effect(effect1)
        
        # Активируем эффект
        event = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="test",
            data={"hp_percent": 0.35}
        )
        effect_manager.activate_effect(effect1.effect_id, event)
        
        stats = effect_manager.get_aggregated_stats()
        
        assert "str_percent" in stats
        assert stats["str_percent"] > 0


class TestSorrowLostMySelfEffect:
    """Тесты эффекта Sorrow of Berserk"""
    
    def test_initial_state(self):
        """Проверка начального состояния"""
        effect = SorrowLostMySelfEffect("player_1")
        
        assert effect.state == EffectState.INACTIVE
        assert effect.hp_threshold == 0.40
        assert effect.scaling_step == 0.10
        assert effect.blood_cost_base == 0.005
        assert effect.blood_damage_base == 0.015
    
    def test_scaling_at_35_hp(self):
        """Проверка скалирования при 35% HP"""
        effect = SorrowLostMySelfEffect("player_1")
        effect._calculate_scaling(0.35)
        
        # Один шаг (35-40% = 5%, это меньше 10%, значит 0 шагов)
        # На самом деле int(0.05 / 0.10) = 0, значит множитель 1.0
        assert effect.scaling_multiplier == 1.0
    
    def test_scaling_at_25_hp(self):
        """Проверка скалирования при 25% HP"""
        effect = SorrowLostMySelfEffect("player_1")
        effect._calculate_scaling(0.25)
        
        # missing = 0.40 - 0.25 = 0.15
        # steps = int(0.15 / 0.10) = 1
        # multiplier = 1.0 + (1 * 0.5) = 1.5
        assert effect.scaling_multiplier == 1.5
        
        bonuses = effect.current_bonuses
        assert bonuses["str_percent"] == 0.20 * 1.5  # 30%
        assert bonuses["crit_damage_percent"] == 0.10 * 1.5  # 15%
    
    def test_scaling_at_8_hp(self):
        """Проверка скалирования при 8% HP"""
        effect = SorrowLostMySelfEffect("player_1")
        effect._calculate_scaling(0.08)
        
        # missing = 0.40 - 0.08 = 0.32
        # steps = int(0.32 / 0.10) = 3
        # multiplier = 1.0 + (3 * 0.5) = 2.5
        assert effect.scaling_multiplier == 2.5
        
        blood_info = effect.get_blood_cost_info()
        assert blood_info["cost_percent"] == 0.005 * 2.5  # 1.25%
        assert blood_info["damage_percent"] == 0.015 * 2.5  # 3.75%
    
    def test_safety_net_trigger(self):
        """Проверка триггера Safety Net"""
        effect = SorrowLostMySelfEffect("player_1")
        effect.state = EffectState.ACTIVE
        
        # HP=1%, cost=2% → Safety Net должен сработать
        safety_triggered = effect._apply_safety_net(0.02, 0.01)
        
        assert safety_triggered is True
        assert effect.last_will_active is True
        assert effect.iframes_until > time.time()
    
    def test_safety_net_no_trigger_when_enough_hp(self):
        """Проверка что Safety Net не срабатывает если HP достаточно"""
        effect = SorrowLostMySelfEffect("player_1")
        effect.state = EffectState.ACTIVE
        
        # HP=10%, cost=5% → достаточно HP
        safety_triggered = effect._apply_safety_net(0.05, 0.10)
        
        assert safety_triggered is False
        assert effect.last_will_active is False
    
    def test_safety_net_cooldown(self):
        """Проверка cooldown Safety Net"""
        effect = SorrowLostMySelfEffect("player_1")
        effect.state = EffectState.ACTIVE
        effect.safety_net_available_at = time.time() + 30.0  # В cooldown
        
        # Пытаемся активировать во время cooldown
        safety_triggered = effect._apply_safety_net(0.02, 0.01)
        
        assert safety_triggered is False
    
    def test_kill_refresh_extends_iframe(self):
        """Проверка продления iframe за убийство"""
        effect = SorrowLostMySelfEffect("player_1")
        effect.state = EffectState.ACTIVE
        effect.last_will_active = True
        before_time = time.time()
        effect.last_will_expires = before_time + 1.0
        
        kill_event = Event(
            type=EventType.KILL_CONFIRMED,
            source="player",
            data={}
        )
        
        effect.handle_event(kill_event)
        
        # Iframe должен продлиться на 5 сек от текущего момента
        assert effect.last_will_expires >= before_time + 5.0
        assert effect.iframes_until >= before_time + 5.0
    
    def test_amp_multiplier_at_1_hp(self):
        """Проверка усиления баффов при 1% HP"""
        effect = SorrowLostMySelfEffect("player_1")
        effect.state = EffectState.ACTIVE
        
        # Сначала рассчитываем скалирование для 1% HP
        effect._calculate_scaling(0.01)
        
        # missing = 0.40 - 0.01 = 0.39
        # steps = int(0.39 / 0.10) = 3
        # amp = 2^3 = 8
        effect._apply_safety_net(effect.current_blood_cost, 0.01)
        
        # Базовый str_percent = 0.20
        # После scaling (x2.5) = 0.50
        # После amp (x8) = 4.0 (400%)
        expected_str = 0.20 * 2.5 * 8
        assert effect.current_bonuses["str_percent"] == pytest.approx(expected_str, rel=0.01)
    
    def test_handle_event_hp_changed_activates(self):
        """Проверка что событие HP_CHANGED правильно обрабатывается"""
        effect = SorrowLostMySelfEffect("player_1")
        
        event = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="damage",
            data={"hp_percent": 0.30}
        )
        
        effect.handle_event(event)
        
        # Эффект должен рассчитать скалирование
        assert effect.scaling_multiplier > 1.0
    
    def test_subscription_config(self):
        """Проверка конфигурации подписки"""
        effect = SorrowLostMySelfEffect("player_1")
        config = effect.get_subscription_config()
        
        assert "event_types" in config
        assert "condition" in config
        assert EventType.HP_PERCENT_CHANGED in config["event_types"]
        assert EventType.ATTACK_PERFORMED in config["event_types"]
        assert callable(config["condition"])


class TestIntegration:
    """Интеграционные тесты полного цикла"""
    
    def test_full_activation_cycle(self):
        """Полный цикл: регистрация → активация → получение статов"""
        cas_manager = CASSubscriptionManager()
        effect_manager = EffectManager("hero_1", cas_manager)
        
        sorrow = SorrowLostMySelfEffect("hero_1")
        effect_manager.register_effect(sorrow)
        
        # HP падает до 30%
        hp_event = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="damage",
            data={"hp_percent": 0.30, "current_hp": 300, "max_hp": 1000}
        )
        
        cas_manager.emit(hp_event)
        effect_manager.activate_effect(sorrow.effect_id, hp_event)
        
        # Проверяем статы
        stats = effect_manager.get_aggregated_stats()
        assert stats["str_percent"] > 0.20  # Базовый + scaling
    
    def test_blood_cost_attack_sequence(self):
        """Серия атак с кровью"""
        cas_manager = CASSubscriptionManager()
        effect_manager = EffectManager("hero_1", cas_manager)
        
        sorrow = SorrowLostMySelfEffect("hero_1")
        effect_manager.register_effect(sorrow)
        
        # Активируем при 25% HP
        hp_event = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="damage",
            data={"hp_percent": 0.25}
        )
        cas_manager.emit(hp_event)
        effect_manager.activate_effect(sorrow.effect_id, hp_event)
        
        # Атака при 25% HP (250 HP из 1000)
        # cost = 0.005 * 1.5 * 1000 = 7.5 HP
        # 250 HP > 7.5 HP → Safety Net не сработает
        attack_event = Event(
            type=EventType.ATTACK_PERFORMED,
            source="hero",
            data={"max_hp": 1000, "current_hp": 250}
        )
        cas_manager.emit(attack_event)
        sorrow.handle_event(attack_event)
        
        # Проверка что атака прошла без Safety Net
        assert sorrow.last_will_active is False
    
    def test_multiple_effects_independence(self):
        """Независимость нескольких эффектов"""
        cas_manager = CASSubscriptionManager()
        effect_manager = EffectManager("hero_1", cas_manager)
        
        sorrow1 = SorrowLostMySelfEffect("hero_1")
        sorrow2 = SorrowLostMySelfEffect("hero_1")  # Второй экземпляр
        
        effect_manager.register_effect(sorrow1)
        effect_manager.register_effect(sorrow2)
        
        # Активируем только первый
        hp_event = Event(
            type=EventType.HP_PERCENT_CHANGED,
            source="damage",
            data={"hp_percent": 0.30}
        )
        cas_manager.emit(hp_event)
        
        # Вручную активируем первый эффект
        activated = effect_manager.activate_effect(sorrow1.effect_id, hp_event)
        assert activated is True
        
        assert sorrow1.state == EffectState.ACTIVE
        assert sorrow2.state == EffectState.INACTIVE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
