#!/usr/bin/env python3
"""Attribute System - система атрибутов и производных характеристик"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState
from src.core.constants import constants_manager, ToughnessType, StanceState
from src.core.state_manager import StateManager, StateType

logger = logging.getLogger(__name__)

class BaseAttribute(Enum):
    """Базовые атрибуты"""
    STRENGTH = "strength"           # Сила - влияет на физический урон, переносимый вес
    AGILITY = "agility"            # Ловкость - влияет на скорость атаки, уклонение, критический удар
    INTELLIGENCE = "intelligence"   # Интеллект - влияет на магический урон, ману, регенерацию маны
    VITALITY = "vitality"          # Жизненная сила - влияет на здоровье, регенерацию здоровья
    WISDOM = "wisdom"              # Мудрость - влияет на сопротивление магии, регенерацию маны
    CHARISMA = "charisma"          # Харизма - влияет на торговлю, дипломатию, лидерство
    LUCK = "luck"                  # Удача - влияет на критические удары, редкие находки
    ENDURANCE = "endurance"        # Выносливость - влияет на стамину, сопротивление усталости

class DerivedStat(Enum):
    """Производные характеристики"""
    HEALTH = "health"
    MANA = "mana"
    STAMINA = "stamina"
    PHYSICAL_DAMAGE = "physical_damage"
    MAGICAL_DAMAGE = "magical_damage"
    DEFENSE = "defense"
    ATTACK_SPEED = "attack_speed"
    SKILL_RECOVERY_SPEED = "skill_recovery_speed"
    HEALTH_REGEN = "health_regen"
    MANA_REGEN = "mana_regen"
    STAMINA_REGEN = "stamina_regen"
    CRITICAL_CHANCE = "critical_chance"
    CRITICAL_DAMAGE = "critical_damage"
    DODGE_CHANCE = "dodge_chance"
    BLOCK_CHANCE = "block_chance"
    MAGIC_RESISTANCE = "magic_resistance"
    MAX_WEIGHT = "max_weight"
    MOVEMENT_SPEED = "movement_speed"
    TOUGHNESS = "toughness"
    TOUGHNESS_RECOVERY = "toughness_recovery"

@dataclass
class AttributeModifier:
    """Модификатор атрибута"""
    modifier_id: str
    attribute: BaseAttribute
    value: float
    source: str  # Источник модификатора (предмет, эффект, и т.д.)
    duration: float = -1.0  # -1 для постоянных модификаторов
    start_time: float = field(default_factory=time.time)
    is_percentage: bool = False  # Процентный или абсолютный модификатор

@dataclass
class StatModifier:
    """Модификатор характеристики"""
    modifier_id: str
    stat: DerivedStat
    value: float
    source: str
    duration: float = -1.0
    start_time: float = field(default_factory=time.time)
    is_percentage: bool = False

@dataclass
class AttributeSet:
    """Набор атрибутов"""
    strength: float = 10.0
    agility: float = 10.0
    intelligence: float = 10.0
    vitality: float = 10.0
    wisdom: float = 10.0
    charisma: float = 10.0
    luck: float = 10.0
    endurance: float = 10.0
    
    def to_dict(self) -> Dict[str, float]:
        """Преобразование в словарь"""
        return {
            'strength': self.strength,
            'agility': self.agility,
            'intelligence': self.intelligence,
            'vitality': self.vitality,
            'wisdom': self.wisdom,
            'charisma': self.charisma,
            'luck': self.luck,
            'endurance': self.endurance
        }
    
    def from_dict(self, data: Dict[str, float]):
        """Загрузка из словаря"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

class StatCalculator:
    """Калькулятор производных характеристик"""
    
    @staticmethod
    def calculate_health(attributes: Dict[str, float]) -> float:
        """Расчет здоровья"""
        base = 100
        vitality = attributes.get('vitality', 0)
        strength = attributes.get('strength', 0)
        return base + (vitality * 10) + (strength * 2)
    
    @staticmethod
    def calculate_mana(attributes: Dict[str, float]) -> float:
        """Расчет маны"""
        base = 50
        intelligence = attributes.get('intelligence', 0)
        wisdom = attributes.get('wisdom', 0)
        return base + (intelligence * 8) + (wisdom * 4)
    
    @staticmethod
    def calculate_stamina(attributes: Dict[str, float]) -> float:
        """Расчет стамины"""
        base = 100
        endurance = attributes.get('endurance', 0)
        vitality = attributes.get('vitality', 0)
        return base + (endurance * 10) + (vitality * 3)
    
    @staticmethod
    def calculate_physical_damage(attributes: Dict[str, float]) -> float:
        """Расчет физического урона"""
        base = 10
        strength = attributes.get('strength', 0)
        agility = attributes.get('agility', 0)
        return base + (strength * 2) + (agility * 1)
    
    @staticmethod
    def calculate_magical_damage(attributes: Dict[str, float]) -> float:
        """Расчет магического урона"""
        base = 5
        intelligence = attributes.get('intelligence', 0)
        wisdom = attributes.get('wisdom', 0)
        return base + (intelligence * 3) + (wisdom * 1)
    
    @staticmethod
    def calculate_defense(attributes: Dict[str, float]) -> float:
        """Расчет защиты"""
        base = 5
        vitality = attributes.get('vitality', 0)
        endurance = attributes.get('endurance', 0)
        return base + (vitality * 1) + (endurance * 1)
    
    @staticmethod
    def calculate_attack_speed(attributes: Dict[str, float]) -> float:
        """Расчет скорости атаки"""
        base = 1.0
        agility = attributes.get('agility', 0)
        strength = attributes.get('strength', 0)
        return base + (agility * 0.05) + (strength * 0.02)
    
    @staticmethod
    def calculate_skill_recovery_speed(attributes: Dict[str, float]) -> float:
        """Расчет скорости восстановления навыков"""
        base = 1.0
        intelligence = attributes.get('intelligence', 0)
        wisdom = attributes.get('wisdom', 0)
        return base + (intelligence * 0.03) + (wisdom * 0.02)
    
    @staticmethod
    def calculate_health_regen(attributes: Dict[str, float]) -> float:
        """Расчет регенерации здоровья"""
        base = 1.0
        vitality = attributes.get('vitality', 0)
        endurance = attributes.get('endurance', 0)
        return base + (vitality * 0.5) + (endurance * 0.2)
    
    @staticmethod
    def calculate_mana_regen(attributes: Dict[str, float]) -> float:
        """Расчет регенерации маны"""
        base = 2.0
        intelligence = attributes.get('intelligence', 0)
        wisdom = attributes.get('wisdom', 0)
        return base + (intelligence * 0.4) + (wisdom * 0.3)
    
    @staticmethod
    def calculate_stamina_regen(attributes: Dict[str, float]) -> float:
        """Расчет регенерации стамины"""
        base = 3.0
        endurance = attributes.get('endurance', 0)
        vitality = attributes.get('vitality', 0)
        return base + (endurance * 0.6) + (vitality * 0.2)
    
    @staticmethod
    def calculate_critical_chance(attributes: Dict[str, float]) -> float:
        """Расчет шанса критического удара"""
        base = 0.05
        agility = attributes.get('agility', 0)
        luck = attributes.get('luck', 0)
        return base + (agility * 0.01) + (luck * 0.02)
    
    @staticmethod
    def calculate_critical_damage(attributes: Dict[str, float]) -> float:
        """Расчет критического урона"""
        base = 1.5
        strength = attributes.get('strength', 0)
        agility = attributes.get('agility', 0)
        return base + (strength * 0.05) + (agility * 0.03)
    
    @staticmethod
    def calculate_dodge_chance(attributes: Dict[str, float]) -> float:
        """Расчет шанса уклонения"""
        base = 0.05
        agility = attributes.get('agility', 0)
        luck = attributes.get('luck', 0)
        return base + (agility * 0.015) + (luck * 0.01)
    
    @staticmethod
    def calculate_block_chance(attributes: Dict[str, float]) -> float:
        """Расчет шанса блока"""
        base = 0.05
        strength = attributes.get('strength', 0)
        endurance = attributes.get('endurance', 0)
        return base + (strength * 0.01) + (endurance * 0.01)
    
    @staticmethod
    def calculate_magic_resistance(attributes: Dict[str, float]) -> float:
        """Расчет сопротивления магии"""
        base = 0.0
        wisdom = attributes.get('wisdom', 0)
        intelligence = attributes.get('intelligence', 0)
        return base + (wisdom * 0.02) + (intelligence * 0.01)
    
    @staticmethod
    def calculate_max_weight(attributes: Dict[str, float]) -> float:
        """Расчет максимального веса"""
        base = 50.0
        strength = attributes.get('strength', 0)
        endurance = attributes.get('endurance', 0)
        return base + (strength * 5) + (endurance * 2)
    
    @staticmethod
    def calculate_movement_speed(attributes: Dict[str, float]) -> float:
        """Расчет скорости движения"""
        base = 1.0
        agility = attributes.get('agility', 0)
        endurance = attributes.get('endurance', 0)
        return base + (agility * 0.03) + (endurance * 0.01)
    
    @staticmethod
    def calculate_toughness(attributes: Dict[str, float]) -> float:
        """Расчет стойкости"""
        base = 100.0
        vitality = attributes.get('vitality', 0)
        endurance = attributes.get('endurance', 0)
        return base + (vitality * 8) + (endurance * 5)
    
    @staticmethod
    def calculate_toughness_recovery(attributes: Dict[str, float]) -> float:
        """Расчет восстановления стойкости"""
        base = 10.0
        endurance = attributes.get('endurance', 0)
        vitality = attributes.get('vitality', 0)
        return base + (endurance * 0.8) + (vitality * 0.4)
    
    @classmethod
    def calculate_all_stats(cls, attributes: Dict[str, float]) -> Dict[str, float]:
        """Расчет всех характеристик"""
        return {
            'health': cls.calculate_health(attributes),
            'mana': cls.calculate_mana(attributes),
            'stamina': cls.calculate_stamina(attributes),
            'physical_damage': cls.calculate_physical_damage(attributes),
            'magical_damage': cls.calculate_magical_damage(attributes),
            'defense': cls.calculate_defense(attributes),
            'attack_speed': cls.calculate_attack_speed(attributes),
            'skill_recovery_speed': cls.calculate_skill_recovery_speed(attributes),
            'health_regen': cls.calculate_health_regen(attributes),
            'mana_regen': cls.calculate_mana_regen(attributes),
            'stamina_regen': cls.calculate_stamina_regen(attributes),
            'critical_chance': cls.calculate_critical_chance(attributes),
            'critical_damage': cls.calculate_critical_damage(attributes),
            'dodge_chance': cls.calculate_dodge_chance(attributes),
            'block_chance': cls.calculate_block_chance(attributes),
            'magic_resistance': cls.calculate_magic_resistance(attributes),
            'max_weight': cls.calculate_max_weight(attributes),
            'movement_speed': cls.calculate_movement_speed(attributes),
            'toughness': cls.calculate_toughness(attributes),
            'toughness_recovery': cls.calculate_toughness_recovery(attributes)
        }

class AttributeSystem(BaseComponent):
    """Система атрибутов и характеристик"""
    
    def __init__(self):
        super().__init__(
            component_id="attribute_system",
            component_type=ComponentType.SYSTEM,
            priority=Priority.HIGH
        )
        
        # Архитектурные компоненты
        self.state_manager: Optional[StateManager] = None
        
        # Калькулятор характеристик
        self.stat_calculator = StatCalculator()
        
        # Настройки системы
        self.system_settings = {
            'auto_recalculate_on_modifier_change': True,
            'cache_calculated_stats': True,
            'max_modifiers_per_attribute': 50,
            'modifier_cleanup_interval': 60.0  # секунды
        }
        
        # Статистика системы
        self.system_stats = {
            'total_entities': 0,
            'active_modifiers': 0,
            'stat_calculations': 0,
            'modifier_applications': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'update_time': 0.0
        }
        
        # Кэш расчетов
        self._stat_cache: Dict[str, Dict[str, float]] = {}
        self._last_cleanup_time = time.time()
    
    def set_architecture_components(self, state_manager: StateManager):
        """Установка архитектурных компонентов"""
        self.state_manager = state_manager
        logger.info("Архитектурные компоненты установлены в AttributeSystem")
    
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
                self._state,
                StateType.SYSTEM_STATE
            )
    
    def initialize(self) -> bool:
        """Инициализация системы атрибутов"""
        try:
            logger.info("Инициализация AttributeSystem...")
            
            self._register_system_states()
            
            self._state = LifecycleState.READY
            logger.info("AttributeSystem инициализирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации AttributeSystem: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def start(self) -> bool:
        """Запуск системы атрибутов"""
        try:
            logger.info("Запуск AttributeSystem...")
            
            if self._state != LifecycleState.READY:
                logger.error("AttributeSystem не готов к запуску")
                return False
            
            self._state = LifecycleState.RUNNING
            logger.info("AttributeSystem запущен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска AttributeSystem: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def update(self, delta_time: float):
        """Обновление системы атрибутов"""
        if self._state != LifecycleState.RUNNING:
            return
        
        try:
            start_time = time.time()
            
            # Очистка кэша и устаревших модификаторов
            self._cleanup_cache_and_modifiers()
            
            self.system_stats['update_time'] = time.time() - start_time
            
            # Обновляем состояние в менеджере состояний
            if self.state_manager:
                self.state_manager.set_state(
                    f"{self.component_id}_stats",
                    self.system_stats,
                    StateType.STATISTICS
                )
                
        except Exception as e:
            logger.error(f"Ошибка обновления AttributeSystem: {e}")
    
    def stop(self) -> bool:
        """Остановка системы атрибутов"""
        try:
            logger.info("Остановка AttributeSystem...")
            
            self._state = LifecycleState.STOPPED
            logger.info("AttributeSystem остановлен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки AttributeSystem: {e}")
            return False
    
    def destroy(self) -> bool:
        """Уничтожение системы атрибутов"""
        try:
            logger.info("Уничтожение AttributeSystem...")
            
            self._stat_cache.clear()
            
            self._state = LifecycleState.DESTROYED
            logger.info("AttributeSystem уничтожен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения AttributeSystem: {e}")
            return False
    
    def _cleanup_cache_and_modifiers(self):
        """Очистка кэша и устаревших модификаторов"""
        current_time = time.time()
        
        # Очищаем кэш каждые 60 секунд
        if current_time - self._last_cleanup_time >= self.system_settings['modifier_cleanup_interval']:
            self._stat_cache.clear()
            self._last_cleanup_time = current_time
            logger.debug("Кэш характеристик очищен")
    
    def calculate_stats_for_entity(self, entity_id: str, base_attributes: AttributeSet, 
                                 attribute_modifiers: List[AttributeModifier] = None,
                                 stat_modifiers: List[StatModifier] = None) -> Dict[str, float]:
        """Расчет характеристик для сущности"""
        try:
            # Проверяем кэш
            cache_key = f"{entity_id}_{hash(str(base_attributes))}"
            if self.system_settings['cache_calculated_stats'] and cache_key in self._stat_cache:
                self.system_stats['cache_hits'] += 1
                return self._stat_cache[cache_key].copy()
            
            self.system_stats['cache_misses'] += 1
            
            # Применяем модификаторы атрибутов
            final_attributes = self._apply_attribute_modifiers(base_attributes, attribute_modifiers or [])
            
            # Рассчитываем базовые характеристики
            calculated_stats = self.stat_calculator.calculate_all_stats(final_attributes)
            
            # Применяем модификаторы характеристик
            final_stats = self._apply_stat_modifiers(calculated_stats, stat_modifiers or [])
            
            # Кэшируем результат
            if self.system_settings['cache_calculated_stats']:
                self._stat_cache[cache_key] = final_stats.copy()
            
            self.system_stats['stat_calculations'] += 1
            
            return final_stats
            
        except Exception as e:
            logger.error(f"Ошибка расчета характеристик для сущности {entity_id}: {e}")
            return {}
    
    def _apply_attribute_modifiers(self, base_attributes: AttributeSet, 
                                 modifiers: List[AttributeModifier]) -> Dict[str, float]:
        """Применение модификаторов атрибутов"""
        try:
            # Начинаем с базовых атрибутов
            final_attributes = base_attributes.to_dict()
            
            current_time = time.time()
            
            for modifier in modifiers:
                # Проверяем, не истек ли модификатор
                if modifier.duration > 0 and current_time - modifier.start_time > modifier.duration:
                    continue
                
                attr_name = modifier.attribute.value
                if attr_name in final_attributes:
                    if modifier.is_percentage:
                        # Процентный модификатор
                        final_attributes[attr_name] *= (1.0 + modifier.value / 100.0)
                    else:
                        # Абсолютный модификатор
                        final_attributes[attr_name] += modifier.value
                
                self.system_stats['modifier_applications'] += 1
            
            return final_attributes
            
        except Exception as e:
            logger.error(f"Ошибка применения модификаторов атрибутов: {e}")
            return base_attributes.to_dict()
    
    def _apply_stat_modifiers(self, base_stats: Dict[str, float], 
                            modifiers: List[StatModifier]) -> Dict[str, float]:
        """Применение модификаторов характеристик"""
        try:
            final_stats = base_stats.copy()
            
            current_time = time.time()
            
            for modifier in modifiers:
                # Проверяем, не истек ли модификатор
                if modifier.duration > 0 and current_time - modifier.start_time > modifier.duration:
                    continue
                
                stat_name = modifier.stat.value
                if stat_name in final_stats:
                    if modifier.is_percentage:
                        # Процентный модификатор
                        final_stats[stat_name] *= (1.0 + modifier.value / 100.0)
                    else:
                        # Абсолютный модификатор
                        final_stats[stat_name] += modifier.value
                
                self.system_stats['modifier_applications'] += 1
            
            return final_stats
            
        except Exception as e:
            logger.error(f"Ошибка применения модификаторов характеристик: {e}")
            return base_stats
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.component_id,
            'state': self.state.value,
            'priority': self.priority.value,
            'total_entities': self.system_stats['total_entities'],
            'active_modifiers': self.system_stats['active_modifiers'],
            'stat_calculations': self.system_stats['stat_calculations'],
            'modifier_applications': self.system_stats['modifier_applications'],
            'cache_hits': self.system_stats['cache_hits'],
            'cache_misses': self.system_stats['cache_misses'],
            'cache_size': len(self._stat_cache),
            'update_time': self.system_stats['update_time']
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.system_stats = {
            'total_entities': 0,
            'active_modifiers': 0,
            'stat_calculations': 0,
            'modifier_applications': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'update_time': 0.0
        }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.component_id,
            'state': self.state.value,
            'priority': self.priority.value,
            'total_entities': self.system_stats['total_entities'],
            'active_modifiers': self.system_stats['active_modifiers'],
            'stat_calculations': self.system_stats['stat_calculations'],
            'modifier_applications': self.system_stats['modifier_applications'],
            'cache_hits': self.system_stats['cache_hits'],
            'cache_misses': self.system_stats['cache_misses'],
            'cache_size': len(self._stat_cache),
            'update_time': self.system_stats['update_time']
        }
