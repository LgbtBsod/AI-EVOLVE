#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import random
import time
from typing import List, Dict, Tuple, Optional
from panda3d.core import CardMaker, Vec3, Vec4, TransparencyAttrib
from direct.task import Task

class Particle:
    """Отдельная частица"""
    
    def __init__(self, x=0, y=0, z=0, vx=0, vy=0, vz=0, 
                 color=(1, 1, 1, 1), size=0.1, lifetime=1.0):
        self.x = x
        self.y = y
        self.z = z
        self.vx = vx
        self.vy = vy
        self.vz = vz
        self.color = color
        self.size = size
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.node = None
        self.is_alive = True
        
    def update(self, dt):
        """Обновление частицы"""
        if not self.is_alive:
            return False
            
        # Обновляем позицию
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z += self.vz * dt
        
        # Обновляем время жизни
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.is_alive = False
            return False
            
        # Обновляем прозрачность
        alpha = self.lifetime / self.max_lifetime
        self.color = (self.color[0], self.color[1], self.color[2], alpha)
        
        # Обновляем размер (уменьшаем со временем)
        self.size = (self.lifetime / self.max_lifetime) * 0.1
        
        # Обновляем визуальное представление
        if self.node:
            self.node.setPos(self.x, self.y, self.z)
            self.node.setScale(self.size)
            self.node.setColor(*self.color)
            
        return True
        
    def create_visual(self, parent):
        """Создание визуального представления частицы"""
        # Создаем простой квадрат для частицы
        cm = CardMaker("particle")
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        self.node = parent.attachNewNode(cm.generate())
        self.node.setPos(self.x, self.y, self.z)
        self.node.setScale(self.size)
        self.node.setColor(*self.color)
        self.node.setTransparency(TransparencyAttrib.MAlpha)
        
    def destroy(self):
        """Уничтожение частицы"""
        if self.node:
            self.node.removeNode()
            self.node = None

class ParticleSystem:
    """Система частиц для визуальных эффектов"""
    
    def __init__(self, game):
        self.game = game
        self.particles = []
        self.emitters = []
        self.parent_node = None
        
    def initialize(self):
        """Инициализация системы частиц"""
        # Создаем родительский узел для всех частиц
        self.parent_node = self.game.render.attachNewNode("particle_system")
        
    def create_emitter(self, name, x=0, y=0, z=0, 
                      particle_count=100, emission_rate=10.0,
                      particle_lifetime=2.0, particle_size=0.1,
                      color=(1, 1, 1, 1), velocity_range=(1, 5),
                      direction=(0, 0, 1), spread=45):
        """Создание эмиттера частиц"""
        emitter = {
            'name': name,
            'x': x, 'y': y, 'z': z,
            'particle_count': particle_count,
            'emission_rate': emission_rate,
            'particle_lifetime': particle_lifetime,
            'particle_size': particle_size,
            'color': color,
            'velocity_range': velocity_range,
            'direction': direction,
            'spread': spread,
            'last_emission': 0,
            'is_active': True
        }
        self.emitters.append(emitter)
        
    def start_emission(self, emitter_name):
        """Запуск эмиссии частиц"""
        for emitter in self.emitters:
            if emitter['name'] == emitter_name:
                emitter['is_active'] = True
                break
                
    def stop_emission(self, emitter_name):
        """Остановка эмиссии частиц"""
        for emitter in self.emitters:
            if emitter['name'] == emitter_name:
                emitter['is_active'] = False
                break
                
    def update(self, dt):
        """Обновление системы частиц"""
        current_time = time.time()
        
        # Обновляем эмиттеры
        for emitter in self.emitters:
            if not emitter['is_active']:
                continue
                
            # Проверяем, нужно ли создать новые частицы
            time_since_last = current_time - emitter['last_emission']
            if time_since_last >= 1.0 / emitter['emission_rate']:
                self._emit_particles(emitter)
                emitter['last_emission'] = current_time
                
        # Обновляем существующие частицы
        for particle in self.particles[:]:  # Используем копию для безопасного удаления
            if not particle.update(dt):
                particle.destroy()
                self.particles.remove(particle)
                
    def _emit_particles(self, emitter):
        """Создание новых частиц из эмиттера"""
        # Создаем несколько частиц за раз
        for _ in range(min(5, emitter['particle_count'])):
            # Случайная скорость в заданном направлении
            velocity = random.uniform(*emitter['velocity_range'])
            
            # Случайное отклонение от основного направления
            spread_rad = math.radians(emitter['spread'])
            angle_x = random.uniform(-spread_rad, spread_rad)
            angle_y = random.uniform(-spread_rad, spread_rad)
            
            # Вычисляем направление с учетом разброса
            dir_x, dir_y, dir_z = emitter['direction']
            vx = velocity * dir_x + random.uniform(-0.5, 0.5)
            vy = velocity * dir_y + random.uniform(-0.5, 0.5)
            vz = velocity * dir_z + random.uniform(-0.5, 0.5)
            
            # Создаем частицу
            particle = Particle(
                x=emitter['x'] + random.uniform(-0.1, 0.1),
                y=emitter['y'] + random.uniform(-0.1, 0.1),
                z=emitter['z'] + random.uniform(-0.1, 0.1),
                vx=vx, vy=vy, vz=vz,
                color=emitter['color'],
                size=emitter['particle_size'],
                lifetime=emitter['particle_lifetime']
            )
            
            # Создаем визуальное представление
            particle.create_visual(self.parent_node)
            
            # Добавляем в список
            self.particles.append(particle)
            
    def create_explosion(self, x, y, z, intensity=1.0):
        """Создание эффекта взрыва"""
        # Создаем множество частиц для взрыва
        particle_count = int(50 * intensity)
        
        for _ in range(particle_count):
            # Случайное направление во все стороны
            angle = random.uniform(0, 2 * math.pi)
            velocity = random.uniform(2, 8) * intensity
            
            vx = velocity * math.cos(angle)
            vy = velocity * math.sin(angle)
            vz = random.uniform(-2, 5) * intensity
            
            # Случайный цвет (красный, оранжевый, желтый)
            color_choice = random.choice([
                (1, 0.2, 0, 1),      # Красный
                (1, 0.5, 0, 1),      # Оранжевый
                (1, 1, 0, 1),        # Желтый
                (1, 0.8, 0.2, 1)     # Золотой
            ])
            
            particle = Particle(
                x=x, y=y, z=z,
                vx=vx, vy=vy, vz=vz,
                color=color_choice,
                size=random.uniform(0.05, 0.2),
                lifetime=random.uniform(0.5, 2.0)
            )
            
            particle.create_visual(self.parent_node)
            self.particles.append(particle)
            
    def create_smoke(self, x, y, z, duration=5.0):
        """Создание эффекта дыма"""
        # Создаем эмиттер дыма
        self.create_emitter(
            name=f"smoke_{int(time.time())}",
            x=x, y=y, z=z,
            particle_count=200,
            emission_rate=20.0,
            particle_lifetime=3.0,
            particle_size=0.3,
            color=(0.3, 0.3, 0.3, 0.5),
            velocity_range=(0.5, 2),
            direction=(0, 0, 1),
            spread=30
        )
        
        # Запускаем эмиссию
        self.start_emission(f"smoke_{int(time.time())}")
        
        # Останавливаем через заданное время
        def stop_smoke():
            time.sleep(duration)
            self.stop_emission(f"smoke_{int(time.time())}")
            
        import threading
        threading.Thread(target=stop_smoke, daemon=True).start()
        
    def create_magic_sparkles(self, x, y, z, count=20):
        """Создание магических искр"""
        for _ in range(count):
            # Случайное направление
            angle = random.uniform(0, 2 * math.pi)
            velocity = random.uniform(1, 3)
            
            vx = velocity * math.cos(angle)
            vy = velocity * math.sin(angle)
            vz = random.uniform(-1, 2)
            
            # Магический цвет (синий, фиолетовый, белый)
            color_choice = random.choice([
                (0, 0.5, 1, 1),      # Синий
                (0.5, 0, 1, 1),      # Фиолетовый
                (1, 1, 1, 1),        # Белый
                (0, 1, 1, 1)         # Голубой
            ])
            
            particle = Particle(
                x=x, y=y, z=z,
                vx=vx, vy=vy, vz=vz,
                color=color_choice,
                size=random.uniform(0.02, 0.08),
                lifetime=random.uniform(1.0, 3.0)
            )
            
            particle.create_visual(self.parent_node)
            self.particles.append(particle)
            
    def create_healing_effect(self, x, y, z):
        """Создание эффекта лечения"""
        # Создаем зеленые частицы, поднимающиеся вверх
        for _ in range(30):
            angle = random.uniform(0, 2 * math.pi)
            velocity = random.uniform(1, 3)
            
            vx = velocity * math.cos(angle) * 0.3
            vy = velocity * math.sin(angle) * 0.3
            vz = velocity * 2  # Вверх
            
            particle = Particle(
                x=x, y=y, z=z,
                vx=vx, vy=vy, vz=vz,
                color=(0, 1, 0, 0.8),
                size=random.uniform(0.05, 0.15),
                lifetime=random.uniform(1.5, 3.0)
            )
            
            particle.create_visual(self.parent_node)
            self.particles.append(particle)
            
    def clear_all_particles(self):
        """Очистка всех частиц"""
        for particle in self.particles:
            particle.destroy()
        self.particles.clear()
        
    def destroy(self):
        """Уничтожение системы частиц"""
        self.clear_all_particles()
        if self.parent_node:
            self.parent_node.removeNode()
            self.parent_node = None
