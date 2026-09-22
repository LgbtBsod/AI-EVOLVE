#!/usr/bin/env python3
"""
ICombatSystem Protocol - Unified Combat Interface

Purpose:
- Define standard interface for all combat system implementations
- Enable dependency injection via Protocol (structural typing)
- Allow swapping combat systems without code changes
- Follow Interface Segregation Principle (ISP)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class DamageInfo:
    """Информация о нанесённом уроне."""
    damage: float
    damage_type: str  # "physical", "magical", "true"
    is_critical: bool = False
    is_blocked: bool = False
    is_dodged: bool = False
    source_id: str = ""
    target_id: str = ""
    toughness_damage: float = 0.0


@dataclass(slots=True)
class CombatStats:
    """Боевые характеристики сущности."""
    physical_damage: float = 10.0
    magical_damage: float = 5.0
    defense: float = 5.0
    attack_speed: float = 1.0
    critical_chance: float = 0.05
    critical_damage: float = 1.5
    dodge_chance: float = 0.05
    block_chance: float = 0.05
    magic_resistance: float = 0.0
    accuracy: float = 0.8
    initiative: float = 10.0
    range: float = 2.0


class ICombatEntity(Protocol):
    """
    Интерфейс боевой сущности.
    
    Минимальный набор свойств и методов для участия в бою.
    Используется structural typing - любой класс с этими методами
    считается ICombatEntity.
    """
    
    @property
    def entity_id(self) -> str:
        """Уникальный идентификатор сущности."""
        ...
    
    @property
    def current_health(self) -> float:
        """Текущее здоровье."""
        ...
    
    @property
    def max_health(self) -> float:
        """Максимальное здоровье."""
        ...
    
    @property
    def is_alive(self) -> bool:
        """Жива ли сущность."""
        ...
    
    def take_damage(self, damage: float, damage_type: str) -> float:
        """
        Получить урон.
        
        Args:
            damage: Количество урона
            damage_type: Тип урона ("physical", "magical", "true")
        
        Returns:
            Фактически полученный урон (после защиты/блока)
        """
        ...
    
    def get_combat_stats(self) -> CombatStats:
        """Получить боевые характеристики."""
        ...


class ICombatSystem(Protocol):
    """
    Интерфейс системы боя.
    
    Основной контракт для всех реализаций боевой системы.
    Позволяет менять реализации без изменения клиентского кода.
    """
    
    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        """Инициализирована ли система."""
        ...
    
    @abstractmethod
    def register_entity(self, entity: ICombatEntity) -> bool:
        """
        Зарегистрировать сущность в боевой системе.
        
        Args:
            entity: Сущность для регистрации
        
        Returns:
            True если успешно, False если уже зарегистрирована
        """
        ...
    
    @abstractmethod
    def unregister_entity(self, entity_id: str) -> bool:
        """
        Удалить сущность из боевой системы.
        
        Args:
            entity_id: ID сущности для удаления
        
        Returns:
            True если успешно, False если не найдена
        """
        ...
    
    @abstractmethod
    def get_entity(self, entity_id: str) -> ICombatEntity | None:
        """
        Получить сущность по ID.
        
        Args:
            entity_id: ID сущности
        
        Returns:
            Сущность или None если не найдена
        """
        ...
    
    @abstractmethod
    def attack(
        self,
        attacker_id: str,
        target_id: str,
        attack_type: str = "melee",
        skill_id: str | None = None,
    ) -> DamageInfo:
        """
        Выполнить атаку.
        
        Args:
            attacker_id: ID атакующего
            target_id: ID цели
            attack_type: Тип атаки ("melee", "ranged", "magic", "skill")
            skill_id: ID скилла (если используется)
        
        Returns:
            DamageInfo с результатами атаки
        """
        ...
    
    @abstractmethod
    def calculate_damage(
        self,
        attacker: ICombatEntity,
        defender: ICombatEntity,
        base_damage: float,
        damage_type: str,
    ) -> tuple[float, DamageInfo]:
        """
        Рассчитать урон без нанесения.
        
        Args:
            attacker: Атакующий
            defender: Защищающийся
            base_damage: Базовый урон
            damage_type: Тип урона
        
        Returns:
            (final_damage, damage_info) - финальный урон и детали
        """
        ...
    
    @abstractmethod
    def start_combat(self, combat_id: str, participants: list[str]) -> bool:
        """
        Начать бой.
        
        Args:
            combat_id: Уникальный ID боя
            participants: Список ID участников
        
        Returns:
            True если бой начат, False если уже существует
        """
        ...
    
    @abstractmethod
    def end_combat(self, combat_id: str, winner_id: str | None = None) -> bool:
        """
        Завершить бой.
        
        Args:
            combat_id: ID боя
            winner_id: ID победителя (опционально)
        
        Returns:
            True если бой завершён, False если не найден
        """
        ...
    
    @abstractmethod
    def get_active_combats(self) -> list[str]:
        """Получить список активных боёв."""
        ...
    
    @abstractmethod
    def heal(self, entity_id: str, amount: float) -> float:
        """
        Полечить сущность.
        
        Args:
            entity_id: ID сущности
            amount: Количество лечения
        
        Returns:
            Фактически применённое лечение
        """
        ...
    
    @abstractmethod
    def get_combat_stats(self, entity_id: str) -> dict[str, Any] | None:
        """
        Получить статистику сущности.
        
        Args:
            entity_id: ID сущности
        
        Returns:
            Dict со статистикой или None
        """
        ...
    
    @abstractmethod
    def reset(self) -> None:
        """Сбросить состояние системы."""
        ...


# ============================================================================
# ABSTRACT BASE CLASS (для наследования реализациями)
# ============================================================================


class BaseCombatSystem(ABC):
    """
    Базовый класс для реализаций ICombatSystem.
    
    Предоставляет общую инфраструктуру:
    - Хранилище сущностей
    - Управление боями
    - Логирование
    - Метрики
    """
    
    def __init__(self) -> None:
        self._entities: dict[str, ICombatEntity] = {}
        self._active_combats: dict[str, dict[str, Any]] = {}
        self._is_initialized = False
        self._stats: dict[str, Any] = {
            "total_attacks": 0,
            "total_damage_dealt": 0.0,
            "total_kills": 0,
            "combats_started": 0,
        }
    
    @property
    def is_initialized(self) -> bool:
        return self._is_initialized
    
    def initialize(self) -> bool:
        """Инициализировать систему."""
        self._is_initialized = True
        return True
    
    def shutdown(self) -> bool:
        """Остановить систему."""
        self.reset()
        self._is_initialized = False
        return True
    
    def register_entity(self, entity: ICombatEntity) -> bool:
        if entity.entity_id in self._entities:
            return False
        self._entities[entity.entity_id] = entity
        return True
    
    def unregister_entity(self, entity_id: str) -> bool:
        if entity_id not in self._entities:
            return False
        del self._entities[entity_id]
        return True
    
    def get_entity(self, entity_id: str) -> ICombatEntity | None:
        return self._entities.get(entity_id)
    
    def start_combat(self, combat_id: str, participants: list[str]) -> bool:
        if combat_id in self._active_combats:
            return False
        
        self._active_combats[combat_id] = {
            "participants": participants,
            "start_time": 0,
            "turn": 0,
            "winner": None,
        }
        self._stats["combats_started"] += 1
        return True
    
    def end_combat(self, combat_id: str, winner_id: str | None = None) -> bool:
        if combat_id not in self._active_combats:
            return False
        
        combat = self._active_combats[combat_id]
        combat["winner"] = winner_id
        del self._active_combats[combat_id]
        return True
    
    def get_active_combats(self) -> list[str]:
        return list(self._active_combats.keys())
    
    def get_metrics(self) -> dict[str, Any]:
        """Получить метрики системы."""
        return {
            **self._stats,
            "registered_entities": len(self._entities),
            "active_combats": len(self._active_combats),
        }
    
    @abstractmethod
    def attack(
        self,
        attacker_id: str,
        target_id: str,
        attack_type: str = "melee",
        skill_id: str | None = None,
    ) -> DamageInfo:
        pass
    
    @abstractmethod
    def calculate_damage(
        self,
        attacker: ICombatEntity,
        defender: ICombatEntity,
        base_damage: float,
        damage_type: str,
    ) -> tuple[float, DamageInfo]:
        pass
    
    @abstractmethod
    def heal(self, entity_id: str, amount: float) -> float:
        pass
    
    @abstractmethod
    def get_combat_stats(self, entity_id: str) -> dict[str, Any] | None:
        pass
    
    @abstractmethod
    def reset(self) -> None:
        pass
