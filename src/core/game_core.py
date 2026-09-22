#!/usr/bin/env python3
"""
Game Core - центральное ядро игры
Управляет жизненным циклом, координирует системы и плагины
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from src.core.architecture import BaseComponent, ComponentType, LifecycleState, Priority
from src.core.event_system import EventSystem
from src.core.state_manager import StateManager, StateType

if TYPE_CHECKING:
    from src.database.db_core import DatabaseCore
    from src.scenes.scene_manager import SceneManager

logger = logging.getLogger(__name__)


class GameCore(BaseComponent):
    """
    Центральное ядро игры
    
    Отвечает за:
    - Инициализацию и жизненный цикл игры
    - Координацию между системами
    - Управление плагинами/фичами
    - Доступ к глобальным сервисам (БД, события, состояния)
    """
    
    def __init__(self):
        super().__init__(
            component_id="game_core",
            component_type=ComponentType.CORE,
            priority=Priority.CRITICAL
        )
        
        # Ядерные компоненты
        self.database_core: Optional["DatabaseCore"] = None
        self.event_system: Optional[EventSystem] = None
        self.state_manager: Optional[StateManager] = None
        self.scene_manager: Optional["SceneManager"] = None
        
        # Зарегистрированные плагины/фичи
        self.plugins: dict[str, Any] = {}
        self.plugin_order: list[str] = []
        
        # Конфигурация ядра
        self.core_config = {
            'enable_plugins': True,
            'plugin_auto_discovery': True,
            'strict_plugin_dependencies': True,
            'core_timeout': 30.0,
        }
        
        # Статистика ядра
        self.core_stats = {
            'plugins_loaded': 0,
            'plugins_failed': 0,
            'systems_initialized': 0,
            'update_count': 0,
            'total_update_time': 0.0,
        }
        
        logger.info("GameCore создан")
    
    def set_dependencies(
        self,
        database_core: "DatabaseCore",
        event_system: EventSystem,
        state_manager: StateManager,
    ) -> None:
        """Установка зависимостей ядра"""
        self.database_core = database_core
        self.event_system = event_system
        self.state_manager = state_manager
        logger.info("Зависимости GameCore установлены")
    
    def set_scene_manager(self, scene_manager: "SceneManager") -> None:
        """Установка менеджера сцен"""
        self.scene_manager = scene_manager
        logger.info("SceneManager подключен к GameCore")
    
    def initialize(self) -> bool:
        """Инициализация ядра игры"""
        try:
            logger.info("=== Инициализация GameCore ===")
            
            # Проверяем зависимости
            if not self.database_core:
                logger.error("DatabaseCore не установлен")
                return False
            
            if not self.event_system:
                logger.error("EventSystem не установлен")
                return False
            
            if not self.state_manager:
                logger.error("StateManager не установлен")
                return False
            
            # Инициализируем базовые системы
            if not self.database_core.initialize():
                logger.error("Не удалось инициализировать DatabaseCore")
                return False
            
            if not self.event_system.initialize():
                logger.error("Не удалось инициализировать EventSystem")
                return False
            
            if not self.state_manager.initialize():
                logger.error("Не удалось инициализировать StateManager")
                return False
            
            self.core_stats['systems_initialized'] = 3
            
            # Регистрируем состояние ядра
            self.state_manager.set_state(
                f"{self.component_id}_config",
                self.core_config,
                StateType.CONFIGURATION
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_stats",
                self.core_stats,
                StateType.STATISTICS
            )
            
            self.system_state = LifecycleState.READY
            logger.info("GameCore успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации GameCore: {e}", exc_info=True)
            self.system_state = LifecycleState.ERROR
            return False
    
    def start(self) -> bool:
        """Запуск ядра игры"""
        try:
            logger.info("=== Запуск GameCore ===")
            
            if self.system_state != LifecycleState.READY:
                logger.error("GameCore не готов к запуску")
                return False
            
            # Запускаем базовые системы
            if not self.database_core.start():
                logger.error("Не удалось запустить DatabaseCore")
                return False
            
            if not self.event_system.start():
                logger.error("Не удалось запустить EventSystem")
                return False
            
            if not self.state_manager.start():
                logger.error("Не удалось запустить StateManager")
                return False
            
            # Запускаем плагины
            for plugin_id in self.plugin_order:
                plugin = self.plugins.get(plugin_id)
                if plugin and hasattr(plugin, 'start'):
                    try:
                        if not plugin.start():
                            logger.warning(f"Плагин {plugin_id} не смог запуститься")
                    except Exception as e:
                        logger.error(f"Ошибка запуска плагина {plugin_id}: {e}")
            
            # Запускаем SceneManager если есть
            if self.scene_manager and not self.scene_manager.start():
                logger.warning("Не удалось запустить SceneManager")
            
            self.system_state = LifecycleState.RUNNING
            logger.info("GameCore успешно запущен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска GameCore: {e}", exc_info=True)
            self.system_state = LifecycleState.ERROR
            return False
    
    def update(self, delta_time: float) -> None:
        """Обновление ядра игры"""
        if self.system_state != LifecycleState.RUNNING:
            return
        
        try:
            import time
            start_time = time.perf_counter()
            
            # Обновляем системы
            self.database_core.update(delta_time)
            self.event_system.update(delta_time)
            self.state_manager.update(delta_time)
            
            # Обновляем плагины
            for plugin_id in self.plugin_order:
                plugin = self.plugins.get(plugin_id)
                if plugin and hasattr(plugin, 'update'):
                    try:
                        plugin.update(delta_time)
                    except Exception as e:
                        logger.error(f"Ошибка обновления плагина {plugin_id}: {e}")
            
            # Обновляем SceneManager если есть
            if self.scene_manager:
                self.scene_manager.update(delta_time)
            
            # Статистика
            self.core_stats['update_count'] += 1
            self.core_stats['total_update_time'] += time.perf_counter() - start_time
            
        except Exception as e:
            logger.error(f"Ошибка обновления GameCore: {e}", exc_info=True)
    
    def stop(self) -> bool:
        """Остановка ядра игры"""
        try:
            logger.info("=== Остановка GameCore ===")
            
            # Останавливаем плагины
            for plugin_id in reversed(self.plugin_order):
                plugin = self.plugins.get(plugin_id)
                if plugin and hasattr(plugin, 'stop'):
                    try:
                        plugin.stop()
                    except Exception as e:
                        logger.error(f"Ошибка остановки плагина {plugin_id}: {e}")
            
            # Останавливаем SceneManager
            if self.scene_manager:
                self.scene_manager.stop()
            
            # Останавливаем базовые системы
            self.state_manager.stop()
            self.event_system.stop()
            self.database_core.stop()
            
            self.system_state = LifecycleState.STOPPED
            logger.info("GameCore успешно остановлен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки GameCore: {e}", exc_info=True)
            return False
    
    def destroy(self) -> bool:
        """Уничтожение ядра игры"""
        try:
            logger.info("=== Уничтожение GameCore ===")
            
            # Уничтожаем плагины
            for plugin_id in reversed(self.plugin_order):
                plugin = self.plugins.get(plugin_id)
                if plugin and hasattr(plugin, 'destroy'):
                    try:
                        plugin.destroy()
                    except Exception as e:
                        logger.error(f"Ошибка уничтожения плагина {plugin_id}: {e}")
            
            self.plugins.clear()
            self.plugin_order.clear()
            
            # Уничтожаем SceneManager
            if self.scene_manager:
                self.scene_manager.destroy()
            
            # Уничтожаем базовые системы
            self.state_manager.destroy()
            self.event_system.destroy()
            self.database_core.destroy()
            
            # Очищаем зависимости
            self.database_core = None
            self.event_system = None
            self.state_manager = None
            self.scene_manager = None
            
            self.system_state = LifecycleState.DESTROYED
            logger.info("GameCore успешно уничтожен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения GameCore: {e}", exc_info=True)
            return False
    
    def register_plugin(self, plugin_id: str, plugin: Any, dependencies: list[str] | None = None) -> bool:
        """
        Регистрация плагина/фичи
        
        Args:
            plugin_id: Уникальный идентификатор плагина
            plugin: Объект плагина с методами initialize/start/update/stop/destroy
            dependencies: Список ID плагинов от которых зависит этот
        
        Returns:
            bool: True если регистрация успешна
        """
        try:
            if plugin_id in self.plugins:
                logger.warning(f"Плагин {plugin_id} уже зарегистрирован")
                return False
            
            # Проверяем зависимости
            if dependencies and self.core_config['strict_plugin_dependencies']:
                for dep_id in dependencies:
                    if dep_id not in self.plugins:
                        logger.error(f"Плагин {plugin_id} требует зависимость {dep_id}")
                        return False
            
            # Инициализируем плагин
            if hasattr(plugin, 'initialize'):
                if not plugin.initialize():
                    logger.error(f"Не удалось инициализировать плагин {plugin_id}")
                    self.core_stats['plugins_failed'] += 1
                    return False
            
            self.plugins[plugin_id] = plugin
            self.plugin_order.append(plugin_id)
            self.core_stats['plugins_loaded'] += 1
            
            # Обновляем статистику в state manager
            if self.state_manager:
                self.state_manager.set_state(
                    f"{self.component_id}_stats",
                    self.core_stats,
                    StateType.STATISTICS
                )
            
            logger.info(f"Плагин {plugin_id} зарегистрирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка регистрации плагина {plugin_id}: {e}", exc_info=True)
            return False
    
    def unregister_plugin(self, plugin_id: str) -> bool:
        """Удаление плагина"""
        try:
            if plugin_id not in self.plugins:
                logger.warning(f"Плагин {plugin_id} не найден")
                return False
            
            plugin = self.plugins[plugin_id]
            
            # Уничтожаем плагин
            if hasattr(plugin, 'destroy'):
                plugin.destroy()
            
            del self.plugins[plugin_id]
            self.plugin_order.remove(plugin_id)
            
            logger.info(f"Плагин {plugin_id} удален")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления плагина {plugin_id}: {e}", exc_info=True)
            return False
    
    def get_plugin(self, plugin_id: str) -> Any | None:
        """Получение плагина по ID"""
        return self.plugins.get(plugin_id)
    
    def has_plugin(self, plugin_id: str) -> bool:
        """Проверка наличия плагина"""
        return plugin_id in self.plugins
    
    def get_database(self) -> Optional["DatabaseCore"]:
        """Получение ядра БД"""
        return self.database_core
    
    def get_event_system(self) -> Optional[EventSystem]:
        """Получение системы событий"""
        return self.event_system
    
    def get_state_manager(self) -> Optional[StateManager]:
        """Получение менеджера состояний"""
        return self.state_manager
    
    def get_scene_manager(self) -> Optional["SceneManager"]:
        """Получение менеджера сцен"""
        return self.scene_manager
    
    def get_system_info(self) -> dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.system_name,
            'state': self.system_state.value,
            'priority': self.system_priority.value,
            'plugins_loaded': self.core_stats['plugins_loaded'],
            'plugins_failed': self.core_stats['plugins_failed'],
            'systems_initialized': self.core_stats['systems_initialized'],
            'update_count': self.core_stats['update_count'],
            'avg_update_time': (
                self.core_stats['total_update_time'] / self.core_stats['update_count']
                if self.core_stats['update_count'] > 0 else 0.0
            ),
        }
