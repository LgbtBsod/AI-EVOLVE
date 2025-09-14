from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import *
from typing import Dict, List, Optional, Any, Type, TypeVar, Generic, Callable
import logging
import os
import sys
import threading
import time

#!/usr/bin/env python3
"""Улучшенная архитектура для AI - EVOLVE
Модульная архитектура с принципом единой ответственности"""

from abc import ABC, abstractmethod
from .component_types import ComponentType, LifecycleState, Priority, BaseComponent, IComponent

# = БАЗОВЫЕ КЛАССЫ АРХИТЕКТУРЫ
class IComponent(ABC):
    """Базовый интерфейс для всех компонентов архитектуры"""
    
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
    def update(self, delta_time: float) -> bool:
        """Обновление компонента"""
        pass

# = БАЗОВЫЕ КЛАССЫ РЕАЛИЗАЦИИ
class BaseComponent(IComponent):
    """Базовая реализация компонента архитектуры"""
    
    def __init__(self, component_id: str, component_type: ComponentType, priority: Priority = Priority.NORMAL):
        self._component_id = component_id
        self._component_type = component_type
        self._priority = priority
        self._state = LifecycleState.UNINITIALIZED
        self._logger = logging.getLogger(f"{__name__}.{component_id}")
        self._dependencies: List[str] = []
        self._dependents: List[str] = []
        self._error_count = 0
        self._last_error = None
        self._initialization_time = 0.0
        self._total_runtime = 0.0
        self._update_count = 0
    
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
    
    def add_dependency(self, component_id: str) -> None:
        """Добавление зависимости от другого компонента"""
        if component_id not in self._dependencies:
            self._dependencies.append(component_id)
    
    def remove_dependency(self, component_id: str) -> None:
        """Удаление зависимости от компонента"""
        if component_id in self._dependencies:
            self._dependencies.remove(component_id)
    
    def add_dependent(self, component_id: str) -> None:
        """Добавление зависимого компонента"""
        if component_id not in self._dependents:
            self._dependents.append(component_id)
    
    def remove_dependent(self, component_id: str) -> None:
        """Удаление зависимого компонента"""
        if component_id in self._dependents:
            self._dependents.remove(component_id)
    
    def initialize(self) -> bool:
        """Инициализация компонента"""
        try:
            if self._state != LifecycleState.UNINITIALIZED:
                self._logger.warning(f"Попытка инициализации компонента в состоянии {self._state}")
                return False
            
            self._state = LifecycleState.INITIALIZING
            self._logger.info(f"Инициализация компонента {self._component_id}")
            
            if self._on_initialize():
                self._state = LifecycleState.READY
                self._initialization_time = time.time()
                self._logger.info(f"Компонент {self._component_id} успешно инициализирован")
                return True
            else:
                self._state = LifecycleState.ERROR
                self._logger.error(f"Ошибка инициализации компонента {self._component_id}")
                return False
                
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._last_error = str(e)
            self._error_count += 1
            self._logger.error(f"Исключение при инициализации компонента {self._component_id}: {e}")
            return False
    
    def start(self) -> bool:
        """Запуск компонента"""
        try:
            if self._state != LifecycleState.READY:
                self._logger.warning(f"Попытка запуска компонента в состоянии {self._state}")
                return False
            
            self._state = LifecycleState.RUNNING
            self._logger.info(f"Запуск компонента {self._component_id}")
            
            if self._on_start():
                self._logger.info(f"Компонент {self._component_id} успешно запущен")
                return True
            else:
                self._state = LifecycleState.ERROR
                self._logger.error(f"Ошибка запуска компонента {self._component_id}")
                return False
                
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._last_error = str(e)
            self._error_count += 1
            self._logger.error(f"Исключение при запуске компонента {self._component_id}: {e}")
            return False
    
    def pause(self) -> bool:
        """Приостановка компонента"""
        try:
            if self._state != LifecycleState.RUNNING:
                self._logger.warning(f"Попытка приостановки компонента в состоянии {self._state}")
                return False
            
            self._state = LifecycleState.PAUSED
            self._logger.info(f"Приостановка компонента {self._component_id}")
            
            if self._on_pause():
                self._logger.info(f"Компонент {self._component_id} успешно приостановлен")
                return True
            else:
                self._state = LifecycleState.ERROR
                self._logger.error(f"Ошибка приостановки компонента {self._component_id}")
                return False
                
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._last_error = str(e)
            self._error_count += 1
            self._logger.error(f"Исключение при приостановке компонента {self._component_id}: {e}")
            return False
    
    def resume(self) -> bool:
        """Возобновление компонента"""
        try:
            if self._state != LifecycleState.PAUSED:
                self._logger.warning(f"Попытка возобновления компонента в состоянии {self._state}")
                return False
            
            self._state = LifecycleState.RUNNING
            self._logger.info(f"Возобновление компонента {self._component_id}")
            
            if self._on_resume():
                self._logger.info(f"Компонент {self._component_id} успешно возобновлен")
                return True
            else:
                self._state = LifecycleState.ERROR
                self._logger.error(f"Ошибка возобновления компонента {self._component_id}")
                return False
                
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._last_error = str(e)
            self._error_count += 1
            self._logger.error(f"Исключение при возобновлении компонента {self._component_id}: {e}")
            return False
    
    def stop(self) -> bool:
        """Остановка компонента"""
        try:
            if self._state not in [LifecycleState.RUNNING, LifecycleState.PAUSED]:
                self._logger.warning(f"Попытка остановки компонента в состоянии {self._state}")
                return False
            
            self._state = LifecycleState.STOPPING
            self._logger.info(f"Остановка компонента {self._component_id}")
            
            if self._on_stop():
                self._state = LifecycleState.READY
                self._logger.info(f"Компонент {self._component_id} успешно остановлен")
                return True
            else:
                self._state = LifecycleState.ERROR
                self._logger.error(f"Ошибка остановки компонента {self._component_id}")
                return False
                
        except Exception as e:
            self._state = LifecycleState.ERROR
            self._last_error = str(e)
            self._error_count += 1
            self._logger.error(f"Исключение при остановке компонента {self._component_id}: {e}")
            return False
    
    def destroy(self) -> bool:
        """Уничтожение компонента"""
        try:
            if self._state == LifecycleState.DESTROYED:
                self._logger.warning(f"Попытка уничтожения уже уничтоженного компонента {self._component_id}")
                return True
            
            self._logger.info(f"Уничтожение компонента {self._component_id}")
            
            if self._on_destroy():
                self._state = LifecycleState.DESTROYED
                self._logger.info(f"Компонент {self._component_id} успешно уничтожен")
                return True
            else:
                self._logger.error(f"Ошибка уничтожения компонента {self._component_id}")
                return False
                
        except Exception as e:
            self._last_error = str(e)
            self._error_count += 1
            self._logger.error(f"Исключение при уничтожении компонента {self._component_id}: {e}")
            return False
    
    def update(self, delta_time: float) -> bool:
        """Обновление компонента"""
        try:
            if self._state != LifecycleState.RUNNING:
                return True  # Не обновляем неактивные компоненты
            
            start_time = time.time()
            
            if self._on_update(delta_time):
                self._total_runtime += time.time() - start_time
                self._update_count += 1
                return True
            else:
                self._logger.warning(f"Ошибка обновления компонента {self._component_id}")
                return False
                
        except Exception as e:
            self._last_error = str(e)
            self._error_count += 1
            self._logger.error(f"Исключение при обновлении компонента {self._component_id}: {e}")
            return False
    
    # Методы для переопределения в наследниках
    def _on_initialize(self) -> bool:
        """Переопределяемый метод инициализации"""
        return True
    
    def _on_start(self) -> bool:
        """Переопределяемый метод запуска"""
        return True
    
    def _on_pause(self) -> bool:
        """Переопределяемый метод приостановки"""
        return True
    
    def _on_resume(self) -> bool:
        """Переопределяемый метод возобновления"""
        return True
    
    def _on_stop(self) -> bool:
        """Переопределяемый метод остановки"""
        return True
    
    def _on_destroy(self) -> bool:
        """Переопределяемый метод уничтожения"""
        return True
    
    def _on_update(self, delta_time: float) -> bool:
        """Переопределяемый метод обновления"""
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики компонента"""
        return {
            "component_id": self._component_id,
            "component_type": self._component_type.value,
            "priority": self._priority.value,
            "state": self._state.value,
            "error_count": self._error_count,
            "last_error": self._last_error,
            "initialization_time": self._initialization_time,
            "total_runtime": self._total_runtime,
            "update_count": self._update_count,
            "dependencies": self._dependencies.copy(),
            "dependents": self._dependents.copy()
        }
    
    def __str__(self) -> str:
        return f"BaseComponent(id={self._component_id}, type={self._component_type.value}, state={self._state.value})"
    
    def __repr__(self) -> str:
        return self.__str__()

# = СИСТЕМА СОБЫТИЙ
class EventBus:
    """Система событий для межкомпонентного взаимодействия"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_history: List[Dict[str, Any]] = []
        self._max_history = 1000
        self._logger = logging.getLogger(__name__)
    
    def subscribe(self, event_type: str, callback: Callable) -> bool:
        """Подписка на событие"""
        try:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                self._logger.debug(f"Подписка на событие {event_type} для {callback}")
                return True
            else:
                self._logger.warning(f"Повторная подписка на событие {event_type} для {callback}")
                return False
                
        except Exception as e:
            self._logger.error(f"Ошибка подписки на событие {event_type}: {e}")
            return False
    
    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """Отписка от события"""
        try:
            if event_type in self._subscribers and callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
                self._logger.debug(f"Отписка от события {event_type} для {callback}")
                return True
            else:
                self._logger.warning(f"Попытка отписки от несуществующей подписки {event_type}")
                return False
                
        except Exception as e:
            self._logger.error(f"Ошибка отписки от события {event_type}: {e}")
            return False
    
    def publish(self, event_type: str, data: Any = None, source: str = None) -> bool:
        """Публикация события"""
        try:
            event = {
                "type": event_type,
                "data": data,
                "source": source,
                "timestamp": time.time()
            }
            
            # Добавление в историю
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)
            
            # Уведомление подписчиков
            if event_type in self._subscribers:
                for callback in self._subscribers[event_type]:
                    try:
                        callback(event)
                    except Exception as e:
                        self._logger.error(f"Ошибка в обработчике события {event_type}: {e}")
            
            self._logger.debug(f"Событие {event_type} опубликовано от {source}")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка публикации события {event_type}: {e}")
            return False
    
    def get_subscribers(self, event_type: str) -> List[Callable]:
        """Получение списка подписчиков на событие"""
        return self._subscribers.get(event_type, []).copy()
    
    def get_event_history(self, event_type: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение истории событий"""
        if event_type is None:
            return self._event_history[-limit:] if self._event_history else []
        else:
            filtered = [event for event in self._event_history if event["type"] == event_type]
            return filtered[-limit:] if filtered else []
    
    def clear_history(self) -> None:
        """Очистка истории событий"""
        self._event_history.clear()
        self._logger.info("История событий очищена")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики системы событий"""
        total_subscribers = sum(len(subscribers) for subscribers in self._subscribers.values())
        return {
            "event_types": len(self._subscribers),
            "total_subscribers": total_subscribers,
            "event_history_size": len(self._event_history),
            "max_history": self._max_history
        }

# = МЕНЕДЖЕР КОМПОНЕНТОВ
class ComponentManager:
    """Менеджер для управления жизненным циклом компонентов"""
    
    def __init__(self):
        self._components: Dict[str, BaseComponent] = {}
        self._component_order: List[str] = []
        self._initialization_queue: List[str] = []
        self._logger = logging.getLogger(__name__)
    
    def register_component(self, component: BaseComponent) -> bool:
        """Регистрация компонента"""
        try:
            if component.component_id in self._components:
                self._logger.warning(f"Компонент {component.component_id} уже зарегистрирован")
                return False
            
            self._components[component.component_id] = component
            self._component_order.append(component.component_id)
            
            # Сортировка по приоритету
            self._component_order.sort(key=lambda cid: self._components[cid].priority.value)
            
            self._logger.info(f"Компонент {component.component_id} зарегистрирован")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка регистрации компонента {component.component_id}: {e}")
            return False
    
    def unregister_component(self, component_id: str) -> bool:
        """Отмена регистрации компонента"""
        try:
            if component_id not in self._components:
                self._logger.warning(f"Попытка отмены регистрации несуществующего компонента {component_id}")
                return False
            
            component = self._components[component_id]
            
            # Остановка и уничтожение компонента
            if component.state in [LifecycleState.RUNNING, LifecycleState.PAUSED]:
                component.stop()
            
            if component.state != LifecycleState.DESTROYED:
                component.destroy()
            
            # Удаление из менеджера
            del self._components[component_id]
            if component_id in self._component_order:
                self._component_order.remove(component_id)
            
            self._logger.info(f"Компонент {component_id} отменен")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка отмены регистрации компонента {component_id}: {e}")
            return False
    
    def get_component(self, component_id: str) -> Optional[BaseComponent]:
        """Получение компонента по ID"""
        return self._components.get(component_id)
    
    def get_components_by_type(self, component_type: ComponentType) -> List[BaseComponent]:
        """Получение компонентов по типу"""
        return [comp for comp in self._components.values() if comp.component_type == component_type]
    
    def get_components_by_priority(self, priority: Priority) -> List[BaseComponent]:
        """Получение компонентов по приоритету"""
        return [comp for comp in self._components.values() if comp.priority == priority]
    
    def initialize_all(self) -> bool:
        """Инициализация всех компонентов"""
        try:
            self._logger.info("Начало инициализации всех компонентов")
            
            # Инициализация по приоритету
            for component_id in self._component_order:
                component = self._components[component_id]
                if not component.initialize():
                    self._logger.error(f"Ошибка инициализации компонента {component_id}")
                    return False
            
            self._logger.info("Все компоненты успешно инициализированы")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка инициализации компонентов: {e}")
            return False
    
    def start_all(self) -> bool:
        """Запуск всех компонентов"""
        try:
            self._logger.info("Начало запуска всех компонентов")
            
            # Запуск по приоритету
            for component_id in self._component_order:
                component = self._components[component_id]
                if not component.start():
                    self._logger.error(f"Ошибка запуска компонента {component_id}")
                    return False
            
            self._logger.info("Все компоненты успешно запущены")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка запуска компонентов: {e}")
            return False
    
    def stop_all(self) -> bool:
        """Остановка всех компонентов"""
        try:
            self._logger.info("Начало остановки всех компонентов")
            
            # Остановка в обратном порядке приоритета
            for component_id in reversed(self._component_order):
                component = self._components[component_id]
                if component.state in [LifecycleState.RUNNING, LifecycleState.PAUSED]:
                    if not component.stop():
                        self._logger.error(f"Ошибка остановки компонента {component_id}")
                        return False
            
            self._logger.info("Все компоненты успешно остановлены")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка остановки компонентов: {e}")
            return False
    
    def destroy_all(self) -> bool:
        """Уничтожение всех компонентов"""
        try:
            self._logger.info("Начало уничтожения всех компонентов")
            
            # Уничтожение в обратном порядке приоритета
            for component_id in reversed(self._component_order):
                component = self._components[component_id]
                if component.state != LifecycleState.DESTROYED:
                    if not component.destroy():
                        self._logger.error(f"Ошибка уничтожения компонента {component_id}")
                        return False
            
            self._logger.info("Все компоненты успешно уничтожены")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка уничтожения компонентов: {e}")
            return False
    
    def update_all(self, delta_time: float) -> bool:
        """Обновление всех компонентов"""
        try:
            # Обновление по приоритету
            for component_id in self._component_order:
                component = self._components[component_id]
                if not component.update(delta_time):
                    self._logger.warning(f"Ошибка обновления компонента {component_id}")
            
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка обновления компонентов: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики менеджера компонентов"""
        component_stats = {}
        for component_id, component in self._components.items():
            component_stats[component_id] = component.get_stats()
        
        return {
            "total_components": len(self._components),
            "components_by_type": {
                comp_type.value: len(self.get_components_by_type(comp_type))
                for comp_type in ComponentType
            },
            "components_by_priority": {
                priority.value: len(self.get_components_by_type(priority))
                for priority in Priority
            },
            "component_details": component_stats
        }
    
    def __len__(self) -> int:
        return len(self._components)
    
    def __contains__(self, component_id: str) -> bool:
        return component_id in self._components
