#!/usr/bin/env python3
"""Улучшенные интерфейсы для систем - интеграция с новой архитектурой"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Type, TypeVar, Generic, Protocol
import logging
import os
import sys
import time

from .architecture import BaseComponent, ComponentType, Priority
from .repository import RepositoryManager, DataType, StorageType
from .state_manager import StateManager, StateType

logger = logging.getLogger(__name__)

# ============================================================================
# БАЗОВЫЕ ИНТЕРФЕЙСЫ СИСТЕМ
# ============================================================================

class IGameSystem(ABC):
    """Базовый интерфейс для игровых систем"""
    
    @property
    @abstractmethod
    def component_id(self) -> str:
        """ID компонента"""
        pass
    
    @property
    @abstractmethod
    def component_type(self) -> ComponentType:
        """Тип компонента"""
        pass
    
    @property
    @abstractmethod
    def priority(self) -> Priority:
        """Приоритет компонента"""
        pass
    
    @property
    @abstractmethod
    def state(self) -> str:
        """Состояние компонента"""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """Инициализация системы"""
        pass
    
    @abstractmethod
    def start(self) -> bool:
        """Запуск системы"""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Остановка системы"""
        pass
    
    @abstractmethod
    def destroy(self) -> bool:
        """Уничтожение системы"""
        pass
    
    @abstractmethod
    def update(self, delta_time: float) -> bool:
        """Обновление системы"""
        pass

# ============================================================================
# БАЗОВЫЕ КЛАССЫ СИСТЕМ
# ============================================================================

class BaseGameSystem(BaseComponent, IGameSystem):
    """Базовая игровая система с полной интеграцией"""
    
    def __init__(self, component_id: str, component_type: ComponentType, priority: Priority):
        super().__init__(component_id, component_type, priority)
        
        # Архитектурные компоненты
        self.state_manager: Optional[StateManager] = None
        self.repository_manager: Optional[RepositoryManager] = None
        self.event_bus: Optional[Any] = None
        
        # Состояния системы
        self.system_states: Dict[str, str] = {}
        self.system_repositories: Dict[str, str] = {}
        
        # Статистика системы
        self.system_stats: Dict[str, Any] = {
            'initialization_time': 0.0,
            'start_time': 0.0,
            'stop_time': 0.0,
            'update_count': 0,
            'total_update_time': 0.0,
            'last_update_time': 0.0,
            'error_count': 0,
            'warning_count': 0
        }
        
        # Настройки системы
        self.system_settings: Dict[str, Any] = {}
        
        # Callbacks
        self.on_initialized: Optional[callable] = None
        self.on_started: Optional[callable] = None
        self.on_stopped: Optional[callable] = None
        self.on_destroyed: Optional[callable] = None
        self.on_error: Optional[callable] = None
        
        logger.info(f"Базовая игровая система {component_id} создана")
    
    def set_architecture_components(self, state_manager: StateManager, 
                                  repository_manager: Optional[RepositoryManager] = None,
                                  event_bus: Optional[Any] = None):
        """Установка архитектурных компонентов"""
        self.state_manager = state_manager
        self.repository_manager = repository_manager
        self.event_bus = event_bus
        logger.info(f"Архитектурные компоненты установлены в {self.component_id}")
    
    def register_system_state(self, state_id: str, initial_value: Any, state_type: StateType) -> bool:
        """Регистрация состояния системы"""
        if not self.state_manager:
            return False
        
        try:
            full_state_id = f"{self.component_id}_{state_id}"
            container = self.state_manager.register_state(full_state_id, initial_value, state_type)
            if container:
                self.system_states[state_id] = full_state_id
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка регистрации состояния {state_id}: {e}")
            return False
    
    def get_system_state(self, state_id: str, default: Any = None) -> Any:
        """Получение состояния системы"""
        if not self.state_manager or state_id not in self.system_states:
            return default
        
        try:
            return self.state_manager.get_state_value(self.system_states[state_id], default)
        except Exception as e:
            logger.error(f"Ошибка получения состояния {state_id}: {e}")
            return default
    
    def set_system_state(self, state_id: str, value: Any) -> bool:
        """Установка состояния системы"""
        if not self.state_manager or state_id not in self.system_states:
            return False
        
        try:
            return self.state_manager.set_state_value(self.system_states[state_id], value)
        except Exception as e:
            logger.error(f"Ошибка установки состояния {state_id}: {e}")
            return False
    
    def register_system_repository(self, repository_id: str, data_type: DataType,
                                 storage_type: StorageType = StorageType.MEMORY) -> bool:
        """Регистрация репозитория системы"""
        if not self.repository_manager:
            return False
        
        try:
            full_repository_id = f"{self.component_id}_{repository_id}"
            repository = self.repository_manager.create_repository(full_repository_id, data_type, storage_type)
            if repository:
                self.system_repositories[repository_id] = full_repository_id
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка создания репозитория {repository_id}: {e}")
            return False
    
    def get_system_repository(self, repository_id: str):
        """Получение репозитория системы"""
        if not self.repository_manager or repository_id not in self.system_repositories:
            return None
        
        try:
            return self.repository_manager.get_repository(self.system_repositories[repository_id])
        except Exception as e:
            logger.error(f"Ошибка получения репозитория {repository_id}: {e}")
            return None
    
    def publish_system_event(self, event_type: str, data: Dict[str, Any] = None) -> bool:
        """Публикация события системы"""
        if not self.event_bus:
            return False
        
        try:
            # Простая реализация события
            event = {
                'type': event_type,
                'source': self.component_id,
                'data': data or {},
                'timestamp': time.time()
            }
            return self.event_bus.publish(event)
        except Exception as e:
            logger.error(f"Ошибка публикации события {event_type}: {e}")
            return False
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Получение статистики системы"""
        stats = self.system_stats.copy()
        stats['component_id'] = self.component_id
        stats['component_type'] = self.component_type.value
        stats['priority'] = self.priority.value
        stats['state'] = self.state
        return stats
    
    def update_system_stats(self, delta_time: float):
        """Обновление статистики системы"""
        self.system_stats['update_count'] += 1
        self.system_stats['total_update_time'] += delta_time
        self.system_stats['last_update_time'] = time.time()
    
    def reset_system_stats(self):
        """Сброс статистики системы"""
        self.system_stats.update({
            'initialization_time': 0.0,
            'start_time': 0.0,
            'stop_time': 0.0,
            'update_count': 0,
            'total_update_time': 0.0,
            'last_update_time': 0.0,
            'error_count': 0,
            'warning_count': 0
        })

# ============================================================================
# СПЕЦИАЛИЗИРОВАННЫЕ ИНТЕРФЕЙСЫ
# ============================================================================

class IRenderableSystem(IGameSystem):
    """Интерфейс для рендерируемых систем"""
    
    @abstractmethod
    def render(self, delta_time: float) -> bool:
        """Рендеринг системы"""
        pass
    
    @abstractmethod
    def get_render_stats(self) -> Dict[str, Any]:
        """Получение статистики рендеринга"""
        pass

class IUpdatableSystem(IGameSystem):
    """Интерфейс для обновляемых систем"""
    
    @abstractmethod
    def update(self, delta_time: float) -> bool:
        """Обновление системы"""
        pass
