#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import time
from direct.gui.DirectGui import OnscreenText
from panda3d.core import TextNode

from .animated_menu import AnimatedMenu
from .base_screen import BaseScreen

class EnhancedStartScreen(BaseScreen):
    """Улучшенный стартовый экран с анимациями"""
    
    def __init__(self, game):
        super().__init__(game)
        self.animated_menu = None
        self.logo_animation = None
        
    def enter(self):
        """Вход в состояние стартового экрана"""
        # Создаем анимированное меню
        self.animated_menu = AnimatedMenu(self.game)
        self.animated_menu.create_animated_background(0.9, (0.05, 0.05, 0.15, 0.9))
        
        # Создаем анимированный заголовок
        self.animated_menu.create_animated_title(
            "AI-EVOLVE Enhanced Edition", 
            (0, 0.3), 
            0.15, 
            (1, 1, 1, 1)
        )
        
        # Создаем подзаголовок
        self.animated_menu.create_animated_title(
            "Isometric Adventure", 
            (0, 0.1), 
            0.08, 
            (0.8, 0.8, 0.8, 1)
        )
        
        # Создаем анимированные кнопки
        self.new_game_button = self.animated_menu.create_animated_button(
            "New Game", 
            self.start_new_game, 
            (0, 0, -0.1),
            hover_color=(0.2, 0.8, 0.2, 1),
            click_color=(0.1, 0.6, 0.1, 1)
        )
        
        self.settings_button = self.animated_menu.create_animated_button(
            "Settings", 
            self.open_settings, 
            (0, 0, -0.25),
            hover_color=(0.2, 0.2, 0.8, 1),
            click_color=(0.1, 0.1, 0.6, 1)
        )
        
        self.exit_button = self.animated_menu.create_animated_button(
            "Exit", 
            self.exit_game, 
            (0, 0, -0.4),
            frame_color=(0.8, 0.2, 0.2, 1),
            hover_color=(1, 0.3, 0.3, 1),
            click_color=(0.6, 0.1, 0.1, 1)
        )
        
        # Создаем логотип с анимацией
        self._create_animated_logo()
        
        # Создаем информационную панель
        self._create_info_panel()
        
        # Показываем меню с анимацией
        self.animated_menu.show()
        
    def _create_animated_logo(self):
        """Создание анимированного логотипа"""
        # Создаем логотип как набор кубов
        self.logo = self.game.render.attachNewNode("logo")
        
        # Основной куб
        self._create_logo_cube(self.logo, "main", 0, 0, 0, 0.3, (0, 0.8, 1, 1))
        
        # Вращающиеся кубы вокруг
        for i in range(6):
            angle = i * 60
            x = math.cos(math.radians(angle)) * 0.5
            y = math.sin(math.radians(angle)) * 0.5
            self._create_logo_cube(self.logo, f"orbit_{i}", x, y, 0, 0.1, (1, 1, 1, 0.8))
        
        # Позиционируем логотип
        self.logo.setPos(0, 0, 0.5)
        self.logo.setScale(2)
        
        # Запускаем анимацию логотипа
        self._start_logo_animation()
        
    def _create_logo_cube(self, parent, name, x, y, z, size, color):
        """Создание куба для логотипа"""
        cube = parent.attachNewNode(name)
        
        # Создаем куб из 6 граней
        from panda3d.core import CardMaker
        
        # Передняя грань
        cm = CardMaker(f"{name}_front")
        cm.setFrame(-size/2, size/2, -size/2, size/2)
        front = cube.attachNewNode(cm.generate())
        front.setPos(0, size/2, 0)
        front.setColor(*color)
        
        # Задняя грань
        cm = CardMaker(f"{name}_back")
        cm.setFrame(-size/2, size/2, -size/2, size/2)
        back = cube.attachNewNode(cm.generate())
        back.setPos(0, -size/2, 0)
        back.setHpr(0, 180, 0)
        back.setColor(color[0] * 0.7, color[1] * 0.7, color[2] * 0.7, color[3])
        
        # Левая грань
        cm = CardMaker(f"{name}_left")
        cm.setFrame(-size/2, size/2, -size/2, size/2)
        left = cube.attachNewNode(cm.generate())
        left.setPos(-size/2, 0, 0)
        left.setHpr(0, -90, 0)
        left.setColor(color[0] * 0.8, color[1] * 0.8, color[2] * 0.8, color[3])
        
        # Правая грань
        cm = CardMaker(f"{name}_right")
        cm.setFrame(-size/2, size/2, -size/2, size/2)
        right = cube.attachNewNode(cm.generate())
        right.setPos(size/2, 0, 0)
        right.setHpr(0, 90, 0)
        right.setColor(color[0] * 0.6, color[1] * 0.6, color[2] * 0.6, color[3])
        
        # Верхняя грань
        cm = CardMaker(f"{name}_top")
        cm.setFrame(-size/2, size/2, -size/2, size/2)
        top = cube.attachNewNode(cm.generate())
        top.setPos(0, 0, size/2)
        top.setHpr(0, 0, -90)
        top.setColor(color[0] * 1.2, color[1] * 1.2, color[2] * 1.2, color[3])
        
        # Нижняя грань
        cm = CardMaker(f"{name}_bottom")
        cm.setFrame(-size/2, size/2, -size/2, size/2)
        bottom = cube.attachNewNode(cm.generate())
        bottom.setPos(0, 0, -size/2)
        bottom.setHpr(0, 0, 90)
        bottom.setColor(color[0] * 0.4, color[1] * 0.4, color[2] * 0.4, color[3])
        
        cube.setPos(x, y, z)
        return cube
        
    def _start_logo_animation(self):
        """Запуск анимации логотипа"""
        def animate_logo(task):
            current_time = time.time()
            
            # Вращение основного куба
            self.logo.setHpr(current_time * 30, current_time * 45, current_time * 15)
            
            # Вращение орбитальных кубов
            for i in range(6):
                orbit_cube = self.logo.find(f"orbit_{i}")
                if orbit_cube:
                    orbit_angle = current_time * 60 + i * 60
                    orbit_cube.setHpr(orbit_angle, orbit_angle * 0.5, orbit_angle * 0.3)
            
            # Пульсация масштаба
            scale_factor = 1.0 + math.sin(current_time * 2) * 0.1
            self.logo.setScale(2 * scale_factor)
            
            return Task.cont
            
        self.game.showbase.taskMgr.add(animate_logo, "logo_animation")
        
    def _create_info_panel(self):
        """Создание информационной панели"""
        # Панель с информацией о версии
        info_text = f"Version 2.0 Enhanced\nPanda3D Engine\nFPS: {self.game.showbase.getAverageFrameRate():.1f}"
        
        self.info_label = OnscreenText(
            text=info_text,
            pos=(-0.8, -0.8),
            scale=0.04,
            fg=(0.6, 0.6, 0.6, 1),
            parent=self.animated_menu.background,
            align=TextNode.ALeft
        )
        self.elements.append(self.info_label)
        
        # Анимация обновления FPS
        self._start_fps_animation()
        
    def _start_fps_animation(self):
        """Запуск анимации обновления FPS"""
        def update_fps(task):
            if hasattr(self, 'info_label'):
                fps = self.game.showbase.getAverageFrameRate()
                info_text = f"Version 2.0 Enhanced\nPanda3D Engine\nFPS: {fps:.1f}"
                self.info_label.setText(info_text)
            return Task.cont
            
        self.game.showbase.taskMgr.add(update_fps, "fps_animation")
        
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
        if hasattr(self, 'logo'):
            self.game.showbase.taskMgr.remove("logo_animation")
        self.game.showbase.taskMgr.remove("fps_animation")
        
        # Уничтожаем логотип
        if hasattr(self, 'logo'):
            self.logo.removeNode()
            
        # Уничтожаем анимированное меню
        if self.animated_menu:
            self.animated_menu.destroy()
            
        # Уничтожаем базовые элементы
        super().exit()
