#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .base_screen import BaseScreen

class DeathScreen(BaseScreen):
    """Экран смерти"""
    
    def __init__(self, game):
        super().__init__(game)
        
    def enter(self):
        """Вход в состояние смерти"""
        self.create_background(0.9)
        self.create_title("GAME OVER", (0, 0.3), 0.15, (1, 0, 0, 1))
        self.create_subtitle("You have died", (0, 0.1), 0.08, (0.8, 0.8, 0.8, 1))
        
        # Кнопки
        self.create_button("Restart", self.restart_game, (0, 0, -0.1))
        self.create_button("Main Menu", self.return_to_menu, (0, 0, -0.25))
        self.create_button("Exit", self.exit_game, (0, 0, -0.4), 
                          frame_color=(0.8, 0.2, 0.2, 1))
        
    def restart_game(self):
        """Перезапустить игру"""
        if hasattr(self.game, 'state_manager'):
            self.game.state_manager.change_state("game")
        else:
            print("State manager not available")
        
    def return_to_menu(self):
        """Вернуться в главное меню"""
        if hasattr(self.game, 'state_manager'):
            self.game.state_manager.change_state("start")
        else:
            print("State manager not available")
        
    def exit_game(self):
        """Выход из игры"""
        if hasattr(self.game, 'quit'):
            self.game.quit()
        else:
            print("Exit not available")