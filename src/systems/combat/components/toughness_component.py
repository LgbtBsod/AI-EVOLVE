#!/usr/bin/env python3
"""Toughness Component - Система стойкости в стиле HSR/BNS

Компонент управляет полоской стойкости врага:
- При достижении 0 стойкости враг получает состояние BROKEN
- В состоянии BROKEN враг оглушен и получает повышенный урон
- После выхода из BROKEN стойкость восстанавливается полностью
- Каждый пробив повышает максимальную стойкость на % от макс HP (до 20%)
- Урон по стойкости зависит от типа атаки и типа стойкости врага
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from src.core.architecture import BaseComponent, ComponentType, LifecycleState, Priority
from src.core.constants import StanceState, ToughnessType

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToughnessConfig:
    """Конфигурация системы стойкости"""
    max_toughness: float = 100.0
    recovery_rate: float = 10.0  # Единиц стойкости в секунду
    recovery_delay: float = 3.0  # Задержка перед началом восстановления после удара
    break_duration: float = 5.0  # Длительность состояния BROKEN
    damage_taken_multiplier_broken: float = 0.25  # +25% урона когда сломан
    toughness_from_hp_ratio: float = 0.05  # 5% от макс HP при каждом пробиве (накопительно)
    max_toughness_cap_ratio: float = 0.2  # Максимум 20% от HP
    auto_recover_on_break_end: bool = True  # Авто-восстановление до full после BREAK


@dataclass(slots=True)
class ToughnessBreakEvent:
    """Событие пробития стойкости"""
    entity_id: str
    previous_state: StanceState
    new_state: StanceState
    toughness_damage: float
    remaining_toughness: float
    break_count: int
    timestamp: float = field(default_factory=time.perf_counter)


@dataclass(slots=True)
class ToughnessRecoveryEvent:
    """Событие восстановления стойкости"""
    entity_id: str
    recovered_amount: float
    current_toughness: float
    timestamp: float = field(default_factory=time.perf_counter)


class ToughnessComponent(BaseComponent):
    """Компонент стойкости сущности"""
    
    __slots__ = (
        '_config',
        '_current_toughness',
        '_max_toughness',
        '_state',
        '_break_count',
        '_last_damage_time',
        '_break_start_time',
        '_base_max_toughness',
        '_hp_based_bonus',
        'on_toughness_changed',
        'on_toughness_broken',
        'on_toughness_recovered',
        'on_state_changed'
    )
    
    def __init__(
        self,
        entity_id: str = "unknown",
        config: ToughnessConfig | None = None,
        max_health: float = 100.0
    ):
        super().__init__(
            component_id=f"toughness_{entity_id}",
            component_type=ComponentType.COMPONENT,
            priority=Priority.NORMAL
        )
        
        self._config = config or ToughnessConfig()
        self._base_max_toughness = self._config.max_toughness
        self._max_toughness = self._base_max_toughness
        self._current_toughness = self._max_toughness
        self._state = StanceState.NORMAL
        self._break_count = 0
        self._last_damage_time: float = 0.0
        self._break_start_time: float = 0.0
        self._hp_based_bonus: float = 0.0
        self._max_health = max_health
        
        # Callbacks
        self.on_toughness_changed: Callable | None = None
        self.on_toughness_broken: Callable | None = None
        self.on_toughness_recovered: Callable | None = None
        self.on_state_changed: Callable | None = None
        
        logger.debug(f"ToughnessComponent создан для {entity_id}: max={self._max_toughness}")
    
    @property
    def current_toughness(self) -> float:
        """Текущее значение стойкости"""
        return self._current_toughness
    
    @property
    def max_toughness(self) -> float:
        """Максимальное значение стойкости (с учетом бонусов от пробивов)"""
        return self._max_toughness
    
    @property
    def state(self) -> StanceState:
        """Текущее состояние стойкости"""
        return self._state
    
    @property
    def break_count(self) -> int:
        """Количество пробитий стойкости"""
        return self._break_count
    
    @property
    def toughness_percent(self) -> float:
        """Процент текущей стойкости"""
        if self._max_toughness <= 0:
            return 0.0
        return (self._current_toughness / self._max_toughness) * 100.0
    
    @property
    def is_broken(self) -> bool:
        """Проверка состояния BROKEN"""
        return self._state == StanceState.BROKEN
    
    @property
    def is_recovering(self) -> bool:
        """Проверка состояния RECOVERING"""
        return self._state == StanceState.RECOVERING
    
    @property
    def damage_multiplier(self) -> float:
        """Множитель входящего урона в зависимости от состояния"""
        if self._state == StanceState.BROKEN:
            return 1.0 + self._config.damage_taken_multiplier_broken
        elif self._state == StanceState.WEAKENED:
            return 1.0 + (self._config.damage_taken_multiplier_broken * 0.5)
        elif self._state == StanceState.RECOVERING:
            return 1.0 + (self._config.damage_taken_multiplier_broken * 0.2)
        return 1.0
    
    def _on_update(self, delta_time: float) -> None:
        """Обновление компонента"""
        if self._state != LifecycleState.READY and self._state not in (StanceState.NORMAL, StanceState.WEAKENED, StanceState.BROKEN, StanceState.RECOVERING):
            # Проверяем что это не StanceState
            pass
        
        current_time = time.perf_counter()
        
        # Обработка состояния BROKEN
        if self._state == StanceState.BROKEN:
            time_in_break = current_time - self._break_start_time
            if time_in_break >= self._config.break_duration:
                self._exit_break_state(current_time)
                return  # Выходим чтобы не делать восстановление в том же тике
        
        # Восстановление стойкости
        if self._state in (StanceState.NORMAL, StanceState.RECOVERING):
            self._recover_toughness(delta_time, current_time)
    
    def take_toughness_damage(
        self,
        damage: float,
        toughness_type: ToughnessType = ToughnessType.UNIVERSAL,
        enemy_toughness_type: ToughnessType = ToughnessType.PHYSICAL
    ) -> float:
        """
        Получение урона по стойкости.
        
        Args:
            damage: Базовый урон по стойкости
            toughness_type: Тип урона атакующего
            enemy_toughness_type: Тип стойкости врага
        
        Returns:
            Фактический нанесенный урон с учетом множителей
        """
        if self._state == StanceState.BROKEN:
            logger.debug("Стойкость уже пробита, урон не применяется")
            return 0.0
        
        # Игнорируем отрицательный урон (нельзя лечить стойкость)
        if damage <= 0:
            return 0.0
        
        # Расчет множителя эффективности стихии
        effectiveness = self._get_elemental_effectiveness(toughness_type, enemy_toughness_type)
        actual_damage = damage * effectiveness
        
        # Применение урона
        old_toughness = self._current_toughness
        self._current_toughness = max(0.0, self._current_toughness - actual_damage)
        self._last_damage_time = time.perf_counter()
        
        # Проверка на ослабленную стойкость (ниже 25%)
        if self._state == StanceState.NORMAL and self._current_toughness < self._max_toughness * 0.25:
            self._set_state(StanceState.WEAKENED)
        
        # Проверка на пробитие
        if self._current_toughness <= 0.0:
            self._trigger_break()
        
        # Вызов callback
        if self.on_toughness_changed:
            self.on_toughness_changed(self._current_toughness, old_toughness)
        
        logger.debug(
            f"Урон по стойкости: {damage:.1f} -> {actual_damage:.1f} (eff={effectiveness:.2f}), "
            f"осталось: {self._current_toughness:.1f}/{self._max_toughness:.1f}"
        )
        
        return actual_damage
    
    def _get_elemental_effectiveness(
        self, 
        attack_type: ToughnessType, 
        defense_type: ToughnessType
    ) -> float:
        """Получение множителя эффективности стихии"""
        from src.core.constants import TOUGHNESS_CONSTANTS
        
        elemental = TOUGHNESS_CONSTANTS.get("elemental_effectiveness", {})
        attack_key = attack_type.value
        defense_key = defense_type.value
        
        if attack_key in elemental and defense_key in elemental[attack_key]:
            return elemental[attack_key][defense_key]
        
        # По умолчанию универсальный тип
        return 1.0
    
    def _trigger_break(self) -> None:
        """Срабатывание пробития стойкости"""
        self._break_count += 1
        self._current_toughness = 0.0
        self._break_start_time = time.perf_counter()
        
        previous_state = self._state
        self._set_state(StanceState.BROKEN)
        
        # Увеличение максимальной стойкости на % от макс HP
        self._increase_max_toughness()
        
        logger.info(
            f"СТОЙКОСТЬ ПРОБИТА! #{self._break_count}, "
            f"новый макс: {self._max_toughness:.1f}"
        )
        
        # Событие пробития
        if self.on_toughness_broken:
            event = ToughnessBreakEvent(
                entity_id=self.component_id,
                previous_state=previous_state,
                new_state=StanceState.BROKEN,
                toughness_damage=self._max_toughness,
                remaining_toughness=0.0,
                break_count=self._break_count
            )
            self.on_toughness_broken(event)
    
    def _increase_max_toughness(self) -> None:
        """Увеличение максимальной стойкости после пробития"""
        if self._max_health <= 0:
            return
        
        # Бонус от HP с накоплением
        hp_bonus = self._max_health * self._config.toughness_from_hp_ratio
        
        # Текущий бонус увеличивается с каждым пробитием
        self._hp_based_bonus += hp_bonus
        
        # Ограничение максимумом
        max_allowed_bonus = self._max_health * self._config.max_toughness_cap_ratio
        self._hp_based_bonus = min(self._hp_based_bonus, max_allowed_bonus)
        
        # Пересчет максимума
        self._max_toughness = self._base_max_toughness + self._hp_based_bonus
        
        logger.debug(
            f"Макс стойкость увеличен: base={self._base_max_toughness:.1f}, "
            f"bonus={self._hp_based_bonus:.1f}, total={self._max_toughness:.1f}"
        )
    
    def _exit_break_state(self, current_time: float) -> None:
        """Выход из состояния BROKEN"""
        previous_state = self._state
        
        if self._config.auto_recover_on_break_end:
            # Полное восстановление стойкости
            old_toughness = self._current_toughness
            self._current_toughness = self._max_toughness
            
            logger.info(f"Стойкость восстановлена полностью: {self._current_toughness:.1f}")
            
            if self.on_toughness_recovered:
                event = ToughnessRecoveryEvent(
                    entity_id=self.component_id,
                    recovered_amount=self._current_toughness - old_toughness,
                    current_toughness=self._current_toughness
                )
                self.on_toughness_recovered(event)
        
        # Переход в NORMAL сразу после восстановления
        self._set_state(StanceState.NORMAL)
        
        # Сброс таймера для восстановления
        self._break_start_time = current_time
        
        if self.on_state_changed:
            self.on_state_changed(StanceState.NORMAL)
    
    def _recover_toughness(self, delta_time: float, current_time: float) -> None:
        """Восстановление стойкости со временем"""
        # Проверка задержки после получения урона
        time_since_damage = current_time - self._last_damage_time
        if time_since_damage < self._config.recovery_delay:
            return
        
        # Если в состоянии RECOVERING, проверяем задержку после выхода из BREAK
        if self._state == StanceState.RECOVERING:
            time_in_recovering = current_time - self._break_start_time
            if time_in_recovering < self._config.recovery_delay:
                return
        
        # Восстановление
        recovery_amount = self._config.recovery_rate * delta_time
        old_toughness = self._current_toughness
        
        if self._current_toughness < self._max_toughness:
            self._current_toughness = min(self._max_toughness, self._current_toughness + recovery_amount)
            
            # Переход в NORMAL при полном восстановлении
            if self._current_toughness >= self._max_toughness and self._state == StanceState.RECOVERING:
                self._set_state(StanceState.NORMAL)
            
            # Вызов callback только если стойкость изменилась и это не полный恢复
            if abs(self._current_toughness - old_toughness) > 0.01 and self.on_toughness_changed:
                self.on_toughness_changed(self._current_toughness, old_toughness)
    
    def _set_state(self, new_state: StanceState) -> None:
        """Установка нового состояния"""
        if self._state == new_state:
            return
        
        old_state = self._state
        self._state = new_state
        
        logger.debug(f"Состояние стойкости: {old_state.value} -> {new_state.value}")
        
        if self.on_state_changed:
            self.on_state_changed(new_state)
    
    def set_max_health(self, max_health: float) -> None:
        """Установка максимального здоровья (для расчета бонусов)"""
        self._max_health = max_health
    
    def reset(self) -> None:
        """Сброс компонента к начальному состоянию"""
        self._current_toughness = self._base_max_toughness
        self._max_toughness = self._base_max_toughness
        self._hp_based_bonus = 0.0
        self._break_count = 0
        self._state = StanceState.NORMAL
        self._last_damage_time = 0.0
        self._break_start_time = 0.0
        
        logger.info("ToughnessComponent сброшен")
    
    def get_metrics(self) -> dict:
        """Метрики компонента"""
        base_metrics = super().get_metrics()
        base_metrics.update({
            "current_toughness": self._current_toughness,
            "max_toughness": self._max_toughness,
            "toughness_percent": self.toughness_percent,
            "state": self._state.value,
            "break_count": self._break_count,
            "damage_multiplier": self.damage_multiplier,
            "hp_based_bonus": self._hp_based_bonus,
            "recovery_delay_remaining": max(
                0.0,
                self._config.recovery_delay - (time.perf_counter() - self._last_damage_time)
            ) if self._last_damage_time > 0 else 0.0
        })
        return base_metrics
