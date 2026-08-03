#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import time
import random
from typing import Dict, List, Optional, Any, Tuple
from panda3d.core import CardMaker, Vec3, Vec4, TransparencyAttrib, LODNode

from .base_entity import BaseEntity
from ..core.constants import EntityType
import logging

logger = logging.getLogger(__name__)

class Character(BaseEntity):
    """Класс персонажа с улучшенной графикой - наследуется от BaseEntity"""
    
    def __init__(self, character_id: str, game, x=0, y=0, z=0, character_class="warrior", color=(1, 1, 1, 1), is_player=False):
        # Инициализируем базовую сущность
        entity_type = EntityType.PLAYER if is_player else EntityType.NPC
        super().__init__(character_id, entity_type, f"character_{character_id}")
        
        self.game = game
        self.x = x
        self.y = y
        self.z = z
        self.character_class = character_class
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
        # Скорость передвижения героя. Для демонстрации поискового поведения
        # делаем её повыше, чтобы движение было явно заметно.
        self.speed = 8.0
        
        # Восстановление
        self.health_regen = 1.0
        self.mana_regen = 5.0
        self.stamina_regen = 10.0
        
        # Кулдаун атаки
        self.attack_cooldown = 0
        self.attack_cooldown_time = 1.0 / self.attack_speed
        
        # Анимация
        self.animation_state = "idle"
        self.animation_time = 0
        self.bob_offset = 0
        self.rotation_offset = 0
        self.attack_start_time = 0
        
        # ID сущности для систем
        self.entity_id = f"character_{id(self)}"
        
        # ИИ управление
        self.ai_enabled = True
        self.ai_state = "idle"  # idle, exploring, fighting, looting
        self.target_enemy = None
        self.target_item = None
        self.last_ai_update = 0
        self.ai_update_interval = 0.1  # Обновление ИИ каждые 100мс
        self.last_defensive_skill_time = 0.0
        self.defensive_skill_cooldown = 3.0
        self.exploration_target = None
        self.exploration_retarget_interval = 2.0
        self.last_exploration_target_time = 0.0
        
        # Дополнительные характеристики игрока
        self.is_player = is_player
        if is_player:
            self.reputation = 0
            self.fame = 0
            self.achievements = []
            self.total_playtime = 0.0
            self.charisma_bonus = 0.0
            self.persuasion_skill = 0.5
            self.quests_completed = []
            self.locations_visited = []
            self.npcs_met = []
            self.last_save = 0.0
            self.last_exploration = 0.0
            self.last_social = 0.0
        
        # Настройки класса
        self._setup_character_class()
        
    def _setup_character_class(self):
        """Настройка характеристик в зависимости от класса"""
        if self.character_class == "warrior":
            self.max_health = 120
            self.health = self.max_health
            self.physical_damage = 25
            self.defense = 8
            self.color = (0.8, 0.2, 0.2, 1)  # Красный
            self.size = 1.1
        elif self.character_class == "mage":
            self.max_health = 80
            self.health = self.max_health
            self.max_mana = 100
            self.mana = self.max_mana
            self.physical_damage = 15
            self.magical_damage = 30
            self.defense = 3
            self.color = (0.2, 0.2, 0.8, 1)  # Синий
            self.size = 0.9
        elif self.character_class == "rogue":
            self.max_health = 90
            self.health = self.max_health
            self.physical_damage = 20
            self.defense = 4
            self.critical_chance = 15.0
            self.dodge_chance = 10.0
            self.speed = 7.0
            self.color = (0.2, 0.8, 0.2, 1)  # Зеленый
            self.size = 0.95
        else:
            # Дефолтные значения
            self.size = 1.0
            
    def create_character(self):
        """Создание визуального представления персонажа"""
        # Создаем персонажа как иерархию узлов
        character = self.game.render.attachNewNode("character")
        
        # Основное тело
        self._create_detailed_body(character)
        
        # Голова с деталями
        self._create_detailed_head(character)
        
        # Руки с анимацией
        self._create_animated_arms(character)
        
        # Ноги
        self._create_detailed_legs(character)
        
        # Экипировка
        self._create_equipment(character)
        
        # Эффекты
        self._create_character_effects(character)
        
        character.setPos(self.x, self.y, self.z)
        self.node = character
        
        # Запускаем анимации
        self._start_animations()
        
        return character
        
    def _create_detailed_body(self, parent):
        """Создание детализированного тела"""
        body_size = self.size
        
        # Основное тело
        self.body = self._create_advanced_cube(
            parent, "body", 0, 0, body_size/2, 
            body_size, body_size, body_size, 
            self.color, "body_texture"
        )
        
        # Грудь (более светлая)
        chest_color = (
            min(1, self.color[0] + 0.2),
            min(1, self.color[1] + 0.2),
            min(1, self.color[2] + 0.2),
            self.color[3]
        )
        self.chest = self._create_advanced_cube(
            parent, "chest", 0, 0, body_size/2 + 0.1, 
            body_size * 0.8, body_size * 0.8, body_size * 0.3, 
            chest_color, "chest_texture"
        )
        
    def _create_detailed_head(self, parent):
        """Создание детализированной головы"""
        head_size = self.size * 0.6
        head_color = (
            self.color[0] * 0.8,
            self.color[1] * 0.8,
            self.color[2] * 0.8,
            self.color[3]
        )
        
        # Голова
        self.head = self._create_advanced_cube(
            parent, "head", 0, 0, self.size + head_size/2, 
            head_size, head_size, head_size, 
            head_color, "head_texture"
        )
        
        # Глаза
        eye_size = head_size * 0.15
        self.left_eye = self._create_advanced_cube(
            parent, "left_eye", -head_size/3, head_size/2 + 0.05, self.size + head_size/2 + head_size/4, 
            eye_size, eye_size/2, eye_size, 
            (1, 1, 1, 1), "eye_texture"
        )
        self.right_eye = self._create_advanced_cube(
            parent, "right_eye", head_size/3, head_size/2 + 0.05, self.size + head_size/2 + head_size/4, 
            eye_size, eye_size/2, eye_size, 
            (1, 1, 1, 1), "eye_texture"
        )
        
        # Зрачки
        pupil_size = eye_size * 0.5
        self.left_pupil = self._create_advanced_cube(
            parent, "left_pupil", -head_size/3, head_size/2 + 0.06, self.size + head_size/2 + head_size/4, 
            pupil_size, pupil_size/2, pupil_size, 
            (0, 0, 0, 1), "pupil_texture"
        )
        self.right_pupil = self._create_advanced_cube(
            parent, "right_pupil", head_size/3, head_size/2 + 0.06, self.size + head_size/2 + head_size/4, 
            pupil_size, pupil_size/2, pupil_size, 
            (0, 0, 0, 1), "pupil_texture"
        )
        
    def _create_animated_arms(self, parent):
        """Создание анимированных рук"""
        arm_size = self.size * 0.4
        arm_color = (
            self.color[0] * 0.7,
            self.color[1] * 0.7,
            self.color[2] * 0.7,
            self.color[3]
        )
        
        # Левая рука
        self.left_arm = self._create_advanced_cube(
            parent, "left_arm", -self.size/2 - arm_size/2, 0, self.size/2, 
            arm_size, arm_size, self.size, 
            arm_color, "arm_texture"
        )
        
        # Правая рука
        self.right_arm = self._create_advanced_cube(
            parent, "right_arm", self.size/2 + arm_size/2, 0, self.size/2, 
            arm_size, arm_size, self.size, 
            arm_color, "arm_texture"
        )
        
        # Кисти
        hand_size = arm_size * 0.6
        self.left_hand = self._create_advanced_cube(
            parent, "left_hand", -self.size/2 - arm_size/2, 0, 0, 
            hand_size, hand_size, hand_size, 
            arm_color, "hand_texture"
        )
        self.right_hand = self._create_advanced_cube(
            parent, "right_hand", self.size/2 + arm_size/2, 0, 0, 
            hand_size, hand_size, hand_size, 
            arm_color, "hand_texture"
        )
        
    def _create_detailed_legs(self, parent):
        """Создание детализированных ног"""
        leg_size = self.size * 0.3
        leg_color = (
            self.color[0] * 0.6,
            self.color[1] * 0.6,
            self.color[2] * 0.6,
            self.color[3]
        )
        
        # Левая нога
        self.left_leg = self._create_advanced_cube(
            parent, "left_leg", -self.size/3, 0, 0, 
            leg_size, leg_size, self.size/2, 
            leg_color, "leg_texture"
        )
        
        # Правая нога
        self.right_leg = self._create_advanced_cube(
            parent, "right_leg", self.size/3, 0, 0, 
            leg_size, leg_size, self.size/2, 
            leg_color, "leg_texture"
        )
        
        # Ступни
        foot_size = leg_size * 0.8
        self.left_foot = self._create_advanced_cube(
            parent, "left_foot", -self.size/3, 0, -self.size/4, 
            foot_size, foot_size * 1.5, foot_size, 
            leg_color, "foot_texture"
        )
        self.right_foot = self._create_advanced_cube(
            parent, "right_foot", self.size/3, 0, -self.size/4, 
            foot_size, foot_size * 1.5, foot_size, 
            leg_color, "foot_texture"
        )
        
    def _create_equipment(self, parent):
        """Создание экипировки"""
        if self.character_class == "warrior":
            # Меч
            sword_color = (0.7, 0.7, 0.7, 1)
            self.sword = self._create_advanced_cube(
                parent, "sword", self.size/2 + 0.3, 0, self.size/2, 
                0.1, 0.1, 0.8, 
                sword_color, "sword_texture"
            )
            
        elif self.character_class == "mage":
            # Посох
            staff_color = (0.6, 0.4, 0.2, 1)
            self.staff = self._create_advanced_cube(
                parent, "staff", self.size/2 + 0.2, 0, self.size/2, 
                0.1, 0.1, 1.0, 
                staff_color, "staff_texture"
            )
            
            # Магический шар
            orb_color = (0, 0.8, 1, 0.8)
            self.orb = self._create_advanced_cube(
                parent, "orb", self.size/2 + 0.3, 0, self.size/2 + 0.5, 
                0.2, 0.2, 0.2, 
                orb_color, "orb_texture"
            )
            
        elif self.character_class == "rogue":
            # Кинжалы
            dagger_color = (0.5, 0.5, 0.5, 1)
            self.left_dagger = self._create_advanced_cube(
                parent, "left_dagger", -self.size/2 - 0.2, 0, self.size/2, 
                0.05, 0.05, 0.4, 
                dagger_color, "dagger_texture"
            )
            self.right_dagger = self._create_advanced_cube(
                parent, "right_dagger", self.size/2 + 0.2, 0, self.size/2, 
                0.05, 0.05, 0.4, 
                dagger_color, "dagger_texture"
            )
            
    def _create_character_effects(self, parent):
        """Создание эффектов персонажа"""
        # Аура класса
        if self.character_class == "mage":
            # Магическая аура
            aura_color = (0, 0.5, 1, 0.3)
            self.aura = self._create_advanced_cube(
                parent, "aura", 0, 0, self.size/2, 
                self.size * 1.5, self.size * 1.5, self.size * 1.5, 
                aura_color, "aura_texture"
            )
            self.aura.setTransparency(TransparencyAttrib.MAlpha)
            
    def _create_advanced_cube(self, parent, name, x, y, z, width, height, depth, color, texture_name):
        """Создание продвинутого куба с текстурами"""
        cube = parent.attachNewNode(name)
        
        # Создаем куб из 6 граней с разными текстурами
        from panda3d.core import CardMaker
        
        # Передняя грань
        cm = CardMaker(f"{name}_front")
        cm.setFrame(-width/2, width/2, -height/2, height/2)
        front = cube.attachNewNode(cm.generate())
        front.setPos(0, depth/2, 0)
        front.setColor(*color)
        self._apply_texture(front, texture_name, "front")
        
        # Задняя грань
        cm = CardMaker(f"{name}_back")
        cm.setFrame(-width/2, width/2, -height/2, height/2)
        back = cube.attachNewNode(cm.generate())
        back.setPos(0, -depth/2, 0)
        back.setHpr(0, 180, 0)
        back.setColor(color[0] * 0.7, color[1] * 0.7, color[2] * 0.7, color[3])
        self._apply_texture(back, texture_name, "back")
        
        # Левая грань
        cm = CardMaker(f"{name}_left")
        cm.setFrame(-depth/2, depth/2, -height/2, height/2)
        left = cube.attachNewNode(cm.generate())
        left.setPos(-width/2, 0, 0)
        left.setHpr(0, -90, 0)
        left.setColor(color[0] * 0.8, color[1] * 0.8, color[2] * 0.8, color[3])
        self._apply_texture(left, texture_name, "side")
        
        # Правая грань
        cm = CardMaker(f"{name}_right")
        cm.setFrame(-depth/2, depth/2, -height/2, height/2)
        right = cube.attachNewNode(cm.generate())
        right.setPos(width/2, 0, 0)
        right.setHpr(0, 90, 0)
        right.setColor(color[0] * 0.6, color[1] * 0.6, color[2] * 0.6, color[3])
        self._apply_texture(right, texture_name, "side")
        
        # Верхняя грань
        cm = CardMaker(f"{name}_top")
        cm.setFrame(-width/2, width/2, -depth/2, depth/2)
        top = cube.attachNewNode(cm.generate())
        top.setPos(0, 0, height/2)
        top.setHpr(0, 0, -90)
        top.setColor(color[0] * 1.2, color[1] * 1.2, color[2] * 1.2, color[3])
        self._apply_texture(top, texture_name, "top")
        
        # Нижняя грань
        cm = CardMaker(f"{name}_bottom")
        cm.setFrame(-width/2, width/2, -depth/2, depth/2)
        bottom = cube.attachNewNode(cm.generate())
        bottom.setPos(0, 0, -height/2)
        bottom.setHpr(0, 0, 90)
        bottom.setColor(color[0] * 0.4, color[1] * 0.4, color[2] * 0.4, color[3])
        self._apply_texture(bottom, texture_name, "bottom")
        
        cube.setPos(x, y, z)
        return cube
        
    def _apply_texture(self, node, texture_name, face):
        """Применение текстуры к грани"""
        # В реальной игре здесь была бы загрузка и применение текстур
        # Пока что просто применяем базовый цвет
        pass
        
    def _start_animations(self):
        """Запуск анимаций персонажа"""
        from direct.task import Task
        
        def animate_character(task):
            current_time = time.time()
            self.animation_time = current_time
            
            # Анимация покачивания (idle)
            if self.animation_state == "idle":
                self.bob_offset = math.sin(current_time * 2) * 0.05
                if self.node:
                    self.node.setZ(self.z + self.bob_offset)
                
                # Анимация дыхания
                breath_scale = 1.0 + math.sin(current_time * 3) * 0.02
                if self.node:
                    self.node.setScale(breath_scale)
                
            # Анимация ходьбы
            elif self.animation_state == "walking":
                walk_cycle = math.sin(current_time * 4) * 0.1
                self.bob_offset = walk_cycle
                if self.node:
                    self.node.setZ(self.z + self.bob_offset)
                
                # Анимация рук
                arm_swing = math.sin(current_time * 4) * 0.3
                if hasattr(self, 'left_arm'):
                    self.left_arm.setHpr(arm_swing, 0, 0)
                if hasattr(self, 'right_arm'):
                    self.right_arm.setHpr(-arm_swing, 0, 0)
                    
            # Анимация атаки
            elif self.animation_state == "attacking":
                attack_progress = (current_time - self.attack_start_time) / 0.5
                if attack_progress < 1.0:
                    # Анимация замаха
                    swing_angle = math.sin(attack_progress * math.pi) * 0.5
                    if hasattr(self, 'right_arm'):
                        self.right_arm.setHpr(swing_angle, 0, 0)
                else:
                    # Возврат к idle
                    self.animation_state = "idle"
                    
            # Анимация магических эффектов
            if self.character_class == "mage" and hasattr(self, 'orb'):
                orb_glow = 1.0 + math.sin(current_time * 5) * 0.2
                self.orb.setScale(orb_glow)
                
                # Вращение орба
                self.orb.setHpr(current_time * 30, 0, 0)
                
            return Task.cont
            
        self.game.showbase.taskMgr.add(animate_character, "character_animation")
        
    def set_animation_state(self, state):
        """Установка состояния анимации"""
        self.animation_state = state
        if state == "attacking":
            self.attack_start_time = time.time()
            
    def move_to(self, x, y, z=None):
        """Перемещение персонажа"""
        self.x = x
        self.y = y
        if z is not None:
            self.z = z
        if self.node:
            self.node.setPos(self.x, self.y, self.z)
            self.set_animation_state("walking")
            
    def move_by(self, dx, dy, dz=0, dt=0.016):
        """Перемещение персонажа на относительное расстояние"""
        move_speed = self.speed * dt
        self.x += dx * move_speed
        self.y += dy * move_speed
        self.z += dz * move_speed
        if self.node:
            self.node.setPos(self.x, self.y, self.z)
            if dx != 0 or dy != 0:
                self.set_animation_state("walking")
            else:
                self.set_animation_state("idle")
                
    def attack(self, target):
        """Атака цели"""
        if self.attack_cooldown <= 0 and self.is_alive():
            self.set_animation_state("attacking")
            
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
                is_critical = random.random() * 100 < self.critical_chance
                if is_critical:
                    base_damage *= (self.critical_damage / 100)
                    logger.info("Critical hit!")
                
                # Атакуем цель
                target.take_damage(base_damage, "physical")
                self.attack_cooldown = self.attack_cooldown_time
                logger.info(f"Player attacked enemy for {base_damage:.1f} damage!")
                return True
        return False
        
    def is_alive(self):
        """Проверка, жив ли персонаж"""
        return self.health > 0
        
    def take_damage(self, damage, damage_type="physical"):
        """Получение урона"""
        actual_damage = max(1, damage - self.defense)
        self.health = max(0, self.health - actual_damage)
        return self.health <= 0
        
    def update_ai(self, enemies, items, dt, exit_position=None, vision_range: float = 0.0,
                  known_exit_positions: Optional[List[Tuple[float, float]]] = None,
                  hint_positions: Optional[List[Tuple[float, float]]] = None):
        """Обновление ИИ персонажа.

        :param exit_position: текущие координаты маяка выхода (если известны системе сцены)
        :param vision_range: дистанция, на которой герой может «увидеть» маяк визуально
        :param known_exit_positions: подсказки о координатах выхода, полученные от карт / NPC
        :param hint_positions: позиции объектов-подсказок (карты/NPC), которые стоит посетить
        до получения точного местоположения выхода
        """
        if not self.ai_enabled or not self.is_alive():
            return
            
        current_time = time.time()
        if current_time - self.last_ai_update < self.ai_update_interval:
            return
            
        self.last_ai_update = current_time
        
        # Определяем ближайшего врага
        nearest_enemy = self._find_nearest_enemy(enemies)

        # 1. Бой и преследование врагов
        # Если здоровье низкое, приоритет — выживание: отходим от врага.
        if nearest_enemy and self.health <= self.max_health * 0.3 and self.get_distance_to(nearest_enemy) <= 12:
            self.ai_state = "retreating"
            self._move_away_from_enemy(nearest_enemy, dt)
            return

        if nearest_enemy and self.get_distance_to(nearest_enemy) <= self.attack_range:
            # Враг в зоне атаки - атакуем
            self.ai_state = "fighting"
            self.target_enemy = nearest_enemy
            self.attack(nearest_enemy)
            return
        elif nearest_enemy and self.get_distance_to(nearest_enemy) <= 10:
            # Враг рядом - преследуем
            self.ai_state = "fighting"
            self.target_enemy = nearest_enemy
            self._move_towards_enemy(nearest_enemy, dt)
            return

        # 2. Лутинг и взаимодействие с найденными интерактивными объектами (например, сундуки)
        nearest_item = self._find_nearest_item(items)
        if nearest_item:
            item_x, item_y = self._extract_item_position(nearest_item)
            if item_x is not None and item_y is not None:
                # Не уходим в бесконечный лут-маршрут через всю карту:
                # лутим только достижимые/ближние интерактивные объекты.
                dist_to_item = math.sqrt((self.x - item_x) ** 2 + (self.y - item_y) ** 2)
                if dist_to_item <= 30.0:
                    self.ai_state = "looting"
                    self.move_towards(item_x, item_y, dt)
                    return

        # 3. Поиск выхода на следующий уровень
        target_exit = self._select_best_exit_target(
            known_exit_positions=known_exit_positions,
            exit_position=exit_position,
            vision_range=vision_range,
        )

        if target_exit:
            self.ai_state = "seeking_exit"
            self.move_towards(target_exit[0], target_exit[1], dt)
            return

        # 4. Если выход неизвестен, но есть доступные подсказки — идём к ближайшей.
        hint_target = self._select_best_hint_target(hint_positions)
        if hint_target:
            self.ai_state = "seeking_hint"
            self.move_towards(hint_target[0], hint_target[1], dt)
            return

        # 5. Нет врагов, лута и информации о выходе — фоновое исследование
        self.ai_state = "exploring"
        self.target_enemy = None
        self._explore_area(dt)
    

    def _select_best_hint_target(self, hint_positions=None):
        """Выбор ближайшей позиции подсказки (карта/NPC)."""
        candidates = []
        for pos in hint_positions or []:
            if not isinstance(pos, (tuple, list)) or len(pos) < 2:
                continue
            try:
                hx, hy = float(pos[0]), float(pos[1])
            except (TypeError, ValueError):
                continue
            dist = math.sqrt((self.x - hx) ** 2 + (self.y - hy) ** 2)
            candidates.append((dist, (hx, hy)))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _select_best_exit_target(self, known_exit_positions=None, exit_position=None, vision_range: float = 0.0):
        """Выбор наилучшей цели выхода: ближайшая известная/видимая точка."""
        candidates = []

        for pos in known_exit_positions or []:
            if not isinstance(pos, (tuple, list)) or len(pos) < 2:
                continue
            try:
                ex, ey = float(pos[0]), float(pos[1])
            except (TypeError, ValueError):
                continue
            dist = math.sqrt((self.x - ex) ** 2 + (self.y - ey) ** 2)
            candidates.append((dist, (ex, ey)))

        if exit_position and len(exit_position) >= 2 and vision_range > 0.0:
            try:
                ex, ey = float(exit_position[0]), float(exit_position[1])
            except (TypeError, ValueError):
                ex, ey = None, None
            if ex is not None and ey is not None:
                dist = math.sqrt((self.x - ex) ** 2 + (self.y - ey) ** 2)
                if dist <= vision_range:
                    candidates.append((dist, (ex, ey)))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _find_nearest_enemy(self, enemies):
        """Поиск ближайшего врага"""
        nearest_enemy = None
        nearest_distance = float('inf')
        
        for enemy in enemies:
            if enemy.is_alive():
                distance = self.get_distance_to(enemy)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_enemy = enemy
                    
        return nearest_enemy
    
    def _find_nearest_item(self, items):
        """Поиск ближайшего интерактивного объекта (например, сундука)."""
        nearest_item = None
        nearest_distance = float('inf')

        for item in items or []:
            item_x, item_y = self._extract_item_position(item)
            if item_x is None or item_y is None:
                continue

            distance = math.sqrt((self.x - item_x) ** 2 + (self.y - item_y) ** 2)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_item = item

        return nearest_item

    def _extract_item_position(self, item):
        """Извлекает 2D-позицию объекта для навигации ИИ."""
        if hasattr(item, 'x') and hasattr(item, 'y'):
            return item.x, item.y

        if hasattr(item, 'getPos'):
            pos = item.getPos()
            if hasattr(pos, 'x') and hasattr(pos, 'y'):
                return pos.x, pos.y
            if isinstance(pos, (tuple, list)) and len(pos) >= 2:
                return pos[0], pos[1]

        if hasattr(item, 'get_position'):
            x, y, _ = item.get_position()
            return x, y

        return None, None

    def _move_away_from_enemy(self, enemy, dt):
        """Отход от врага при критическом здоровье."""
        if hasattr(enemy, 'x') and hasattr(enemy, 'y'):
            dx = self.x - enemy.x
            dy = self.y - enemy.y
        elif hasattr(enemy, 'get_position'):
            ex, ey, _ = enemy.get_position()
            dx = self.x - ex
            dy = self.y - ey
        else:
            return

        distance = math.sqrt(dx * dx + dy * dy)
        if distance <= 0.001:
            # Если позиции совпали, делаем небольшой случайный рывок.
            self.move_by(1.0, 0.0, 0.0, dt)
            return

        # Нормализуем вектор от врага к персонажу и идем в этом направлении.
        dx /= distance
        dy /= distance
        retreat_target_x = self.x + dx * 5.0
        retreat_target_y = self.y + dy * 5.0
        self.move_towards(retreat_target_x, retreat_target_y, dt)

    def _move_towards_enemy(self, enemy, dt):
        """Движение к врагу"""
        if hasattr(enemy, 'x') and hasattr(enemy, 'y'):
            self.move_towards(enemy.x, enemy.y, dt)
        elif hasattr(enemy, 'get_position'):
            target_x, target_y, target_z = enemy.get_position()
            self.move_towards(target_x, target_y, dt)
    
    def _explore_area(self, dt):
        """Исследование области с устойчивой целевой точкой, а не хаотичными рывками."""
        import random

        now = time.time()
        need_new_target = (
            self.exploration_target is None
            or (now - self.last_exploration_target_time) >= self.exploration_retarget_interval
        )

        if need_new_target:
            self.exploration_target = (
                self.x + random.uniform(-8.0, 8.0),
                self.y + random.uniform(-8.0, 8.0),
            )
            self.last_exploration_target_time = now

        tx, ty = self.exploration_target
        self.move_towards(tx, ty, dt)

        # Если приблизились к точке — выбираем новую на следующем тике.
        if math.sqrt((self.x - tx) ** 2 + (self.y - ty) ** 2) <= 0.75:
            self.exploration_target = None
    
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
            move_distance = self.speed * dt
            self.x += dx * move_distance
            self.y += dy * move_distance
            
            if self.node:
                self.node.setPos(self.x, self.y, self.z)
                self.set_animation_state("walking")
                
            # Поворачиваем персонажа лицом к цели
            angle = math.atan2(dy, dx) * 180 / math.pi
            if self.node:
                self.node.setHpr(angle, 0, 0)
    
    def get_distance_to(self, target):
        """Получение расстояния до цели"""
        if hasattr(target, 'x') and hasattr(target, 'y'):
            return math.sqrt((self.x - target.x)**2 + (self.y - target.y)**2)
        elif hasattr(target, 'get_position'):
            target_x, target_y, target_z = target.get_position()
            return math.sqrt((self.x - target_x)**2 + (self.y - target_y)**2)
        return float('inf')
    
    def use_skill_automatically(self, enemies, dt):
        """Автоматическое использование скилов."""
        if not self.is_alive():
            return

        # Защитные/выживательные действия имеют приоритет над атакой,
        # но ограничены кулдауном, чтобы не спамить каждый тик.
        now = time.time()
        defensive_ready = (now - self.last_defensive_skill_time) >= self.defensive_skill_cooldown
        if defensive_ready and self.health <= self.max_health * 0.4:
            if self.character_class == "mage" and self.mana >= 15 and self.health < self.max_health:
                if self._cast_self_heal():
                    self.last_defensive_skill_time = now
                    return
            if self.character_class in ("warrior", "rogue") and self.stamina >= 25 and self.health < self.max_health:
                if self._use_second_wind():
                    self.last_defensive_skill_time = now
                    return

        # Простое использование скилов на основе класса
        if self.character_class == "warrior":
            # Воин использует атаку ближайшего врага
            nearest_enemy = self._find_nearest_enemy(enemies)
            if nearest_enemy and self.get_distance_to(nearest_enemy) <= self.attack_range:
                self.attack(nearest_enemy)
        elif self.character_class == "mage":
            # Маг использует магические атаки
            if self.mana >= 10:  # Требует маны
                nearest_enemy = self._find_nearest_enemy(enemies)
                if nearest_enemy and self.get_distance_to(nearest_enemy) <= self.attack_range * 2:
                    self._cast_magic_attack(nearest_enemy)
        elif self.character_class == "rogue":
            # Разбойник использует скрытность и критические атаки
            if self.stamina >= 20:  # Требует выносливости
                nearest_enemy = self._find_nearest_enemy(enemies)
                if nearest_enemy and self.get_distance_to(nearest_enemy) <= self.attack_range:
                    self._stealth_attack(nearest_enemy)
    
    def _cast_self_heal(self):
        """Самоисцеление мага за счет маны."""
        if self.mana < 15 or self.health >= self.max_health:
            return False
        self.mana -= 15
        heal_amount = 20
        self.health = min(self.max_health, self.health + heal_amount)
        return True

    def _use_second_wind(self):
        """Экстренное восстановление воина/разбойника за счет выносливости."""
        if self.stamina < 25 or self.health >= self.max_health:
            return False
        self.stamina -= 25
        heal_amount = 15
        self.health = min(self.max_health, self.health + heal_amount)
        return True

    def _cast_magic_attack(self, target):
        """Магическая атака"""
        if self.mana >= 10:
            self.mana -= 10
            damage = self.magical_damage
            target.take_damage(damage, "magical")
            logger.info(f"Маг атаковал врага магией на {damage} урона!")
    
    def _stealth_attack(self, target):
        """Скрытная атака"""
        if self.stamina >= 20:
            self.stamina -= 20
            damage = self.physical_damage * 1.5  # Увеличенный урон
            target.take_damage(damage, "physical")
            logger.info(f"Разбойник атаковал врага скрытно на {damage} урона!")
    
    def destroy(self):
        """Уничтожение персонажа"""
        if self.node:
            self.node.removeNode()
            self.node = None
    
    # Методы игрока
    def add_achievement(self, achievement: str):
        """Добавление достижения"""
        if self.is_player and achievement not in self.achievements:
            self.achievements.append(achievement)
            logger.info(f"Достижение получено: {achievement}")
    
    def complete_quest(self, quest_id: str):
        """Завершение квеста"""
        if self.is_player and quest_id not in self.quests_completed:
            self.quests_completed.append(quest_id)
            self.experience += 100  # Награда за квест
            logger.info(f"Квест завершен: {quest_id}")
    
    def visit_location(self, location: str):
        """Посещение локации"""
        if self.is_player and location not in self.locations_visited:
            self.locations_visited.append(location)
            logger.info(f"Локация посещена: {location}")
    
    def meet_npc(self, npc_id: str):
        """Встреча с NPC"""
        if self.is_player and npc_id not in self.npcs_met:
            self.npcs_met.append(npc_id)
            logger.info(f"Встречен NPC: {npc_id}")
    
    def update_playtime(self, dt: float):
        """Обновление времени игры"""
        if self.is_player:
            self.total_playtime += dt
    
    def save_game(self):
        """Сохранение игры"""
        if self.is_player:
            self.last_save = time.time()
            logger.info("Игра сохранена")
    
    def get_player_stats(self):
        """Получение статистики игрока"""
        if not self.is_player:
            return None
        
        return {
            'reputation': self.reputation,
            'fame': self.fame,
            'achievements_count': len(self.achievements),
            'quests_completed_count': len(self.quests_completed),
            'locations_visited_count': len(self.locations_visited),
            'npcs_met_count': len(self.npcs_met),
            'total_playtime': self.total_playtime,
            'charisma_bonus': self.charisma_bonus,
            'persuasion_skill': self.persuasion_skill
        }
