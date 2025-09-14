#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .base_screen import BaseScreen

class SettingsScreen(BaseScreen):
    """Экран настроек"""
    
    def __init__(self, game):
        super().__init__(game)
        self.graphics_quality = "Medium"
        self.sound_enabled = True
        
    def enter(self):
        """Вход в состояние настроек"""
        self.create_background(0.9)
        self.create_title("SETTINGS", (0, 0.4), 0.15, (1, 1, 0, 1))
        
        # Кнопки настроек
        self.create_button(f"Graphics: {self.graphics_quality}", self.toggle_graphics, (0, 0, 0.1))
        self.create_button(f"Sound: {'ON' if self.sound_enabled else 'OFF'}", self.toggle_sound, (0, 0, -0.05))
        self.create_button("Controls", self.show_controls, (0, 0, -0.2))
        self.create_button("Back", self.go_back, (0, 0, -0.35))
        
    def toggle_graphics(self):
        """Переключение качества графики"""
        qualities = ["Low", "Medium", "High", "Ultra"]
        current_index = qualities.index(self.graphics_quality)
        next_index = (current_index + 1) % len(qualities)
        self.graphics_quality = qualities[next_index]
        
        # Обновляем кнопку
        if hasattr(self, 'frame') and self.frame:
            # Удаляем старую кнопку и создаем новую
            for element in self.elements[:]:
                if hasattr(element, 'getText') and "Graphics:" in str(element.getText()):
                    element.destroy()
                    self.elements.remove(element)
            
            # Создаем новую кнопку
            self.create_button(f"Graphics: {self.graphics_quality}", self.toggle_graphics, (0, 0, 0.1))
        
        print(f"Graphics quality set to: {self.graphics_quality}")
        
    def toggle_sound(self):
        """Переключение звука"""
        self.sound_enabled = not self.sound_enabled
        
        # Обновляем кнопку
        if hasattr(self, 'frame') and self.frame:
            # Удаляем старую кнопку и создаем новую
            for element in self.elements[:]:
                if hasattr(element, 'getText') and "Sound:" in str(element.getText()):
                    element.destroy()
                    self.elements.remove(element)
            
            # Создаем новую кнопку
            self.create_button(f"Sound: {'ON' if self.sound_enabled else 'OFF'}", self.toggle_sound, (0, 0, -0.05))
        
        print(f"Sound {'enabled' if self.sound_enabled else 'disabled'}")
        
    def show_controls(self):
        """Показать управление"""
        print("Controls:")
        print("WASD - Movement")
        print("Mouse - Look around")
        print("ESC - Pause/Menu")
        print("Space - Jump")
        print("Shift - Run")
        
    def go_back(self):
        """Вернуться назад"""
        if hasattr(self.game, 'state_manager'):
            # Возвращаемся к стартовому экрану
            self.game.state_manager.change_state("start")
        else:
            print("State manager not available")
