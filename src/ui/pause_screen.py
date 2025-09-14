#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .base_screen import BaseScreen

class PauseScreen(BaseScreen):
    """Экран паузы"""
    
    def __init__(self, game):
        super().__init__(game)
        
    def enter(self):
        """Вход в состояние паузы"""
        self.create_background(0.8)
        self.create_title("PAUSED", (0, 0.3), 0.15, (1, 1, 0, 1))
        
        # Кнопки
        self.create_button("Resume", self.resume_game, (0, 0, 0))
        self.create_button("Settings", self.open_settings, (0, 0, -0.15))
        self.create_button("Main Menu", self.return_to_menu, (0, 0, -0.3))
        
    def resume_game(self):
        """Продолжить игру"""
        if hasattr(self.game, 'state_manager'):
            self.game.state_manager.change_state("game")
        else:
            print("State manager not available")
        
    def open_settings(self):
        """Открыть настройки"""
        if hasattr(self.game, 'state_manager'):
            self.game.state_manager.change_state("settings")
        else:
            print("Settings not available")
        
    def return_to_menu(self):
        """Вернуться в главное меню"""
        if hasattr(self.game, 'state_manager'):
            self.game.state_manager.change_state("start")
        else:
            print("State manager not available")
