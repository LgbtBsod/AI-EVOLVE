#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import time
import random
from typing import Dict, List, Optional, Any
from panda3d.core import CardMaker, Vec3, Vec4, TransparencyAttrib

class EnhancedGameScene:
    """Улучшенная игровая сцена с правильным рендерингом"""
    
    def __init__(self, game):
        self.game = game
        self.player = None
        self.enemies = []
        self.hud = None
        self.world_objects = []
        self.is_paused = False
        
        # Настройки мира
        self.world_size = 50
        self.enemy_spawn_rate = 0.1  # Вероятность появления врага за кадр
        self.max_enemies = 10
        
        # Время
        self.last_enemy_spawn = 0
        self.enemy_spawn_interval = 3.0  # Интервал между появлениями врагов
        
        # Система создания объектов игроком
        self.player_created_objects = []
        self.creation_mode = None  # None, "enemy", "trap", "chest"
        
        # Маяк смерти
        self.death_beacon = None
        self.death_position = None
        
    def enter(self):
        """Вход в игровую сцену"""
        print("Entering enhanced game scene...")
        
        # Создаем игровой мир
        self._create_world()
        
        # Создаем игрока
        self._create_player()
        
        # Создаем HUD
        self._create_hud()
        
        # Создаем начальных врагов
        self._spawn_initial_enemies()
        
        # Настраиваем камеру
        self._setup_camera()
        
        print("Enhanced game scene initialized!")
        
    def _create_world(self):
        """Создание игрового мира"""
        # Создаем землю
        self._create_ground()
        
        # Создаем стены
        self._create_walls()
        
        # Создаем декоративные объекты
        self._create_decorations()
        
    def _create_ground(self):
        """Создание земли"""
        # Создаем большую плоскость для земли
        ground = self.game.render.attachNewNode("ground")
        
        # Создаем землю из карточек
        cm = CardMaker("ground")
        cm.setFrame(-self.world_size/2, self.world_size/2, -self.world_size/2, self.world_size/2)
        ground_plane = ground.attachNewNode(cm.generate())
        ground_plane.setPos(0, 0, 0)
        ground_plane.setHpr(0, 0, 0)
        ground_plane.setColor(0.3, 0.6, 0.3, 1)  # Зеленый цвет травы
        
        self.world_objects.append(ground)
        
    def _create_walls(self):
        """Создание стен по периметру"""
        wall_height = 3
        wall_thickness = 0.5
        
        # Северная стена
        north_wall = self._create_wall_segment(
            -self.world_size/2, self.world_size/2, 
            self.world_size/2, self.world_size/2,
            wall_height, wall_thickness
        )
        self.world_objects.append(north_wall)
        
        # Южная стена
        south_wall = self._create_wall_segment(
            -self.world_size/2, -self.world_size/2,
            self.world_size/2, -self.world_size/2,
            wall_height, wall_thickness
        )
        self.world_objects.append(south_wall)
        
        # Западная стена
        west_wall = self._create_wall_segment(
            -self.world_size/2, -self.world_size/2,
            -self.world_size/2, self.world_size/2,
            wall_height, wall_thickness
        )
        self.world_objects.append(west_wall)
        
        # Восточная стена
        east_wall = self._create_wall_segment(
            self.world_size/2, -self.world_size/2,
            self.world_size/2, self.world_size/2,
            wall_height, wall_thickness
        )
        self.world_objects.append(east_wall)
        
    def _create_wall_segment(self, x1, y1, x2, y2, height, thickness):
        """Создание сегмента стены"""
        wall = self.game.render.attachNewNode("wall")
        
        # Вычисляем центр и размеры стены
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        width = abs(x2 - x1)
        depth = abs(y2 - y1)
        
        # Создаем стену как куб
        self._create_visible_cube(
            wall, "wall_body", 0, 0, height/2, 
            width, depth, height, (0.6, 0.6, 0.6, 1)
        )
        
        wall.setPos(center_x, center_y, 0)
        return wall
        
    def _create_visible_cube(self, parent, name, x, y, z, width, height, depth, color):
        """Создание видимого куба с правильной ориентацией"""
        cube = parent.attachNewNode(name)
        
        # Передняя грань
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
        
    def _create_decorations(self):
        """Создание декоративных объектов"""
        # Создаем несколько деревьев
        for i in range(5):
            x = random.uniform(-self.world_size/2 + 2, self.world_size/2 - 2)
            y = random.uniform(-self.world_size/2 + 2, self.world_size/2 - 2)
            self._create_tree(x, y)
            
        # Создаем несколько камней
        for i in range(8):
            x = random.uniform(-self.world_size/2 + 2, self.world_size/2 - 2)
            y = random.uniform(-self.world_size/2 + 2, self.world_size/2 - 2)
            self._create_rock(x, y)
            
    def _create_tree(self, x, y):
        """Создание дерева"""
        tree = self.game.render.attachNewNode("tree")
        
        # Ствол
        trunk = self._create_visible_cube(
            tree, "trunk", 0, 0, 0.5, 0.3, 0.3, 1.0, (0.4, 0.2, 0.1, 1)
        )
        
        # Крона
        leaves = self._create_visible_cube(
            tree, "leaves", 0, 0, 1.5, 1.2, 1.2, 1.0, (0.2, 0.8, 0.2, 1)
        )
        
        tree.setPos(x, y, 0)
        self.world_objects.append(tree)
        
    def _create_rock(self, x, y):
        """Создание камня"""
        rock = self.game.render.attachNewNode("rock")
        
        # Создаем камень как куб
        self._create_visible_cube(
            rock, "rock_body", 0, 0, 0.2, 0.8, 0.8, 0.4, (0.5, 0.5, 0.5, 1)
        )
        
        rock.setPos(x, y, 0)
        self.world_objects.append(rock)
        
    def _create_player(self):
        """Создание игрока"""
        from src.entities.character import Character
        
        # Создаем игрока немного выше земли
        self.player = Character("player_1", self.game, 0, 0, 0.5, "warrior", (0, 0, 1, 1), is_player=True)  # Синий цвет
        self.player.create_character()
        
    def _create_hud(self):
        """Создание HUD"""
        from src.ui.hud import EnhancedHUD
        
        self.hud = EnhancedHUD(self.game)
        self.hud.create_hud()
        
    def _spawn_initial_enemies(self):
        """Создание начальных врагов"""
        from src.entities.enemy import EnhancedEnemy
        
        # Создаем несколько врагов в разных местах
        enemy_positions = [
            (5, 5, 0.5),
            (-5, 5, 0.5),
            (5, -5, 0.5),
            (-5, -5, 0.5)
        ]
        
        for i, (x, y, z) in enumerate(enemy_positions):
            enemy_type = "basic" if i < 2 else "strong"
            enemy = EnhancedEnemy(self.game, x, y, z, enemy_type)
            enemy.create_enemy()
            self.enemies.append(enemy)
            
    def _setup_camera(self):
        """Настройка камеры"""
        if hasattr(self.game, 'render_system'):
            # Используем изометрическую камеру
            self.game.render_system.switch_camera("isometric")
        else:
            # Простая настройка камеры - изометрический вид
            if hasattr(self.game, 'cam'):
                # Позиционируем камеру для изометрического вида
                self.game.cam.setPos(15, -15, 12)
                self.game.cam.lookAt(0, 0, 0)
                # Устанавливаем правильный угол для изометрии
                self.game.cam.setHpr(45, -30, 0)
                
                # Запускаем задачу следования камеры за игроком
                self._start_camera_follow()
    
    def _start_camera_follow(self):
        """Запуск следования камеры за игроком"""
        def follow_player(task):
            if self.player and hasattr(self.game, 'cam'):
                # Получаем позицию игрока
                player_x = self.player.x
                player_y = self.player.y
                player_z = self.player.z
                
                # Позиционируем камеру для изометрического вида
                camera_offset_x = 20
                camera_offset_y = -20
                camera_offset_z = 15
                
                self.game.cam.setPos(
                    player_x + camera_offset_x,
                    player_y + camera_offset_y,
                    player_z + camera_offset_z
                )
                # Устанавливаем правильный угол для изометрии
                self.game.cam.setHpr(45, -30, 0)
                
            return task.cont
            
        self.game.showbase.taskMgr.add(follow_player, "camera_follow")
                
    def update(self, dt):
        """Обновление игровой сцены"""
        if self.is_paused:
            return
            
        # Обновляем игрока
        if self.player:
            # Обновляем кулдаун атаки
            if self.player.attack_cooldown > 0:
                self.player.attack_cooldown -= dt
            if self.player.attack_cooldown < 0:
                self.player.attack_cooldown = 0
                
            # Восстанавливаем характеристики
            self.player.health = min(self.player.max_health, self.player.health + self.player.health_regen * dt)
            self.player.mana = min(self.player.max_mana, self.player.mana + self.player.mana_regen * dt)
            self.player.stamina = min(self.player.max_stamina, self.player.stamina + self.player.stamina_regen * dt)
            
            # Обновляем ИИ персонажа
            self.player.update_ai(self.enemies, [], dt)
            
            # Автоматическое использование скилов
            self.player.use_skill_automatically(self.enemies, dt)
            
        # Обновляем врагов
        for enemy in self.enemies[:]:  # Используем копию списка для безопасного удаления
            if enemy.is_alive():
                enemy.update_ai(self.player, dt)
            else:
                # Удаляем мертвых врагов
                enemy.destroy()
                self.enemies.remove(enemy)
                
        # Спавним новых врагов
        self._spawn_enemies(dt)
        
        # Обновляем HUD
        if self.hud and self.player:
            self.hud.update_hud(self.player)
            
        # Проверяем смерть персонажа
        if self.player and not self.player.is_alive():
            self._handle_player_death()
            
    def _spawn_enemies(self, dt):
        """Спавн новых врагов"""
        current_time = time.time()
        
        # Проверяем, можно ли заспавнить нового врага
        if (current_time - self.last_enemy_spawn >= self.enemy_spawn_interval and 
            len(self.enemies) < self.max_enemies):
            
            from src.entities.enemy import EnhancedEnemy
            
            # Выбираем случайную позицию на краю карты
            side = random.randint(0, 3)
            if side == 0:  # Север
                x = random.uniform(-self.world_size/2 + 2, self.world_size/2 - 2)
                y = self.world_size/2 - 2
            elif side == 1:  # Юг
                x = random.uniform(-self.world_size/2 + 2, self.world_size/2 - 2)
                y = -self.world_size/2 + 2
            elif side == 2:  # Запад
                x = -self.world_size/2 + 2
                y = random.uniform(-self.world_size/2 + 2, self.world_size/2 - 2)
            else:  # Восток
                x = self.world_size/2 - 2
                y = random.uniform(-self.world_size/2 + 2, self.world_size/2 - 2)
            
            # Выбираем тип врага
            enemy_types = ["basic", "strong", "elite"]
            enemy_type = random.choices(enemy_types, weights=[70, 25, 5])[0]
            
            # Создаем врага
            enemy = EnhancedEnemy(self.game, x, y, 0, enemy_type)
            enemy.create_enemy()
            self.enemies.append(enemy)
            
            self.last_enemy_spawn = current_time
            
    def handle_input(self, keys):
        """Обработка ввода"""
        if self.is_paused:
            return
            
        if not self.player:
            return
            
        # Движение игрока
        move_speed = 5.0
        dx = 0
        dy = 0
        
        if keys.get('w', False) or keys.get('W', False):
            dy += 1
        if keys.get('s', False) or keys.get('S', False):
            dy -= 1
        if keys.get('a', False) or keys.get('A', False):
            dx -= 1
        if keys.get('d', False) or keys.get('D', False):
            dx += 1
            
        # Нормализуем движение по диагонали
        if dx != 0 and dy != 0:
            dx *= 0.707
            dy *= 0.707
            
        # Перемещаем игрока
        if dx != 0 or dy != 0:
            self.player.move_by(dx, dy, 0, 0.016)
            # Обновляем анимацию
            self.player.set_animation_state("walking")
        else:
            # Если не двигаемся, переходим в idle
            self.player.set_animation_state("idle")
            
        # Атака ближайшего врага
        if keys.get('space', False):
            self._attack_nearest_enemy()
            
        # Создание объектов
        if keys.get('1', False):
            self.creation_mode = "enemy"
            self._create_object_at_player()
        elif keys.get('2', False):
            self.creation_mode = "trap"
            self._create_object_at_player()
        elif keys.get('3', False):
            self.creation_mode = "chest"
            self._create_object_at_player()
            
    def _attack_nearest_enemy(self):
        """Атака ближайшего врага"""
        if not self.player:
            return
            
        nearest_enemy = None
        nearest_distance = float('inf')
        
        for enemy in self.enemies:
            if enemy.is_alive():
                distance = self.player.get_distance_to(enemy)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_enemy = enemy
                    
        if nearest_enemy and nearest_distance <= self.player.attack_range:
            self.player.attack(nearest_enemy)
            
    def pause(self):
        """Пауза игры"""
        self.is_paused = True
        
    def resume(self):
        """Возобновление игры"""
        self.is_paused = False
        
    def exit(self):
        """Выход из игровой сцены"""
        # Уничтожаем игрока
        if self.player:
            self.player.destroy()
            self.player = None
            
        # Уничтожаем врагов
        for enemy in self.enemies:
            enemy.destroy()
        self.enemies.clear()
        
        # Уничтожаем HUD
        if self.hud:
            self.hud.destroy()
            self.hud = None
            
        # Уничтожаем объекты мира
        for obj in self.world_objects:
            if hasattr(obj, 'removeNode'):
                obj.removeNode()
        self.world_objects.clear()
        
        # Удаляем маяк смерти
        self._remove_death_beacon()
        
        print("Enhanced game scene exited!")
    
    def _create_object_at_player(self):
        """Создание объекта рядом с игроком"""
        if not self.player:
            return
            
        # Создаем объект рядом с игроком
        offset_x = random.uniform(-3, 3)
        offset_y = random.uniform(-3, 3)
        x = self.player.x + offset_x
        y = self.player.y + offset_y
        z = 0.5
        
        if self.creation_mode == "enemy":
            self._create_enemy_at(x, y, z)
        elif self.creation_mode == "trap":
            self._create_trap_at(x, y, z)
        elif self.creation_mode == "chest":
            self._create_chest_at(x, y, z)
            
        print(f"Создан {self.creation_mode} в позиции ({x:.1f}, {y:.1f})")
    
    def _create_enemy_at(self, x, y, z):
        """Создание врага в указанной позиции"""
        from src.entities.enemy import EnhancedEnemy
        
        enemy_types = ["basic", "strong", "elite"]
        enemy_type = random.choice(enemy_types)
        
        enemy = EnhancedEnemy(self.game, x, y, z, enemy_type)
        enemy.create_enemy()
        self.enemies.append(enemy)
        self.player_created_objects.append(enemy)
    
    def _create_trap_at(self, x, y, z):
        """Создание ловушки в указанной позиции"""
        trap = self.game.render.attachNewNode("trap")
        
        # Создаем ловушку как куб
        self._create_visible_cube(
            trap, "trap_body", 0, 0, 0.2, 1.0, 1.0, 0.4, (0.8, 0.4, 0.2, 1)
        )
        
        trap.setPos(x, y, z)
        self.world_objects.append(trap)
        self.player_created_objects.append(trap)
        
        # Добавляем логику ловушки
        self._add_trap_logic(trap, x, y, z)
    
    def _create_chest_at(self, x, y, z):
        """Создание сундука в указанной позиции"""
        chest = self.game.render.attachNewNode("chest")
        
        # Создаем сундук как куб
        self._create_visible_cube(
            chest, "chest_body", 0, 0, 0.3, 1.2, 0.8, 0.6, (0.6, 0.4, 0.2, 1)
        )
        
        # Крышка сундука
        self._create_visible_cube(
            chest, "chest_lid", 0, 0, 0.6, 1.2, 0.8, 0.1, (0.7, 0.5, 0.3, 1)
        )
        
        chest.setPos(x, y, z)
        self.world_objects.append(chest)
        self.player_created_objects.append(chest)
        
        # Добавляем логику сундука
        self._add_chest_logic(chest, x, y, z)
    
    def _add_trap_logic(self, trap, x, y, z):
        """Добавление логики ловушки"""
        def check_trap_trigger(task):
            if self.player:
                distance = math.sqrt((self.player.x - x)**2 + (self.player.y - y)**2)
                if distance <= 1.5:  # Радиус срабатывания
                    # Ловушка срабатывает
                    self.player.take_damage(20, "physical")
                    print("Ловушка сработала!")
                    # Удаляем ловушку после срабатывания
                    trap.removeNode()
                    if trap in self.world_objects:
                        self.world_objects.remove(trap)
                    if trap in self.player_created_objects:
                        self.player_created_objects.remove(trap)
                    return task.done
            return task.cont
            
        self.game.showbase.taskMgr.add(check_trap_trigger, f"trap_{id(trap)}")
    
    def _add_chest_logic(self, chest, x, y, z):
        """Добавление логики сундука"""
        def check_chest_interaction(task):
            if self.player:
                distance = math.sqrt((self.player.x - x)**2 + (self.player.y - y)**2)
                if distance <= 2.0:  # Радиус взаимодействия
                    # Игрок может открыть сундук
                    if hasattr(self.player, 'keys') and 'e' in self.player.keys and self.player.keys['e']:
                        # Открываем сундук
                        self._open_chest(chest, x, y, z)
                        return task.done
            return task.cont
            
        self.game.showbase.taskMgr.add(check_chest_interaction, f"chest_{id(chest)}")
    
    def _open_chest(self, chest, x, y, z):
        """Открытие сундука"""
        # Даем игроку награду
        if self.player:
            self.player.experience += 50
            self.player.health = min(self.player.max_health, self.player.health + 25)
            print("Сундук открыт! Получено: 50 опыта, 25 здоровья")
        
        # Анимация открытия
        chest.setHpr(0, 0, 45)  # Поворачиваем крышку
        
        # Удаляем сундук через некоторое время
        def remove_chest(task):
            chest.removeNode()
            if chest in self.world_objects:
                self.world_objects.remove(chest)
            if chest in self.player_created_objects:
                self.player_created_objects.remove(chest)
            return task.done
            
        self.game.showbase.taskMgr.doMethodLater(2.0, remove_chest, f"remove_chest_{id(chest)}")
    
    def _handle_player_death(self):
        """Обработка смерти персонажа"""
        if not self.death_beacon and self.player:
            # Сохраняем позицию смерти
            self.death_position = (self.player.x, self.player.y, self.player.z)
            
            # Создаем маяк смерти
            self._create_death_beacon()
            
            # Переходим к экрану смерти
            if hasattr(self.game, 'state_manager'):
                self.game.state_manager.change_state("death")
    
    def _create_death_beacon(self):
        """Создание маяка смерти"""
        if not self.death_position:
            return
            
        try:
            # Создаем маяк в месте смерти персонажа
            self.death_beacon = self.game.render.attachNewNode("death_beacon")
            
            # Создаем маяк как светящийся столб
            from panda3d.core import CardMaker
            cm = CardMaker("beacon")
            cm.setFrame(-0.5, 0.5, -0.5, 0.5)
            beacon_plane = self.death_beacon.attachNewNode(cm.generate())
            beacon_plane.setColor(1, 0, 0, 0.8)  # Красный цвет
            
            # Позиционируем маяк
            self.death_beacon.setPos(*self.death_position)
            self.death_beacon.setHpr(0, 0, 0)
            
            # Анимация маяка
            self._animate_death_beacon()
            
            print(f"Маяк смерти создан в позиции {self.death_position}")
            
        except Exception as e:
            print(f"Ошибка создания маяка смерти: {e}")
    
    def _animate_death_beacon(self):
        """Анимация маяка смерти"""
        import time
        start_time = time.time()
        
        def animate_beacon(task):
            if not self.death_beacon:
                return task.done
                
            current_time = time.time()
            # Пульсация маяка
            scale = 1.0 + 0.3 * (current_time - start_time) % 2
            self.death_beacon.setScale(scale)
            
            # Вращение
            self.death_beacon.setHpr(0, 0, (current_time - start_time) * 30)
            
            return task.cont
            
        self.game.showbase.taskMgr.add(animate_beacon, "death_beacon_animation")
    
    def _remove_death_beacon(self):
        """Удаление маяка смерти"""
        if self.death_beacon:
            self.death_beacon.removeNode()
            self.death_beacon = None
            self.death_position = None
            print("Маяк смерти удален")
