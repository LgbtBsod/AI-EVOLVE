#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import time
from typing import Dict, List, Optional, Any
from panda3d.core import CardMaker, Vec3, Vec4, TransparencyAttrib

class EnhancedCharacter:
    """Улучшенный класс персонажа с правильным рендерингом"""
    
    def __init__(self, game, x=0, y=0, z=0, color=(1, 1, 1, 1)):
        self.game = game
        self.x = x
        self.y = y
        self.z = z
        self.color = color
        self.node = None
        
        # Базовые характеристики
        self.level = 1
        self.experience = 0
        self.experience_to_next_level = 100
        
        # Здоровье, мана, выносливость
        self.max_health = 100
        self.health = self.max_health
        self.max_mana = 50
        self.mana = self.max_mana
        self.max_stamina = 100
        self.stamina = self.max_stamina
        
        # Боевые характеристики
        self.physical_damage = 20
        self.magical_damage = 0
        self.defense = 5
        self.attack_speed = 1.0
        self.attack_range = 2.0
        self.critical_chance = 5.0
        self.critical_damage = 150.0
        self.dodge_chance = 0.0
        self.magic_resistance = 0.0
        self.speed = 5.0
        
        # Восстановление
        self.health_regen = 1.0
        self.mana_regen = 5.0
        self.stamina_regen = 10.0
        
        # Кулдаун атаки
        self.attack_cooldown = 0
        self.attack_cooldown_time = 1.0 / self.attack_speed
        
        # Базовые атрибуты
        self.base_attributes = {
            'strength': 12.0,
            'agility': 10.0,
            'intelligence': 8.0,
            'vitality': 15.0,
            'wisdom': 9.0,
            'charisma': 7.0,
            'luck': 10.0,
            'endurance': 11.0
        }
        
        # ID сущности для систем
        self.entity_id = f"character_{id(self)}"
        
    def create_character(self):
        """Создание визуального представления персонажа"""
        # Создаем персонажа как простой куб
        character = self.game.render.attachNewNode("character")
        
        # Основное тело (куб) - используем простой подход
        self.create_visible_cube(character, "body", 0, 0, 0.5, 0.6, 0.6, 0.6, self.color)
        
        # Голова
        head_color = (self.color[0] * 0.8, self.color[1] * 0.8, self.color[2] * 0.8, self.color[3])
        self.create_visible_cube(character, "head", 0, 0, 1.2, 0.4, 0.4, 0.4, head_color)
        
        # Ноги
        leg_color = (self.color[0] * 0.6, self.color[1] * 0.6, self.color[2] * 0.6, self.color[3])
        self.create_visible_cube(character, "leg1", -0.2, 0, 0.2, 0.2, 0.2, 0.4, leg_color)
        self.create_visible_cube(character, "leg2", 0.2, 0, 0.2, 0.2, 0.2, 0.4, leg_color)
        
        # Руки
        arm_color = (self.color[0] * 0.7, self.color[1] * 0.7, self.color[2] * 0.7, self.color[3])
        self.create_visible_cube(character, "arm1", -0.4, 0, 0.8, 0.2, 0.2, 0.4, arm_color)
        self.create_visible_cube(character, "arm2", 0.4, 0, 0.8, 0.2, 0.2, 0.4, arm_color)
        
        character.setPos(self.x, self.y, self.z)
        self.node = character
        return character
        
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
        """Перемещение персонажа"""
        self.x = x
        self.y = y
        if z is not None:
            self.z = z
        if self.node:
            self.node.setPos(self.x, self.y, self.z)
    
    def move_by(self, dx, dy, dz=0, dt=0.016):
        """Перемещение персонажа на относительное расстояние"""
        # Используем скорость из характеристик
        move_speed = self.speed * dt
        self.x += dx * move_speed
        self.y += dy * move_speed
        self.z += dz * move_speed
        if self.node:
            self.node.setPos(self.x, self.y, self.z)
            
    def get_position(self):
        """Получение позиции персонажа"""
        return (self.x, self.y, self.z)
    
    def get_distance_to(self, target):
        """Получение расстояния до цели"""
        if hasattr(target, 'x') and hasattr(target, 'y'):
            return math.sqrt((self.x - target.x)**2 + (self.y - target.y)**2)
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
            import random
            if random.random() * 100 < self.dodge_chance:
                print("Dodged!")
                return False
        
        self.health = max(0, self.health - actual_damage)
        return self.health <= 0
        
    def heal(self, amount):
        """Лечение"""
        self.health = min(self.max_health, self.health + amount)
        
    def restore_mana(self, amount):
        """Восстановление маны"""
        self.mana = min(self.max_mana, self.mana + amount)
        
    def restore_stamina(self, amount):
        """Восстановление выносливости"""
        self.stamina = min(self.max_stamina, self.stamina + amount)
        
    def use_mana(self, amount):
        """Использование маны"""
        if self.mana >= amount:
            self.mana -= amount
            return True
        return False
        
    def use_stamina(self, amount):
        """Использование выносливости"""
        if self.stamina >= amount:
            self.stamina -= amount
            return True
        return False
        
    def is_alive(self):
        """Проверка, жив ли персонаж"""
        return self.health > 0
        
    def attack(self, target):
        """Атака цели с учетом критических ударов"""
        if self.attack_cooldown <= 0 and self.is_alive():
            # Проверяем расстояние до цели
            if hasattr(target, 'get_position'):
                target_x, target_y, target_z = target.get_position()
            elif hasattr(target, 'x') and hasattr(target, 'y') and hasattr(target, 'z'):
                target_x, target_y, target_z = target.x, target.y, target.z
            else:
                return False
            distance = math.sqrt((self.x - target_x)**2 + (self.y - target_y)**2)
            
            if distance <= self.attack_range:
                # Рассчитываем урон
                base_damage = self.physical_damage
                
                # Проверяем критический удар
                import random
                is_critical = random.random() * 100 < self.critical_chance
                if is_critical:
                    base_damage *= (self.critical_damage / 100)
                    print("Critical hit!")
                
                # Атакуем цель
                target.take_damage(base_damage, "physical")
                self.attack_cooldown = self.attack_cooldown_time
                print(f"Player attacked enemy for {base_damage:.1f} damage!")
                return True
        return False
    
    def update_cooldown(self, dt):
        """Обновление кулдауна атаки и восстановление ресурсов"""
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt
            
        # Восстановление ресурсов
        self.restore_mana(self.mana_regen * dt)
        self.restore_stamina(self.stamina_regen * dt)
        self.heal(self.health_regen * dt)
    
    def add_experience(self, amount):
        """Добавление опыта"""
        self.experience += amount
        if self.experience >= self.experience_to_next_level:
            self.level_up()
    
    def level_up(self):
        """Повышение уровня"""
        self.level += 1
        self.experience -= self.experience_to_next_level
        self.experience_to_next_level = int(self.experience_to_next_level * 1.2)
        
        # Увеличиваем атрибуты при повышении уровня
        self.base_attributes['strength'] += 1
        self.base_attributes['agility'] += 1
        self.base_attributes['intelligence'] += 1
        self.base_attributes['vitality'] += 2
        self.base_attributes['wisdom'] += 1
        self.base_attributes['charisma'] += 1
        self.base_attributes['luck'] += 1
        self.base_attributes['endurance'] += 1
        
        # Обновляем характеристики
        self._update_derived_stats()
        
        # Восстанавливаем здоровье и ману
        self.health = self.max_health
        self.mana = self.max_mana
        self.stamina = self.max_stamina
        
        print(f"Level up! Now level {self.level}")
    
    def _update_derived_stats(self):
        """Обновление производных характеристик на основе атрибутов"""
        # Обновляем максимальные значения
        self.max_health = max(1, 50 + self.base_attributes['vitality'] * 10)
        self.max_mana = max(1, 20 + self.base_attributes['intelligence'] * 5)
        self.max_stamina = max(1, 50 + self.base_attributes['endurance'] * 5)
        
        # Обновляем урон
        self.physical_damage = 10 + self.base_attributes['strength'] * 2
        self.magical_damage = self.base_attributes['intelligence'] * 1.5
        
        # Обновляем защиту
        self.defense = self.base_attributes['vitality'] * 0.5
        
        # Обновляем скорость
        self.speed = 3 + self.base_attributes['agility'] * 0.2
        
        # Обновляем критические шансы
        self.critical_chance = 2 + self.base_attributes['luck'] * 0.5
        self.dodge_chance = self.base_attributes['agility'] * 0.3
        
        # Обновляем кулдаун атаки
        self.attack_cooldown_time = 1.0 / self.attack_speed
    
    def get_stats(self):
        """Получение всех характеристик"""
        return {
            'health': self.health,
            'max_health': self.max_health,
            'mana': self.mana,
            'max_mana': self.max_mana,
            'stamina': self.stamina,
            'max_stamina': self.max_stamina,
            'level': self.level,
            'experience': self.experience,
            'experience_to_next': self.experience_to_next_level,
            'physical_damage': self.physical_damage,
            'magical_damage': self.magical_damage,
            'defense': self.defense,
            'attack_speed': self.attack_speed,
            'critical_chance': self.critical_chance,
            'critical_damage': self.critical_damage,
            'dodge_chance': self.dodge_chance,
            'magic_resistance': self.magic_resistance,
            'speed': self.speed
        }
    
    def destroy(self):
        """Уничтожение персонажа"""
        if self.node:
            self.node.removeNode()
            self.node = None
