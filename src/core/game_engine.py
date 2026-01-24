from .architecture import ComponentManager, EventBus, Priority, ComponentType
from .repository import RepositoryManager, DataType, StorageType
from .state_manager import StateManager, StateType
from dataclasses import dataclass
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from enum import Enum
from panda3d.core import WindowProperties
from pathlib import Path
from typing import *
from typing import Dict, Any, Optional
import logging
import os
import sys
import time

#!/usr/bin/env python3
"""Game Engine - Основной игровой движок на Panda3D
Упрощенная архитектура с четким разделением ответственности"""

# Panda3D imports
# Новая архитектура
logger = logging.getLogger(__name__)

class GameEngine(ShowBase):
    """Основной игровой движок на Panda3D
    Упрощенная архитектура с четким разделением ответственности"""
    
    def __init__(self, config: Dict[str, Any]):
        # Инициализация Panda3D ShowBase
        super().__init__()
        self.settings = config
        self.running = False
        self.paused = False
        
        # Состояние игры
        self.current_state = "initializing"
        self.delta_time = 0.0
        self.last_frame_time = time.time()
        
        # Статистика
        self.fps = 0
        self.frame_count = 0
        self.start_time = time.time()
        
        # Новая архитектура - основные менеджеры
        self.component_manager: Optional[ComponentManager] = None
        self.event_bus: Optional[EventBus] = None
        self.state_manager: Optional[StateManager] = None
        self.repository_manager: Optional[RepositoryManager] = None
        # Используем forward reference через Optional[Any], чтобы избежать предупреждений до импорта
        from typing import Any as _Any
        self.master_integrator: Optional[_Any] = None
        
        # Адаптеры для существующих систем (только для совместимости)
        self._legacy_adapters = {}
        
        logger.info("Игровой движок Panda3D с упрощенной архитектурой инициализирован")
    
    def initialize(self) -> bool:
        """Инициализация игрового движка"""
        try:
            logger.info("Начало инициализации игрового движка Panda3D...")
            
            # Инициализация Panda3D
            if not self._initialize_panda3d():
                return False
            
            # Инициализация менеджеров новой архитектуры
            if not self._initialize_new_architecture():
                return False
            
            # Инициализация существующих систем (для совместимости)
            if not self._initialize_legacy_systems():
                return False
            
            # Настройка основного цикла
            if not self._setup_main_loop():
                return False
            
            self.current_state = "ready"
            logger.info("Игровой движок успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"Критическая ошибка инициализации игрового движка: {e}")
            self.current_state = "error"
            return False
    
    def _initialize_panda3d(self) -> bool:
        """Инициализация базовых компонентов Panda3D"""
        try:
            # Настройка окна
            props = WindowProperties()
            props.setTitle("AI-EVOLVE: Эволюционная Адаптация")
            props.setSize(1280, 720)
            props.setCursorHidden(False)
            
            # Применение настроек окна
            self.win.requestProperties(props)
            
            # Настройка камеры
            self.cam.setPos(0, -20, 0)
            self.cam.lookAt(0, 0, 0)
            
            # Настройка освещения
            self.setup_lighting()
            
            logger.info("Panda3D базовые компоненты инициализированы")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации Panda3D: {e}")
            return False
    
    def _initialize_new_architecture(self) -> bool:
        """Инициализация новой архитектуры"""
        try:
            # Создание EventBus
            self.event_bus = EventBus()
            logger.info("EventBus создан")
            
            # Создание ComponentManager
            self.component_manager = ComponentManager()
            logger.info("ComponentManager создан")
            
            # Создание StateManager
            self.state_manager = StateManager()
            logger.info("StateManager создан")
            
            # Создание RepositoryManager
            self.repository_manager = RepositoryManager()
            logger.info("RepositoryManager создан")

            # Создание MasterIntegrator
            from .master_integrator import MasterIntegrator  # локальный импорт, чтобы избежать циклов
            self.master_integrator = MasterIntegrator()
            logger.info("MasterIntegrator создан")
            
            # Регистрация основных менеджеров как компонентов
            self.component_manager.register_component(self.state_manager)
            self.component_manager.register_component(self.repository_manager)
            self.component_manager.register_component(self.master_integrator)

            # Передаем архитектурные компоненты в MasterIntegrator до инициализации
            # AttributeSystem будет создан внутри MasterIntegrator, поэтому передаем None
            if self.master_integrator and self.state_manager:
                try:
                    # AttributeSystem будет создан в _create_all_systems, поэтому пока передаем None
                    self.master_integrator.set_architecture_components(self.state_manager, None)  # type: ignore[arg-type]
                except Exception as e:
                    logger.warning(f"Не удалось передать архитектурные компоненты в MasterIntegrator до инициализации: {e}")

            # Инициализация всех компонентов
            if not self.component_manager.initialize_all():
                logger.error("Ошибка инициализации компонентов архитектуры")
                return False
            
            logger.info("Новая архитектура инициализирована")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации новой архитектуры: {e}")
            return False
    
    def _initialize_legacy_systems(self) -> bool:
        """Инициализация существующих систем для совместимости"""
        try:
            # Здесь будет инициализация существующих систем
            # Пока что просто логируем
            logger.info("Legacy системы подготовлены к инициализации")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации legacy систем: {e}")
            return False
    
    def _setup_main_loop(self) -> bool:
        """Настройка основного игрового цикла"""
        try:
            # Добавление задачи обновления
            self.taskMgr.add(self._update_loop, "GameUpdateLoop")
            
            # Добавление задачи рендеринга
            self.taskMgr.add(self._render_loop, "GameRenderLoop")
            
            logger.info("Основной игровой цикл настроен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка настройки основного цикла: {e}")
            return False
    
    def setup_lighting(self):
        """Настройка освещения сцены"""
        try:
            # Основное освещение
            main_light = self.render.attachNewNode("MainLight")
            main_light.setPos(10, -10, 10)
            main_light.lookAt(0, 0, 0)
            
            # Ambient освещение
            ambient_light = self.render.attachNewNode("AmbientLight")
            ambient_light.setPos(0, 0, 10)
            
            logger.debug("Освещение сцены настроено")
            
        except Exception as e:
            logger.warning(f"Ошибка настройки освещения: {e}")
    
    def start(self) -> bool:
        """Запуск игрового движка"""
        try:
            if self.current_state != "ready":
                logger.error(f"Нельзя запустить движок в состоянии {self.current_state}")
                return False
            
            logger.info("Запуск игрового движка...")
            
            # Запуск всех компонентов
            if not self.component_manager.start_all():
                logger.error("Ошибка запуска компонентов")
                return False

            # Запуск MasterIntegrator (инициализация и запуск внутренних систем)
            if self.master_integrator:
                # MasterIntegrator уже инициализирован как компонент; убедимся, что он запущен
                pass
            
            self.running = True
            self.current_state = "running"
            self.start_time = time.time()
            
            logger.info("Игровой движок запущен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска игрового движка: {e}")
            self.current_state = "error"
            return False
    
    def stop(self) -> bool:
        """Остановка игрового движка"""
        try:
            if not self.running:
                logger.warning("Попытка остановки уже остановленного движка")
                return True
            
            logger.info("Остановка игрового движка...")
            
            # Остановка всех компонентов
            if not self.component_manager.stop_all():
                logger.error("Ошибка остановки компонентов")
                return False
            
            self.running = False
            self.current_state = "stopped"
            
            logger.info("Игровой движок остановлен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки игрового движка: {e}")
            return False
    
    def pause(self) -> bool:
        """Приостановка игрового движка"""
        try:
            if not self.running:
                logger.warning("Нельзя приостановить неработающий движок")
                return False
            
            if self.paused:
                logger.warning("Движок уже приостановлен")
                return True
            
            logger.info("Приостановка игрового движка...")
            
            # Приостановка всех компонентов
            for component in self.component_manager._components.values():
                if component.state.value == "running":
                    component.pause()
            
            self.paused = True
            self.current_state = "paused"
            
            logger.info("Игровой движок приостановлен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка приостановки игрового движка: {e}")
            return False
    
    def resume(self) -> bool:
        """Возобновление игрового движка"""
        try:
            if not self.paused:
                logger.warning("Нельзя возобновить неприостановленный движок")
                return False
            
            logger.info("Возобновление игрового движка...")
            
            # Возобновление всех компонентов
            for component in self.component_manager._components.values():
                if component.state.value == "paused":
                    component.resume()
            
            self.paused = False
            self.current_state = "running"
            
            logger.info("Игровой движок возобновлен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка возобновления игрового движка: {e}")
            return False
    
    def _update_loop(self, task: Task) -> int:
        """Основной цикл обновления игры"""
        try:
            if not self.running:
                return Task.cont
            
            # Вычисление delta time
            current_time = time.time()
            self.delta_time = current_time - self.last_frame_time
            self.last_frame_time = current_time
            
            # Обновление всех компонентов
            if self.component_manager:
                self.component_manager.update_all(self.delta_time)
            
            # Обновление статистики
            self.frame_count += 1
            if self.frame_count % 60 == 0:
                self.fps = 60.0 / self.delta_time if self.delta_time > 0 else 0
            
            return Task.cont
            
        except Exception as e:
            logger.error(f"Ошибка в цикле обновления: {e}")
            return Task.cont
    
    def _render_loop(self, task: Task) -> int:
        """Цикл рендеринга"""
        try:
            if not self.running:
                return Task.cont
            
            # Panda3D автоматически рендерит сцену
            # Здесь можно добавить дополнительную логику рендеринга
            
            return Task.cont
            
        except Exception as e:
            logger.error(f"Ошибка в цикле рендеринга: {e}")
            return Task.cont
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики игрового движка"""
        try:
            stats = {
                "current_state": self.current_state,
                "running": self.running,
                "paused": self.paused,
                "fps": self.fps,
                "frame_count": self.frame_count,
                "delta_time": self.delta_time,
                "uptime": time.time() - self.start_time if self.start_time > 0 else 0
            }
            
            # Добавление статистики компонентов
            if self.component_manager:
                stats["components"] = self.component_manager.get_stats()
            
            # Добавление статистики событий
            if self.event_bus:
                stats["events"] = self.event_bus.get_stats()
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {"error": str(e)}
    
    def cleanup(self):
        """Очистка ресурсов"""
        try:
            logger.info("Начало очистки ресурсов игрового движка...")
            
            # Остановка движка
            if self.running:
                self.stop()
            
            # Уничтожение всех компонентов
            if self.component_manager:
                self.component_manager.destroy_all()
            
            # Очистка Panda3D (ShowBase имеет собственный cleanup, не вызываем рекурсивно метод класса)
            try:
                super().cleanup()
            except Exception:
                pass
            
            logger.info("Ресурсы игрового движка очищены")
            
        except Exception as e:
            logger.error(f"Ошибка очистки ресурсов: {e}")
    
    def __del__(self):
        """Деструктор"""
        try:
            self.cleanup()
        except:
            pass
