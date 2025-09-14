#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import math
from typing import List, Optional, Callable
from direct.gui.DirectGui import DirectFrame, DirectButton, OnscreenText, DirectLabel
from panda3d.core import LVector4, TextNode, CardMaker
from direct.task import Task

class AnimatedMenu:
    """Анимированное меню с плавными переходами"""
    
    def __init__(self, game):
        self.game = game
        self.elements = []
        self.animations = []
        self.is_visible = False
        self.animation_speed = 1.0
        
    def create_animated_background(self, alpha=0.8, color=(0, 0, 0, 0.8)):
        """Создание анимированного фона"""
        # Основной фон
        self.background = DirectFrame(
            frameColor=color,
            frameSize=(-1, 1, -1, 1),
            parent=self.game.aspect2d
        )
        self.elements.append(self.background)
        
        # Анимированные частицы на фоне
        self._create_background_particles()
        
    def _create_background_particles(self):
        """Создание анимированных частиц на фоне"""
        self.particles = []
        
        # Создаем несколько частиц
        for i in range(20):
            particle = DirectFrame(
                frameColor=(1, 1, 1, 0.1),
                frameSize=(-0.01, 0.01, -0.01, 0.01),
                parent=self.background
            )
            
            # Случайная позиция
            x = (i % 10 - 5) * 0.2
            y = (i // 10 - 1) * 0.2
            particle.setPos(x, 0, y)
            
            self.particles.append(particle)
            
        # Запускаем анимацию частиц
        self._start_particle_animation()
        
    def _start_particle_animation(self):
        """Запуск анимации частиц"""
        def animate_particles(task):
            current_time = time.time()
            
            for i, particle in enumerate(self.particles):
                # Движение по синусоиде
                offset_x = math.sin(current_time * 0.5 + i * 0.5) * 0.1
                offset_y = math.cos(current_time * 0.3 + i * 0.3) * 0.1
                
                # Пульсация размера
                scale = 1.0 + math.sin(current_time * 2 + i) * 0.2
                
                # Обновляем позицию и размер
                pos = particle.getPos()
                particle.setPos(pos[0] + offset_x, pos[1], pos[2] + offset_y)
                particle.setScale(scale)
                
                # Обновляем прозрачность
                alpha = 0.1 + math.sin(current_time * 1.5 + i) * 0.05
                particle['frameColor'] = (1, 1, 1, alpha)
                
            return Task.cont
            
        self.game.showbase.taskMgr.add(animate_particles, "particle_animation")
        
    def create_animated_title(self, text, pos=(0, 0.7), scale=0.15, color=(1, 1, 1, 1)):
        """Создание анимированного заголовка"""
        # Основной текст
        self.title = OnscreenText(
            text=text,
            pos=pos,
            scale=scale,
            fg=color,
            parent=self.background,
            align=TextNode.ACenter
        )
        self.elements.append(self.title)
        
        # Эффект свечения
        self.title_glow = OnscreenText(
            text=text,
            pos=(pos[0] + 0.002, pos[1] - 0.002),
            scale=scale,
            fg=(0, 0.5, 1, 0.3),
            parent=self.background,
            align=TextNode.ACenter
        )
        self.elements.append(self.title_glow)
        
        # Запускаем анимацию заголовка
        self._start_title_animation()
        
    def _start_title_animation(self):
        """Запуск анимации заголовка"""
        def animate_title(task):
            current_time = time.time()
            
            # Пульсация масштаба
            scale_factor = 1.0 + math.sin(current_time * 2) * 0.05
            self.title.setScale(0.15 * scale_factor)
            self.title_glow.setScale(0.15 * scale_factor)
            
            # Эффект свечения
            glow_intensity = 0.3 + math.sin(current_time * 3) * 0.1
            from panda3d.core import LVector4
            glow_color = LVector4(0, 0.5, 1, glow_intensity)
            self.title_glow.setFg(glow_color)
            
            return Task.cont
            
        self.game.showbase.taskMgr.add(animate_title, "title_animation")
        
    def create_animated_button(self, text, command, pos=(0, 0, 0), scale=0.1, 
                             frame_color=(0.8, 0.8, 0.8, 1), text_color=(0, 0, 0, 1),
                             hover_color=(1, 1, 1, 1), click_color=(0.6, 0.6, 0.6, 1)):
        """Создание анимированной кнопки"""
        button = DirectButton(
            text=text,
            scale=scale,
            pos=pos,
            command=command,
            parent=self.background,
            frameColor=frame_color,
            text_fg=text_color,
            text_scale=0.7,
            frameSize=(-2, 2, -0.5, 0.5)
        )
        # Сразу показываем кнопку
        button.show()
        self.elements.append(button)
        return button
        
    def create_fade_in_animation(self, duration=1.0):
        """Создание анимации появления"""
        def fade_in(task):
            elapsed = task.time
            progress = min(elapsed / duration, 1.0)
            
            # Плавное появление
            alpha = progress
            self.background['frameColor'] = (0, 0, 0, 0.8 * alpha)
            
            # Анимация элементов
            for element in self.elements:
                if hasattr(element, 'setAlpha'):
                    element.setAlpha(alpha)
                elif hasattr(element, 'setColor'):
                    # Для OnscreenText используем setFg вместо setColor
                    if hasattr(element, 'setFg'):
                        # Получаем текущий цвет из fg параметра
                        current_fg = getattr(element, 'fg', (1, 1, 1, 1))
                        # setFg принимает LVector4 или tuple
                        from panda3d.core import LVector4
                        new_color = LVector4(current_fg[0], current_fg[1], current_fg[2], current_fg[3] * alpha)
                        element.setFg(new_color)
                    else:
                        # Для других элементов используем setColor
                        color = (1, 1, 1, 1)
                        element.setColor(color[0], color[1], color[2], color[3] * alpha)
            
            if progress >= 1.0:
                return Task.done
            return Task.cont
            
        self.game.showbase.taskMgr.add(fade_in, "fade_in_animation")
        
    def create_fade_out_animation(self, duration=0.5):
        """Создание анимации исчезновения"""
        def fade_out(task):
            elapsed = task.time
            progress = min(elapsed / duration, 1.0)
            
            # Плавное исчезновение
            alpha = 1.0 - progress
            self.background['frameColor'] = (0, 0, 0, 0.8 * alpha)
            
            # Анимация элементов
            for element in self.elements:
                if hasattr(element, 'setAlpha'):
                    element.setAlpha(alpha)
                elif hasattr(element, 'setColor'):
                    # Для OnscreenText используем setFg вместо setColor
                    if hasattr(element, 'setFg'):
                        # Получаем текущий цвет из fg параметра
                        current_fg = getattr(element, 'fg', (1, 1, 1, 1))
                        # setFg принимает LVector4 или tuple
                        from panda3d.core import LVector4
                        new_color = LVector4(current_fg[0], current_fg[1], current_fg[2], current_fg[3] * alpha)
                        element.setFg(new_color)
                    else:
                        # Для других элементов используем setColor
                        color = (1, 1, 1, 1)
                        element.setColor(color[0], color[1], color[2], color[3] * alpha)
            
            if progress >= 1.0:
                return Task.done
            return Task.cont
            
        self.game.showbase.taskMgr.add(fade_out, "fade_out_animation")
        
    def show(self):
        """Показать меню с анимацией"""
        if not self.is_visible:
            self.is_visible = True
            self.create_fade_in_animation()
            
    def hide(self):
        """Скрыть меню с анимацией"""
        if self.is_visible:
            self.is_visible = False
            self.create_fade_out_animation()
            
    def destroy(self):
        """Уничтожение меню"""
        # Останавливаем анимации
        self.game.showbase.taskMgr.remove("particle_animation")
        self.game.showbase.taskMgr.remove("title_animation")
        self.game.showbase.taskMgr.remove("fade_in_animation")
        self.game.showbase.taskMgr.remove("fade_out_animation")
        
        # Уничтожаем элементы
        for element in self.elements:
            if hasattr(element, 'destroy'):
                element.destroy()
            elif hasattr(element, 'removeNode'):
                element.removeNode()
        self.elements.clear()

class AnimatedButton(DirectButton):
    """Анимированная кнопка с эффектами наведения и нажатия"""
    
    def __init__(self, hover_color=(1, 1, 1, 1), click_color=(0.6, 0.6, 0.6, 1), **kwargs):
        super().__init__(**kwargs)
        
        self.hover_color = hover_color
        self.click_color = click_color
        self.original_color = self['frameColor']
        self.original_scale = self.getScale()
        
        # Привязываем события
        try:
            self.bind(DirectButton.ENTER, self._on_enter)
            self.bind(DirectButton.EXIT, self._on_exit)
            self.bind(DirectButton.B1PRESS, self._on_press)
            self.bind(DirectButton.B1RELEASE, self._on_release)
        except AttributeError:
            # Альтернативный способ привязки событий
            self.bind("enter", self._on_enter)
            self.bind("exit", self._on_exit)
            self.bind("press", self._on_press)
            self.bind("release", self._on_release)
        
    def _on_enter(self, event):
        """Обработка наведения мыши"""
        # Анимация увеличения
        self.scaleTo(1.1, duration=0.2)
        
        # Изменение цвета
        self['frameColor'] = self.hover_color
        
    def _on_exit(self, event):
        """Обработка ухода мыши"""
        # Возврат к исходному размеру
        self.scaleTo(1.0, duration=0.2)
        
        # Возврат к исходному цвету
        self['frameColor'] = self.original_color
        
    def _on_press(self, event):
        """Обработка нажатия"""
        # Анимация уменьшения
        self.scaleTo(0.95, duration=0.1)
        
        # Изменение цвета
        self['frameColor'] = self.click_color
        
    def _on_release(self, event):
        """Обработка отпускания"""
        # Возврат к размеру при наведении
        self.scaleTo(1.1, duration=0.1)
        
        # Возврат к цвету при наведении
        self['frameColor'] = self.hover_color
