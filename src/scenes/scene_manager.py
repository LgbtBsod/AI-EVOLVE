#!/usr/bin/env python3
"""Scene Manager - управление игровыми сценами"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from src.core.architecture import BaseComponent, ComponentType, LifecycleState, Priority
from src.core.constants import SceneType, constants_manager
from src.core.state_manager import StateManager, StateType

logger = logging.getLogger(__name__)

class Scene:
    """Базовый класс сцены с единым жизненным циклом"""
    
    def __init__(self, scene_id: str):
        self.scene_id = scene_id
        self.scene_manager: SceneManager | None = None
        self.ui_root = None
        self.initialized = False
        self.active = False
    
    def attach_manager(self, manager: "SceneManager") -> None:
        self.scene_manager = manager
    
    def initialize(self) -> bool:
        self.initialized = True
        return True
    
    def start(self) -> bool:
        if not self.initialized:
            if not self.initialize():
                return False
        self.active = True
        return True
    
    def update(self, delta_time: float) -> None:
        """Обновление логики сцены каждый кадр. Переопределяется в наследниках."""
        # Базовая реализация не делает ничего
        # Наследники должны переопределить этот метод для своей логики
        
    def render(self, render_node: Any) -> None:
        """Отрисовка сцены. Переопределяется в наследниках."""
        # Базовая реализация не делает ничего
        # Наследники должны переопределить этот метод для своей отрисовки
        
    def handle_event(self, event: Any) -> None:
        """Обработка событий ввода. Переопределяется в наследниках."""
        # Базовая реализация не делает ничего
        # Наследники должны переопределить этот метод для обработки событий
    
    def cleanup(self) -> None:
        self.active = False

"""Используются централизованные перечисления SceneType и SceneState из src.core.constants"""

@dataclass(slots=True)
class SceneData:
    """Данные сцены"""
    scene_id: str
    scene_type: SceneType
    scene_name: str
    scene_file: str
    properties: dict[str, Any] = field(default_factory=dict)
    entities: list[str] = field(default_factory=list)
    ui_elements: list[str] = field(default_factory=list)
    background_music: str | None = None
    ambient_sounds: list[str] = field(default_factory=list)
    instance: Optional["Scene"] = None

@dataclass(slots=True)
class SceneTransition:
    """Переход между сценами"""
    from_scene: str
    to_scene: str
    transition_type: str = "fade"
    duration: float = 1.0
    callback: Callable | None = None

class SceneManager(BaseComponent):
    """Менеджер игровых сцен"""
    
    def __init__(self):
        super().__init__(
            component_id="scene_manager",
            component_type=ComponentType.SYSTEM,
            priority=Priority.HIGH
        )
        
        # Архитектурные компоненты
        self.state_manager: StateManager | None = None
        
        # Сцены и переходы
        self.scenes: dict[str, SceneData] = {}
        self.scene_instances: dict[str, Scene] = {}
        self.active_scene: str | None = None
        self.previous_scene: str | None = None
        self.scene_stack: list[str] = []
        
        # Переходы
        self.current_transition: SceneTransition | None = None
        self.transition_queue: list[SceneTransition] = []
        
        # Настройки сцен
        self.scene_settings = {
            'auto_save_on_scene_change': True,
            'preload_adjacent_scenes': True,
            'scene_transition_effects': True,
            'scene_loading_timeout': 30.0,
            'max_scene_stack_size': 10
        }
        
        # Статистика сцен
        self.scene_stats = {
            'total_scenes': 0,
            'scenes_loaded': 0,
            'scenes_unloaded': 0,
            'scene_transitions': 0,
            'current_scene_time': 0.0,
            'total_scene_time': 0.0,
            'update_time': 0.0
        }
    
    def set_architecture_components(self, state_manager: StateManager):
        """Установка архитектурных компонентов"""
        self.state_manager = state_manager
        logger.info("Архитектурные компоненты установлены в SceneManager")
    
    def _register_system_states(self):
        """Регистрация состояний системы"""
        if self.state_manager:
            # Регистрируем состояния сцен
            self.state_manager.set_state(
                f"{self.component_id}_settings",
                self.scene_settings,
                StateType.SETTINGS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_stats",
                self.scene_stats,
                StateType.STATISTICS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_state",
                self.system_state,
                StateType.SYSTEM_STATE
            )
    
    def initialize(self) -> bool:
        """Инициализация менеджера сцен"""
        try:
            logger.info("Инициализация SceneManager...")
            
            # Регистрируем состояния системы
            self._register_system_states()
            
            # Регистрируем встроенные сцены
            self._register_builtin_scenes()
            
            # Загружаем настройки сцен
            self._load_scene_settings()
            
            self.system_state = LifecycleState.READY
            logger.info("SceneManager инициализирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации SceneManager: {e}")
            self.system_state = LifecycleState.ERROR
            return False
    
    def start(self) -> bool:
        """Запуск менеджера сцен"""
        try:
            logger.info("Запуск SceneManager...")
            
            if self.system_state != LifecycleState.READY:
                logger.error("SceneManager не готов к запуску")
                return False
            
            # Активируем начальную сцену
            if self.scenes:
                first_scene = "main_menu" if "main_menu" in self.scenes else list(self.scenes.keys())[0]
                self.load_scene(first_scene)
            
            self.system_state = LifecycleState.RUNNING
            logger.info("SceneManager запущен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска SceneManager: {e}")
            self.system_state = LifecycleState.ERROR
            return False
    
    def update(self, delta_time: float):
        """Обновление менеджера сцен"""
        if self.system_state != LifecycleState.RUNNING:
            return
        
        try:
            start_time = time.perf_counter()
            
            # Обновляем активную сцену
            self._update_active_scene(delta_time)
            
            # Обрабатываем переходы
            self._process_transitions(delta_time)
            
            # Обновляем статистику
            self.scene_stats['current_scene_time'] += delta_time
            self.scene_stats['total_scene_time'] += delta_time
            self.scene_stats['update_time'] = time.perf_counter() - start_time
            
            # Обновляем состояние в менеджере состояний
            if self.state_manager:
                self.state_manager.set_state(
                    f"{self.system_name}_stats",
                    self.scene_stats,
                    StateType.STATISTICS
                )
                
        except Exception as e:
            logger.error(f"Ошибка обновления SceneManager: {e}")
    
    def stop(self) -> bool:
        """Остановка менеджера сцен"""
        try:
            logger.info("Остановка SceneManager...")
            
            # Выгружаем все сцены
            for scene_id in list(self.scenes.keys()):
                self.unload_scene(scene_id)
            
            self.system_state = LifecycleState.STOPPED
            logger.info("SceneManager остановлен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки SceneManager: {e}")
            return False
    
    def destroy(self) -> bool:
        """Уничтожение менеджера сцен"""
        try:
            logger.info("Уничтожение SceneManager...")
            
            # Очищаем все сцены
            self.scenes.clear()
            self.scene_stack.clear()
            self.transition_queue.clear()
            
            self.system_state = LifecycleState.DESTROYED
            logger.info("SceneManager уничтожен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения SceneManager: {e}")
            return False
    
    def _create_default_scenes(self):
        """Создание базовых сцен"""
        # Создаем главное меню
        main_menu = SceneData(
            scene_id="main_menu",
            scene_type=SceneType.MAIN_MENU,
            scene_name="Главное меню",
            scene_file="scenes/main_menu.json",
            background_music="music/main_menu.ogg"
        )
        
        # Создаем игровой мир
        game_world = SceneData(
            scene_id="game_world",
            scene_type=SceneType.GAME_WORLD,
            scene_name="Игровой мир",
            scene_file="scenes/game_world.json",
            background_music="music/game_world.ogg",
            ambient_sounds=["sounds/ambient_forest.ogg", "sounds/ambient_wind.ogg"]
        )
        
        # Создаем сцену боя
        combat = SceneData(
            scene_id="combat",
            scene_type=SceneType.COMBAT,
            scene_name="Бой",
            scene_file="scenes/combat.json",
            background_music="music/combat.ogg"
        )
        
        # Добавляем сцены
        self.scenes["main_menu"] = main_menu
        self.scenes["game_world"] = game_world
        self.scenes["combat"] = combat
        
        self.scene_stats['total_scenes'] = len(self.scenes)
    
    def _load_scene_settings(self):
        """Загрузка настроек сцен"""
        try:
            # Загружаем настройки из менеджера констант
            scene_constants = constants_manager.get_scene_settings()
            if scene_constants:
                self.scene_settings.update(scene_constants)
            
            logger.info("Настройки сцен загружены")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек сцен: {e}")
    
    def _update_active_scene(self, delta_time: float):
        """Обновление активной сцены"""
        if self.active_scene and self.active_scene in self.scenes:
            # Обновляем активную сцену
            scene = self.scenes[self.active_scene]
            self._update_scene(scene, delta_time)
    
    def _update_scene(self, scene: SceneData, delta_time: float):
        """Обновление отдельной сцены"""
        if scene.instance and scene.instance.active:
            try:
                scene.instance.update(delta_time)
            except Exception as e:
                logger.error(f"Ошибка обновления сцены {scene.scene_id}: {e}")
    
    def _process_transitions(self, delta_time: float):
        """Обработка переходов между сценами"""
        if self.current_transition:
            # Обрабатываем текущий переход
            self._update_transition(self.current_transition, delta_time)
        elif self.transition_queue:
            # Начинаем следующий переход
            self.current_transition = self.transition_queue.pop(0)
            self._start_transition(self.current_transition)
    
    def _update_transition(self, transition: SceneTransition, delta_time: float):
        """Обновление перехода"""
        # Здесь будет логика обновления перехода
    
    def _start_transition(self, transition: SceneTransition):
        """Начало перехода"""
        try:
            logger.info(f"Начало перехода: {transition.from_scene} -> {transition.to_scene}")
            
            # Здесь будет логика начала перехода
            
        except Exception as e:
            logger.error(f"Ошибка начала перехода: {e}")

    def register_scene(self, scene_id: str, scene_instance: "Scene", scene_type: SceneType,
                       scene_name: str, scene_file: str = "") -> bool:
        """Регистрация экземпляра сцены"""
        try:
            scene_instance.attach_manager(self)
            data = SceneData(
                scene_id=scene_id,
                scene_type=scene_type,
                scene_name=scene_name,
                scene_file=scene_file,
                instance=scene_instance
            )
            self.scenes[scene_id] = data
            self.scene_instances[scene_id] = scene_instance
            self.scene_stats['total_scenes'] = len(self.scenes)
            logger.info(f"Зарегистрирована сцена: {scene_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка регистрации сцены {scene_id}: {e}")
            return False
    
    def create_scene(self, scene_id: str, scene_type: SceneType, scene_name: str, 
                    scene_file: str) -> SceneData | None:
        """Создание новой сцены"""
        try:
            if scene_id in self.scenes:
                logger.warning(f"Сцена с ID {scene_id} уже существует")
                return None
            
            scene = SceneData(
                scene_id=scene_id,
                scene_type=scene_type,
                scene_name=scene_name,
                scene_file=scene_file
            )
            
            self.scenes[scene_id] = scene
            self.scene_stats['total_scenes'] = len(self.scenes)
            
            logger.info(f"Создана сцена: {scene_id}")
            return scene
            
        except Exception as e:
            logger.error(f"Ошибка создания сцены {scene_id}: {e}")
            return None
    
    def load_scene(self, scene_id: str) -> bool:
        """Загрузка сцены"""
        try:
            if scene_id not in self.scenes:
                logger.warning(f"Сцена с ID {scene_id} не найдена")
                return False
            
            # Сохраняем предыдущую сцену
            if self.active_scene:
                self.previous_scene = self.active_scene
                self.scene_stack.append(self.active_scene)
                # Останавливаем предыдущую сцену
                prev_data = self.scenes.get(self.previous_scene)
                if prev_data and prev_data.instance and prev_data.instance.active:
                    try:
                        prev_data.instance.cleanup()
                    except Exception as e:
                        logger.error(f"Ошибка очистки предыдущей сцены {self.previous_scene}: {e}")
                
                # Ограничиваем размер стека
                if len(self.scene_stack) > self.scene_settings['max_scene_stack_size']:
                    self.scene_stack.pop(0)
            
            # Активируем новую сцену
            self.active_scene = scene_id
            self.scene_stats['scenes_loaded'] += 1
            self.scene_stats['current_scene_time'] = 0.0
            
            # Инициализируем и запускаем сцену
            data = self.scenes[scene_id]
            if data.instance:
                try:
                    if not data.instance.initialized:
                        if not data.instance.initialize():
                            logger.error(f"Инициализация сцены {scene_id} не удалась")
                            return False
                    data.instance.start()
                except Exception as e:
                    logger.error(f"Ошибка старта сцены {scene_id}: {e}")
                    return False
            
            logger.info(f"Загружена сцена: {scene_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки сцены {scene_id}: {e}")
            return False
    
    def unload_scene(self, scene_id: str) -> bool:
        """Выгрузка сцены"""
        try:
            if scene_id not in self.scenes:
                logger.warning(f"Сцена с ID {scene_id} не найдена")
                return False
            
            # Если это активная сцена, деактивируем её
            if self.active_scene == scene_id:
                try:
                    data = self.scenes[scene_id]
                    if data.instance and data.instance.active:
                        data.instance.cleanup()
                finally:
                    self.active_scene = None
            
            # Удаляем из стека
            if scene_id in self.scene_stack:
                self.scene_stack.remove(scene_id)
            
            self.scene_stats['scenes_unloaded'] += 1
            
            logger.info(f"Выгружена сцена: {scene_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка выгрузки сцены {scene_id}: {e}")
            return False
    
    def transition_to_scene(self, to_scene: str, transition_type: str = "fade", 
                          duration: float = 1.0, callback: Callable | None = None) -> bool:
        """Переход к сцене"""
        try:
            if to_scene not in self.scenes:
                logger.warning(f"Сцена с ID {to_scene} не найдена")
                return False
            
            transition = SceneTransition(
                from_scene=self.active_scene or "",
                to_scene=to_scene,
                transition_type=transition_type,
                duration=duration,
                callback=callback
            )
            
            self.transition_queue.append(transition)
            self.scene_stats['scene_transitions'] += 1
            
            logger.info(f"Добавлен переход к сцене: {to_scene}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания перехода к сцене {to_scene}: {e}")
            return False
    
    def go_back(self) -> bool:
        """Возврат к предыдущей сцене"""
        try:
            if not self.scene_stack:
                logger.warning("Нет предыдущих сцен для возврата")
                return False
            
            previous_scene = self.scene_stack.pop()
            return self.load_scene(previous_scene)
            
        except Exception as e:
            logger.error(f"Ошибка возврата к предыдущей сцене: {e}")
            return False
    
    def get_scene(self, scene_id: str) -> SceneData | None:
        """Получение сцены"""
        return self.scenes.get(scene_id)
    
    def get_active_scene_data(self) -> SceneData | None:
        """Получение данных активной сцены"""
        if self.active_scene:
            return self.scenes.get(self.active_scene)
        return None
    
    def get_all_scenes(self) -> dict[str, SceneData]:
        """Получение всех сцен"""
        return self.scenes.copy()
    
    def get_scene_stack(self) -> list[str]:
        """Получение стека сцен"""
        return self.scene_stack.copy()
    
    def get_system_info(self) -> dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.system_name,
            'state': self.system_state.value,
            'priority': self.system_priority.value,
            'total_scenes': self.scene_stats['total_scenes'],
            'scenes_loaded': self.scene_stats['scenes_loaded'],
            'scenes_unloaded': self.scene_stats['scenes_unloaded'],
            'scene_transitions': self.scene_stats['scene_transitions'],
            'active_scene': self.active_scene,
            'previous_scene': self.previous_scene,
            'scene_stack_size': len(self.scene_stack),
            'current_scene_time': self.scene_stats['current_scene_time'],
            'total_scene_time': self.scene_stats['total_scene_time'],
            'update_time': self.scene_stats['update_time']
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.scene_stats = {
            'total_scenes': len(self.scenes),
            'scenes_loaded': 0,
            'scenes_unloaded': 0,
            'scene_transitions': 0,
            'current_scene_time': 0.0,
            'total_scene_time': 0.0,
            'update_time': 0.0
        }

    def _register_builtin_scenes(self):
        """Регистрация встроенных сцен"""
        try:
            # Локальные импорты для избежания циклов
            from .creator_scene import CreatorScene
            from .game_scene import GameScene
            from .load_scene import LoadScene
            from .menu_scene import MenuScene
            from .pause_scene import PauseScene
            from .settings_scene import SettingsScene

            self.register_scene("main_menu", MenuScene(), SceneType.MAIN_MENU, "Главное меню")
            self.register_scene("settings", SettingsScene(), SceneType.SETTINGS, "Настройки")
            self.register_scene("load_game", LoadScene(), SceneType.LOADING, "Загрузка")
            # Для pauze используем SETTINGS как ближайший тип при отсутствии особого
            self.register_scene("pause", PauseScene(), SceneType.SETTINGS, "Пауза")
            self.register_scene("creator", CreatorScene(), SceneType.GAME_WORLD, "Творец мира")
            self.register_scene("game_world", GameScene(), SceneType.GAME_WORLD, "Игровой мир")
        except Exception as e:
            logger.error(f"Ошибка регистрации встроенных сцен: {e}")
