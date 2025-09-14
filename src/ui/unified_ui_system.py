#!/usr/bin/env python3
"""Объединенная система UI
Объединяет UISystem и UIManager в единую систему управления интерфейсом"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Callable
import logging
import time

# Panda3D UI imports
try:
    from direct.gui.DirectGui import *
    from direct.gui.OnscreenText import OnscreenText
    from direct.gui.OnscreenImage import OnscreenImage
    from panda3d.core import TextNode, Vec4, Vec3
except ImportError:
    # Заглушки для случая отсутствия Panda3D
    class OnscreenText:
        def __init__(self, **kwargs): pass
        def setText(self, text): pass
        def destroy(self): pass
    
    class OnscreenImage:
        def __init__(self, **kwargs): pass
        def destroy(self): pass

from ..core.component_types import BaseComponent, ComponentType, Priority, LifecycleState
from ..core.state_manager import StateManager, StateType

logger = logging.getLogger(__name__)

# = ТИПЫ UI

class UIElementType(Enum):
    """Типы UI элементов"""
    TEXT = "text"
    BUTTON = "button"
    PANEL = "panel"
    IMAGE = "image"
    BAR = "bar"
    MENU = "menu"
    WINDOW = "window"
    TOOLTIP = "tooltip"
    NOTIFICATION = "notification"

class UITheme(Enum):
    """Темы UI"""
    DEFAULT = "default"
    DARK = "dark"
    LIGHT = "light"
    NEON = "neon"
    RETRO = "retro"

class UIState(Enum):
    """Состояния UI"""
    HIDDEN = "hidden"
    VISIBLE = "visible"
    DISABLED = "disabled"
    HIGHLIGHTED = "highlighted"
    SELECTED = "selected"

# = СТРУКТУРЫ ДАННЫХ

@dataclass
class UIPosition:
    """Позиция UI элемента"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    anchor: str = "center"  # center, top_left, top_right, bottom_left, bottom_right

@dataclass
class UISize:
    """Размер UI элемента"""
    width: float = 100.0
    height: float = 50.0
    scale: float = 1.0
    auto_size: bool = False

@dataclass
class UIStyle:
    """Стиль UI элемента"""
    background_color: Vec4 = Vec4(0.2, 0.2, 0.2, 0.8)
    text_color: Vec4 = Vec4(1.0, 1.0, 1.0, 1.0)
    border_color: Vec4 = Vec4(0.5, 0.5, 0.5, 1.0)
    font_size: float = 14.0
    font_family: str = "arial"
    border_width: float = 1.0
    corner_radius: float = 5.0
    transparency: float = 1.0

@dataclass
class UIElement:
    """Базовый UI элемент"""
    element_id: str
    element_type: UIElementType
    position: UIPosition = field(default_factory=UIPosition)
    size: UISize = field(default_factory=UISize)
    style: UIStyle = field(default_factory=UIStyle)
    state: UIState = UIState.VISIBLE
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    callbacks: Dict[str, Callable] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    panda3d_node: Optional[Any] = None  # Panda3D UI node
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

@dataclass
class StatsPanel(UIElement):
    """Панель статистики"""
    show_health: bool = True
    show_mana: bool = True
    show_stamina: bool = True
    show_experience: bool = True
    show_level: bool = True
    show_attributes: bool = True
    show_skills: bool = False
    auto_update: bool = True
    update_interval: float = 0.1

class UnifiedUISystem(BaseComponent):
    """Объединенная система UI с поддержкой настроек
    Управляет всеми элементами пользовательского интерфейса"""
    
    def __init__(self):
        super().__init__(
            component_id="unified_ui_system",
            component_type=ComponentType.SYSTEM,
            priority=Priority.HIGH
        )
        
        # Архитектурные компоненты
        self.state_manager: Optional[StateManager] = None
        self.attribute_system: Optional[Any] = None
        self.item_system: Optional[Any] = None
        
        # UI элементы
        self.elements: Dict[str, UIElement] = {}
        self.element_hierarchy: Dict[str, List[str]] = {}
        self.active_theme = UITheme.DEFAULT
        
        # Panda3D UI компоненты
        self.ui_root: Optional[Any] = None
        self.font_cache: Dict[str, Any] = {}
        
        # Специализированные панели
        self.hud_elements: Dict[str, Any] = {}
        self.menu_elements: Dict[str, Any] = {}
        self.dialog_elements: Dict[str, Any] = {}
        
        # Статистика
        self.stats = {
            'total_elements': 0,
            'visible_elements': 0,
            'active_animations': 0,
            'theme_switches': 0,
            'update_time': 0.0,
            'render_calls': 0
        }
        
        # Настройки
        self.settings = {
            'auto_hide_inactive': True,
            'animation_speed': 1.0,
            'tooltip_delay': 0.5,
            'notification_duration': 3.0,
            'max_notifications': 5
        }
        
        # Настройки игры
        self.game_settings = {
            'graphics_quality': 'Medium',
            'sound_enabled': True,
            'music_volume': 0.7,
            'sfx_volume': 0.8,
            'fullscreen': False,
            'resolution': (1920, 1080),
            'vsync': True,
            'fps_limit': 60
        }
        
        logger.info("Объединенная система UI создана")
    
    def set_architecture_components(self, state_manager: StateManager, attribute_system=None, item_system=None):
        """Установка архитектурных компонентов"""
        self.state_manager = state_manager
        self.attribute_system = attribute_system
        self.item_system = item_system
        logger.info("Архитектурные компоненты установлены в UnifiedUISystem")
    
    def initialize(self) -> bool:
        """Инициализация системы UI"""
        try:
            logger.info("Инициализация объединенной системы UI...")
            
            # Регистрация состояний
            self._register_system_states()
            
            # Инициализация UI root
            self._initialize_ui_root()
            
            # Создание базовых элементов
            self._create_base_elements()
            
            # Загрузка темы
            self._load_theme(self.active_theme)
            
            self.system_state = LifecycleState.READY
            logger.info("Объединенная система UI инициализирована")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации объединенной системы UI: {e}")
            self.system_state = LifecycleState.ERROR
            return False
    
    def start(self) -> bool:
        """Запуск системы UI"""
        try:
            logger.info("Запуск объединенной системы UI...")
            
            if self.system_state != LifecycleState.READY:
                logger.error("Система не готова к запуску")
                return False
            
            # Показ HUD
            self._show_hud()
            
            # Запуск анимаций
            self._start_animations()
            
            self.system_state = LifecycleState.RUNNING
            logger.info("Объединенная система UI запущена")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска объединенной системы UI: {e}")
            self.system_state = LifecycleState.ERROR
            return False
    
    def _initialize_ui_root(self):
        """Инициализация корневого UI узла"""
        try:
            # В реальной реализации здесь будет создание UI root для Panda3D
            # self.ui_root = aspect2d.attachNewNode("ui_root")
            logger.info("UI root инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации UI root: {e}")
    
    def _create_base_elements(self):
        """Создание базовых элементов UI"""
        try:
            # Создание HUD элементов
            self._create_hud_elements()
            
            # Создание меню элементов
            self._create_menu_elements()
            
            logger.info("Базовые элементы UI созданы")
            
        except Exception as e:
            logger.error(f"Ошибка создания базовых элементов: {e}")
    
    def _create_hud_elements(self):
        """Создание элементов HUD"""
        try:
            # Панель здоровья
            health_panel = StatsPanel(
                element_id="health_panel",
                element_type=UIElementType.PANEL,
                position=UIPosition(-0.9, 0.9, 0),
                size=UISize(200, 50),
                show_health=True,
                show_mana=True,
                show_stamina=True
            )
            self.elements["health_panel"] = health_panel
            
            # Панель навыков
            skills_panel = UIElement(
                element_id="skills_panel",
                element_type=UIElementType.PANEL,
                position=UIPosition(0.9, -0.9, 0),
                size=UISize(300, 100)
            )
            self.elements["skills_panel"] = skills_panel
            
            logger.info("HUD элементы созданы")
            
        except Exception as e:
            logger.error(f"Ошибка создания HUD элементов: {e}")
    
    def _create_menu_elements(self):
        """Создание элементов меню"""
        try:
            # Главное меню
            main_menu = UIElement(
                element_id="main_menu",
                element_type=UIElementType.MENU,
                position=UIPosition(0, 0, 0),
                size=UISize(400, 600),
                state=UIState.HIDDEN
            )
            self.elements["main_menu"] = main_menu
            
            logger.info("Элементы меню созданы")
            
        except Exception as e:
            logger.error(f"Ошибка создания элементов меню: {e}")
    
    def _load_theme(self, theme: UITheme):
        """Загрузка темы UI"""
        try:
            # Настройки темы
            theme_settings = {
                UITheme.DEFAULT: {
                    'background_color': Vec4(0.2, 0.2, 0.2, 0.8),
                    'text_color': Vec4(1.0, 1.0, 1.0, 1.0),
                    'border_color': Vec4(0.5, 0.5, 0.5, 1.0)
                },
                UITheme.DARK: {
                    'background_color': Vec4(0.1, 0.1, 0.1, 0.9),
                    'text_color': Vec4(0.9, 0.9, 0.9, 1.0),
                    'border_color': Vec4(0.3, 0.3, 0.3, 1.0)
                },
                UITheme.NEON: {
                    'background_color': Vec4(0.0, 0.0, 0.0, 0.8),
                    'text_color': Vec4(0.0, 1.0, 1.0, 1.0),
                    'border_color': Vec4(0.0, 0.8, 0.8, 1.0)
                }
            }
            
            if theme in theme_settings:
                settings = theme_settings[theme]
                # Применение настроек ко всем элементам
                for element in self.elements.values():
                    element.style.background_color = settings['background_color']
                    element.style.text_color = settings['text_color']
                    element.style.border_color = settings['border_color']
            
            logger.info(f"Тема {theme} загружена")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки темы: {e}")
    
    def _show_hud(self):
        """Показ HUD"""
        try:
            hud_elements = ["health_panel", "skills_panel"]
            for element_id in hud_elements:
                if element_id in self.elements:
                    self.elements[element_id].state = UIState.VISIBLE
            
            logger.info("HUD показан")
            
        except Exception as e:
            logger.error(f"Ошибка показа HUD: {e}")
    
    def _start_animations(self):
        """Запуск анимаций UI"""
        try:
            # Здесь будет логика анимаций
            logger.info("Анимации UI запущены")
            
        except Exception as e:
            logger.error(f"Ошибка запуска анимаций: {e}")
    
    def _register_system_states(self):
        """Регистрация состояний системы"""
        if self.state_manager:
            self.state_manager.set_state(
                f"{self.component_id}_settings",
                self.settings,
                StateType.SETTINGS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_stats",
                self.stats,
                StateType.STATISTICS
            )
    
    def update(self, delta_time: float):
        """Обновление системы UI"""
        if self.system_state != LifecycleState.RUNNING:
            return
        
        try:
            start_time = time.time()
            
            # Обновление элементов
            self._update_elements(delta_time)
            
            # Обновление статистики
            self.stats['update_time'] = time.time() - start_time
            self.stats['visible_elements'] = sum(
                1 for element in self.elements.values() 
                if element.state == UIState.VISIBLE
            )
            
            # Обновление состояния в менеджере
            if self.state_manager:
                self.state_manager.set_state(
                    f"{self.component_id}_stats",
                    self.stats,
                    StateType.STATISTICS
                )
                
        except Exception as e:
            logger.error(f"Ошибка обновления системы UI: {e}")
    
    def _update_elements(self, delta_time: float):
        """Обновление UI элементов"""
        try:
            for element in self.elements.values():
                if element.state == UIState.VISIBLE:
                    # Обновление элемента
                    if isinstance(element, StatsPanel) and element.auto_update:
                        self._update_stats_panel(element)
                        
        except Exception as e:
            logger.error(f"Ошибка обновления элементов: {e}")
    
    def _update_stats_panel(self, panel: StatsPanel):
        """Обновление панели статистики"""
        try:
            if self.attribute_system and panel.show_attributes:
                # Получение данных из системы атрибутов
                # stats = self.attribute_system.get_entity_stats("player")
                # Обновление отображения
                pass
                
        except Exception as e:
            logger.error(f"Ошибка обновления панели статистики: {e}")
    
    def create_element(self, element_id: str, element_type: UIElementType, **kwargs) -> bool:
        """Создание UI элемента"""
        try:
            if element_id in self.elements:
                logger.warning(f"Элемент {element_id} уже существует")
                return False
            
            element = UIElement(
                element_id=element_id,
                element_type=element_type,
                **kwargs
            )
            
            self.elements[element_id] = element
            self.stats['total_elements'] += 1
            
            logger.info(f"UI элемент {element_id} создан")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания элемента {element_id}: {e}")
            return False
    
    def show_element(self, element_id: str) -> bool:
        """Показ UI элемента"""
        try:
            if element_id in self.elements:
                self.elements[element_id].state = UIState.VISIBLE
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка показа элемента {element_id}: {e}")
            return False
    
    def hide_element(self, element_id: str) -> bool:
        """Скрытие UI элемента"""
        try:
            if element_id in self.elements:
                self.elements[element_id].state = UIState.HIDDEN
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка скрытия элемента {element_id}: {e}")
            return False
    
    def switch_theme(self, new_theme: UITheme) -> bool:
        """Переключение темы UI"""
        try:
            if self.active_theme == new_theme:
                return True
            
            old_theme = self.active_theme
            self.active_theme = new_theme
            
            # Загрузка новой темы
            self._load_theme(new_theme)
            
            self.stats['theme_switches'] += 1
            logger.info(f"Тема UI переключена: {old_theme} -> {new_theme}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка переключения темы: {e}")
            return False
    
    def stop(self) -> bool:
        """Остановка системы UI"""
        try:
            logger.info("Остановка объединенной системы UI...")
            
            # Скрытие всех элементов
            for element in self.elements.values():
                element.state = UIState.HIDDEN
            
            self.system_state = LifecycleState.STOPPED
            logger.info("Объединенная система UI остановлена")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки системы UI: {e}")
            return False
    
    def get_setting(self, key: str, default=None):
        """Получить настройку игры"""
        return self.game_settings.get(key, default)
    
    def set_setting(self, key: str, value: Any):
        """Установить настройку игры"""
        self.game_settings[key] = value
        logger.info(f"Настройка {key} установлена в {value}")
    
    def toggle_graphics_quality(self):
        """Переключение качества графики"""
        qualities = ["Low", "Medium", "High", "Ultra"]
        current_index = qualities.index(self.game_settings['graphics_quality'])
        next_index = (current_index + 1) % len(qualities)
        self.set_setting('graphics_quality', qualities[next_index])
    
    def toggle_sound(self):
        """Переключение звука"""
        self.set_setting('sound_enabled', not self.game_settings['sound_enabled'])
    
    def set_volume(self, volume_type: str, volume: float):
        """Установка громкости"""
        if volume_type in ['music_volume', 'sfx_volume']:
            self.set_setting(volume_type, max(0.0, min(1.0, volume)))
    
    def create_settings_screen(self):
        """Создание экрана настроек"""
        settings_elements = []
        
        # Заголовок
        title = self.create_text(
            "SETTINGS",
            position=(0, 0, 0.4),
            scale=0.15,
            color=(1, 1, 0, 1),
            element_id="settings_title"
        )
        settings_elements.append(title)
        
        # Качество графики
        graphics_text = self.create_text(
            f"Graphics: {self.game_settings['graphics_quality']}",
            position=(0, 0, 0.1),
            scale=0.08,
            color=(1, 1, 1, 1),
            element_id="graphics_text"
        )
        settings_elements.append(graphics_text)
        
        # Звук
        sound_text = self.create_text(
            f"Sound: {'ON' if self.game_settings['sound_enabled'] else 'OFF'}",
            position=(0, 0, -0.05),
            scale=0.08,
            color=(1, 1, 1, 1),
            element_id="sound_text"
        )
        settings_elements.append(sound_text)
        
        return settings_elements
    
    def destroy(self) -> bool:
        """Уничтожение системы UI"""
        try:
            logger.info("Уничтожение объединенной системы UI...")
            
            # Остановка если запущена
            if self.system_state == LifecycleState.RUNNING:
                self.stop()
            
            # Уничтожение всех элементов
            for element in self.elements.values():
                if element.panda3d_node:
                    element.panda3d_node.destroy()
            
            self.elements.clear()
            self.element_hierarchy.clear()
            self.hud_elements.clear()
            self.menu_elements.clear()
            self.dialog_elements.clear()
            
            self.system_state = LifecycleState.DESTROYED
            logger.info("Объединенная система UI уничтожена")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения системы UI: {e}")
            return False
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'component_id': self.component_id,
            'state': self.system_state.value,
            'theme': self.active_theme.value,
            'stats': self.stats.copy(),
            'total_elements': len(self.elements),
            'settings': self.settings.copy()
        }
