#!/usr/bin/env python3
"""Централизованный менеджер состояний
Управляет всеми состояниями игры с версионированием и валидацией"""

from dataclasses import dataclass, field
from enum import Enum
from typing import *
from typing import Dict, List, Optional, Any, Callable, Generic, TypeVar
import logging
import time
import threading
import hashlib
import json
from abc import ABC, abstractmethod

from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState

logger = logging.getLogger(__name__)

# = ТИПЫ СОСТОЯНИЙ

class StateType(Enum):
    """Типы состояний"""
    GAME_STATE = "game_state"           # Игровые состояния
    UI_STATE = "ui_state"               # Состояния интерфейса
    SYSTEM_STATE = "system_state"       # Системные состояния
    ENTITY_STATE = "entity_state"       # Состояния сущностей
    WORLD_STATE = "world_state"         # Состояния мира
    SETTINGS = "settings"               # Настройки
    STATISTICS = "statistics"           # Статистика

class StateScope(Enum):
    """Области видимости состояний"""
    PUBLIC = "public"                   # Публичное состояние
    PROTECTED = "protected"             # Защищенное состояние
    PRIVATE = "private"                 # Приватное состояние

class StateValidation(Enum):
    """Типы валидации состояний"""
    NONE = "none"                       # Без валидации
    TYPE_CHECK = "type_check"           # Проверка типа
    RANGE_CHECK = "range_check"         # Проверка диапазона
    CUSTOM = "custom"                   # Пользовательская валидация

# = СТРУКТУРЫ ДАННЫХ

@dataclass
class StateChange:
    """Изменение состояния с улучшенной структурой"""
    state_id: str
    old_value: Any
    new_value: Any
    timestamp: float
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    change_type: str = "update"  # update, reset, restore, clear

@dataclass
class StateSnapshot:
    """Снимок состояния с версионированием"""
    state_id: str
    value: Any
    timestamp: float
    version: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    checksum: Optional[str] = None

@dataclass
class StateValidationRule:
    """Правило валидации состояния"""
    validation_type: StateValidation
    rule_data: Dict[str, Any]
    error_message: str = "Валидация не пройдена"
    custom_validator: Optional[Callable[[Any], bool]] = None

class IStateContainer(Generic[TypeVar('T')]):
    """Интерфейс для контейнера состояний"""
    
    @abstractmethod
    def get_state(self, state_id: str) -> Optional[TypeVar('T')]:
        """Получение состояния"""
        pass
    
    @abstractmethod
    def set_state(self, state_id: str, value: TypeVar('T')) -> bool:
        """Установка состояния"""
        pass
    
    @abstractmethod
    def has_state(self, state_id: str) -> bool:
        """Проверка наличия состояния"""
        pass
    
    @abstractmethod
    def remove_state(self, state_id: str) -> bool:
        """Удаление состояния"""
        pass
    
    @abstractmethod
    def get_all_states(self) -> Dict[str, TypeVar('T')]:
        """Получение всех состояний"""
        pass

# = РЕАЛИЗАЦИЯ МЕНЕДЖЕРА СОСТОЯНИЙ

class StateManager(BaseComponent):
    """Централизованный менеджер состояний"""
    
    def __init__(self):
        super().__init__(
            component_id="state_manager",
            component_type=ComponentType.MANAGER,
            priority=Priority.CRITICAL
        )
        
        # Хранилище состояний
        self._states: Dict[str, Any] = {}
        self._state_metadata: Dict[str, Dict[str, Any]] = {}
        self._state_history: Dict[str, List[StateChange]] = {}
        self._state_snapshots: Dict[str, List[StateSnapshot]] = {}
        self._validation_rules: Dict[str, StateValidationRule] = {}
        
        # Группы состояний
        self._state_groups: Dict[str, List[str]] = {}
        self._group_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Подписчики на изменения
        self._subscribers: Dict[str, List[Callable]] = {}
        self._global_subscribers: List[Callable] = []
        
        # Производительность и мониторинг
        self._change_count = 0
        self._validation_failures = 0
        self._last_cleanup = time.time()
        self._cleanup_interval = 300.0  # 5 минут
        
        # Потокобезопасность
        self._lock = threading.RLock()
        
        logger.info("StateManager инициализирован")
    
    def _on_initialize(self) -> bool:
        """Инициализация менеджера состояний"""
        try:
            # Создание базовых групп состояний
            self._create_default_groups()
            
            # Инициализация базовых состояний
            self._initialize_default_states()
            
            logger.info("StateManager успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации StateManager: {e}")
            return False
    
    def _create_default_groups(self):
        """Создание базовых групп состояний"""
        default_groups = {
            "game": {
                "description": "Игровые состояния",
                "scope": StateScope.PUBLIC,
                "auto_cleanup": False
            },
            "ui": {
                "description": "Состояния интерфейса",
                "scope": StateScope.PROTECTED,
                "auto_cleanup": True
            },
            "system": {
                "description": "Системные состояния",
                "scope": StateScope.PRIVATE,
                "auto_cleanup": False
            },
            "temporary": {
                "description": "Временные состояния",
                "scope": StateScope.PRIVATE,
                "auto_cleanup": True
            }
        }
        
        for group_name, metadata in default_groups.items():
            self.create_state_group(group_name, metadata)
    
    def _initialize_default_states(self):
        """Инициализация базовых состояний"""
        default_states = {
            "game.running": False,
            "game.paused": False,
            "game.current_level": 1,
            "system.initialized": False,
            "system.version": "1.0.0",
            "ui.main_menu_active": True,
            "ui.current_screen": "main_menu"
        }
        
        for state_id, value in default_states.items():
            self.set_state(state_id, value, source="system")
    
    def set_state(self, state_id: str, value: Any, source: str = "unknown", 
                  metadata: Dict[str, Any] = None) -> bool:
        """Установка состояния с валидацией и историей"""
        try:
            with self._lock:
                # Валидация
                if not self._validate_state(state_id, value):
                    return False
                
                # Получение старого значения
                old_value = self._states.get(state_id)
                
                # Проверка на реальное изменение
                if old_value == value:
                    return True  # Нет изменений
                
                # Установка нового значения
                self._states[state_id] = value
                
                # Обновление метаданных
                if metadata:
                    self._state_metadata[state_id] = metadata
                elif state_id not in self._state_metadata:
                    self._state_metadata[state_id] = {}
                
                # Запись в историю
                self._record_state_change(state_id, old_value, value, source)
                
                # Уведомление подписчиков
                self._notify_subscribers(state_id, old_value, value, source)
                
                self._change_count += 1
                logger.debug(f"Состояние {state_id} изменено: {old_value} -> {value}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка установки состояния {state_id}: {e}")
            return False
    
    def get_state(self, state_id: str, default: Any = None) -> Any:
        """Получение состояния"""
        try:
            with self._lock:
                return self._states.get(state_id, default)
        except Exception as e:
            logger.error(f"Ошибка получения состояния {state_id}: {e}")
            return default
    
    def has_state(self, state_id: str) -> bool:
        """Проверка наличия состояния"""
        try:
            with self._lock:
                return state_id in self._states
        except Exception as e:
            logger.error(f"Ошибка проверки состояния {state_id}: {e}")
            return False
    
    def remove_state(self, state_id: str) -> bool:
        """Удаление состояния"""
        try:
            with self._lock:
                if state_id in self._states:
                    old_value = self._states[state_id]
                    del self._states[state_id]
                    
                    # Очистка связанных данных
                    if state_id in self._state_metadata:
                        del self._state_metadata[state_id]
                    if state_id in self._state_history:
                        del self._state_history[state_id]
                    if state_id in self._validation_rules:
                        del self._validation_rules[state_id]
                    
                    # Уведомление подписчиков
                    self._notify_subscribers(state_id, old_value, None, "system")
                    
                    logger.debug(f"Состояние {state_id} удалено")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Ошибка удаления состояния {state_id}: {e}")
            return False
    
    def get_all_states(self) -> Dict[str, Any]:
        """Получение всех состояний"""
        try:
            with self._lock:
                return self._states.copy()
        except Exception as e:
            logger.error(f"Ошибка получения всех состояний: {e}")
            return {}
    
    def create_state_group(self, group_name: str, metadata: Dict[str, Any] = None) -> bool:
        """Создание группы состояний"""
        try:
            with self._lock:
                if group_name in self._state_groups:
                    logger.warning(f"Группа состояний {group_name} уже существует")
                    return False
                
                self._state_groups[group_name] = []
                self._group_metadata[group_name] = metadata or {}
                
                logger.debug(f"Создана группа состояний {group_name}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка создания группы состояний {group_name}: {e}")
            return False
    
    def add_state_to_group(self, group_name: str, state_id: str) -> bool:
        """Добавление состояния в группу"""
        try:
            with self._lock:
                if group_name not in self._state_groups:
                    logger.error(f"Группа состояний {group_name} не существует")
                    return False
                
                if state_id not in self._state_groups[group_name]:
                    self._state_groups[group_name].append(state_id)
                    logger.debug(f"Состояние {state_id} добавлено в группу {group_name}")
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка добавления состояния {state_id} в группу {group_name}: {e}")
            return False
    
    def get_group_states(self, group_name: str) -> Dict[str, Any]:
        """Получение всех состояний группы"""
        try:
            with self._lock:
                if group_name not in self._state_groups:
                    return {}
                
                group_states = {}
                for state_id in self._state_groups[group_name]:
                    if state_id in self._states:
                        group_states[state_id] = self._states[state_id]
                
                return group_states
                
        except Exception as e:
            logger.error(f"Ошибка получения состояний группы {group_name}: {e}")
            return {}
    
    def subscribe_to_state(self, state_id: str, callback: Callable) -> bool:
        """Подписка на изменения состояния"""
        try:
            with self._lock:
                if state_id not in self._subscribers:
                    self._subscribers[state_id] = []
                
                if callback not in self._subscribers[state_id]:
                    self._subscribers[state_id].append(callback)
                    logger.debug(f"Подписка на состояние {state_id}")
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка подписки на состояние {state_id}: {e}")
            return False
    
    def unsubscribe_from_state(self, state_id: str, callback: Callable) -> bool:
        """Отписка от изменений состояния"""
        try:
            with self._lock:
                if state_id in self._subscribers and callback in self._subscribers[state_id]:
                    self._subscribers[state_id].remove(callback)
                    logger.debug(f"Отписка от состояния {state_id}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Ошибка отписки от состояния {state_id}: {e}")
            return False
    
    def subscribe_to_all_states(self, callback: Callable) -> bool:
        """Подписка на все изменения состояний"""
        try:
            with self._lock:
                if callback not in self._global_subscribers:
                    self._global_subscribers.append(callback)
                    logger.debug("Подписка на все изменения состояний")
                    return True
                
        except Exception as e:
            logger.error(f"Ошибка подписки на все состояния: {e}")
            return False
    
    def _validate_state(self, state_id: str, value: Any) -> bool:
        """Валидация состояния"""
        try:
            if state_id not in self._validation_rules:
                return True  # Нет правил валидации
            
            rule = self._validation_rules[state_id]
            
            if rule.validation_type == StateValidation.NONE:
                return True
            
            elif rule.validation_type == StateValidation.TYPE_CHECK:
                expected_type = rule.rule_data.get("type")
                if expected_type and not isinstance(value, expected_type):
                    logger.warning(f"Неверный тип для {state_id}: ожидается {expected_type}, получен {type(value)}")
                    return False
            
            elif rule.validation_type == StateValidation.RANGE_CHECK:
                min_val = rule.rule_data.get("min")
                max_val = rule.rule_data.get("max")
                
                if min_val is not None and value < min_val:
                    logger.warning(f"Значение {state_id} меньше минимального: {value} < {min_val}")
                    return False
                
                if max_val is not None and value > max_val:
                    logger.warning(f"Значение {state_id} больше максимального: {value} > {max_val}")
                    return False
            
            elif rule.validation_type == StateValidation.CUSTOM:
                if rule.custom_validator and not rule.custom_validator(value):
                    logger.warning(f"Пользовательская валидация не пройдена для {state_id}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка валидации состояния {state_id}: {e}")
            return False
    
    def _record_state_change(self, state_id: str, old_value: Any, new_value: Any, source: str):
        """Запись изменения состояния в историю"""
        try:
            if state_id not in self._state_history:
                self._state_history[state_id] = []
            
            change = StateChange(
                state_id=state_id,
                old_value=old_value,
                new_value=new_value,
                timestamp=time.time(),
                source=source
            )
            
            self._state_history[state_id].append(change)
            
            # Ограничиваем размер истории
            if len(self._state_history[state_id]) > 100:
                self._state_history[state_id] = self._state_history[state_id][-50:]
                
        except Exception as e:
            logger.error(f"Ошибка записи изменения состояния {state_id}: {e}")
    
    def _notify_subscribers(self, state_id: str, old_value: Any, new_value: Any, source: str):
        """Уведомление подписчиков об изменении состояния"""
        try:
            # Уведомляем подписчиков конкретного состояния
            if state_id in self._subscribers:
                for callback in self._subscribers[state_id]:
                    try:
                        callback(state_id, old_value, new_value, source)
                    except Exception as e:
                        logger.error(f"Ошибка в callback для {state_id}: {e}")
            
            # Уведомляем глобальных подписчиков
            for callback in self._global_subscribers:
                try:
                    callback(state_id, old_value, new_value, source)
                except Exception as e:
                    logger.error(f"Ошибка в глобальном callback: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка уведомления подписчиков для {state_id}: {e}")
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.component_id,
            'state': self.state.value,
            'priority': self.priority.value,
            'total_states': len(self._states),
            'total_groups': len(self._state_groups),
            'total_subscribers': len(self._subscribers),
            'change_count': self._change_count,
            'validation_failures': self._validation_failures
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self._change_count = 0
        self._validation_failures = 0
        self._last_cleanup = time.time()
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.component_id,
            'state': self.state.value,
            'priority': self.priority.value,
            'total_states': len(self._states),
            'total_groups': len(self._state_groups),
            'total_subscribers': len(self._subscribers),
            'change_count': self._change_count,
            'validation_failures': self._validation_failures
        }
