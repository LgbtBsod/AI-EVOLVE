#!/usr/bin/env python3
"""Система памяти - расширенная память с AI и эволюцией
Управление памятью сущностей, обучением и эволюционными изменениями"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import *
from typing import Dict, List, Optional, Any, Tuple, Callable
import logging
import math
import time
import random
import json
import pickle

from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState

logger = logging.getLogger(__name__)

# = ТИПЫ ПАМЯТИ

class MemoryType(Enum):
    """Типы памяти"""
    SHORT_TERM = "short_term"      # Кратковременная память
    LONG_TERM = "long_term"        # Долговременная память
    EPISODIC = "episodic"          # Эпизодическая память
    SEMANTIC = "semantic"          # Семантическая память
    PROCEDURAL = "procedural"      # Процедурная память
    EMOTIONAL = "emotional"        # Эмоциональная память
    GENETIC = "genetic"            # Генетическая память

class MemoryCategory(Enum):
    """Категории памяти"""
    COMBAT = "combat"              # Боевые воспоминания
    SOCIAL = "social"              # Социальные взаимодействия
    EXPLORATION = "exploration"    # Исследования
    LEARNING = "learning"          # Обучение
    SURVIVAL = "survival"          # Выживание
    EVOLUTION = "evolution"        # Эволюция

class MemoryStrength(Enum):
    """Сила памяти"""
    WEAK = "weak"                  # Слабая
    NORMAL = "normal"              # Обычная
    STRONG = "strong"              # Сильная
    INTENSE = "intense"            # Интенсивная

# = СТРУКТУРЫ ДАННЫХ

@dataclass
class Memory:
    """Воспоминание"""
    memory_id: str
    entity_id: str
    memory_type: MemoryType
    category: MemoryCategory
    title: str
    description: str
    data: Dict[str, Any] = field(default_factory=dict)
    strength: MemoryStrength = MemoryStrength.NORMAL
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    emotional_value: float = 0.0
    importance: float = 0.5
    decay_rate: float = 0.01
    is_consolidated: bool = False

@dataclass
class MemoryPattern:
    """Паттерн памяти"""
    pattern_id: str
    name: str
    description: str
    memory_types: List[MemoryType] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)
    triggers: List[str] = field(default_factory=list)
    effects: Dict[str, Any] = field(default_factory=dict)

@dataclass
class EntityMemory:
    """Память сущности"""
    entity_id: str
    short_term_memories: List[Memory] = field(default_factory=list)
    long_term_memories: List[Memory] = field(default_factory=list)
    memory_patterns: List[MemoryPattern] = field(default_factory=list)
    learning_rate: float = 1.0
    memory_capacity: int = 1000
    consolidation_threshold: float = 0.7
    last_consolidation: float = field(default_factory=time.time)

@dataclass
class SharedMemory:
    """Общая память"""
    memory_id: str
    title: str
    description: str
    contributors: List[str] = field(default_factory=list)
    memory_type: MemoryType = MemoryType.SEMANTIC
    category: MemoryCategory = MemoryCategory.LEARNING
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    access_count: int = 0

@dataclass
class EvolutionMemory:
    """Эволюционная память"""
    memory_id: str
    species_id: str
    generation: int
    evolution_type: str
    changes: Dict[str, Any] = field(default_factory=dict)
    success_rate: float = 0.0
    created_at: float = field(default_factory=time.time)
    inherited_by: List[str] = field(default_factory=list)

class MemorySystem(BaseComponent):
    """Система памяти"""
    
    def __init__(self):
        super().__init__(
            component_id="memory_system",
            component_type=ComponentType.SYSTEM,
            priority=Priority.NORMAL
        )
        
        # Память сущностей
        self.entity_memories: Dict[str, EntityMemory] = {}
        
        # Общая память
        self.shared_memories: Dict[str, SharedMemory] = {}
        
        # Эволюционная память
        self.evolution_memories: Dict[str, EvolutionMemory] = {}
        
        # Паттерны памяти
        self.memory_patterns: Dict[str, MemoryPattern] = {}
        
        # Интеграция с другими системами
        self.ai_system = None
        self.evolution_system = None
        self.social_system = None
        
        # Настройки
        self.max_short_term_memories: int = 50
        self.max_long_term_memories: int = 1000
        self.consolidation_interval: float = 60.0  # секунды
        self.decay_interval: float = 300.0  # секунды
        
        # Статистика
        self.total_memories_created: int = 0
        self.total_memories_consolidated: int = 0
        self.total_memories_decayed: int = 0
        
        # Callbacks
        self.on_memory_created: Optional[Callable] = None
        self.on_memory_consolidated: Optional[Callable] = None
        self.on_memory_decayed: Optional[Callable] = None
        self.on_pattern_triggered: Optional[Callable] = None
        
        logger.info("Система памяти инициализирована")
    
    def initialize(self) -> bool:
        """Инициализация системы памяти"""
        try:
            logger.info("Инициализация системы памяти...")
            
            # Создание паттернов памяти
            if not self._create_memory_patterns():
                return False
            
            # Запуск процессов памяти
            self._start_memory_processes()
            
            self.state = LifecycleState.READY
            logger.info("Система памяти успешно инициализирована")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации системы памяти: {e}")
            self.state = LifecycleState.ERROR
            return False
    
    def _create_memory_patterns(self) -> bool:
        """Создание паттернов памяти"""
        try:
            # Паттерн боевого опыта
            combat_pattern = MemoryPattern(
                pattern_id="combat_experience",
                name="Боевой опыт",
                description="Накопление боевого опыта",
                memory_types=[MemoryType.EPISODIC, MemoryType.PROCEDURAL],
                conditions={
                    "combat_events": 5,
                    "success_rate": 0.6
                },
                triggers=["combat_victory", "combat_defeat", "skill_improvement"],
                effects={
                    "combat_bonus": 0.1,
                    "skill_learning_rate": 0.2
                }
            )
            
            # Паттерн социального взаимодействия
            social_pattern = MemoryPattern(
                pattern_id="social_interaction",
                name="Социальное взаимодействие",
                description="Накопление социального опыта",
                memory_types=[MemoryType.EMOTIONAL, MemoryType.SEMANTIC],
                conditions={
                    "interactions": 10,
                    "positive_ratio": 0.7
                },
                triggers=["dialogue", "relationship_change", "reputation_change"],
                effects={
                    "social_skills": 0.15,
                    "relationship_bonus": 0.1
                }
            )
            
            # Паттерн исследования
            exploration_pattern = MemoryPattern(
                pattern_id="exploration_experience",
                name="Опыт исследования",
                description="Накопление опыта исследования",
                memory_types=[MemoryType.EPISODIC, MemoryType.SEMANTIC],
                conditions={
                    "locations_discovered": 20,
                    "exploration_time": 3600
                },
                triggers=["location_discovered", "treasure_found", "danger_encountered"],
                effects={
                    "exploration_bonus": 0.1,
                    "survival_skills": 0.1
                }
            )
            
            # Паттерн эволюции
            evolution_pattern = MemoryPattern(
                pattern_id="evolution_memory",
                name="Эволюционная память",
                description="Накопление эволюционного опыта",
                memory_types=[MemoryType.GENETIC, MemoryType.LONG_TERM],
                conditions={
                    "generations": 3,
                    "successful_mutations": 5
                },
                triggers=["mutation", "evolution", "generation_change"],
                effects={
                    "evolution_rate": 0.2,
                    "mutation_success": 0.15
                }
            )
            
            patterns = [combat_pattern, social_pattern, exploration_pattern, evolution_pattern]
            
            for pattern in patterns:
                self.memory_patterns[pattern.pattern_id] = pattern
            
            logger.info(f"Создано {len(self.memory_patterns)} паттернов памяти")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания паттернов памяти: {e}")
            return False
    
    def _start_memory_processes(self):
        """Запуск процессов памяти"""
        try:
            import threading
            
            # Процесс консолидации памяти
            self.consolidation_thread = threading.Thread(
                target=self._consolidation_process,
                daemon=True
            )
            self.consolidation_thread.start()
            
            # Процесс распада памяти
            self.decay_thread = threading.Thread(
                target=self._decay_process,
                daemon=True
            )
            self.decay_thread.start()
            
            logger.info("Процессы памяти запущены")
            
        except Exception as e:
            logger.error(f"Ошибка запуска процессов памяти: {e}")
    
    def set_system_integrations(self, ai_system=None, evolution_system=None, social_system=None):
        """Установка интеграций с другими системами"""
        try:
            self.ai_system = ai_system
            self.evolution_system = evolution_system
            self.social_system = social_system
            
            logger.info("Интеграции с другими системами установлены")
            
        except Exception as e:
            logger.error(f"Ошибка установки интеграций: {e}")
    
    def create_memory(self, entity_id: str, memory_type: MemoryType, 
                     category: MemoryCategory, title: str, description: str,
                     data: Dict[str, Any] = None, emotional_value: float = 0.0,
                     importance: float = 0.5) -> Optional[str]:
        """Создание воспоминания"""
        try:
            # Проверка существования памяти сущности
            if entity_id not in self.entity_memories:
                self.entity_memories[entity_id] = EntityMemory(entity_id=entity_id)
            
            entity_memory = self.entity_memories[entity_id]
            
            # Создание воспоминания
            memory_id = f"memory_{entity_id}_{int(time.time())}_{random.randint(1000, 9999)}"
            
            memory = Memory(
                memory_id=memory_id,
                entity_id=entity_id,
                memory_type=memory_type,
                category=category,
                title=title,
                description=description,
                data=data or {},
                emotional_value=emotional_value,
                importance=importance,
                decay_rate=self._calculate_decay_rate(memory_type, importance)
            )
            
            # Добавление в кратковременную память
            entity_memory.short_term_memories.append(memory)
            
            # Проверка лимита кратковременной памяти
            if len(entity_memory.short_term_memories) > self.max_short_term_memories:
                self._cleanup_short_term_memory(entity_id)
            
            # Обновление статистики
            self.total_memories_created += 1
            
            # Вызов callback
            if self.on_memory_created:
                self.on_memory_created(entity_id, memory)
            
            # Проверка паттернов
            self._check_memory_patterns(entity_id, memory)
            
            logger.debug(f"Создано воспоминание {memory_id} для {entity_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"Ошибка создания воспоминания: {e}")
            return None
    
    def _calculate_decay_rate(self, memory_type: MemoryType, importance: float) -> float:
        """Расчет скорости распада памяти"""
        try:
            base_decay_rates = {
                MemoryType.SHORT_TERM: 0.1,
                MemoryType.LONG_TERM: 0.01,
                MemoryType.EPISODIC: 0.05,
                MemoryType.SEMANTIC: 0.02,
                MemoryType.PROCEDURAL: 0.03,
                MemoryType.EMOTIONAL: 0.04,
                MemoryType.GENETIC: 0.001
            }
            
            base_rate = base_decay_rates.get(memory_type, 0.05)
            
            # Модификация по важности
            importance_modifier = 1.0 - (importance * 0.5)
            
            return base_rate * importance_modifier
            
        except Exception as e:
            logger.error(f"Ошибка расчета скорости распада: {e}")
            return 0.05
    
    def _cleanup_short_term_memory(self, entity_id: str):
        """Очистка кратковременной памяти"""
        try:
            entity_memory = self.entity_memories[entity_id]
            
            if len(entity_memory.short_term_memories) <= self.max_short_term_memories:
                return
            
            # Сортировка по важности и времени создания
            entity_memory.short_term_memories.sort(
                key=lambda m: (m.importance, m.created_at)
            )
            
            # Удаление наименее важных воспоминаний
            memories_to_remove = entity_memory.short_term_memories[:-self.max_short_term_memories]
            
            for memory in memories_to_remove:
                entity_memory.short_term_memories.remove(memory)
                self.total_memories_decayed += 1
                
                # Вызов callback
                if self.on_memory_decayed:
                    self.on_memory_decayed(entity_id, memory)
            
            logger.debug(f"Очищено {len(memories_to_remove)} воспоминаний из кратковременной памяти {entity_id}")
            
        except Exception as e:
            logger.error(f"Ошибка очистки кратковременной памяти: {e}")
    
    def _check_memory_patterns(self, entity_id: str, memory: Memory):
        """Проверка паттернов памяти"""
        try:
            entity_memory = self.entity_memories[entity_id]
            
            for pattern in self.memory_patterns.values():
                if self._matches_pattern(memory, pattern):
                    self._trigger_pattern(entity_id, pattern, memory)
            
        except Exception as e:
            logger.error(f"Ошибка проверки паттернов памяти: {e}")
    
    def _matches_pattern(self, memory: Memory, pattern: MemoryPattern) -> bool:
        """Проверка соответствия памяти паттерну"""
        try:
            # Проверка типа памяти
            if memory.memory_type not in pattern.memory_types:
                return False
            
            # Проверка категории
            if hasattr(pattern, 'category') and memory.category != pattern.category:
                return False
            
            # Проверка условий
            for condition, value in pattern.conditions.items():
                if not self._check_condition(memory, condition, value):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки соответствия паттерну: {e}")
            return False
    
    def _check_condition(self, memory: Memory, condition: str, value: Any) -> bool:
        """Проверка условия паттерна"""
        try:
            if condition == "combat_events":
                combat_memories = [m for m in self.entity_memories[memory.entity_id].short_term_memories
                                 if m.category == MemoryCategory.COMBAT]
                return len(combat_memories) >= value
            
            elif condition == "success_rate":
                # Здесь должна быть логика расчета успешности
                return True
            
            elif condition == "interactions":
                social_memories = [m for m in self.entity_memories[memory.entity_id].short_term_memories
                                 if m.category == MemoryCategory.SOCIAL]
                return len(social_memories) >= value
            
            elif condition == "locations_discovered":
                exploration_memories = [m for m in self.entity_memories[memory.entity_id].short_term_memories
                                      if m.category == MemoryCategory.EXPLORATION]
                return len(exploration_memories) >= value
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки условия: {e}")
            return False
    
    def _trigger_pattern(self, entity_id: str, pattern: MemoryPattern, memory: Memory):
        """Срабатывание паттерна"""
        try:
            # Применение эффектов паттерна
            for effect, value in pattern.effects.items():
                self._apply_pattern_effect(entity_id, effect, value)
            
            # Добавление паттерна к сущности
            if pattern not in self.entity_memories[entity_id].memory_patterns:
                self.entity_memories[entity_id].memory_patterns.append(pattern)
            
            # Вызов callback
            if self.on_pattern_triggered:
                self.on_pattern_triggered(entity_id, pattern, memory)
            
            logger.info(f"Сработал паттерн {pattern.pattern_id} для {entity_id}")
            
        except Exception as e:
            logger.error(f"Ошибка срабатывания паттерна: {e}")
    
    def _apply_pattern_effect(self, entity_id: str, effect: str, value: float):
        """Применение эффекта паттерна"""
        try:
            # Интеграция с AI системой
            if self.ai_system and effect in ["combat_bonus", "social_skills", "exploration_bonus"]:
                # Здесь должна быть логика применения бонусов к AI
                pass
            
            # Интеграция с эволюционной системой
            if self.evolution_system and effect in ["evolution_rate", "mutation_success"]:
                # Здесь должна быть логика применения эволюционных бонусов
                pass
            
            # Интеграция с социальной системой
            if self.social_system and effect in ["relationship_bonus"]:
                # Здесь должна быть логика применения социальных бонусов
                pass
            
        except Exception as e:
            logger.error(f"Ошибка применения эффекта паттерна: {e}")
    
    def consolidate_memories(self, entity_id: str) -> int:
        """Консолидация воспоминаний"""
        try:
            if entity_id not in self.entity_memories:
                return 0
            
            entity_memory = self.entity_memories[entity_id]
            consolidated_count = 0
            
            # Фильтрация воспоминаний для консолидации
            memories_to_consolidate = [
                memory for memory in entity_memory.short_term_memories
                if (memory.importance >= entity_memory.consolidation_threshold and
                    not memory.is_consolidated and
                    time.time() - memory.created_at >= self.consolidation_interval)
            ]
            
            for memory in memories_to_consolidate:
                # Перемещение в долговременную память
                entity_memory.short_term_memories.remove(memory)
                entity_memory.long_term_memories.append(memory)
                memory.is_consolidated = True
                consolidated_count += 1
                
                # Вызов callback
                if self.on_memory_consolidated:
                    self.on_memory_consolidated(entity_id, memory)
            
            # Проверка лимита долговременной памяти
            if len(entity_memory.long_term_memories) > entity_memory.memory_capacity:
                self._cleanup_long_term_memory(entity_id)
            
            self.total_memories_consolidated += consolidated_count
            entity_memory.last_consolidation = time.time()
            
            logger.debug(f"Консолидировано {consolidated_count} воспоминаний для {entity_id}")
            return consolidated_count
            
        except Exception as e:
            logger.error(f"Ошибка консолидации воспоминаний: {e}")
            return 0
    
    def _cleanup_long_term_memory(self, entity_id: str):
        """Очистка долговременной памяти"""
        try:
            entity_memory = self.entity_memories[entity_id]
            
            if len(entity_memory.long_term_memories) <= entity_memory.memory_capacity:
                return
            
            # Сортировка по важности и времени последнего доступа
            entity_memory.long_term_memories.sort(
                key=lambda m: (m.importance, m.last_accessed)
            )
            
            # Удаление наименее важных воспоминаний
            memories_to_remove = entity_memory.long_term_memories[:-entity_memory.memory_capacity]
            
            for memory in memories_to_remove:
                entity_memory.long_term_memories.remove(memory)
                self.total_memories_decayed += 1
                
                # Вызов callback
                if self.on_memory_decayed:
                    self.on_memory_decayed(entity_id, memory)
            
            logger.debug(f"Очищено {len(memories_to_remove)} воспоминаний из долговременной памяти {entity_id}")
            
        except Exception as e:
            logger.error(f"Ошибка очистки долговременной памяти: {e}")
    
    def create_shared_memory(self, title: str, description: str, 
                           contributors: List[str], memory_type: MemoryType = MemoryType.SEMANTIC,
                           category: MemoryCategory = MemoryCategory.LEARNING,
                           data: Dict[str, Any] = None) -> Optional[str]:
        """Создание общей памяти"""
        try:
            memory_id = f"shared_memory_{int(time.time())}_{random.randint(1000, 9999)}"
            
            shared_memory = SharedMemory(
                memory_id=memory_id,
                title=title,
                description=description,
                contributors=contributors.copy(),
                memory_type=memory_type,
                category=category,
                data=data or {}
            )
            
            self.shared_memories[memory_id] = shared_memory
            
            logger.info(f"Создана общая память {memory_id}: {title}")
            return memory_id
            
        except Exception as e:
            logger.error(f"Ошибка создания общей памяти: {e}")
            return None
    
    def create_evolution_memory(self, species_id: str, generation: int, 
                              evolution_type: str, changes: Dict[str, Any],
                              success_rate: float = 0.0) -> Optional[str]:
        """Создание эволюционной памяти"""
        try:
            memory_id = f"evolution_memory_{species_id}_{generation}_{int(time.time())}"
            
            evolution_memory = EvolutionMemory(
                memory_id=memory_id,
                species_id=species_id,
                generation=generation,
                evolution_type=evolution_type,
                changes=changes.copy(),
                success_rate=success_rate
            )
            
            self.evolution_memories[memory_id] = evolution_memory
            
            logger.info(f"Создана эволюционная память {memory_id} для вида {species_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"Ошибка создания эволюционной памяти: {e}")
            return None
    
    def get_memories(self, entity_id: str, memory_type: Optional[MemoryType] = None,
                    category: Optional[MemoryCategory] = None, limit: int = 10) -> List[Memory]:
        """Получение воспоминаний сущности"""
        try:
            if entity_id not in self.entity_memories:
                return []
            
            entity_memory = self.entity_memories[entity_id]
            all_memories = entity_memory.short_term_memories + entity_memory.long_term_memories
            
            # Фильтрация
            if memory_type:
                all_memories = [m for m in all_memories if m.memory_type == memory_type]
            
            if category:
                all_memories = [m for m in all_memories if m.category == category]
            
            # Сортировка по важности и времени последнего доступа
            all_memories.sort(key=lambda m: (m.importance, m.last_accessed), reverse=True)
            
            # Обновление времени доступа
            for memory in all_memories[:limit]:
                memory.last_accessed = time.time()
                memory.access_count += 1
            
            return all_memories[:limit]
            
        except Exception as e:
            logger.error(f"Ошибка получения воспоминаний: {e}")
            return []
    
    def _consolidation_process(self):
        """Процесс консолидации памяти"""
        try:
            while self.state == LifecycleState.READY:
                # Консолидация для всех сущностей
                for entity_id in list(self.entity_memories.keys()):
                    self.consolidate_memories(entity_id)
                
                time.sleep(self.consolidation_interval)
                
        except Exception as e:
            logger.error(f"Ошибка процесса консолидации: {e}")
    
    def _decay_process(self):
        """Процесс распада памяти"""
        try:
            while self.state == LifecycleState.READY:
                current_time = time.time()
                
                # Распад кратковременной памяти
                for entity_id, entity_memory in self.entity_memories.items():
                    memories_to_decay = []
                    
                    for memory in entity_memory.short_term_memories:
                        # Расчет распада
                        time_since_creation = current_time - memory.created_at
                        decay_factor = memory.decay_rate * time_since_creation
                        
                        if decay_factor > 1.0:
                            memories_to_decay.append(memory)
                    
                    # Удаление распавшихся воспоминаний
                    for memory in memories_to_decay:
                        entity_memory.short_term_memories.remove(memory)
                        self.total_memories_decayed += 1
                        
                        if self.on_memory_decayed:
                            self.on_memory_decayed(entity_id, memory)
                
                time.sleep(self.decay_interval)
                
        except Exception as e:
            logger.error(f"Ошибка процесса распада: {e}")
    
    def get_memory_statistics(self) -> Dict[str, Any]:
        """Получение статистики памяти"""
        try:
            total_entities = len(self.entity_memories)
            total_short_term = sum(len(em.short_term_memories) for em in self.entity_memories.values())
            total_long_term = sum(len(em.long_term_memories) for em in self.entity_memories.values())
            
            return {
                "total_entities": total_entities,
                "total_short_term_memories": total_short_term,
                "total_long_term_memories": total_long_term,
                "total_shared_memories": len(self.shared_memories),
                "total_evolution_memories": len(self.evolution_memories),
                "total_memories_created": self.total_memories_created,
                "total_memories_consolidated": self.total_memories_consolidated,
                "total_memories_decayed": self.total_memories_decayed,
                "memory_patterns": len(self.memory_patterns)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики памяти: {e}")
            return {}
    
    def cleanup(self):
        """Очистка системы памяти"""
        try:
            # Очистка памяти сущностей
            self.entity_memories.clear()
            
            # Очистка общей памяти
            self.shared_memories.clear()
            
            # Очистка эволюционной памяти
            self.evolution_memories.clear()
            
            # Очистка паттернов
            self.memory_patterns.clear()
            
            logger.info("Система памяти очищена")
            
        except Exception as e:
            logger.error(f"Ошибка очистки системы памяти: {e}")
