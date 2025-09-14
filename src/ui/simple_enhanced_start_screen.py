#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import time
from direct.gui.DirectGui import DirectFrame, DirectButton, OnscreenText
from direct.task import Task
from panda3d.core import TextNode

from .base_screen import BaseScreen

class SimpleEnhancedStartScreen(BaseScreen):
    """Упрощенный улучшенный стартовый экран"""
    
    def __init__(self, game):
        super().__init__(game)
        
    def enter(self):
        """Вход в состояние стартового экрана"""
        self.create_background(0.9)
        
        # Создаем заголовок с эффектом
        self.create_title("AI-EVOLVE Enhanced Edition", (0, 0.3), 0.15, (1, 1, 1, 1))
        self.create_subtitle("Isometric Adventure", (0, 0.1), 0.08, (0.8, 0.8, 0.8, 1))
        
        # Создаем кнопки с улучшенным дизайном
        self.create_button("New Game", self.start_new_game, (0, 0, -0.1), 
                          frame_color=(0.2, 0.8, 0.2, 1), text_color=(1, 1, 1, 1))
        self.create_button("Settings", self.open_settings, (0, 0, -0.25),
                          frame_color=(0.2, 0.2, 0.8, 1), text_color=(1, 1, 1, 1))
        self.create_button("Exit", self.exit_game, (0, 0, -0.4),
                          frame_color=(0.8, 0.2, 0.2, 1), text_color=(1, 1, 1, 1))
        
        # Создаем информационную панель
        self._create_info_panel()
        
        # Запускаем простые анимации
        self._start_simple_animations()
        
    def _create_info_panel(self):
        """Создание информационной панели"""
        # Панель с информацией о версии
        try:
            fps = self.game.showbase.getAverageFrameRate()
        except:
            fps = 60.0
        info_text = f"Version 2.0 Enhanced\nPanda3D Engine\nFPS: {fps:.1f}"
        
        self.info_label = OnscreenText(
            text=info_text,
            pos=(-0.8, -0.8),
            scale=0.04,
            fg=(0.6, 0.6, 0.6, 1),
            parent=self.frame,
            align=TextNode.ALeft
        )
        self.elements.append(self.info_label)
        
        # Анимация обновления FPS
        self._start_fps_animation()
        
    def _start_fps_animation(self):
        """Запуск анимации обновления FPS"""
        def update_fps(task):
            if hasattr(self, 'info_label'):
                try:
                    fps = self.game.showbase.getAverageFrameRate()
                except:
                    fps = 60.0
                info_text = f"Version 2.0 Enhanced\nPanda3D Engine\nFPS: {fps:.1f}"
                self.info_label.setText(info_text)
            return Task.cont
            
        self.game.showbase.taskMgr.add(update_fps, "fps_animation")
        
    def _start_simple_animations(self):
        """Запуск простых анимаций"""
        def animate_title(task):
            current_time = time.time()
            
            # Простая пульсация заголовка
            scale_factor = 1.0 + math.sin(current_time * 2) * 0.05
            if hasattr(self, 'title'):
                self.title.setScale(0.15 * scale_factor)
                
            return Task.cont
            
        self.game.showbase.taskMgr.add(animate_title, "title_animation")
        
    def start_new_game(self):
        """Начать новую игру"""
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
        
    def exit_game(self):
        """Выход из игры"""
        if hasattr(self.game, 'quit'):
            self.game.quit()
        else:
            print("Exit not available")
            
    def exit(self):
        """Выход с экрана"""
        # Останавливаем анимации
        self.game.showbase.taskMgr.remove("fps_animation")
        self.game.showbase.taskMgr.remove("title_animation")
        
        # Уничтожаем базовые элементы
        super().exit()
