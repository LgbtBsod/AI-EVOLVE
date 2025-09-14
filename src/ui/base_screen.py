#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from direct.gui.DirectGui import DirectFrame, DirectButton, OnscreenText
from panda3d.core import LVector4

class BaseScreen:
    """Базовый класс для всех экранов"""
    
    def __init__(self, game):
        self.game = game
        self.frame = None
        self.elements = []
        
    def create_background(self, alpha=0.8):
        """Создание фона экрана"""
        self.frame = DirectFrame(
            frameColor=(0, 0, 0, alpha),
            frameSize=(-1, 1, -1, 1),
            parent=self.game.aspect2d
        )
        self.elements.append(self.frame)
        
    def create_title(self, text, pos=(0, 0.7), scale=0.15, color=(1, 1, 1, 1)):
        """Создание заголовка"""
        title = OnscreenText(
            text=text,
            pos=pos,
            scale=scale,
            fg=color,
            parent=self.frame
        )
        self.elements.append(title)
        return title
        
    def create_subtitle(self, text, pos=(0, 0.5), scale=0.08, color=(0.8, 0.8, 0.8, 1)):
        """Создание подзаголовка"""
        subtitle = OnscreenText(
            text=text,
            pos=pos,
            scale=scale,
            fg=color,
            parent=self.frame
        )
        self.elements.append(subtitle)
        return subtitle
        
    def create_button(self, text, command, pos=(0, 0, 0), scale=0.1, 
                     frame_color=(0.8, 0.8, 0.8, 1), text_color=(0, 0, 0, 1)):
        """Создание кнопки"""
        button = DirectButton(
            text=text,
            scale=scale,
            pos=pos,
            command=command,
            parent=self.frame,
            frameColor=frame_color,
            text_fg=text_color,
            text_scale=0.7,
            frameSize=(-2, 2, -0.5, 0.5)
        )
        self.elements.append(button)
        return button
        
    def destroy(self):
        """Уничтожение всех элементов экрана"""
        for element in self.elements:
            if hasattr(element, 'destroy'):
                element.destroy()
            elif hasattr(element, 'removeNode'):
                element.removeNode()
        self.elements.clear()
        
    def enter(self):
        """Вход на экран (переопределяется в наследниках)"""
        pass
        
    def exit(self):
        """Выход с экрана"""
        self.destroy()
