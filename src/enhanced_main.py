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
            from src.core.enhanced_state_manager import EnhancedStateManager
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
            self.showbase.accept("escape", self.quit)
            self.showbase.accept("p", self.toggle_pause)
            
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
        
    def _key_up(self, key):
        """Обработка отпускания клавиши"""
        self.keys[key] = False
        
    def _register_states(self):
        """Регистрация состояний игры"""
        try:
            from src.ui.simple_enhanced_start_screen import SimpleEnhancedStartScreen
            from src.ui.pause_screen import PauseScreen
            from src.ui.settings_screen import SettingsScreen
            from src.ui.death_screen import DeathScreen
            from src.scenes.enhanced_game_scene import EnhancedGameScene
            
            # Регистрируем состояния
            self.state_manager.register_state("start", SimpleEnhancedStartScreen)
            self.state_manager.register_state("game", EnhancedGameScene)
            self.state_manager.register_state("pause", PauseScreen)
            self.state_manager.register_state("settings", SettingsScreen)
            self.state_manager.register_state("death", DeathScreen)
            
            logger.info("Состояния игры зарегистрированы")
            
        except Exception as e:
            logger.error(f"Ошибка регистрации состояний: {e}")
            raise
            
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
                    
                # Обновляем игру
                self.update(dt)
                
                # Обрабатываем ввод
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
