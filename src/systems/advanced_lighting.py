#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import time
from typing import Dict, List, Tuple, Optional
from panda3d.core import (
    AmbientLight, DirectionalLight, PointLight, Spotlight,
    Vec3, Vec4, LColor, LVector3, LVector4
)
from direct.task import Task

class AdvancedLighting:
    """Продвинутая система освещения с эффектами"""
    
    def __init__(self, game):
        self.game = game
        self.lights = {}
        self.light_effects = {}
        self.dynamic_lights = []
        self.ambient_color = Vec4(0.3, 0.3, 0.3, 1)
        self.fog_enabled = False
        self.fog_color = Vec4(0.5, 0.5, 0.5, 1)
        self.fog_density = 0.01
        
    def initialize(self):
        """Инициализация системы освещения"""
        # Создаем базовое освещение
        self._create_base_lighting()
        
        # Настраиваем туман
        self._setup_fog()
        
        # Создаем динамические эффекты
        self._create_dynamic_effects()
        
    def _create_base_lighting(self):
        """Создание базового освещения"""
        # Окружающее освещение
        ambient_light = AmbientLight('ambient_light')
        ambient_light.setColor(self.ambient_color)
        ambient_np = self.game.render.attachNewNode(ambient_light)
        self.game.render.setLight(ambient_np)
        self.lights['ambient'] = ambient_np
        
        # Основное направленное освещение (солнце)
        sun_light = DirectionalLight('sun_light')
        sun_light.setColor(Vec4(0.8, 0.8, 0.7, 1))
        sun_np = self.game.render.attachNewNode(sun_light)
        sun_np.setHpr(45, -45, 0)
        self.game.render.setLight(sun_np)
        self.lights['sun'] = sun_np
        
        # Дополнительное направленное освещение
        fill_light = DirectionalLight('fill_light')
        fill_light.setColor(Vec4(0.4, 0.4, 0.5, 1))
        fill_np = self.game.render.attachNewNode(fill_light)
        fill_np.setHpr(-45, -30, 0)
        self.game.render.setLight(fill_np)
        self.lights['fill'] = fill_np
        
    def _setup_fog(self):
        """Настройка тумана"""
        if self.fog_enabled:
            self.game.render.setFog(
                self.game.render.attachNewNode("fog")
            )
            
    def _create_dynamic_effects(self):
        """Создание динамических эффектов освещения"""
        # Создаем мерцающие огни
        self._create_flickering_lights()
        
        # Создаем движущиеся источники света
        self._create_moving_lights()
        
    def _create_flickering_lights(self):
        """Создание мерцающих огней"""
        # Создаем несколько мерцающих огней
        for i in range(3):
            light = PointLight(f'flicker_light_{i}')
            light.setColor(Vec4(1, 0.8, 0.3, 1))
            light.setAttenuation(Vec3(1, 0.1, 0.01))
            
            light_np = self.game.render.attachNewNode(light)
            light_np.setPos(
                (i - 1) * 10,
                -5 + i * 5,
                2
            )
            
            self.game.render.setLight(light_np)
            self.lights[f'flicker_{i}'] = light_np
            
            # Добавляем эффект мерцания
            self.light_effects[f'flicker_{i}'] = {
                'type': 'flicker',
                'base_intensity': 1.0,
                'flicker_speed': 2.0 + i * 0.5,
                'flicker_amount': 0.3
            }
            
    def _create_moving_lights(self):
        """Создание движущихся источников света"""
        # Создаем движущийся свет
        moving_light = PointLight('moving_light')
        moving_light.setColor(Vec4(0.3, 0.8, 1, 1))
        moving_light.setAttenuation(Vec3(1, 0.2, 0.05))
        
        moving_np = self.game.render.attachNewNode(moving_light)
        self.game.render.setLight(moving_np)
        self.lights['moving'] = moving_np
        
        # Добавляем эффект движения
        self.light_effects['moving'] = {
            'type': 'orbit',
            'center': (0, 0, 3),
            'radius': 8,
            'speed': 0.5,
            'height_variation': 2
        }
        
    def update(self, dt):
        """Обновление системы освещения"""
        current_time = time.time()
        
        # Обновляем мерцающие огни
        for light_name, effect in self.light_effects.items():
            if effect['type'] == 'flicker':
                self._update_flickering_light(light_name, effect, current_time)
            elif effect['type'] == 'orbit':
                self._update_orbiting_light(light_name, effect, current_time)
                
    def _update_flickering_light(self, light_name, effect, current_time):
        """Обновление мерцающего света"""
        if light_name not in self.lights:
            return
            
        light_np = self.lights[light_name]
        
        # Вычисляем мерцание
        flicker = math.sin(current_time * effect['flicker_speed']) * effect['flicker_amount']
        intensity = effect['base_intensity'] + flicker
        
        # Обновляем интенсивность
        light = light_np.node()
        if light:
            color = light.getColor()
            new_color = Vec4(
                color[0] * intensity,
                color[1] * intensity,
                color[2] * intensity,
                color[3]
            )
            light.setColor(new_color)
            
    def _update_orbiting_light(self, light_name, effect, current_time):
        """Обновление орбитального света"""
        if light_name not in self.lights:
            return
            
        light_np = self.lights[light_name]
        
        # Вычисляем позицию на орбите
        angle = current_time * effect['speed']
        center = effect['center']
        radius = effect['radius']
        
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        z = center[2] + math.sin(angle * 2) * effect['height_variation']
        
        light_np.setPos(x, y, z)
        
    def create_torch_light(self, x, y, z, intensity=1.0):
        """Создание света факела"""
        torch_light = PointLight(f'torch_{int(time.time())}')
        torch_light.setColor(Vec4(1, 0.6, 0.2, 1))
        torch_light.setAttenuation(Vec3(1, 0.3, 0.1))
        
        torch_np = self.game.render.attachNewNode(torch_light)
        torch_np.setPos(x, y, z)
        self.game.render.setLight(torch_np)
        
        # Добавляем мерцание
        self.lights[f'torch_{int(time.time())}'] = torch_np
        self.light_effects[f'torch_{int(time.time())}'] = {
            'type': 'flicker',
            'base_intensity': intensity,
            'flicker_speed': 3.0,
            'flicker_amount': 0.4
        }
        
        return torch_np
        
    def create_magic_light(self, x, y, z, color=(0, 0.8, 1, 1)):
        """Создание магического света"""
        magic_light = PointLight(f'magic_{int(time.time())}')
        magic_light.setColor(Vec4(*color))
        magic_light.setAttenuation(Vec3(1, 0.2, 0.05))
        
        magic_np = self.game.render.attachNewNode(magic_light)
        magic_np.setPos(x, y, z)
        self.game.render.setLight(magic_np)
        
        # Добавляем пульсацию
        self.lights[f'magic_{int(time.time())}'] = magic_np
        self.light_effects[f'magic_{int(time.time())}'] = {
            'type': 'pulse',
            'base_intensity': 1.0,
            'pulse_speed': 1.5,
            'pulse_amount': 0.5
        }
        
        return magic_np
        
    def create_spotlight(self, x, y, z, target_x, target_y, target_z, 
                        color=(1, 1, 1, 1), angle=30, intensity=1.0):
        """Создание прожектора"""
        spotlight = Spotlight(f'spotlight_{int(time.time())}')
        spotlight.setColor(Vec4(*color))
        spotlight.setLens(angle)
        
        spot_np = self.game.render.attachNewNode(spotlight)
        spot_np.setPos(x, y, z)
        spot_np.lookAt(target_x, target_y, target_z)
        self.game.render.setLight(spot_np)
        
        self.lights[f'spotlight_{int(time.time())}'] = spot_np
        return spot_np
        
    def set_ambient_light(self, color):
        """Установка окружающего освещения"""
        self.ambient_color = Vec4(*color)
        if 'ambient' in self.lights:
            light = self.lights['ambient'].node()
            if light:
                light.setColor(self.ambient_color)
                
    def set_fog(self, enabled, color=(0.5, 0.5, 0.5, 1), density=0.01):
        """Настройка тумана"""
        self.fog_enabled = enabled
        self.fog_color = Vec4(*color)
        self.fog_density = density
        
        if enabled:
            # Создаем туман
            from panda3d.core import Fog
            fog = Fog("fog")
            fog.setColor(self.fog_color)
            fog.setExpDensity(self.fog_density)
            self.game.render.setFog(fog)
        else:
            # Убираем туман
            self.game.render.clearFog()
            
    def create_day_night_cycle(self):
        """Создание цикла день/ночь"""
        def day_night_cycle(task):
            current_time = time.time()
            
            # Симулируем 24-часовой цикл за 5 минут
            day_progress = (current_time % 300) / 300
            
            # Вычисляем интенсивность солнца
            if 0.2 <= day_progress <= 0.8:  # День
                sun_intensity = 1.0
                ambient_intensity = 0.6
            elif day_progress < 0.2:  # Рассвет
                sun_intensity = day_progress * 5
                ambient_intensity = 0.3 + day_progress * 2.5
            else:  # Закат и ночь
                sun_intensity = max(0, 1.0 - (day_progress - 0.8) * 5)
                ambient_intensity = 0.6 - (day_progress - 0.8) * 3
            
            # Обновляем солнце
            if 'sun' in self.lights:
                sun_light = self.lights['sun'].node()
                if sun_light:
                    sun_light.setColor(Vec4(
                        0.8 * sun_intensity,
                        0.8 * sun_intensity,
                        0.7 * sun_intensity,
                        1
                    ))
            
            # Обновляем окружающее освещение
            if 'ambient' in self.lights:
                ambient_light = self.lights['ambient'].node()
                if ambient_light:
                    ambient_light.setColor(Vec4(
                        self.ambient_color[0] * ambient_intensity,
                        self.ambient_color[1] * ambient_intensity,
                        self.ambient_color[2] * ambient_intensity,
                        self.ambient_color[3]
                    ))
            
            return Task.cont
            
        self.game.showbase.taskMgr.add(day_night_cycle, "day_night_cycle")
        
    def create_lightning_effect(self):
        """Создание эффекта молнии"""
        def lightning_flash():
            # Создаем яркую вспышку
            flash_light = DirectionalLight('lightning_flash')
            flash_light.setColor(Vec4(1, 1, 1, 1))
            flash_np = self.game.render.attachNewNode(flash_light)
            flash_np.setHpr(0, -90, 0)
            self.game.render.setLight(flash_np)
            
            # Убираем через короткое время
            def remove_flash():
                time.sleep(0.1)
                flash_np.removeNode()
                
            import threading
            threading.Thread(target=remove_flash, daemon=True).start()
            
        # Запускаем молнию
        lightning_flash()
        
    def destroy_light(self, light_name):
        """Уничтожение источника света"""
        if light_name in self.lights:
            self.lights[light_name].removeNode()
            del self.lights[light_name]
            
        if light_name in self.light_effects:
            del self.light_effects[light_name]
            
    def destroy(self):
        """Уничтожение системы освещения"""
        # Убираем все источники света
        for light_np in self.lights.values():
            light_np.removeNode()
        self.lights.clear()
        self.light_effects.clear()
        
        # Убираем туман
        self.game.render.clearFog()
        
        # Останавливаем задачи
        self.game.showbase.taskMgr.remove("day_night_cycle")
