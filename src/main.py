#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import logging
import time
from typing import Dict, Any

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('enhanced_game.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class EnhancedGame:
    """Улучшенная главная игра с правильным рендерингом"""
    
    def __init__(self):
        self.running = False
        self.render_system = None
        self.state_manager = None
        self.input_manager = None
        self.keys = {}
        self.is_paused = False
        self.pause_ui_elements = []
        
        # Panda3D компоненты
        self.showbase = None
        self.render = None
        self.cam = None
        self.aspect2d = None
        
        # Инициализация
        self._initialize_panda3d()
        self._initialize_systems()
        self._register_states()
        
    def _initialize_panda3d(self):
        """Инициализация Panda3D"""
        try:
            from direct.showbase.ShowBase import ShowBase
            from panda3d.core import WindowProperties
            
            logger.info("Инициализация Panda3D...")
            
            # Создаем базовое окно
            self.showbase = ShowBase()
            
            # Настраиваем свойства окна
            props = WindowProperties()
            props.setTitle("AI-EVOLVE Enhanced Edition")
            props.setSize(1280, 720)
            props.setFullscreen(False)
            props.setCursorHidden(False)
            
            # Применяем свойства
            self.showbase.win.requestProperties(props)
            
            # Получаем основные компоненты
            self.render = self.showbase.render
            self.cam = self.showbase.cam
            self.aspect2d = self.showbase.aspect2d
            
            # Настройка камеры
            self.cam.setPos(10, -10, 8)
            self.cam.lookAt(0, 0, 0)
            
            logger.info("Panda3D инициализирован успешно")
            
        except Exception as e:
            logger.error(f"Ошибка инициализации Panda3D: {e}")
            raise
            
    def _initialize_systems(self):
        """Инициализация игровых систем"""
        try:
            # Инициализируем систему рендеринга
            from src.systems.rendering.render_system import RenderSystem
            self.render_system = RenderSystem(self)
            
            # Инициализируем менеджер состояний
            from src.core.game_state_manager import EnhancedStateManager
            self.state_manager = EnhancedStateManager(self)
            
            # Инициализируем систему частиц
            from src.systems.particle_system import ParticleSystem
            self.particle_system = ParticleSystem(self)
            self.particle_system.initialize()
            
            # Инициализируем продвинутую систему освещения
            from src.systems.advanced_lighting import AdvancedLighting
            self.lighting_system = AdvancedLighting(self)
            self.lighting_system.initialize()
            
            # Инициализируем аудио систему
            from src.systems.audio_system import AudioSystem
            self.audio_system = AudioSystem(self)
            self.audio_system.initialize()
            
            # Инициализируем систему оптимизации
            from src.systems.performance_optimizer import PerformanceOptimizer
            self.performance_optimizer = PerformanceOptimizer(self)
            self.performance_optimizer.initialize()
            
            # Инициализируем менеджер ввода
            self._setup_input()
            
            logger.info("Игровые системы инициализированы")
            
        except Exception as e:
            logger.error(f"Ошибка инициализации систем: {e}")
            raise
            
    def _setup_input(self):
        """Настройка системы ввода"""
        try:
            # Настраиваем обработку клавиатуры
            # ESC теперь открывает/закрывает меню паузы, а не мгновенно завершает игру.
            self.showbase.accept("escape", self._toggle_pause)
            # Отдельная клавиша для полного выхода из игры (например, Ctrl+Q можно добавить позже).
            self.showbase.accept("p", self._toggle_pause)
            
            # Настраиваем отслеживание клавиш
            self.showbase.accept("w", self._key_down, ["w"])
            self.showbase.accept("w-up", self._key_up, ["w"])
            self.showbase.accept("s", self._key_down, ["s"])
            self.showbase.accept("s-up", self._key_up, ["s"])
            self.showbase.accept("a", self._key_down, ["a"])
            self.showbase.accept("a-up", self._key_up, ["a"])
            self.showbase.accept("d", self._key_down, ["d"])
            self.showbase.accept("d-up", self._key_up, ["d"])
            self.showbase.accept("space", self._key_down, ["space"])
            self.showbase.accept("space-up", self._key_up, ["space"])
            
            logger.info("Система ввода настроена")
            
        except Exception as e:
            logger.error(f"Ошибка настройки ввода: {e}")
            
    def _key_down(self, key):
        """Обработка нажатия клавиши"""
        self.keys[key] = True
        
        # Обработка клавиши ESC для паузы
        if key == 'escape':
            self._toggle_pause()
        
    def _key_up(self, key):
        """Обработка отпускания клавиши"""
        self.keys[key] = False
        
    def _register_states(self):
        """Регистрация состояний игры"""
        try:
            from src.ui.start_screen import StartScreen
            from src.ui.death_screen import DeathScreen
            from src.scenes.main_game_scene import EnhancedGameScene
            
            # Регистрируем состояния
            self.state_manager.register_state("start", StartScreen)
            self.state_manager.register_state("game", EnhancedGameScene)
            self.state_manager.register_state("death", DeathScreen)
            
            # Пауза и настройки теперь обрабатываются через UnifiedUISystem
            # Добавляем методы для работы с UI системой
            self._setup_ui_handlers()
            
            logger.info("Состояния игры зарегистрированы")
            
        except Exception as e:
            logger.error(f"Ошибка регистрации состояний: {e}")
            raise
    
    def _setup_ui_handlers(self):
        """Настройка обработчиков UI"""
        try:
            # Получаем UnifiedUISystem из master_integrator
            if hasattr(self, 'master_integrator') and self.master_integrator:
                ui_system = self.master_integrator.get_system('unified_ui_system')
                if ui_system:
                    # Добавляем методы для паузы и настроек
                    self.show_pause_menu = lambda: self._show_pause_menu(ui_system)
                    self.show_settings = lambda: self._show_settings(ui_system)
                    logger.info("UI обработчики настроены")
        except Exception as e:
            logger.error(f"Ошибка настройки UI обработчиков: {e}")
    
    def _show_pause_menu(self, ui_system):
        """Показать меню паузы"""
        try:
            # Создаем элементы паузы через UnifiedUISystem
            pause_elements = ui_system.create_text(
                "PAUSED",
                position=(0, 0, 0.3),
                scale=0.15,
                color=(1, 1, 0, 1),
                element_id="pause_title"
            )
            logger.info("Меню паузы показано")
        except Exception as e:
            logger.error(f"Ошибка показа меню паузы: {e}")
    
    def _show_settings(self, ui_system):
        """Показать настройки"""
        try:
            # Создаем экран настроек через UnifiedUISystem
            settings_elements = ui_system.create_settings_screen()
            logger.info("Настройки показаны")
        except Exception as e:
            logger.error(f"Ошибка показа настроек: {e}")
    
    def _toggle_pause(self):
        """Переключение паузы"""
        try:
            # Пауза доступна только из игрового состояния.
            if not self.state_manager:
                return
            current_state = self.state_manager.get_current_state_name()
            if current_state != "game":
                return

            if self.is_paused:
                self._resume_game()
            else:
                self._pause_game()
        except Exception as e:
            logger.error(f"Ошибка переключения паузы: {e}")
    
    def _pause_game(self):
        """Поставить игру на паузу"""
        try:
            self.is_paused = True
            logger.info("Игра поставлена на паузу")
            
            # Создаем меню паузы
            self._create_pause_menu()
            
        except Exception as e:
            logger.error(f"Ошибка постановки на паузу: {e}")
    
    def _resume_game(self):
        """Возобновить игру"""
        try:
            self.is_paused = False
            logger.info("Игра возобновлена")
            
            # Удаляем меню паузы
            self._remove_pause_menu()
            
        except Exception as e:
            logger.error(f"Ошибка возобновления игры: {e}")
    
    def _create_pause_menu(self):
        """Создание меню паузы"""
        try:
            from direct.gui.OnscreenText import OnscreenText
            from direct.gui.DirectButton import DirectButton
            from direct.gui.DirectFrame import DirectFrame
            from panda3d.core import TextNode
            
            # Фон паузы
            pause_bg = DirectFrame(
                frameColor=(0, 0, 0, 0.7),
                frameSize=(-1, 1, -1, 1),
                pos=(0, 0, 0),
                parent=self.aspect2d
            )
            pause_bg.show()
            self.pause_ui_elements.append(pause_bg)
            
            # Заголовок паузы
            pause_title = OnscreenText(
                text="PAUSED",
                pos=(0, 0.3),
                scale=0.15,
                fg=(1, 1, 0, 1),
                parent=self.aspect2d,
                align=TextNode.ACenter
            )
            pause_title.show()
            self.pause_ui_elements.append(pause_title)
            
            # Кнопка возобновления
            resume_button = DirectButton(
                text="Resume",
                scale=0.1,
                pos=(0, 0, 0),
                command=self._resume_game,
                parent=self.aspect2d,
                frameColor=(0.3, 0.3, 0.3, 0.8),
                text_fg=(1, 1, 1, 1),
                frameSize=(-1, 1, -0.3, 0.3)
            )
            resume_button.show()
            self.pause_ui_elements.append(resume_button)
            
            # Кнопка настроек
            settings_button = DirectButton(
                text="Settings",
                scale=0.1,
                pos=(0, 0, -0.15),
                command=self._show_settings_menu,
                parent=self.aspect2d,
                frameColor=(0.3, 0.3, 0.3, 0.8),
                text_fg=(1, 1, 1, 1),
                frameSize=(-1, 1, -0.3, 0.3)
            )
            settings_button.show()
            self.pause_ui_elements.append(settings_button)
            
            # Кнопка выхода в меню
            menu_button = DirectButton(
                text="Main Menu",
                scale=0.1,
                pos=(0, 0, -0.3),
                command=self._return_to_menu,
                parent=self.aspect2d,
                frameColor=(0.3, 0.3, 0.3, 0.8),
                text_fg=(1, 1, 1, 1),
                frameSize=(-1, 1, -0.3, 0.3)
            )
            menu_button.show()
            self.pause_ui_elements.append(menu_button)
            
            logger.info("Меню паузы создано и показано")
            
        except Exception as e:
            logger.error(f"Ошибка создания меню паузы: {e}")
    
    def _remove_pause_menu(self):
        """Удаление меню паузы"""
        try:
            for element in self.pause_ui_elements:
                if hasattr(element, 'destroy'):
                    element.destroy()
            self.pause_ui_elements.clear()
        except Exception as e:
            logger.error(f"Ошибка удаления меню паузы: {e}")
    
    def _show_settings_menu(self):
        """Показать меню настроек"""
        try:
            # Создаем простое меню настроек
            self._create_settings_menu()
        except Exception as e:
            logger.error(f"Ошибка показа настроек: {e}")
    
    def _create_settings_menu(self):
        """Создание меню настроек"""
        try:
            from direct.gui.OnscreenText import OnscreenText
            from direct.gui.DirectButton import DirectButton
            from panda3d.core import TextNode
            
            # Фон настроек
            settings_bg = OnscreenText(
                text="",
                pos=(0, 0),
                scale=1.0,
                fg=(0, 0, 0, 0.7),
                parent=self.aspect2d
            )
            self.pause_ui_elements.append(settings_bg)
            
            # Заголовок настроек
            settings_title = OnscreenText(
                text="SETTINGS",
                pos=(0, 0.3),
                scale=0.15,
                fg=(1, 1, 0, 1),
                parent=self.aspect2d,
                align=TextNode.ACenter
            )
            self.pause_ui_elements.append(settings_title)
            
            # Кнопка графики
            graphics_button = DirectButton(
                text="Graphics: High",
                scale=0.1,
                pos=(0, 0, 0.1),
                command=self._toggle_graphics,
                parent=self.aspect2d
            )
            self.pause_ui_elements.append(graphics_button)
            
            # Кнопка звука
            sound_button = DirectButton(
                text="Sound: On",
                scale=0.1,
                pos=(0, 0, -0.05),
                command=self._toggle_sound,
                parent=self.aspect2d
            )
            self.pause_ui_elements.append(sound_button)
            
            # Кнопка возврата
            back_button = DirectButton(
                text="Back",
                scale=0.1,
                pos=(0, 0, -0.2),
                command=self._return_to_pause,
                parent=self.aspect2d
            )
            self.pause_ui_elements.append(back_button)
            
        except Exception as e:
            logger.error(f"Ошибка создания меню настроек: {e}")
    
    def _toggle_graphics(self):
        """Переключение графики"""
        print("Graphics settings toggled")
    
    def _toggle_sound(self):
        """Переключение звука"""
        print("Sound settings toggled")
    
    def _return_to_pause(self):
        """Возврат к меню паузы"""
        self._remove_pause_menu()
        self._create_pause_menu()
    
    def _return_to_menu(self):
        """Вернуться в главное меню"""
        try:
            self._remove_pause_menu()
            self.is_paused = False
            if hasattr(self, 'state_manager'):
                self.state_manager.change_state("start")
        except Exception as e:
            logger.error(f"Ошибка возврата в меню: {e}")
            
    def start(self):
        """Запуск игры"""
        try:
            logger.info("=" * 60)
            logger.info("🚀 ЗАПУСК УЛУЧШЕННОЙ ИГРЫ AI-EVOLVE")
            logger.info("=" * 60)
            
            # Переходим в стартовое состояние
            if not self.state_manager.change_state("start"):
                raise Exception("Не удалось перейти в стартовое состояние")
                
            # Запускаем главный цикл
            self.running = True
            self._main_loop()
            
        except Exception as e:
            logger.error(f"Ошибка запуска игры: {e}")
            raise
            
    def _main_loop(self):
        """Главный игровой цикл"""
        try:
            last_time = time.time()
            
            while self.running:
                # Вычисляем время кадра
                current_time = time.time()
                dt = current_time - last_time
                last_time = current_time
                
                # Ограничиваем время кадра
                if dt > 0.1:
                    dt = 0.1
                    
                # Обновляем игру только если не на паузе
                if not self.is_paused:
                    self.update(dt)
                
                # Обрабатываем ввод (всегда, даже на паузе)
                self.handle_input()
                
                # Рендерим кадр
                self.render_frame()
                
                # Проверяем события Panda3D
                self.showbase.taskMgr.step()
                
        except Exception as e:
            logger.error(f"Ошибка в главном цикле: {e}")
            raise
            
    def update(self, dt: float):
        """Обновление игры"""
        try:
            # Обновляем менеджер состояний
            if self.state_manager:
                self.state_manager.update(dt)
                
            # Обновляем систему частиц
            if hasattr(self, 'particle_system'):
                self.particle_system.update(dt)
                
            # Обновляем систему освещения
            if hasattr(self, 'lighting_system'):
                self.lighting_system.update(dt)
                
            # Обновляем систему оптимизации
            if hasattr(self, 'performance_optimizer'):
                # Система оптимизации обновляется автоматически через задачи
                pass
                
        except Exception as e:
            logger.error(f"Ошибка обновления игры: {e}")
            
    def handle_input(self):
        """Обработка ввода"""
        try:
            # Обрабатываем ввод через менеджер состояний
            if self.state_manager:
                self.state_manager.handle_input(self.keys)
                
        except Exception as e:
            logger.error(f"Ошибка обработки ввода: {e}")
            
    def render_frame(self):
        """Рендеринг кадра"""
        try:
            # Panda3D автоматически рендерит кадр
            pass
            
        except Exception as e:
            logger.error(f"Ошибка рендеринга: {e}")
            
    def toggle_pause(self):
        """Переключение паузы"""
        try:
            current_state = self.state_manager.get_current_state_name()
            
            if current_state == "game":
                # Переходим в паузу
                self.state_manager.push_state("pause")
            elif current_state == "pause":
                # Возвращаемся в игру
                self.state_manager.pop_state()
                
        except Exception as e:
            logger.error(f"Ошибка переключения паузы: {e}")
            
    def quit(self):
        """Выход из игры"""
        try:
            logger.info("Выход из игры...")
            self.running = False
            
            # Очищаем ресурсы
            self.cleanup()
            
        except Exception as e:
            logger.error(f"Ошибка выхода из игры: {e}")
            
    def cleanup(self):
        """Очистка ресурсов"""
        try:
            # Очищаем менеджер состояний
            if self.state_manager and self.state_manager.current_state:
                self.state_manager.current_state.exit()
                
            # Очищаем систему рендеринга
            if self.render_system:
                self.render_system.cleanup()
                
            # Очищаем систему частиц
            if hasattr(self, 'particle_system'):
                self.particle_system.destroy()
                
            # Очищаем систему освещения
            if hasattr(self, 'lighting_system'):
                self.lighting_system.destroy()
                
            # Очищаем аудио систему
            if hasattr(self, 'audio_system'):
                self.audio_system.destroy()
                
            # Очищаем систему оптимизации
            if hasattr(self, 'performance_optimizer'):
                self.performance_optimizer.destroy()
                
            logger.info("Ресурсы очищены")
            
        except Exception as e:
            logger.error(f"Ошибка очистки ресурсов: {e}")

def main():
    """Главная функция"""
    try:
        logger.info("=" * 60)
        logger.info("🎮 ЗАПУСК AI-EVOLVE ENHANCED EDITION")
        logger.info("=" * 60)
        
        # Создаем игру
        game = EnhancedGame()
        
        # Запускаем игру
        game.start()
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        import traceback
        logger.error(f"Детали ошибки: {traceback.format_exc()}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
