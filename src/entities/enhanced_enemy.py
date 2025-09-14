#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import time
import random
from typing import Dict, List, Optional, Any
from panda3d.core import CardMaker, Vec3, Vec4, TransparencyAttrib

class EnhancedEnemy:
    """Улучшенный класс врага с правильным рендерингом"""
    
    def __init__(self, game, x=0, y=0, z=0, enemy_type="basic", color=(1, 0, 0, 1)):
        self.game = game
        self.x = x
        self.y = y
        self.z = z
        self.enemy_type = enemy_type
        self.color = color
        self.node = None
        
        # Базовые характеристики в зависимости от типа
        self._setup_enemy_type()
        
        # ID сущности для систем
        self.entity_id = f"enemy_{id(self)}"
        
        # AI состояние
        self.state = "idle"  # idle, chasing, attacking, dead
        self.target = None
        self.last_attack_time = 0
        self.attack_cooldown = 1.0
        
        # Движение
        self.move_speed = 3.0
        self.detection_range = 8.0
        self.attack_range = 1.5
        
    def _setup_enemy_type(self):
        """Настройка характеристик в зависимости от типа врага"""
        if self.enemy_type == "basic":
            self.level = 1
            self.max_health = 50
            self.health = self.max_health
            self.physical_damage = 15
            self.defense = 2
            self.experience_reward = 25
            self.size = 0.8
            self.color = (1, 0, 0, 1)  # Красный
        elif self.enemy_type == "strong":
            self.level = 3
            self.max_health = 120
            self.health = self.max_health
            self.physical_damage = 30
            self.defense = 5
            self.experience_reward = 75
            self.size = 1.2
            self.color = (0.8, 0.2, 0.2, 1)  # Темно-красный
        elif self.enemy_type == "elite":
            self.level = 5
            self.max_health = 200
            self.health = self.max_health
            self.physical_damage = 45
            self.defense = 8
            self.experience_reward = 150
            self.size = 1.5
            self.color = (0.6, 0.1, 0.6, 1)  # Фиолетовый
        elif self.enemy_type == "boss":
            self.level = 10
            self.max_health = 500
            self.health = self.max_health
            self.physical_damage = 80
            self.defense = 15
            self.experience_reward = 500
            self.size = 2.0
            self.color = (0.3, 0.1, 0.1, 1)  # Очень темно-красный
        else:
            # Дефолтные значения
            self.level = 1
            self.max_health = 50
            self.health = self.max_health
            self.physical_damage = 15
            self.defense = 2
            self.experience_reward = 25
            self.size = 0.8
            self.color = (1, 0, 0, 1)
        
        # Дополнительные характеристики
        self.critical_chance = 5.0
        self.critical_damage = 150.0
        self.dodge_chance = 0.0
        self.magic_resistance = 0.0
        
    def create_enemy(self):
        """Создание визуального представления врага"""
        # Создаем врага как куб с дополнительными деталями
        enemy = self.game.render.attachNewNode("enemy")
        
        # Основное тело
        body_size = self.size
        self.create_visible_cube(enemy, "body", 0, 0, body_size/2, body_size, body_size, body_size, self.color)
        
        # Голова
        head_size = body_size * 0.6
        head_color = (self.color[0] * 0.7, self.color[1] * 0.7, self.color[2] * 0.7, self.color[3])
        self.create_visible_cube(enemy, "head", 0, 0, body_size + head_size/2, head_size, head_size, head_size, head_color)
        
        # Ноги
        leg_size = body_size * 0.3
        leg_color = (self.color[0] * 0.5, self.color[1] * 0.5, self.color[2] * 0.5, self.color[3])
        self.create_visible_cube(enemy, "leg1", -body_size/3, 0, 0, leg_size, leg_size, body_size/2, leg_color)
        self.create_visible_cube(enemy, "leg2", body_size/3, 0, 0, leg_size, leg_size, body_size/2, leg_color)
        
        # Руки
        arm_size = body_size * 0.4
        arm_color = (self.color[0] * 0.6, self.color[1] * 0.6, self.color[2] * 0.6, self.color[3])
        self.create_visible_cube(enemy, "arm1", -body_size/2, 0, body_size/2, arm_size, arm_size, body_size, arm_color)
        self.create_visible_cube(enemy, "arm2", body_size/2, 0, body_size/2, arm_size, arm_size, body_size, arm_color)
        
        # Глаза (для более зловещего вида)
        eye_size = head_size * 0.2
        eye_color = (1, 1, 1, 1)  # Белые глаза
        self.create_visible_cube(enemy, "eye1", -head_size/4, head_size/2 + 0.1, head_size/4, eye_size, eye_size/2, eye_size, eye_color)
        self.create_visible_cube(enemy, "eye2", head_size/4, head_size/2 + 0.1, head_size/4, eye_size, eye_size/2, eye_size, eye_color)
        
        enemy.setPos(self.x, self.y, self.z)
        self.node = enemy
        return enemy
        
    def create_visible_cube(self, parent, name, x, y, z, width, height, depth, color):
        """Создание видимого куба с правильной ориентацией"""
        # Создаем куб из 6 граней с правильной ориентацией
        cube = parent.attachNewNode(name)
        
        # Передняя грань (обращена к камере)
        cm = CardMaker(f"{name}_front")
        cm.setFrame(-width/2, width/2, -height/2, height/2)
        front = cube.attachNewNode(cm.generate())
        front.setPos(0, depth/2, 0)
        front.setColor(*color)
        
        # Задняя грань
        cm = CardMaker(f"{name}_back")
        cm.setFrame(-width/2, width/2, -height/2, height/2)
        back = cube.attachNewNode(cm.generate())
        back.setPos(0, -depth/2, 0)
        back.setHpr(0, 180, 0)
        back.setColor(color[0] * 0.7, color[1] * 0.7, color[2] * 0.7, color[3])
        
        # Левая грань
        cm = CardMaker(f"{name}_left")
        cm.setFrame(-depth/2, depth/2, -height/2, height/2)
        left = cube.attachNewNode(cm.generate())
        left.setPos(-width/2, 0, 0)
        left.setHpr(0, -90, 0)
        left.setColor(color[0] * 0.8, color[1] * 0.8, color[2] * 0.8, color[3])
        
        # Правая грань
        cm = CardMaker(f"{name}_right")
        cm.setFrame(-depth/2, depth/2, -height/2, height/2)
        right = cube.attachNewNode(cm.generate())
        right.setPos(width/2, 0, 0)
        right.setHpr(0, 90, 0)
        right.setColor(color[0] * 0.6, color[1] * 0.6, color[2] * 0.6, color[3])
        
        # Верхняя грань
        cm = CardMaker(f"{name}_top")
        cm.setFrame(-width/2, width/2, -depth/2, depth/2)
        top = cube.attachNewNode(cm.generate())
        top.setPos(0, 0, height/2)
        top.setHpr(0, 0, -90)
        top.setColor(color[0] * 1.2, color[1] * 1.2, color[2] * 1.2, color[3])
        
        # Нижняя грань
        cm = CardMaker(f"{name}_bottom")
        cm.setFrame(-width/2, width/2, -depth/2, depth/2)
        bottom = cube.attachNewNode(cm.generate())
        bottom.setPos(0, 0, -height/2)
        bottom.setHpr(0, 0, 90)
        bottom.setColor(color[0] * 0.4, color[1] * 0.4, color[2] * 0.4, color[3])
        
        cube.setPos(x, y, z)
        return cube
        
    def move_to(self, x, y, z=None):
        """Перемещение врага"""
        self.x = x
        self.y = y
        if z is not None:
            self.z = z
        if self.node:
            self.node.setPos(self.x, self.y, self.z)
    
    def move_towards(self, target_x, target_y, dt=0.016):
        """Движение к цели"""
        # Вычисляем направление к цели
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance > 0.1:  # Если не слишком близко
            # Нормализуем направление
            dx /= distance
            dy /= distance
            
            # Двигаемся с учетом скорости
            move_distance = self.move_speed * dt
            self.x += dx * move_distance
            self.y += dy * move_distance
            
            if self.node:
                self.node.setPos(self.x, self.y, self.z)
                
            # Поворачиваем врага лицом к цели
            angle = math.atan2(dy, dx) * 180 / math.pi
            if self.node:
                self.node.setHpr(angle, 0, 0)
    
    def get_position(self):
        """Получение позиции врага"""
        return (self.x, self.y, self.z)
    
    def get_distance_to(self, target):
        """Получение расстояния до цели"""
        if hasattr(target, 'x') and hasattr(target, 'y'):
            return math.sqrt((self.x - target.x)**2 + (self.y - target.y)**2)
        elif hasattr(target, 'get_position'):
            target_x, target_y, target_z = target.get_position()
            return math.sqrt((self.x - target_x)**2 + (self.y - target_y)**2)
        return float('inf')
    
    def take_damage(self, damage, damage_type="physical"):
        """Получение урона с учетом защиты"""
        # Применяем защиту
        if damage_type == "physical":
            actual_damage = max(1, damage - self.defense)
        elif damage_type == "magical":
            actual_damage = max(1, damage * (1 - self.magic_resistance / 100))
        else:
            actual_damage = damage
        
        # Проверяем уклонение
        if damage_type == "physical" and self.dodge_chance > 0:
            if random.random() * 100 < self.dodge_chance:
                print("Enemy dodged!")
                return False
        
        self.health = max(0, self.health - actual_damage)
        if self.health <= 0:
            self.state = "dead"
        return self.health <= 0
        
    def is_alive(self):
        """Проверка, жив ли враг"""
        return self.health > 0 and self.state != "dead"
    
    def attack(self, target):
        """Атака цели"""
        current_time = time.time()
        if current_time - self.last_attack_time >= self.attack_cooldown and self.is_alive():
            # Проверяем расстояние до цели
            distance = self.get_distance_to(target)
            
            if distance <= self.attack_range:
                # Рассчитываем урон
                base_damage = self.physical_damage
                
                # Проверяем критический удар
                is_critical = random.random() * 100 < self.critical_chance
                if is_critical:
                    base_damage *= (self.critical_damage / 100)
                    print("Enemy critical hit!")
                
                # Атакуем цель
                target.take_damage(base_damage, "physical")
                self.last_attack_time = current_time
                print(f"Enemy attacked player for {base_damage:.1f} damage!")
                return True
        return False
    
    def update_ai(self, player, dt=0.016):
        """Обновление ИИ врага"""
        if not self.is_alive():
            return
        
        # Вычисляем расстояние до игрока
        distance_to_player = self.get_distance_to(player)
        
        if distance_to_player <= self.detection_range:
            # Игрок в зоне обнаружения
            if distance_to_player <= self.attack_range:
                # Игрок в зоне атаки
                self.state = "attacking"
                self.attack(player)
            else:
                # Преследуем игрока
                self.state = "chasing"
                if hasattr(player, 'x') and hasattr(player, 'y'):
                    self.move_towards(player.x, player.y, dt)
                elif hasattr(player, 'get_position'):
                    target_x, target_y, target_z = player.get_position()
                    self.move_towards(target_x, target_y, dt)
        else:
            # Игрок вне зоны обнаружения
            self.state = "idle"
    
    def get_stats(self):
        """Получение характеристик врага"""
        return {
            'enemy_type': self.enemy_type,
            'level': self.level,
            'health': self.health,
            'max_health': self.max_health,
            'physical_damage': self.physical_damage,
            'defense': self.defense,
            'experience_reward': self.experience_reward,
            'state': self.state,
            'position': (self.x, self.y, self.z)
        }
    
    def destroy(self):
        """Уничтожение врага"""
        if self.node:
            self.node.removeNode()
            self.node = None
