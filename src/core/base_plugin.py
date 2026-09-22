#!/usr/bin/env python3
"""
Base Plugin - базовый класс для плагинов/фич
Все фичи игры должны наследоваться от этого класса
"""

import logging
from typing import Any, Optional

from src.core.architecture import BaseComponent, ComponentType, LifecycleState, Priority

logger = logging.getLogger(__name__)


class BasePlugin(BaseComponent):
    """
    Базовый класс плагина/фичи
    
    Предоставляет:
    - Жизненный цикл (initialize/start/update/stop/destroy)
    - Интеграцию с GameCore
    - Доступ к ядрам (БД, события, состояния)
    - Статистику и логирование
    
    Пример использования:
        class CombatPlugin(BasePlugin):
            def __init__(self):
                super().__init__("combat_plugin")
            
            def initialize(self) -> bool:
                # Инициализация
                return True
            
            def start(self) -> bool:
                # Запуск
                return True
            
            def update(self, delta_time: float):
                # Логика каждый кадр
                pass
    """
    
    def __init__(
        self,
        plugin_id: str,
        plugin_name: str | None = None,
        version: str = "1.0.0",
        dependencies: list[str] | None = None,
    ):
        """
        Инициализация плагина
        
        Args:
            plugin_id: Уникальный ID плагина
            plugin_name: Человекочитаемое имя
            version: Версия плагина
            dependencies: Список зависимостей (ID других плагинов)
        """
        super().__init__(
            component_id=plugin_id,
            component_type=ComponentType.PLUGIN,
            priority=Priority.NORMAL
        )
        
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name or plugin_id
        self.version = version
        self._dependencies = dependencies or []
        
        # Ссылки на ядра (устанавливаются GameCore при регистрации)
        self.game_core: Any = None
        self.database_core: Any = None
        self.event_system: Any = None
        self.state_manager: Any = None
        
        # Конфигурация плагина
        self.plugin_config: dict[str, Any] = {}
        
        # Статистика плагина
        self.plugin_stats = {
            'update_count': 0,
            'total_update_time': 0.0,
            'errors_count': 0,
        }
        
        logger.info(f"Плагин {self.plugin_id} v{self.version} создан")
    
    def set_core_references(
        self,
        game_core: Any,
        database_core: Any,
        event_system: Any,
        state_manager: Any,
    ) -> None:
        """Установка ссылок на ядра системы"""
        self.game_core = game_core
        self.database_core = database_core
        self.event_system = event_system
        self.state_manager = state_manager
        logger.debug(f"Плагин {self.plugin_id} получил ссылки на ядра")
    
    @property
    def dependencies(self) -> list[str]:
        return self._dependencies.copy()
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Получение значения конфигурации"""
        return self.plugin_config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """Установка значения конфигурации"""
        self.plugin_config[key] = value
    
    def get_database(self):
        """Получение ядра БД"""
        return self.database_core
    
    def get_event_system(self):
        """Получение системы событий"""
        return self.event_system
    
    def get_state_manager(self):
        """Получение менеджера состояний"""
        return self.state_manager
    
    def emit_event(self, event_type: str, data: Any = None) -> None:
        """
        Отправка события через систему событий
        
        Args:
            event_type: Тип события
            data: Данные события
        """
        if self.event_system:
            self.event_system.emit(event_type, data)
    
    def save_state(self, state_data: dict[str, Any]) -> bool:
        """
        Сохранение состояния плагина в БД
        
        Args:
            state_data: Данные для сохранения
        
        Returns:
            bool: True если успешно
        """
        if not self.database_core:
            logger.error(f"Плагин {self.plugin_id}: DatabaseCore недоступен")
            return False
        
        try:
            with self.database_core.get_session() as session:
                # Здесь должна быть логика сохранения через ORM
                # Для примера просто логируем
                logger.debug(f"Сохранение состояния {self.plugin_id}: {state_data}")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния {self.plugin_id}: {e}")
            return False
    
    def load_state(self) -> dict[str, Any] | None:
        """
        Загрузка состояния плагина из БД
        
        Returns:
            dict: Данные состояния или None
        """
        if not self.database_core:
            logger.error(f"Плагин {self.plugin_id}: DatabaseCore недоступен")
            return None
        
        try:
            with self.database_core.get_session() as session:
                # Здесь должна быть логика загрузки через ORM
                # Для примера просто возвращаем пустой dict
                logger.debug(f"Загрузка состояния {self.plugin_id}")
                return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки состояния {self.plugin_id}: {e}")
            return None
    
    def update(self, delta_time: float) -> None:
        """Обновление плагина с подсчетом статистики"""
        if self.system_state != LifecycleState.RUNNING:
            return
        
        try:
            import time
            start_time = time.perf_counter()
            
            # Вызываем переопределенный метод update_logic
            self.update_logic(delta_time)
            
            # Статистика
            self.plugin_stats['update_count'] += 1
            self.plugin_stats['total_update_time'] += time.perf_counter() - start_time
            
        except Exception as e:
            self.plugin_stats['errors_count'] += 1
            logger.error(f"Ошибка обновления плагина {self.plugin_id}: {e}", exc_info=True)
    
    def update_logic(self, delta_time: float) -> None:
        """
        Логика обновления плагина
        Переопределяется в наследниках
        
        Args:
            delta_time: Время прошедшее с последнего кадра
        """
        pass
    
    def get_plugin_info(self) -> dict[str, Any]:
        """Получение информации о плагине"""
        return {
            'plugin_id': self.plugin_id,
            'plugin_name': self.plugin_name,
            'version': self.version,
            'state': self.system_state.value,
            'dependencies': self.dependencies,
            'config': self.plugin_config,
            'stats': self.plugin_stats,
        }
    
    def get_system_info(self) -> dict[str, Any]:
        """Переопределение для включения информации о плагине"""
        base_info = super().get_system_info()
        base_info.update({
            'plugin_name': self.plugin_name,
            'version': self.version,
            'dependencies': self.dependencies,
        })
        return base_info


__all__ = ['BasePlugin']
