#!/usr/bin/env python3
"""Game Scene - Main Gameplay"""

import logging
from src.scenes.scene_manager import Scene

logger = logging.getLogger(__name__)


class GameScene(Scene):
    """Основная игровая сцена"""
    
    def __init__(self):
        super().__init__("game_world")
        self.game_instance = None
        
    def initialize(self) -> bool:
        logger.info("Инициализация GameScene")
        return super().initialize()
    
    def start(self) -> bool:
        logger.info("Запуск GameScene")
        if not super().start():
            return False
        
        # Получаем ссылку на игру из менеджера сцен
        if self.scene_manager and hasattr(self.scene_manager, 'game'):
            self.game_instance = self.scene_manager.game
        
        self._setup_game()
        return True
    
    def update(self, delta_time: float) -> None:
        """Обновление игровой логики"""
        if self.game_instance and hasattr(self.game_instance, 'scene'):
            self.game_instance.scene.update(delta_time)
    
    def _setup_game(self):
        """Настройка игры"""
        logger.debug("Настройка игровой сцены")
    
    def handle_event(self, event: any) -> None:
        """Обработка событий ввода"""
        if self.game_instance and hasattr(self.game_instance, 'scene'):
            self.game_instance.scene.handle_input(event)
