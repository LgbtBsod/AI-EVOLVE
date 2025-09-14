#!/usr/bin/env python3
"""Типы компонентов архитектуры - выделено из architecture.py"""

from enum import Enum
from typing import Dict, List, Optional, Any, Type, TypeVar, Generic, Callable
import logging
import time

# = БАЗОВЫЕ ТИПЫ КОМПОНЕНТОВ

class ComponentType(Enum):
    """Типы компонентов архитектуры"""
    SYSTEM = "system"
    MANAGER = "manager"
    SERVICE = "service"
    REPOSITORY = "repository"
    FACTORY = "factory"
    CONTROLLER = "controller"
    UTILITY = "utility"
    ADAPTER = "adapter"

class LifecycleState(Enum):
    """Состояния жизненного цикла компонента"""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    DESTROYED = "destroyed"

class Priority(Enum):
    """Приоритеты компонентов"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4

class ComponentState(Enum):
    """Состояния компонентов"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    MAINTENANCE = "maintenance"

# = БАЗОВЫЕ ИНТЕРФЕЙСЫ

class IComponent:
    """Базовый интерфейс компонента"""
    
    @property
    def component_id(self) -> str:
        """ID компонента"""
        pass
    
    @property
    def component_type(self) -> ComponentType:
        """Тип компонента"""
        pass
    
    @property
    def priority(self) -> Priority:
        """Приоритет компонента"""
        pass
    
    @property
    def state(self) -> LifecycleState:
        """Состояние компонента"""
        pass
    
    def initialize(self) -> bool:
        """Инициализация компонента"""
        pass
    
    def start(self) -> bool:
        """Запуск компонента"""
        pass
    
    def stop(self) -> bool:
        """Остановка компонента"""
        pass
    
    def destroy(self) -> bool:
        """Уничтожение компонента"""
        pass
    
    def update(self, delta_time: float) -> bool:
        """Обновление компонента"""
        pass

# = БАЗОВЫЕ КЛАССЫ

class BaseComponent(IComponent):
    """Базовый класс для всех компонентов"""
    
    def __init__(self, component_id: str, component_type: ComponentType, priority: Priority = Priority.NORMAL):
        self._component_id = component_id
        self._component_type = component_type
        self._priority = priority
        self._state = LifecycleState.UNINITIALIZED
        self._logger = logging.getLogger(f"{__name__}.{component_id}")
        
        # Статистика
        self._creation_time = time.time()
        self._last_update_time = 0.0
        self._update_count = 0
        self._error_count = 0
        
        # Callbacks
        self._state_change_callbacks: List[Callable] = []
        self._error_callbacks: List[Callable] = []
    
    @property
    def component_id(self) -> str:
        return self._component_id
    
    @property
    def component_type(self) -> ComponentType:
        return self._component_type
    
    @property
    def priority(self) -> Priority:
        return self._priority
    
    @property
    def state(self) -> LifecycleState:
        return self._state
    
    def initialize(self) -> bool:
        """Инициализация компонента"""
        try:
            self._state = LifecycleState.INITIALIZING
            self._logger.info(f"Инициализация компонента {self._component_id}")
            
            result = self._on_initialize()
            
            if result:
                self._state = LifecycleState.READY
                self._logger.info(f"Компонент {self._component_id} инициализирован")
            else:
                self._state = LifecycleState.ERROR
                self._logger.error(f"Ошибка инициализации компонента {self._component_id}")
            
            return result
            
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._error_count += 1
            self._logger.error(f"Критическая ошибка инициализации {self._component_id}: {e}")
            return False
    
    def start(self) -> bool:
        """Запуск компонента"""
        try:
            if self._state != LifecycleState.READY:
                self._logger.warning(f"Попытка запуска компонента {self._component_id} в состоянии {self._state}")
                return False
            
            self._state = LifecycleState.RUNNING
            self._logger.info(f"Запуск компонента {self._component_id}")
            
            result = self._on_start()
            
            if not result:
                self._state = LifecycleState.ERROR
                self._logger.error(f"Ошибка запуска компонента {self._component_id}")
            
            return result
            
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._error_count += 1
            self._logger.error(f"Критическая ошибка запуска {self._component_id}: {e}")
            return False
    
    def stop(self) -> bool:
        """Остановка компонента"""
        try:
            if self._state not in [LifecycleState.RUNNING, LifecycleState.PAUSED]:
                self._logger.warning(f"Попытка остановки компонента {self._component_id} в состоянии {self._state}")
                return False
            
            self._state = LifecycleState.STOPPING
            self._logger.info(f"Остановка компонента {self._component_id}")
            
            result = self._on_stop()
            
            if result:
                self._state = LifecycleState.STOPPED
                self._logger.info(f"Компонент {self._component_id} остановлен")
            else:
                self._state = LifecycleState.ERROR
                self._logger.error(f"Ошибка остановки компонента {self._component_id}")
            
            return result
            
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._error_count += 1
            self._logger.error(f"Критическая ошибка остановки {self._component_id}: {e}")
            return False
    
    def destroy(self) -> bool:
        """Уничтожение компонента"""
        try:
            if self._state == LifecycleState.DESTROYED:
                return True
            
            self._logger.info(f"Уничтожение компонента {self._component_id}")
            
            # Остановка если запущен
            if self._state in [LifecycleState.RUNNING, LifecycleState.PAUSED]:
                self.stop()
            
            result = self._on_destroy()
            
            self._state = LifecycleState.DESTROYED
            self._logger.info(f"Компонент {self._component_id} уничтожен")
            
            return result
            
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._error_count += 1
            self._logger.error(f"Критическая ошибка уничтожения {self._component_id}: {e}")
            return False
    
    def update(self, delta_time: float) -> bool:
        """Обновление компонента"""
        try:
            if self._state != LifecycleState.RUNNING:
                return True
            
            self._last_update_time = time.time()
            self._update_count += 1
            
            return self._on_update(delta_time)
            
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._error_count += 1
            self._logger.error(f"Критическая ошибка обновления {self._component_id}: {e}")
            return False
    
    # Виртуальные методы для переопределения
    def _on_initialize(self) -> bool:
        """Переопределяется в наследниках"""
        return True
    
    def _on_start(self) -> bool:
        """Переопределяется в наследниках"""
        return True
    
    def _on_stop(self) -> bool:
        """Переопределяется в наследниках"""
        return True
    
    def _on_destroy(self) -> bool:
        """Переопределяется в наследниках"""
        return True
    
    def _on_update(self, delta_time: float) -> bool:
        """Переопределяется в наследниках"""
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики компонента"""
        return {
            'component_id': self._component_id,
            'component_type': self._component_type.value,
            'priority': self._priority.value,
            'state': self._state.value,
            'creation_time': self._creation_time,
            'last_update_time': self._last_update_time,
            'update_count': self._update_count,
            'error_count': self._error_count,
            'uptime': time.time() - self._creation_time
        }
