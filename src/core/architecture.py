#!/usr/bin/env python3
"""
Архитектурное ядро системы - базовые классы и компоненты.
Предоставляет фундамент для всех систем игры.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Type, TypeVar
import logging
import time

logger = logging.getLogger(__name__)

# ============================================================================
# ТИПЫ И КОНСТАНТЫ
# ============================================================================

class ComponentType(Enum):
    """Типы компонентов системы"""
    SYSTEM = "system"
    MANAGER = "manager"
    SERVICE = "service"
    REPOSITORY = "repository"
    FACTORY = "factory"
    CONTROLLER = "controller"
    UTILITY = "utility"
    ADAPTER = "adapter"
    ENTITY = "entity"
    COMPONENT = "component"


class Priority(Enum):
    """Приоритеты выполнения компонентов"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


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


# ============================================================================
# БАЗОВЫЕ ИНТЕРФЕЙСЫ
# ============================================================================

class IComponent(ABC):
    """Базовый интерфейс для всех компонентов"""
    
    @property
    @abstractmethod
    def component_id(self) -> str:
        """Уникальный идентификатор компонента"""
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
    def state(self) -> LifecycleState:
        """Текущее состояние компонента"""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """Инициализация компонента"""
        pass
    
    @abstractmethod
    def start(self) -> bool:
        """Запуск компонента"""
        pass
    
    @abstractmethod
    def pause(self) -> bool:
        """Приостановка компонента"""
        pass
    
    @abstractmethod
    def resume(self) -> bool:
        """Возобновление компонента"""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Остановка компонента"""
        pass
    
    @abstractmethod
    def destroy(self) -> bool:
        """Уничтожение компонента"""
        pass
    
    @abstractmethod
    def update(self, delta_time: float) -> None:
        """Обновление компонента"""
        pass
    
    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Получение диагностической информации"""
        pass
    
    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик производительности"""
        pass
    
    @abstractmethod
    def reset_metrics(self) -> None:
        """Сброс метрик"""
        pass


# ============================================================================
# БАЗОВЫЕ КЛАССЫ
# ============================================================================

@dataclass
class ComponentMetrics:
    """Метрики производительности компонента"""
    update_count: int = 0
    total_update_time: float = 0.0
    last_update_time: float = 0.0
    max_update_time: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_time: float = 0.0
    
    @property
    def avg_update_time(self) -> float:
        if self.update_count == 0:
            return 0.0
        return self.total_update_time / self.update_count
    
    @property
    def updates_per_second(self) -> float:
        if self.total_update_time == 0:
            return 0.0
        return self.update_count / max(self.total_update_time, 0.001)


class BaseComponent(IComponent):
    """
    Базовый класс для всех компонентов системы.
    Реализует полный жизненный цикл и предоставляет общую функциональность.
    """
    
    def __init__(
        self,
        component_id: str,
        component_type: ComponentType,
        priority: Priority = Priority.NORMAL
    ):
        self._component_id = component_id
        self._component_type = component_type
        self._priority = priority
        self._state = LifecycleState.UNINITIALIZED
        self.metrics = ComponentMetrics()
        self._created_at = time.time()
        self._dependencies: List[str] = []
        self._tags: List[str] = []
    
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
    
    @property
    def created_at(self) -> float:
        return self._created_at
    
    @property
    def dependencies(self) -> List[str]:
        return self._dependencies.copy()
    
    @property
    def tags(self) -> List[str]:
        return self._tags.copy()
    
    def add_dependency(self, dependency_id: str) -> 'BaseComponent':
        """Добавить зависимость"""
        if dependency_id not in self._dependencies:
            self._dependencies.append(dependency_id)
        return self
    
    def add_tag(self, tag: str) -> 'BaseComponent':
        """Добавить тег"""
        if tag not in self._tags:
            self._tags.append(tag)
        return self
    
    def has_state(self, *states: LifecycleState) -> bool:
        """Проверка наличия состояния"""
        return self._state in states
    
    def _transition_to(self, new_state: LifecycleState) -> bool:
        """Безопасный переход между состояниями"""
        valid_transitions = {
            LifecycleState.UNINITIALIZED: [LifecycleState.INITIALIZING, LifecycleState.ERROR],
            LifecycleState.INITIALIZING: [LifecycleState.READY, LifecycleState.ERROR],
            LifecycleState.READY: [LifecycleState.RUNNING, LifecycleState.STOPPING, LifecycleState.ERROR],
            LifecycleState.RUNNING: [LifecycleState.PAUSED, LifecycleState.STOPPING, LifecycleState.ERROR],
            LifecycleState.PAUSED: [LifecycleState.RUNNING, LifecycleState.STOPPING, LifecycleState.ERROR],
            LifecycleState.STOPPING: [LifecycleState.STOPPED, LifecycleState.ERROR],
            LifecycleState.STOPPED: [LifecycleState.INITIALIZING, LifecycleState.DESTROYED, LifecycleState.ERROR],
            LifecycleState.ERROR: [LifecycleState.INITIALIZING, LifecycleState.DESTROYED],
            LifecycleState.DESTROYED: []
        }
        
        if new_state not in valid_transitions.get(self._state, []):
            logger.warning(
                f"Недопустимый переход состояния для {self.component_id}: "
                f"{self._state.value} -> {new_state.value}"
            )
            return False
        
        old_state = self._state
        self._state = new_state
        logger.debug(f"Компонент {self.component_id}: {old_state.value} -> {new_state.value}")
        return True
    
    def initialize(self) -> bool:
        """Базовая инициализация компонента"""
        try:
            if not self._transition_to(LifecycleState.INITIALIZING):
                return False
            
            logger.info(f"Инициализация компонента {self.component_id}...")
            result = self._on_initialize()
            
            if result:
                self._transition_to(LifecycleState.READY)
                logger.info(f"Компонент {self.component_id} успешно инициализирован")
            else:
                self._transition_to(LifecycleState.ERROR)
                logger.error(f"Ошибка инициализации компонента {self.component_id}")
            
            return result
            
        except Exception as e:
            self._transition_to(LifecycleState.ERROR)
            self.metrics.error_count += 1
            self.metrics.last_error = str(e)
            self.metrics.last_error_time = time.time()
            logger.exception(f"Исключение при инициализации {self.component_id}: {e}")
            return False
    
    def _on_initialize(self) -> bool:
        """Переопределяемый метод инициализации"""
        return True
    
    def start(self) -> bool:
        """Запуск компонента"""
        try:
            if self._state != LifecycleState.READY:
                logger.warning(f"Компонент {self.component_id} не готов к запуску (состояние: {self._state})")
                return False
            
            if not self._transition_to(LifecycleState.RUNNING):
                return False
            
            logger.info(f"Запуск компонента {self.component_id}...")
            self._on_start()
            logger.info(f"Компонент {self.component_id} запущен")
            return True
            
        except Exception as e:
            self._transition_to(LifecycleState.ERROR)
            self.metrics.error_count += 1
            self.metrics.last_error = str(e)
            self.metrics.last_error_time = time.time()
            logger.exception(f"Исключение при запуске {self.component_id}: {e}")
            return False
    
    def _on_start(self) -> None:
        """Переопределяемый метод запуска"""
        pass
    
    def pause(self) -> bool:
        """Приостановка компонента"""
        try:
            if self._state != LifecycleState.RUNNING:
                return False
            
            if not self._transition_to(LifecycleState.PAUSED):
                return False
            
            logger.info(f"Приостановка компонента {self.component_id}...")
            self._on_pause()
            return True
            
        except Exception as e:
            self.metrics.error_count += 1
            logger.exception(f"Исключение при приостановке {self.component_id}: {e}")
            return False
    
    def _on_pause(self) -> None:
        """Переопределяемый метод приостановки"""
        pass
    
    def resume(self) -> bool:
        """Возобновление компонента"""
        try:
            if self._state != LifecycleState.PAUSED:
                return False
            
            if not self._transition_to(LifecycleState.RUNNING):
                return False
            
            logger.info(f"Возобновление компонента {self.component_id}...")
            self._on_resume()
            return True
            
        except Exception as e:
            self.metrics.error_count += 1
            logger.exception(f"Исключение при возобновлении {self.component_id}: {e}")
            return False
    
    def _on_resume(self) -> None:
        """Переопределяемый метод возобновления"""
        pass
    
    def stop(self) -> bool:
        """Остановка компонента"""
        try:
            if self._state not in [LifecycleState.RUNNING, LifecycleState.PAUSED]:
                return False
            
            if not self._transition_to(LifecycleState.STOPPING):
                return False
            
            logger.info(f"Остановка компонента {self.component_id}...")
            self._on_stop()
            self._transition_to(LifecycleState.STOPPED)
            return True
            
        except Exception as e:
            self._transition_to(LifecycleState.ERROR)
            self.metrics.error_count += 1
            logger.exception(f"Исключение при остановке {self.component_id}: {e}")
            return False
    
    def _on_stop(self) -> None:
        """Переопределяемый метод остановки"""
        pass
    
    def destroy(self) -> bool:
        """Уничтожение компонента"""
        try:
            if self._state == LifecycleState.DESTROYED:
                return True
            
            if self._state in [LifecycleState.RUNNING, LifecycleState.PAUSED]:
                self.stop()
            
            if not self._transition_to(LifecycleState.DESTROYED):
                return False
            
            logger.info(f"Уничтожение компонента {self.component_id}...")
            self._on_destroy()
            return True
            
        except Exception as e:
            self.metrics.error_count += 1
            logger.exception(f"Исключение при уничтожении {self.component_id}: {e}")
            return False
    
    def _on_destroy(self) -> None:
        """Переопределяемый метод уничтожения"""
        pass
    
    def update(self, delta_time: float) -> None:
        """Обновление компонента с метриками"""
        if self._state != LifecycleState.RUNNING:
            return
        
        start_time = time.time()
        try:
            self._on_update(delta_time)
            self.metrics.update_count += 1
            
        except Exception as e:
            self.metrics.error_count += 1
            self.metrics.last_error = str(e)
            self.metrics.last_error_time = time.time()
            logger.exception(f"Исключение при обновлении {self.component_id}: {e}")
        
        finally:
            elapsed = time.time() - start_time
            self.metrics.total_update_time += elapsed
            self.metrics.last_update_time = elapsed
            self.metrics.max_update_time = max(self.metrics.max_update_time, elapsed)
    
    @abstractmethod
    def _on_update(self, delta_time: float) -> None:
        """Переопределяемый метод обновления"""
        pass
    
    def get_info(self) -> Dict[str, Any]:
        """Получение диагностической информации о компоненте"""
        return {
            'component_id': self.component_id,
            'component_type': self.component_type.value,
            'priority': self.priority.value,
            'state': self.state.value,
            'uptime': time.time() - self.created_at,
            'dependencies': self.dependencies,
            'tags': self.tags,
            'metrics': {
                'update_count': self.metrics.update_count,
                'avg_update_time_ms': self.metrics.avg_update_time * 1000,
                'updates_per_second': self.metrics.updates_per_second,
                'error_count': self.metrics.error_count,
                'last_error': self.metrics.last_error,
                'last_error_time': self.metrics.last_error_time
            }
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик производительности"""
        return {
            'update_count': self.metrics.update_count,
            'total_update_time': self.metrics.total_update_time,
            'avg_update_time_ms': self.metrics.avg_update_time * 1000,
            'updates_per_second': self.metrics.updates_per_second,
            'max_update_time_ms': self.metrics.max_update_time * 1000,
            'error_count': self.metrics.error_count,
            'last_error': self.metrics.last_error,
            'last_error_time': self.metrics.last_error_time
        }
    
    def reset_metrics(self) -> None:
        """Сброс метрик"""
        self.metrics = ComponentMetrics()
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.component_id}, type={self.component_type.value}, state={self.state.value})"


# ============================================================================
# УТИЛИТЫ
# ============================================================================

T = TypeVar('T', bound='BaseComponent')


class ComponentRegistry:
    """Реестр компонентов для поиска и управления"""
    
    _instance: Optional['ComponentRegistry'] = None
    
    def __new__(cls) -> 'ComponentRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._components: Dict[str, BaseComponent] = {}
            cls._instance._by_type: Dict[ComponentType, List[str]] = {}
            cls._instance._by_priority: Dict[Priority, List[str]] = {}
        return cls._instance
    
    def register(self, component: BaseComponent) -> bool:
        """Регистрация компонента"""
        if component.component_id in self._components:
            logger.warning(f"Компонент {component.component_id} уже зарегистрирован")
            return False
        
        self._components[component.component_id] = component
        
        # Индексация по типу
        comp_type = component.component_type
        if comp_type not in self._by_type:
            self._by_type[comp_type] = []
        self._by_type[comp_type].append(component.component_id)
        
        # Индексация по приоритету
        priority = component.priority
        if priority not in self._by_priority:
            self._by_priority[priority] = []
        self._by_priority[priority].append(component.component_id)
        
        logger.debug(f"Компонент {component.component_id} зарегистрирован")
        return True
    
    def unregister(self, component_id: str) -> bool:
        """Отмена регистрации компонента"""
        if component_id not in self._components:
            return False
        
        component = self._components[component_id]
        del self._components[component_id]
        
        # Удаляем из индексов
        if component.component_type in self._by_type:
            if component_id in self._by_type[component.component_type]:
                self._by_type[component.component_type].remove(component_id)
        
        if component.priority in self._by_priority:
            if component_id in self._by_priority[component.priority]:
                self._by_priority[component.priority].remove(component_id)
        
        logger.debug(f"Компонент {component_id} удален из реестра")
        return True
    
    def get(self, component_id: str) -> Optional[BaseComponent]:
        """Получение компонента по ID"""
        return self._components.get(component_id)
    
    def get_by_type(self, component_type: ComponentType) -> List[BaseComponent]:
        """Получение компонентов по типу"""
        ids = self._by_type.get(component_type, [])
        return [self._components[cid] for cid in ids if cid in self._components]
    
    def get_by_priority(self, priority: Priority) -> List[BaseComponent]:
        """Получение компонентов по приоритету"""
        ids = self._by_priority.get(priority, [])
        return [self._components[cid] for cid in ids if cid in self._components]
    
    def get_all(self) -> List[BaseComponent]:
        """Получение всех компонентов"""
        return list(self._components.values())
    
    def get_sorted_by_priority(self) -> List[BaseComponent]:
        """Получение всех компонентов, отсортированных по приоритету"""
        components = self.get_all()
        return sorted(components, key=lambda c: c.priority.value)
    
    def clear(self) -> None:
        """Очистка реестра"""
        self._components.clear()
        self._by_type.clear()
        self._by_priority.clear()
        logger.info("Реестр компонентов очищен")
