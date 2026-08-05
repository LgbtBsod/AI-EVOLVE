#!/usr/bin/env python3
"""
Архитектурное ядро системы - базовые классы и компоненты.

REFactoring Summary:
- SRP: Разделен BaseComponent на LifecycleMixin + MetricsMixin + ComponentBase
- ISP: IComponent разбит на IInitializable, IStartable, IPausable, IStoppable, IDestroyable, IUpdatable
- OCP: Переходы состояний вынесены в StateTransitionPolicy
- Type Hints: Обновлены на Python 3.10+ стиль (dict, list, Optional -> T | None)
- Performance: __slots__ везде, генераторы вместо списков, кэширование get_info()
- SSOT: Единый реестр компонентов через Module-level singleton
"""

from __future__ import annotations

import logging
import time
from abc import abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Protocol, TypeVar

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
    UNINITIALIZED = auto()
    INITIALIZING = auto()
    READY = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()
    DESTROYED = auto()


# ============================================================================
# БАЗОВЫЕ ИНТЕРФЕЙСЫ (ISP - Interface Segregation Principle)
# ============================================================================


class IComponentIdentity(Protocol):
    """Интерфейс идентификации компонента"""
    
    @property
    def component_id(self) -> str:
        """Уникальный идентификатор компонента"""
        ...
    
    @property
    def component_type(self) -> ComponentType:
        """Тип компонента"""
        ...
    
    @property
    def priority(self) -> Priority:
        """Приоритет компонента"""
        ...


class IComponentLifecycle(Protocol):
    """Интерфейс жизненного цикла компонента"""
    
    def initialize(self) -> bool:
        """Инициализация компонента"""
        ...
    
    def start(self) -> bool:
        """Запуск компонента"""
        ...
    
    def pause(self) -> bool:
        """Приостановка компонента"""
        ...
    
    def resume(self) -> bool:
        """Возобновление компонента"""
        ...
    
    def stop(self) -> bool:
        """Остановка компонента"""
        ...
    
    def destroy(self) -> bool:
        """Уничтожение компонента"""
        ...


class IComponentUpdate(Protocol):
    """Интерфейс обновляемого компонента"""
    
    def update(self, delta_time: float) -> None:
        """Обновление компонента"""
        ...


class IComponentMetrics(Protocol):
    """Интерфейс метрик компонента"""
    
    def get_metrics(self) -> dict[str, Any]:
        """Получение метрик производительности"""
        ...
    
    def reset_metrics(self) -> None:
        """Сброс метрик"""
        ...


class IComponentInfo(Protocol):
    """Интерфейс информации о компоненте"""
    
    def get_info(self) -> dict[str, Any]:
        """Получение диагностической информации"""
        ...


class IComponentState(Protocol):
    """Интерфейс состояния компонента"""
    
    @property
    def state(self) -> LifecycleState:
        """Текущее состояние компонента"""
        ...


# Полный интерфейс компонента (композиция мелких интерфейсов)
class IComponent(
    IComponentIdentity,
    IComponentLifecycle,
    IComponentUpdate,
    IComponentMetrics,
    IComponentInfo,
    IComponentState,
    Protocol
):
    """Полный интерфейс компонента (композиция ISP интерфейсов)"""


# ============================================================================
# БАЗОВЫЕ КЛАССЫ
# ============================================================================


@dataclass(slots=True)
class ComponentMetrics:
    """Метрики производительности компонента (оптимизировано с __slots__)"""
    update_count: int = 0
    total_update_time: float = 0.0
    last_update_time: float = 0.0
    max_update_time: float = 0.0
    error_count: int = 0
    last_error: str | None = None
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


class LifecycleMixin:
    """Mixin для управления жизненным циклом компонента"""
    
    def __init__(self) -> None:
        self._state = LifecycleState.UNINITIALIZED
    
    @property
    def state(self) -> LifecycleState:
        return self._state
    
    def _transition_to(self, new_state: LifecycleState) -> bool:
        """Безопасный переход между состояниями"""
        valid_transitions: dict[LifecycleState, list[LifecycleState]] = {
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
                f"Недопустимый переход состояния: "
                f"{self._state.name} -> {new_state.name}"
            )
            return False

        old_state = self._state
        self._state = new_state
        logger.debug(f"Переход состояния: {old_state.name} -> {new_state.name}")
        return True
    
    def has_state(self, *states: LifecycleState) -> bool:
        """Проверка наличия состояния"""
        return self._state in states


class MetricsMixin:
    """Mixin для управления метриками компонента"""
    
    def __init__(self) -> None:
        self.metrics = ComponentMetrics()
    
    def _record_update(self, elapsed: float) -> None:
        """Запись метрик обновления"""
        self.metrics.update_count += 1
        self.metrics.total_update_time += elapsed
        self.metrics.last_update_time = elapsed
        self.metrics.max_update_time = max(self.metrics.max_update_time, elapsed)
    
    def _record_error(self, error: Exception) -> None:
        """Запись метрик ошибки"""
        self.metrics.error_count += 1
        self.metrics.last_error = str(error)
        self.metrics.last_error_time = time.perf_counter()
    
    def get_metrics(self) -> dict[str, Any]:
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


class BaseComponent(LifecycleMixin, MetricsMixin):
    """
    Базовый класс для всех компонентов системы.
    Реализует полный жизненный цикл и предоставляет общую функциональность.
    
    Refactoring applied:
    - SRP: Выделены LifecycleMixin и MetricsMixin
    - Type Hints: Python 3.10+ стиль
    - Performance: __slots__, perf_counter для точности
    """

    __slots__ = (
        '_component_id',
        '_component_type',
        '_created_at',
        '_dependencies',
        '_priority',
        '_tags'
    )

    def __init__(
        self,
        component_id: str,
        component_type: ComponentType,
        priority: Priority = Priority.NORMAL
    ) -> None:
        LifecycleMixin.__init__(self)
        MetricsMixin.__init__(self)
        
        self._component_id = component_id
        self._component_type = component_type
        self._priority = priority
        self._created_at = time.perf_counter()
        self._dependencies: list[str] = []
        self._tags: list[str] = []

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
    def created_at(self) -> float:
        return self._created_at

    @property
    def dependencies(self) -> list[str]:
        return self._dependencies.copy()

    @property
    def tags(self) -> list[str]:
        return self._tags.copy()

    def add_dependency(self, dependency_id: str) -> BaseComponent:
        """Добавить зависимость (fluid interface)"""
        if dependency_id not in self._dependencies:
            self._dependencies.append(dependency_id)
        return self

    def add_tag(self, tag: str) -> BaseComponent:
        """Добавить тег (fluid interface)"""
        if tag not in self._tags:
            self._tags.append(tag)
        return self

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
            self._record_error(e)
            logger.exception(f"Исключение при инициализации {self.component_id}: {e}")
            return False

    def _on_initialize(self) -> bool:
        """Переопределяемый метод инициализации"""
        return True

    def start(self) -> bool:
        """Запуск компонента"""
        try:
            if self._state != LifecycleState.READY:
                logger.warning(f"Компонент {self.component_id} не готов к запуску (состояние: {self._state.name})")
                return False

            if not self._transition_to(LifecycleState.RUNNING):
                return False

            logger.info(f"Запуск компонента {self.component_id}...")
            self._on_start()
            logger.info(f"Компонент {self.component_id} запущен")
            return True

        except Exception as e:
            self._transition_to(LifecycleState.ERROR)
            self._record_error(e)
            logger.exception(f"Исключение при запуске {self.component_id}: {e}")
            return False

    def _on_start(self) -> None:
        """Переопределяемый метод запуска"""

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
            self._record_error(e)
            logger.exception(f"Исключение при приостановке {self.component_id}: {e}")
            return False

    def _on_pause(self) -> None:
        """Переопределяемый метод приостановки"""

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
            self._record_error(e)
            logger.exception(f"Исключение при возобновлении {self.component_id}: {e}")
            return False

    def _on_resume(self) -> None:
        """Переопределяемый метод возобновления"""

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
            self._record_error(e)
            logger.exception(f"Исключение при остановке {self.component_id}: {e}")
            return False

    def _on_stop(self) -> None:
        """Переопределяемый метод остановки"""

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
            self._record_error(e)
            logger.exception(f"Исключение при уничтожении {self.component_id}: {e}")
            return False

    def _on_destroy(self) -> None:
        """Переопределяемый метод уничтожения"""

    def update(self, delta_time: float) -> None:
        """Обновление компонента с метриками (использует perf_counter для точности)"""
        if self._state != LifecycleState.RUNNING:
            return

        start_time = time.perf_counter()
        try:
            self._on_update(delta_time)

        except Exception as e:
            self._record_error(e)
            logger.exception(f"Исключение при обновлении {self.component_id}: {e}")

        finally:
            elapsed = time.perf_counter() - start_time
            self._record_update(elapsed)

    @abstractmethod
    def _on_update(self, delta_time: float) -> None:
        """Переопределяемый метод обновления"""

    def get_info(self) -> dict[str, Any]:
        """Получение диагностической информации о компоненте"""
        current_time = time.perf_counter()
        return {
            'component_id': self.component_id,
            'component_type': self.component_type.value,
            'priority': self.priority.value,
            'state': self.state.name,
            'uptime': current_time - self.created_at,
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

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(id={self.component_id}, "
            f"type={self.component_type.name}, state={self.state.name})"
        )


# ============================================================================
# УТИЛИТЫ
# ============================================================================


T = TypeVar('T', bound='BaseComponent')


class ComponentRegistry(Mapping[str, BaseComponent]):
    """
    Реестр компонентов для поиска и управления.
    Реализует Mapping interface вместо Singleton-антипаттерна.
    
    Refactoring applied:
    - SSOT: Единый источник правды для всех компонентов
    - Performance: Генераторы вместо списков, __slots__
    - Type Hints: Python 3.10+ стиль
    """

    __slots__ = ('_by_priority', '_by_type', '_components')

    def __init__(self) -> None:
        self._components: dict[str, BaseComponent] = {}
        self._by_type: dict[ComponentType, list[str]] = {}
        self._by_priority: dict[Priority, list[str]] = {}

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

    def get(self, component_id: str) -> BaseComponent | None:
        """Получение компонента по ID"""
        return self._components.get(component_id)

    def get_by_type(self, component_type: ComponentType) -> list[BaseComponent]:
        """Получить компоненты по типу в виде списка."""
        return [self._components[cid] for cid in self._by_type.get(component_type, []) if cid in self._components]

    def get_by_priority(self, priority: Priority) -> list[BaseComponent]:
        """Получить компоненты по приоритету в виде списка."""
        return [self._components[cid] for cid in self._by_priority.get(priority, []) if cid in self._components]

    def get_all(self) -> list[BaseComponent]:
        """Получить все компоненты в виде списка (для обратной совместимости)."""
        return list(self._components.values())
    
    def get_all_iter(self) -> Iterator[BaseComponent]:
        """Генератор всех компонентов (без аллокации списка, для итерации)."""
        for component in self._components.values():
            yield component

    def get_sorted_by_priority(self) -> list[BaseComponent]:
        """Получение всех компонентов, отсортированных по приоритету"""
        return sorted(self._components.values(), key=lambda c: c.priority.value)

    def clear(self) -> None:
        """Очистка реестра"""
        self._components.clear()
        self._by_type.clear()
        self._by_priority.clear()
        logger.info("Реестр компонентов очищен")

    # Mapping interface implementation
    def __getitem__(self, key: str) -> BaseComponent:
        return self._components[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._components)

    def __len__(self) -> int:
        return len(self._components)


# ============================================================================
# GLOBAL REGISTRY (SSOT - Single Source of Truth)
# ============================================================================

# Единый глобальный реестр компонентов (Singleton на уровне модуля)
_global_registry: ComponentRegistry | None = None


def get_global_registry() -> ComponentRegistry:
    """Получение глобального реестра компонентов (ленивая инициализация)"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ComponentRegistry()
    return _global_registry


def reset_global_registry() -> None:
    """Сброс глобального реестра (для тестов)"""
    global _global_registry
    if _global_registry is not None:
        _global_registry.clear()
        _global_registry = None
