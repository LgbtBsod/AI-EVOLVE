#!/usr/bin/env python3
"""Система эффектов - баффы, дебаффы и визуальные эффекты

Refactored:
- Убран wildcard import from typing import *
- Добавлены type hints (Python 3.10+)
- Заменён time.time() на time.perf_counter()
- Внедрён RNGManager для воспроизводимости
- @dataclass(slots=True) для оптимизации памяти
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable, Set
import logging
import math
import time

from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState
from src.core.constants import EffectType, EffectCategory
from src.core.state_manager import StateManager, StateType
from src.core.rng_manager import RNGManager

logger = logging.getLogger(__name__)

# = ДОПОЛНИТЕЛЬНЫЕ ТИПЫ ЭФФЕКТОВ

class EffectStackType(Enum):
    """Типы стаков эффектов"""
    NONE = "none"              # Без стаков
    REFRESH = "refresh"        # Обновление длительности
    STACK = "stack"            # Накопление силы
    MULTIPLY = "multiply"      # Умножение силы

# = СТРУКТУРЫ ДАННЫХ

@dataclass(slots=True)
class EffectModifier:
    """Модификатор эффекта"""
    stat_type: str
    value: float
    modifier_type: str = "additive"  # additive, multiplicative, override
    condition: Optional[str] = None

@dataclass(slots=True)
class EffectTrigger:
    """Триггер эффекта"""
    trigger_type: str
    condition: str
    chance: float = 1.0
    cooldown: float = 0.0
    last_trigger: float = field(default_factory=lambda: time.perf_counter())

@dataclass(slots=True)
class Effect:
    """Эффект"""
    effect_id: str
    name: str
    description: str
    effect_type: EffectType
    category: EffectCategory
    duration: float = -1.0  # -1 для постоянных эффектов
    stack_type: EffectStackType = EffectStackType.NONE
    max_stacks: int = 1
    current_stacks: int = 1
    modifiers: List[EffectModifier] = field(default_factory=list)
    triggers: List[EffectTrigger] = field(default_factory=list)
    visual_effects: List[str] = field(default_factory=list)
    sound_effects: List[str] = field(default_factory=list)
    icon_path: Optional[str] = None
    created_at: float = field(default_factory=lambda: time.perf_counter())
    source: Optional[str] = None
    removable: bool = True
    dispellable: bool = True

@dataclass(slots=True)
class ActiveEffect:
    """Активный эффект на сущности"""
    effect: Effect
    entity_id: str
    applied_at: float = field(default_factory=lambda: time.perf_counter())
    expires_at: Optional[float] = None
    current_stacks: int = 1
    is_active: bool = True
    last_tick: float = field(default_factory=lambda: time.perf_counter())
    tick_interval: float = 1.0

@dataclass(slots=True)
class EffectTemplate:
    """Шаблон эффекта"""
    template_id: str
    name: str
    description: str
    effect_type: EffectType
    category: EffectCategory
    base_duration: float
    base_modifiers: List[EffectModifier]
    base_triggers: List[EffectTrigger]
    visual_effects: List[str]
    sound_effects: List[str]
    icon_path: Optional[str] = None
    requirements: Dict[str, Any] = field(default_factory=dict)

class EffectSystem(BaseComponent):
    """Система эффектов"""
    
    __slots__ = (
        'effect_templates',
        'active_effects',
        'total_effects_applied',
        'total_effects_removed',
        'effect_statistics',
        'on_effect_applied',
        'on_effect_removed',
        'on_effect_tick',
        '_rng'
    )
    
    def __init__(self) -> None:
        super().__init__(
            component_id="effect_system",
            component_type=ComponentType.SYSTEM,
            priority=Priority.NORMAL
        )
        
        # RNG для воспроизводимости
        self._rng = RNGManager()
        
        # Эффекты
        self.effect_templates: Dict[str, EffectTemplate] = {}
        self.active_effects: Dict[str, List[ActiveEffect]] = {}  # entity_id -> effects
        
        # Статистика
        self.total_effects_applied: int = 0
        self.total_effects_removed: int = 0
        self.effect_statistics: Dict[str, int] = {}
        
        # Callbacks
        self.on_effect_applied: Optional[Callable] = None
        self.on_effect_removed: Optional[Callable] = None
        self.on_effect_tick: Optional[Callable] = None
        
        logger.info("Система эффектов инициализирована")
    
    def initialize(self) -> bool:
        """Инициализация системы эффектов"""
        try:
            logger.info("Инициализация системы эффектов...")
            
            # Загрузка шаблонов эффектов
            if not self._load_effect_templates():
                return False
            
            # Создание базовых эффектов
            if not self._create_base_effects():
                return False
            
            self._state = LifecycleState.READY
            logger.info("Система эффектов успешно инициализирована")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации системы эффектов: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def _load_effect_templates(self) -> bool:
        """Загрузка шаблонов эффектов"""
        try:
            # Базовые шаблоны эффектов
            templates = [
                # Баффы
                EffectTemplate(
                    template_id="strength_buff",
                    name="Усиление силы",
                    description="Увеличивает силу на 20%",
                    effect_type=EffectType.BUFF,
                    category=EffectCategory.STAT_MODIFIER,
                    base_duration=30.0,
                    base_modifiers=[
                        EffectModifier("strength", 0.2, "multiplicative")
                    ],
                    base_triggers=[],
                    visual_effects=["glow_red"],
                    sound_effects=["buff_apply"],
                    icon_path="icons/strength_buff.png"
                ),
                
                EffectTemplate(
                    template_id="speed_buff",
                    name="Ускорение",
                    description="Увеличивает скорость на 30%",
                    effect_type=EffectType.BUFF,
                    category=EffectCategory.MOVEMENT,
                    base_duration=20.0,
                    base_modifiers=[
                        EffectModifier("speed", 0.3, "multiplicative")
                    ],
                    base_triggers=[],
                    visual_effects=["trail_blue"],
                    sound_effects=["speed_buff"],
                    icon_path="icons/speed_buff.png"
                ),
                
                # Дебаффы
                EffectTemplate(
                    template_id="poison_debuff",
                    name="Отравление",
                    description="Наносит урон по времени",
                    effect_type=EffectType.DEBUFF,
                    category=EffectCategory.DAMAGE_OVER_TIME,
                    base_duration=15.0,
                    base_modifiers=[
                        EffectModifier("health", -5, "additive")
                    ],
                    base_triggers=[
                        EffectTrigger("tick", "every_second", 1.0, 1.0)
                    ],
                    visual_effects=["poison_green"],
                    sound_effects=["poison_tick"],
                    icon_path="icons/poison.png"
                ),
                
                EffectTemplate(
                    template_id="slow_debuff",
                    name="Замедление",
                    description="Уменьшает скорость на 50%",
                    effect_type=EffectType.DEBUFF,
                    category=EffectCategory.MOVEMENT,
                    base_duration=10.0,
                    base_modifiers=[
                        EffectModifier("speed", -0.5, "multiplicative")
                    ],
                    base_triggers=[],
                    visual_effects=["slow_purple"],
                    sound_effects=["slow_apply"],
                    icon_path="icons/slow.png"
                ),
                
                # Лечение
                EffectTemplate(
                    template_id="heal_over_time",
                    name="Регенерация",
                    description="Восстанавливает здоровье по времени",
                    effect_type=EffectType.BUFF,
                    category=EffectCategory.HEAL_OVER_TIME,
                    base_duration=12.0,
                    base_modifiers=[
                        EffectModifier("health", 3, "additive")
                    ],
                    base_triggers=[
                        EffectTrigger("tick", "every_second", 1.0, 1.0)
                    ],
                    visual_effects=["heal_gold"],
                    sound_effects=["heal_tick"],
                    icon_path="icons/heal.png"
                ),
                
                # Магические эффекты
                EffectTemplate(
                    template_id="magic_shield",
                    name="Магический щит",
                    description="Поглощает магический урон",
                    effect_type=EffectType.BUFF,
                    category=EffectCategory.COMBAT,
                    base_duration=25.0,
                    base_modifiers=[
                        EffectModifier("magic_resistance", 0.5, "multiplicative")
                    ],
                    base_triggers=[],
                    visual_effects=["shield_blue"],
                    sound_effects=["shield_apply"],
                    icon_path="icons/magic_shield.png"
                )
            ]
            
            for template in templates:
                self.effect_templates[template.template_id] = template
            
            logger.info(f"Загружено {len(self.effect_templates)} шаблонов эффектов")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки шаблонов эффектов: {e}")
            return False
    
    def _create_base_effects(self) -> bool:
        """Создание базовых эффектов"""
        try:
            # Здесь можно создать дополнительные базовые эффекты
            # которые не являются шаблонами
            logger.info("Базовые эффекты созданы")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания базовых эффектов: {e}")
            return False
    
    def apply_effect(self, entity_id: str, template_id: str, source: Optional[str] = None, 
                    duration: Optional[float] = None, stacks: int = 1) -> Optional[str]:
        """Применение эффекта к сущности"""
        try:
            if template_id not in self.effect_templates:
                logger.error("Шаблон эффекта %s не найден", template_id)
                return None
            
            template = self.effect_templates[template_id]
            
            # Создание эффекта
            current_time = time.perf_counter()
            effect = Effect(
                effect_id=f"{template_id}_{entity_id}_{int(current_time)}",
                name=template.name,
                description=template.description,
                effect_type=template.effect_type,
                category=template.category,
                duration=duration if duration is not None else template.base_duration,
                modifiers=template.base_modifiers.copy(),
                triggers=template.base_triggers.copy(),
                visual_effects=template.visual_effects.copy(),
                sound_effects=template.sound_effects.copy(),
                icon_path=template.icon_path,
                source=source
            )
            
            # Создание активного эффекта
            active_effect = ActiveEffect(
                effect=effect,
                entity_id=entity_id,
                current_stacks=stacks
            )
            
            # Установка времени истечения
            if effect.duration > 0:
                active_effect.expires_at = current_time + effect.duration
            
            # Проверка стаков
            if not self._can_apply_effect(entity_id, effect):
                logger.warning(f"Эффект {template_id} не может быть применен к {entity_id}")
                return None
            
            # Применение эффекта
            if entity_id not in self.active_effects:
                self.active_effects[entity_id] = []
            
            self.active_effects[entity_id].append(active_effect)
            
            # Обновление статистики
            self.total_effects_applied += 1
            self.effect_statistics[template_id] = self.effect_statistics.get(template_id, 0) + 1
            
            # Вызов callback
            if self.on_effect_applied:
                self.on_effect_applied(entity_id, active_effect)
            
            logger.info(f"Эффект {template_id} применен к {entity_id}")
            return effect.effect_id
            
        except Exception as e:
            logger.error(f"Ошибка применения эффекта: {e}")
            return None
    
    def _can_apply_effect(self, entity_id: str, effect: Effect) -> bool:
        """Проверка возможности применения эффекта"""
        try:
            if entity_id not in self.active_effects:
                return True
            
            # Проверка конфликтующих эффектов
            for active_effect in self.active_effects[entity_id]:
                if active_effect.effect.name == effect.name:
                    # Проверка стаков
                    if effect.stack_type == EffectStackType.NONE:
                        return False
                    elif effect.stack_type == EffectStackType.STACK:
                        if active_effect.current_stacks >= effect.max_stacks:
                            return False
                    # Для REFRESH и MULTIPLY всегда можно применить
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки возможности применения эффекта: {e}")
            return False
    
    def remove_effect(self, entity_id: str, effect_id: str) -> bool:
        """Удаление эффекта"""
        try:
            if entity_id not in self.active_effects:
                return False
            
            effects = self.active_effects[entity_id]
            for i, active_effect in enumerate(effects):
                if active_effect.effect.effect_id == effect_id:
                    removed_effect = effects.pop(i)
                    
                    # Обновление статистики
                    self.total_effects_removed += 1
                    
                    # Вызов callback
                    if self.on_effect_removed:
                        self.on_effect_removed(entity_id, removed_effect)
                    
                    logger.info(f"Эффект {effect_id} удален с {entity_id}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка удаления эффекта: {e}")
            return False
    
    def remove_all_effects(self, entity_id: str, effect_type: Optional[EffectType] = None) -> int:
        """Удаление всех эффектов сущности"""
        try:
            if entity_id not in self.active_effects:
                return 0
            
            effects = self.active_effects[entity_id]
            removed_count = 0
            
            # Фильтрация эффектов для удаления
            effects_to_remove = []
            for active_effect in effects:
                if effect_type is None or active_effect.effect.effect_type == effect_type:
                    if active_effect.effect.removable:
                        effects_to_remove.append(active_effect)
            
            # Удаление эффектов
            for effect_to_remove in effects_to_remove:
                if self.remove_effect(entity_id, effect_to_remove.effect.effect_id):
                    removed_count += 1
            
            logger.info(f"Удалено {removed_count} эффектов с {entity_id}")
            return removed_count
            
        except Exception as e:
            logger.error(f"Ошибка удаления всех эффектов: {e}")
            return 0
    
    def get_entity_effects(self, entity_id: str, effect_type: Optional[EffectType] = None) -> List[ActiveEffect]:
        """Получение эффектов сущности"""
        try:
            if entity_id not in self.active_effects:
                return []
            
            effects = self.active_effects[entity_id]
            
            if effect_type is None:
                return effects.copy()
            
            return [effect for effect in effects if effect.effect.effect_type == effect_type]
            
        except Exception as e:
            logger.error(f"Ошибка получения эффектов сущности: {e}")
            return []
    
    def has_effect(self, entity_id: str, template_id: str) -> bool:
        """Проверка наличия эффекта у сущности"""
        try:
            if entity_id not in self.active_effects:
                return False
            
            for active_effect in self.active_effects[entity_id]:
                if active_effect.effect.name == self.effect_templates[template_id].name:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки наличия эффекта: {e}")
            return False
    
    def get_effect_modifiers(self, entity_id: str, stat_type: str) -> List[EffectModifier]:
        """Получение модификаторов эффектов для характеристики"""
        try:
            modifiers = []
            
            if entity_id not in self.active_effects:
                return modifiers
            
            for active_effect in self.active_effects[entity_id]:
                if not active_effect.is_active:
                    continue
                
                for modifier in active_effect.effect.modifiers:
                    if modifier.stat_type == stat_type:
                        # Применение стаков
                        if active_effect.current_stacks > 1:
                            if active_effect.effect.stack_type == EffectStackType.STACK:
                                modifier = EffectModifier(
                                    stat_type=modifier.stat_type,
                                    value=modifier.value * active_effect.current_stacks,
                                    modifier_type=modifier.modifier_type
                                )
                        
                        modifiers.append(modifier)
            
            return modifiers
            
        except Exception as e:
            logger.error(f"Ошибка получения модификаторов эффектов: {e}")
            return []
    
    def update(self, delta_time: float) -> None:
        """Обновление системы эффектов - делегирует _on_update"""
        super().update(delta_time)
    
    def _on_update(self, delta_time: float) -> None:
        """Внутренняя логика обновления системы эффектов"""
        try:
            current_time = time.perf_counter()
            
            # Обновление всех активных эффектов
            for entity_id, effects in list(self.active_effects.items()):
                effects_to_remove = []
                
                for active_effect in effects:
                    if not active_effect.is_active:
                        continue
                    
                    # Проверка истечения
                    if active_effect.expires_at and current_time >= active_effect.expires_at:
                        effects_to_remove.append(active_effect)
                        continue
                    
                    # Обработка триггеров
                    self._process_effect_triggers(active_effect, current_time)
                
                # Удаление истекших эффектов
                for effect_to_remove in effects_to_remove:
                    self.remove_effect(entity_id, effect_to_remove.effect.effect_id)
            
        except Exception as e:
            logger.exception("Ошибка обновления системы эффектов: %s", e)
    
    def _process_effect_triggers(self, active_effect: ActiveEffect, current_time: float):
        """Обработка триггеров эффекта"""
        try:
            for trigger in active_effect.effect.triggers:
                if current_time - trigger.last_trigger < trigger.cooldown:
                    continue
                
                if trigger.trigger_type == "tick":
                    # Обработка тиков
                    if current_time - active_effect.last_tick >= active_effect.tick_interval:
                        active_effect.last_tick = current_time
                        trigger.last_trigger = current_time
                        
                        # Вызов callback
                        if self.on_effect_tick:
                            self.on_effect_tick(active_effect.entity_id, active_effect)
                        
                        logger.debug(f"Тик эффекта {active_effect.effect.name} для {active_effect.entity_id}")
                
                elif trigger.trigger_type == "on_hit":
                    # Обработка попаданий
                    pass
                
                elif trigger.trigger_type == "on_damage":
                    # Обработка получения урона
                    pass
                
        except Exception as e:
            logger.error(f"Ошибка обработки триггеров эффекта: {e}")
    
    def create_custom_effect(self, template_id: str, custom_modifiers: List[EffectModifier], 
                           duration: float, name: str = "") -> Optional[str]:
        """Создание пользовательского эффекта"""
        try:
            if template_id not in self.effect_templates:
                return None
            
            template = self.effect_templates[template_id]
            
            current_time = time.perf_counter()
            effect = Effect(
                effect_id=f"custom_{template_id}_{int(current_time)}",
                name=name or template.name,
                description=template.description,
                effect_type=template.effect_type,
                category=template.category,
                duration=duration,
                modifiers=custom_modifiers,
                triggers=template.base_triggers.copy(),
                visual_effects=template.visual_effects.copy(),
                sound_effects=template.sound_effects.copy(),
                icon_path=template.icon_path
            )
            
            return effect.effect_id
            
        except Exception as e:
            logger.exception("Ошибка создания пользовательского эффекта: %s", e)
            return None
    
    def get_effect_statistics(self) -> Dict[str, Any]:
        """Получение статистики эффектов"""
        try:
            return {
                "total_effects_applied": self.total_effects_applied,
                "total_effects_removed": self.total_effects_removed,
                "active_effects_count": sum(len(effects) for effects in self.active_effects.values()),
                "effect_templates_count": len(self.effect_templates),
                "effect_statistics": self.effect_statistics.copy()
            }
            
        except Exception as e:
            logger.exception("Ошибка получения статистики эффектов: %s", e)
            return {}
    
    def cleanup(self) -> None:
        """Очистка системы эффектов"""
        try:
            # Удаление всех эффектов
            for entity_id in list(self.active_effects.keys()):
                self.remove_all_effects(entity_id)
            
            # Очистка данных
            self.effect_templates.clear()
            self.active_effects.clear()
            self.effect_statistics.clear()
            
            logger.info("Система эффектов очищена")
            
        except Exception as e:
            logger.error(f"Ошибка очистки системы эффектов: {e}")
