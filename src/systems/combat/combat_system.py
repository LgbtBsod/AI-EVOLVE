#!/usr/bin/env python3
"""Система боя - интеграция всех боевых механик
Управление боем, атаками, защитой, инициативой и комбо"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import *
from typing import Dict, List, Optional, Any, Tuple, Callable
import logging
import math
import time
import random

from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState
from src.core.constants import DamageType, constants_manager, PROBABILITY_CONSTANTS, ToughnessType
from src.core.state_manager import StateManager, StateType
from src.systems.attributes.attribute_system import AttributeSystem, AttributeSet, AttributeModifier, StatModifier, BaseAttribute, DerivedStat

logger = logging.getLogger(__name__)

# = ТИПЫ БОЯ

class CombatType(Enum):
    """Типы боя"""
    TURN_BASED = "turn_based"      # Пошаговый бой
    REAL_TIME = "real_time"        # Бой в реальном времени
    HYBRID = "hybrid"              # Гибридный бой

class AttackType(Enum):
    """Типы атак"""
    MELEE = "melee"                # Ближний бой
    RANGED = "ranged"              # Дальний бой
    MAGIC = "magic"                # Магическая атака
    AREA = "area"                  # Областная атака
    SPECIAL = "special"            # Специальная атака

class DefenseType(Enum):
    """Типы защиты"""
    ARMOR = "armor"                # Броня
    BLOCK = "block"                # Блок
    RESISTANCE = "resistance"      # Сопротивление

# = СТРУКТУРЫ ДАННЫХ

@dataclass
class CombatStats:
    """Боевые характеристики (теперь получаются из системы атрибутов)"""
    # Основные характеристики из атрибутов
    physical_damage: float = 10.0
    magical_damage: float = 5.0
    defense: float = 5.0
    attack_speed: float = 1.0
    critical_chance: float = 0.05
    critical_damage: float = 1.5
    dodge_chance: float = 0.05
    block_chance: float = 0.05
    magic_resistance: float = 0.0
    
    # Дополнительные боевые характеристики
    accuracy: float = 0.8
    initiative: float = 10.0
    range: float = 2.0
    
    # Модификаторы от экипировки и эффектов
    damage_modifier: float = 1.0
    defense_modifier: float = 1.0
    speed_modifier: float = 1.0

@dataclass
class DamageInfo:
    """Информация об уроне"""
    damage: float
    damage_type: DamageType
    attack_type: AttackType
    is_critical: bool = False
    is_blocked: bool = False
    is_dodged: bool = False
    toughness_damage: float = 0.0
    toughness_type: ToughnessType = ToughnessType.PHYSICAL
    source: str = ""
    target: str = ""

@dataclass
class CombatSession:
    """Сессия боя"""
    session_id: str
    participants: List[str]
    combat_type: CombatType
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    current_turn: int = 0
    turn_order: List[str] = field(default_factory=list)
    active_effects: Dict[str, List[str]] = field(default_factory=dict)
    combat_log: List[str] = field(default_factory=list)
    is_active: bool = True

@dataclass
class CombatResult:
    """Результат боя"""
    winner: str
    duration: float
    total_damage_dealt: float
    total_damage_taken: float
    critical_hits: int
    blocks: int
    dodges: int
    skills_used: Dict[str, int]

class CombatSystem(BaseComponent):
    """Система боя"""
    
    def __init__(self):
        super().__init__(
            component_id="combat_system",
            component_type=ComponentType.SYSTEM,
            priority=Priority.HIGH
        )
        
        # Архитектурные компоненты
        self.state_manager: Optional[StateManager] = None
        self.attribute_system: Optional[AttributeSystem] = None
        
        # Активные сессии боя
        self.active_sessions: Dict[str, CombatSession] = {}
        self.combat_stats: Dict[str, CombatStats] = {}
        
        # Интеграция с другими системами
        self.effect_system = None
        self.skill_system = None
        self.evolution_system = None
        self.ai_system = None
        
        # Настройки системы
        self.system_settings = {
            'auto_calculate_stats_from_attributes': True,
            'use_toughness_system': True,
            'enable_critical_hits': True,
            'enable_dodge_block': True,
            'combat_log_enabled': True,
            'max_combat_duration': 300.0  # 5 минут
        }
        
        # Статистика
        self.system_stats = {
            'total_combats': 0,
            'total_damage_dealt': 0.0,
            'total_damage_taken': 0.0,
            'critical_hits': 0,
            'blocks': 0,
            'dodges': 0,
            'toughness_breaks': 0,
            'combat_sessions_active': 0,
            'update_time': 0.0
        }
        
        # Callbacks
        self.on_combat_start: Optional[Callable] = None
        self.on_combat_end: Optional[Callable] = None
        self.on_turn_start: Optional[Callable] = None
        self.on_turn_end: Optional[Callable] = None
        self.on_damage_dealt: Optional[Callable] = None
        self.on_entity_defeated: Optional[Callable] = None
        
        logger.info("Система боя инициализирована")
    
    def set_architecture_components(self, state_manager: StateManager, attribute_system: AttributeSystem):
        """Установка архитектурных компонентов"""
        self.state_manager = state_manager
        self.attribute_system = attribute_system
        logger.info("Архитектурные компоненты установлены в CombatSystem")
    
    def _register_system_states(self):
        """Регистрация состояний системы"""
        if self.state_manager:
            self.state_manager.set_state(
                f"{self.component_id}_settings",
                self.system_settings,
                StateType.SETTINGS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_stats",
                self.system_stats,
                StateType.STATISTICS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_state",
                self.state,
                StateType.SYSTEM_STATE
            )
    
    def initialize(self) -> bool:
        """Инициализация системы боя"""
        try:
            logger.info("Инициализация CombatSystem...")
            
            self._register_system_states()
            
            self.system_state = LifecycleState.READY
            logger.info("CombatSystem инициализирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации CombatSystem: {e}")
            self.system_state = LifecycleState.ERROR
            return False
    
    def start(self) -> bool:
        """Запуск системы боя"""
        try:
            logger.info("Запуск CombatSystem...")
            
            if self.system_state != LifecycleState.READY:
                logger.error("CombatSystem не готов к запуску")
                return False
            
            self.system_state = LifecycleState.RUNNING
            logger.info("CombatSystem запущен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска CombatSystem: {e}")
            self.system_state = LifecycleState.ERROR
            return False
    
    def _on_update(self, delta_time: float):
        """Переопределяемый метод обновления (вызывается из BaseComponent.update)"""
        if self.system_state != LifecycleState.RUNNING:
            return
        
        try:
            start_time = time.time()
            
            # Обновление активных сессий боя
            self._update_combat_sessions(delta_time)
            
            # Очистка завершенных сессий
            self._cleanup_finished_sessions()
            
            self.system_stats['update_time'] = time.time() - start_time
            
            # Обновляем состояние в менеджере состояний
            if self.state_manager:
                self.state_manager.set_state(
                    f"{self.component_id}_stats",
                    self.system_stats,
                    StateType.STATISTICS
                )
                
        except Exception as e:
            logger.error(f"Ошибка обновления CombatSystem: {e}")
            raise  # Пробрасываем исключение вверх для обработки в BaseComponent
    
    def update(self, delta_time: float):
        """Публичный метод обновления (вызывается извне, делегирует _on_update)"""
        super().update(delta_time)
    
    def stop(self) -> bool:
        """Остановка системы боя"""
        try:
            logger.info("Остановка CombatSystem...")
            
            self.system_state = LifecycleState.STOPPED
            logger.info("CombatSystem остановлен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки CombatSystem: {e}")
            return False
    
    def destroy(self) -> bool:
        """Уничтожение системы боя"""
        try:
            logger.info("Уничтожение CombatSystem...")
            
            # Завершаем все активные сессии
            for session in self.active_sessions.values():
                self._end_combat_session(session.session_id)
            
            self.active_sessions.clear()
            self.combat_stats.clear()
            
            self.system_state = LifecycleState.DESTROYED
            logger.info("CombatSystem уничтожен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения CombatSystem: {e}")
            return False
    
    def _update_combat_sessions(self, delta_time: float):
        """Обновление активных сессий боя"""
        for session in list(self.active_sessions.values()):
            if not session.is_active:
                continue
            
            # Проверяем максимальную длительность боя
            if time.time() - session.start_time > self.system_settings['max_combat_duration']:
                self._end_combat_session(session.session_id, reason="timeout")
                continue
            
            # Обновляем сессию в зависимости от типа боя
            if session.combat_type == CombatType.TURN_BASED:
                self._update_turn_based_combat(session, delta_time)
            elif session.combat_type == CombatType.REAL_TIME:
                self._update_real_time_combat(session, delta_time)
            elif session.combat_type == CombatType.HYBRID:
                self._update_hybrid_combat(session, delta_time)
    
    def _cleanup_finished_sessions(self):
        """Очистка завершенных сессий"""
        finished_sessions = [
            session_id for session_id, session in self.active_sessions.items()
            if not session.is_active
        ]
        
        for session_id in finished_sessions:
            del self.active_sessions[session_id]
            if session_id in self.combat_stats:
                del self.combat_stats[session_id]
    
    def _update_turn_based_combat(self, session: CombatSession, delta_time: float):
        """Обновление пошагового боя"""
        # Логика пошагового боя
        pass
    
    def _update_real_time_combat(self, session: CombatSession, delta_time: float):
        """Обновление боя в реальном времени"""
        # Логика боя в реальном времени
        pass
    
    def _update_hybrid_combat(self, session: CombatSession, delta_time: float):
        """Обновление гибридного боя"""
        # Логика гибридного боя
        pass
    
    def get_combat_stats_for_entity(self, entity_id: str, base_attributes: AttributeSet,
                                  attribute_modifiers: List[AttributeModifier] = None,
                                  stat_modifiers: List[StatModifier] = None) -> CombatStats:
        """Получение боевых характеристик для сущности из системы атрибутов"""
        try:
            if not self.attribute_system or not self.system_settings['auto_calculate_stats_from_attributes']:
                return CombatStats()
            
            # Получаем характеристики из системы атрибутов
            calculated_stats = self.attribute_system.calculate_stats_for_entity(
                entity_id=entity_id,
                base_attributes=base_attributes,
                attribute_modifiers=attribute_modifiers,
                stat_modifiers=stat_modifiers
            )
            
            # Создаем боевые характеристики
            combat_stats = CombatStats(
                physical_damage=calculated_stats.get('physical_damage', 10.0),
                magical_damage=calculated_stats.get('magical_damage', 5.0),
                defense=calculated_stats.get('defense', 5.0),
                attack_speed=calculated_stats.get('attack_speed', 1.0),
                critical_chance=calculated_stats.get('critical_chance', 0.05),
                critical_damage=calculated_stats.get('critical_damage', 1.5),
                dodge_chance=calculated_stats.get('dodge_chance', 0.05),
                block_chance=calculated_stats.get('block_chance', 0.05),
                magic_resistance=calculated_stats.get('magic_resistance', 0.0),
                accuracy=0.8,  # Базовая точность
                initiative=calculated_stats.get('agility', 10.0),  # Инициатива от ловкости
                range=2.0  # Базовая дистанция атаки
            )
            
            return combat_stats
            
        except Exception as e:
            logger.error(f"Ошибка получения боевых характеристик для сущности {entity_id}: {e}")
            return CombatStats()
    
    def perform_attack(self, attacker_id: str, target_id: str, attack_type: AttackType,
                      base_attributes: AttributeSet, attribute_modifiers: List[AttributeModifier] = None,
                      stat_modifiers: List[StatModifier] = None) -> DamageInfo:
        """Выполнение атаки с использованием характеристик из атрибутов"""
        try:
            # Получаем боевые характеристики атакующего
            attacker_stats = self.get_combat_stats_for_entity(
                attacker_id, base_attributes, attribute_modifiers, stat_modifiers
            )
            
            # Получаем боевые характеристики цели
            target_stats = self.get_combat_stats_for_entity(
                target_id, base_attributes, attribute_modifiers, stat_modifiers
            )
            
            # Проверяем уклонение
            is_dodged = self._check_dodge(target_stats)
            if is_dodged:
                return DamageInfo(
                    damage=0.0,
                    damage_type=DamageType.PHYSICAL,
                    attack_type=attack_type,
                    is_dodged=True,
                    source=attacker_id,
                    target=target_id
                )
            
            # Проверяем блок
            is_blocked = self._check_block(target_stats)
            
            # Рассчитываем базовый урон
            base_damage = self._calculate_base_damage(attacker_stats, attack_type)
            
            # Проверяем критический удар
            is_critical = self._check_critical_hit(attacker_stats)
            if is_critical:
                base_damage *= attacker_stats.critical_damage
                self.system_stats['critical_hits'] += 1
            
            # Применяем защиту
            final_damage = self._apply_defense(base_damage, target_stats, is_blocked)
            
            # Рассчитываем урон по стойкости
            toughness_damage = 0.0
            toughness_type = ToughnessType.PHYSICAL
            
            if self.system_settings['use_toughness_system']:
                toughness_damage = self._calculate_toughness_damage(attacker_stats, attack_type)
                toughness_type = self._get_toughness_type_for_attack(attack_type)
            
            # Создаем информацию об уроне
            damage_info = DamageInfo(
                damage=final_damage,
                damage_type=DamageType.PHYSICAL,
                attack_type=attack_type,
                is_critical=is_critical,
                is_blocked=is_blocked,
                is_dodged=False,
                toughness_damage=toughness_damage,
                toughness_type=toughness_type,
                source=attacker_id,
                target=target_id
            )
            
            # Обновляем статистику
            self.system_stats['total_damage_dealt'] += final_damage
            if is_blocked:
                self.system_stats['blocks'] += 1
            if is_dodged:
                self.system_stats['dodges'] += 1
            
            # Вызываем callback
            if self.on_damage_dealt:
                self.on_damage_dealt(damage_info)
            
            return damage_info
            
        except Exception as e:
            logger.error(f"Ошибка выполнения атаки {attacker_id} -> {target_id}: {e}")
            return DamageInfo(
                damage=0.0,
                damage_type=DamageType.PHYSICAL,
                attack_type=attack_type,
                source=attacker_id,
                target=target_id
            )
    
    def _check_dodge(self, target_stats: CombatStats) -> bool:
        """Проверка уклонения"""
        if not self.system_settings['enable_dodge_block']:
            return False
        
        dodge_chance = target_stats.dodge_chance
        return random.random() < dodge_chance
    
    def _check_block(self, target_stats: CombatStats) -> bool:
        """Проверка блока"""
        if not self.system_settings['enable_dodge_block']:
            return False
        
        block_chance = target_stats.block_chance
        return random.random() < block_chance
    
    def _check_critical_hit(self, attacker_stats: CombatStats) -> bool:
        """Проверка критического удара"""
        if not self.system_settings['enable_critical_hits']:
            return False
        
        critical_chance = attacker_stats.critical_chance
        return random.random() < critical_chance
    
    def _calculate_base_damage(self, attacker_stats: CombatStats, attack_type: AttackType) -> float:
        """Расчет базового урона на основе характеристик из атрибутов"""
        try:
            # Выбираем тип урона в зависимости от типа атаки
            if attack_type == AttackType.MAGIC:
                base_damage = attacker_stats.magical_damage
            else:
                base_damage = attacker_stats.physical_damage
            
            # Модификаторы по типу атаки
            type_modifiers = {
                AttackType.MELEE: 1.0,
                AttackType.RANGED: 0.8,
                AttackType.MAGIC: 1.2,
                AttackType.AREA: 0.6,
                AttackType.SPECIAL: 1.5
            }
            
            base_damage *= type_modifiers.get(attack_type, 1.0)
            
            # Применяем модификаторы от экипировки
            base_damage *= attacker_stats.damage_modifier
            
            # Добавление случайности
            variation = random.uniform(0.8, 1.2)
            base_damage *= variation
            
            return max(1, base_damage)
            
        except Exception as e:
            logger.error(f"Ошибка расчета базового урона: {e}")
            return 10.0
    
    def _apply_defense(self, damage: float, target_stats: CombatStats, is_blocked: bool) -> float:
        """Применение защиты на основе характеристик из атрибутов"""
        try:
            final_damage = damage
            
            # Применение брони (защита из атрибутов)
            armor_reduction = target_stats.defense * 0.1  # 1 защита = 10% снижение урона
            final_damage *= (1 - armor_reduction)
            
            # Применение сопротивления магии
            magic_resistance = target_stats.magic_resistance
            final_damage *= (1 - magic_resistance)
            
            # Применение блока
            if is_blocked:
                final_damage *= 0.5  # Блок снижает урон на 50%
            
            # Применяем модификаторы защиты от экипировки
            final_damage *= target_stats.defense_modifier
            
            return max(1, final_damage)
            
        except Exception as e:
            logger.error(f"Ошибка применения защиты: {e}")
            return damage
    
    def _calculate_toughness_damage(self, attacker_stats: CombatStats, attack_type: AttackType) -> float:
        """Расчет урона по стойкости"""
        try:
            # Базовый урон по стойкости зависит от типа атаки
            base_toughness_damage = {
                AttackType.MELEE: 10.0,
                AttackType.RANGED: 5.0,
                AttackType.MAGIC: 15.0,
                AttackType.AREA: 8.0,
                AttackType.SPECIAL: 20.0
            }
            
            toughness_damage = base_toughness_damage.get(attack_type, 10.0)
            
            # Модифицируем урон по стойкости в зависимости от характеристик
            if attack_type == AttackType.MAGIC:
                toughness_damage *= (1.0 + attacker_stats.magical_damage * 0.01)
            else:
                toughness_damage *= (1.0 + attacker_stats.physical_damage * 0.01)
            
            return max(1, toughness_damage)
            
        except Exception as e:
            logger.error(f"Ошибка расчета урона по стойкости: {e}")
            return 10.0
    
    def _get_toughness_type_for_attack(self, attack_type: AttackType) -> ToughnessType:
        """Определение типа стойкости для атаки"""
        toughness_mapping = {
            AttackType.MELEE: ToughnessType.PHYSICAL,
            AttackType.RANGED: ToughnessType.PHYSICAL,
            AttackType.MAGIC: ToughnessType.QUANTUM,  # Магические атаки пробивают квантовую стойкость
            AttackType.AREA: ToughnessType.UNIVERSAL,  # Областные атаки пробивают любую стойкость
            AttackType.SPECIAL: ToughnessType.UNIVERSAL  # Специальные атаки пробивают любую стойкость
        }
        
        return toughness_mapping.get(attack_type, ToughnessType.PHYSICAL)
    
    def start_combat_session(self, session_id: str, participants: List[str], 
                           combat_type: CombatType = CombatType.REAL_TIME) -> bool:
        """Начало сессии боя"""
        try:
            if session_id in self.active_sessions:
                logger.warning(f"Сессия боя {session_id} уже существует")
                return False
            
            session = CombatSession(
                session_id=session_id,
                participants=participants,
                combat_type=combat_type
            )
            
            self.active_sessions[session_id] = session
            self.system_stats['combat_sessions_active'] += 1
            
            if self.on_combat_start:
                self.on_combat_start(session)
            
            logger.info(f"Начата сессия боя {session_id} с {len(participants)} участниками")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка начала сессии боя {session_id}: {e}")
            return False
    
    def _end_combat_session(self, session_id: str, reason: str = "normal"):
        """Завершение сессии боя"""
        try:
            if session_id not in self.active_sessions:
                return
            
            session = self.active_sessions[session_id]
            session.is_active = False
            session.end_time = time.time()
            
            self.system_stats['combat_sessions_active'] -= 1
            
            if self.on_combat_end:
                self.on_combat_end(session, reason)
            
            logger.info(f"Завершена сессия боя {session_id} по причине: {reason}")
            
        except Exception as e:
            logger.error(f"Ошибка завершения сессии боя {session_id}: {e}")
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.component_id,
            'state': self.state.value,
            'priority': self.priority.value,
            'active_sessions': len(self.active_sessions),
            'total_combats': self.system_stats['total_combats'],
            'total_damage_dealt': self.system_stats['total_damage_dealt'],
            'total_damage_taken': self.system_stats['total_damage_taken'],
            'critical_hits': self.system_stats['critical_hits'],
            'blocks': self.system_stats['blocks'],
            'dodges': self.system_stats['dodges'],
            'toughness_breaks': self.system_stats['toughness_breaks'],
            'update_time': self.system_stats['update_time']
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.system_stats = {
            'total_combats': 0,
            'total_damage_dealt': 0.0,
            'total_damage_taken': 0.0,
            'critical_hits': 0,
            'blocks': 0,
            'dodges': 0,
            'toughness_breaks': 0,
            'combat_sessions_active': len(self.active_sessions),
            'update_time': 0.0
        }
