#!/usr/bin/env python3
"""Улучшенная архитектура для AI - EVOLVE
Модульная архитектура с принципом единой ответственности

Этот модуль содержит EventBus и ComponentManager.
Базовые классы IComponent и BaseComponent определены в component_types.py
"""

from typing import *
from typing import Dict, List, Optional, Any, Type, TypeVar, Generic, Callable
import logging
import time

from .component_types import ComponentType, LifecycleState, Priority, BaseComponent, IComponent

# Реэкспорт для обратной совместимости
# Все импорты из architecture.py будут работать
__all__ = ['ComponentType', 'LifecycleState', 'Priority', 'BaseComponent', 'IComponent', 'EventBus', 'ComponentManager']

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
