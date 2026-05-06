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
        # Базовый размер был 50; увеличиваем линейный масштаб в 100 раз,
        # что даёт рост площади примерно в 10 000 раз.
        self.world_size = 50 * 100
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

        # Маяк выхода на следующий уровень
        self.exit_beacon = None
        self.exit_beacon_position = None
        self.player_vision_range = 30.0
        self.known_exit_positions = []
        self.map_hint_items = []
        self.npc_hints = []
        self.echo_trail_nodes = []
        self.echo_trail_points = []
        self._action_key_state = {}
        self.current_level = 1
        self.exit_reach_distance = 2.0
        self.echo_refresh_interval = 1.0
        self.last_echo_refresh_time = 0.0
        self._runtime_task_names = set()
        self._opened_chest_ids = set()
        
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

        # Создаем маяк выхода и подсказки (карты и NPC)
        self._create_exit_beacon()
        self._spawn_exit_hint_maps()
        self._spawn_exit_hint_npcs()
        
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

    def _create_exit_beacon(self):
        """Создание маяка выхода на следующий уровень в случайном месте карты."""
        from panda3d.core import CardMaker
        import random

        if self.exit_beacon:
            self.exit_beacon.removeNode()
            self.exit_beacon = None

        # Случайная позиция в пределах мира с небольшим отступом от краёв
        margin = self.world_size * 0.1
        x = random.uniform(-self.world_size / 2 + margin, self.world_size / 2 - margin)
        y = random.uniform(-self.world_size / 2 + margin, self.world_size / 2 - margin)
        z = 0.5

        self.exit_beacon_position = (x, y, z)
        self.exit_beacon = self.game.render.attachNewNode("exit_beacon")

        # Высокий светящийся столб, заметный издалека
        cm = CardMaker("exit_beacon_card")
        cm.setFrame(-0.5, 0.5, -5.0, 5.0)  # высокий прямоугольник
        card = self.exit_beacon.attachNewNode(cm.generate())
        card.setColor(1, 1, 0, 0.9)  # ярко-жёлтый
        card.setTransparency(TransparencyAttrib.MAlpha)

        self.exit_beacon.setPos(x, y, z)

    def _spawn_exit_hint_maps(self):
        """Создаёт несколько 'карт', которые раскрывают координаты маяка при подборе."""
        from panda3d.core import CardMaker
        import random

        # Простые визуальные маркеры неподалёку от стартовой области
        for i in range(2):
            mx = random.uniform(-20, 20)
            my = random.uniform(-20, 20)
            mz = 0.3

            node = self.game.render.attachNewNode(f"map_hint_{i}")
            cm = CardMaker(f"map_hint_card_{i}")
            cm.setFrame(-0.3, 0.3, -0.3, 0.3)
            card = node.attachNewNode(cm.generate())
            card.setColor(0.2, 0.6, 1.0, 0.9)  # голубая "карта"
            card.setTransparency(TransparencyAttrib.MAlpha)

            node.setPos(mx, my, mz)
            self.map_hint_items.append({"node": node, "used": False})

    def _spawn_exit_hint_npcs(self):
        """Создаёт несколько простых NPC-маркеров, часть из которых даёт подсказку о маяке."""
        from panda3d.core import CardMaker
        import random

        for i in range(3):
            nx = random.uniform(-40, 40)
            ny = random.uniform(-40, 40)
            nz = 0.3

            node = self.game.render.attachNewNode(f"npc_hint_{i}")
            cm = CardMaker(f"npc_hint_card_{i}")
            cm.setFrame(-0.4, 0.4, -0.8, 0.8)
            card = node.attachNewNode(cm.generate())

            # Не все NPC «знают» координаты выхода
            knows_exit = random.random() < 0.6
            if knows_exit:
                card.setColor(0.8, 0.8, 0.2, 0.9)  # жёлтоватый
            else:
                card.setColor(0.5, 0.5, 0.5, 0.9)  # серый

            card.setTransparency(TransparencyAttrib.MAlpha)
            node.setPos(nx, ny, nz)

            self.npc_hints.append({"node": node, "used": False, "knows_exit": knows_exit})
        
    def _create_ground(self):
        """Создание земли"""
        # Создаем большую плоскость для земли
        ground = self.game.render.attachNewNode("ground")
        
        # Создаем землю из карточек
        cm = CardMaker("ground")
        cm.setFrame(-self.world_size/2, self.world_size/2, -self.world_size/2, self.world_size/2)
        ground_plane = ground.attachNewNode(cm.generate())
        # Поворачиваем плоскость так, чтобы она лежала горизонтально (XZ),
        # а не была вертикальной «стенкой» вдоль камеры.
        ground_plane.setPos(0, 0, 0)
        ground_plane.setHpr(0, -90, 0)
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
        
        # Создаем несколько врагов на удалённых позициях по краям арены,
        # чтобы игрок сначала двигался, а не сразу вступал в бой.
        enemy_positions = [
            (self.world_size * 0.3, self.world_size * 0.3, 0.5),
            (-self.world_size * 0.3, self.world_size * 0.3, 0.5),
            (self.world_size * 0.3, -self.world_size * 0.3, 0.5),
            (-self.world_size * 0.3, -self.world_size * 0.3, 0.5)
        ]
        
        for i, (x, y, z) in enumerate(enemy_positions):
            enemy_type = "basic" if i < 2 else "strong"
            enemy = EnhancedEnemy(self.game, x, y, z, enemy_type)
            enemy.create_enemy()
            self.enemies.append(enemy)
            
    def _setup_camera(self):
        """Настройка камеры"""
        if hasattr(self.game, 'render_system'):
            # Пытаемся использовать изометрическую камеру из системы рендеринга
            # Если камера не найдена (например, RenderSystem не полностью инициализирован),
            # используем резервную ручную настройку камеры.
            switched = False
            try:
                switched = self.game.render_system.switch_camera("isometric")
            except Exception:
                switched = False

            if not switched and getattr(self.game, 'cam', None) is not None:
                # Резервный вариант — настраиваем камеру напрямую
                self.game.cam.setPos(15, -15, 12)
                self.game.cam.lookAt(0, 0, 0)
                self.game.cam.setHpr(45, -30, 0)
        else:
            # Простая настройка камеры - изометрический вид
            if getattr(self.game, 'cam', None) is not None:
                # Позиционируем камеру для изометрического вида
                self.game.cam.setPos(15, -15, 12)
                self.game.cam.lookAt(0, 0, 0)
                # Устанавливаем правильный угол для изометрии
                self.game.cam.setHpr(45, -30, 0)
                
                # Запускаем задачу следования камеры за игроком
                self._start_camera_follow()
    
    def _register_task_name(self, task_name: str):
        """Регистрирует имя runtime-задачи для последующей безопасной очистки."""
        if task_name:
            self._runtime_task_names.add(task_name)

    def _complete_runtime_task(self, task_name: str):
        """Отмечает runtime-задачу завершенной и исключает из реестра."""
        if task_name:
            self._runtime_task_names.discard(task_name)

    def _remove_runtime_tasks(self):
        """Удаляет runtime-задачи сцены из taskMgr, если он доступен."""
        task_mgr = getattr(getattr(self.game, "showbase", None), "taskMgr", None)
        if not task_mgr:
            self._runtime_task_names.clear()
            return

        for task_name in list(self._runtime_task_names):
            try:
                task_mgr.remove(task_name)
            except Exception:
                pass
        self._runtime_task_names.clear()

    def _start_camera_follow(self):
        """Запуск следования камеры за игроком"""
        def follow_player(task):
            if self.player and getattr(self.game, 'cam', None) is not None:
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
            
        task_name = "camera_follow"
        self._register_task_name(task_name)
        self.game.showbase.taskMgr.add(follow_player, task_name)
                
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
            ai_known_exits = list(self.known_exit_positions) + list(self.echo_trail_points)
            self.player.update_ai(
                self.enemies,
                self._get_interactive_items(),
                dt,
                exit_position=self.exit_beacon_position,
                vision_range=self.player_vision_range,
                known_exit_positions=ai_known_exits,
                hint_positions=self._get_hint_positions()
            )
            
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
                if enemy in self.player_created_objects:
                    self.player_created_objects.remove(enemy)
                
        # Спавним новых врагов
        self._spawn_enemies(dt)

        # Обрабатываем подсказки по картам и NPC (координаты выхода)
        if self.player:
            self._update_exit_hints(dt)
            self._check_exit_beacon_reached()
        
        # Поддерживаем актуальность эхо-тропы, пока точные координаты выхода не раскрыты.
        if self.player:
            self._refresh_echo_trail_guidance()

        # Обновляем HUD
        if self.hud and self.player:
            self.hud.update_hud(self.player)
            
        # Проверяем смерть персонажа
        if self.player and not self.player.is_alive():
            self._handle_player_death()
            
    def _get_interactive_items(self):
        """Список интерактивных объектов для AI (например, сундуков)."""
        chests = []
        for obj in self.player_created_objects:
            if hasattr(obj, 'getName') and obj.getName() == 'chest':
                chests.append(obj)
        return chests


    def _get_hint_positions(self):
        """Возвращает координаты еще не использованных подсказок (карты/NPC)."""
        points = []

        for hint in self.map_hint_items:
            if hint.get("used"):
                continue
            node = hint.get("node")
            if not node or not hasattr(node, "getPos"):
                continue
            hx, hy, _hz = node.getPos()
            points.append((hx, hy))

        for npc in self.npc_hints:
            if npc.get("used"):
                continue
            node = npc.get("node")
            if not node or not hasattr(node, "getPos"):
                continue
            nx, ny, _nz = node.getPos()
            points.append((nx, ny))

        return points

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

    def _update_exit_hints(self, dt):
        """Обновление подсказок о расположении маяка выхода.

        1) Карты: при подходе достаточно близко игрок автоматически «читает карту»
           и запоминает координаты маяка.
        2) NPC: при подходе к некоторым NPC (knows_exit=True) игрок получает
           такую же подсказку. Не все NPC обладают этой информацией."""
        px, py, pz = self.player.x, self.player.y, self.player.z

        # 1. Карты
        for hint in self.map_hint_items:
            if hint["used"]:
                continue
            node = hint["node"]
            hx, hy, hz = node.getPos()
            dist = math.sqrt((px - hx) ** 2 + (py - hy) ** 2)
            if dist <= 2.0:
                # Игрок «подобрал» карту — узнаёт точные координаты маяка
                self._register_exit_knowledge(precise=True)
                node.removeNode()
                hint["used"] = True

        # 2. NPC
        for npc in self.npc_hints:
            if npc["used"]:
                continue
            node = npc["node"]
            nx, ny, nz = node.getPos()
            dist = math.sqrt((px - nx) ** 2 + (py - ny) ** 2)
            if dist <= 3.0 and npc["knows_exit"]:
                # Этот NPC «подсказал» координаты выхода
                self._register_exit_knowledge(precise=True)
                npc["used"] = True
            elif dist <= 3.0:
                # Даже если NPC не знает точные координаты, он может дать «эхо-направление».
                self._register_exit_knowledge(precise=False)
                npc["used"] = True



    def _refresh_echo_trail_guidance(self):
        """Периодически обновляет эхо-тропу от текущей позиции героя к выходу.

        Это нужно, чтобы направляющие точки не "устаревали", если игрок
        существенно сместился после получения неполной подсказки от NPC."""
        if self.known_exit_positions:
            return
        if not self.echo_trail_points:
            return
        if not self.exit_beacon_position:
            return
        if not self.player or not hasattr(self.player, "x") or not hasattr(self.player, "y"):
            return

        now = time.time()
        if now - self.last_echo_refresh_time < self.echo_refresh_interval:
            return

        ex, ey, _ez = self.exit_beacon_position
        self._rebuild_echo_trail(ex, ey)
        self.last_echo_refresh_time = now

    def _register_exit_knowledge(self, precise: bool):
        """Регистрирует знания о выходе: точные координаты или цепочку эхо-точек."""
        if not self.exit_beacon_position:
            return

        ex, ey, _ez = self.exit_beacon_position
        if precise:
            self.known_exit_positions = [(ex, ey)]
            self._rebuild_echo_trail(ex, ey)
            self.last_echo_refresh_time = time.time()
            return

        # Неполная подсказка: строим эхо-тропу без раскрытия точной конечной точки в known_exit_positions.
        if not self.echo_trail_points:
            self._rebuild_echo_trail(ex, ey)
            self.last_echo_refresh_time = time.time()

    def _rebuild_echo_trail(self, target_x: float, target_y: float):
        """Пересоздаёт эхо-следы от текущей позиции игрока к выходу."""
        for node in self.echo_trail_nodes:
            if hasattr(node, "removeNode"):
                node.removeNode()
        self.echo_trail_nodes = []
        self.echo_trail_points = []

        if not self.player or not hasattr(self.player, "x") or not hasattr(self.player, "y"):
            return

        px, py = self.player.x, self.player.y
        steps = 4
        for idx in range(1, steps + 1):
            t = idx / (steps + 1)
            tx = px + (target_x - px) * t
            ty = py + (target_y - py) * t
            self.echo_trail_points.append((tx, ty))

            if not getattr(self.game, "render", None):
                continue
            marker = self.game.render.attachNewNode(f"echo_trail_{idx}")
            cm = CardMaker(f"echo_trail_card_{idx}")
            cm.setFrame(-0.2, 0.2, -0.2, 0.2)
            card = marker.attachNewNode(cm.generate())
            card.setColor(0.7, 0.9, 1.0, 0.8)
            card.setTransparency(TransparencyAttrib.MAlpha)
            marker.setPos(tx, ty, 0.35)
            self.echo_trail_nodes.append(marker)

    def _check_exit_beacon_reached(self):
        """Проверяет, достиг ли игрок маяка выхода, и запускает переход на новый уровень."""
        if not self.player or not self.exit_beacon_position:
            return
        if not hasattr(self.player, "x") or not hasattr(self.player, "y"):
            return

        ex, ey, _ez = self.exit_beacon_position
        distance = math.sqrt((self.player.x - ex) ** 2 + (self.player.y - ey) ** 2)
        if distance <= self.exit_reach_distance:
            self._advance_to_next_level()

    def _advance_to_next_level(self):
        """Переводит сцену на следующий уровень без пересоздания всего состояния игры."""
        self.current_level += 1

        # Повышаем сложность плавно, но ограничиваем верхней границей.
        self.max_enemies = min(40, self.max_enemies + 2)
        self.enemy_spawn_interval = max(1.2, self.enemy_spawn_interval * 0.95)

        # Очищаем временные объекты текущего уровня и перегенерируем маяк/подсказки.
        self._remove_runtime_tasks()
        self._clear_exit_hints()
        self._destroy_non_player_created_enemies()
        self._opened_chest_ids.clear()
        self._create_exit_beacon()
        self._spawn_exit_hint_maps()
        self._spawn_exit_hint_npcs()
        self.known_exit_positions = []

        # Возвращаем героя в стартовую зону нового уровня и сбрасываем исследовательскую цель.
        if self.player and hasattr(self.player, "set_position"):
            self.player.set_position(0.0, 0.0, getattr(self.player, "z", 0.5))
        elif self.player and hasattr(self.player, "x") and hasattr(self.player, "y"):
            self.player.x = 0.0
            self.player.y = 0.0
        if self.player and hasattr(self.player, "exploration_target"):
            self.player.exploration_target = None

        # Новый уровень стартует с волной врагов (если рендер инициализирован).
        if getattr(self.game, "render", None):
            self._spawn_initial_enemies()

        # После очистки runtime-задач возвращаем слежение камеры.
        if getattr(getattr(self.game, "showbase", None), "taskMgr", None) and getattr(self.game, "cam", None) is not None:
            self._start_camera_follow()

        # Пытаемся сохранить прогресс уровня на объекте игры, если есть подходящее поле.
        if hasattr(self.game, "current_level"):
            self.game.current_level = self.current_level

    def _clear_exit_hints(self):
        """Удаляет текущие объекты подсказок и очищает их внутренние списки."""
        for hint in self.map_hint_items:
            node = hint.get("node")
            if node and hasattr(node, "removeNode"):
                node.removeNode()
        self.map_hint_items.clear()

        for npc in self.npc_hints:
            node = npc.get("node")
            if node and hasattr(node, "removeNode"):
                node.removeNode()
        self.npc_hints.clear()

        for node in self.echo_trail_nodes:
            if node and hasattr(node, "removeNode"):
                node.removeNode()
        self.echo_trail_nodes.clear()
        self.echo_trail_points.clear()

    def _destroy_non_player_created_enemies(self):
        """Удаляет активных врагов уровня, оставляя только созданные игроком сущности."""
        player_created_enemy_ids = {
            id(obj) for obj in self.player_created_objects if hasattr(obj, "destroy")
        }

        remaining_enemies = []
        for enemy in self.enemies:
            if id(enemy) in player_created_enemy_ids:
                remaining_enemies.append(enemy)
                continue
            enemy.destroy()

        self.enemies = remaining_enemies
            
    def handle_input(self, keys):
        """Обработка ввода с гибридной схемой управления.

        Перемещение и автоскилы персонажа выполняет ИИ,
        а игрок управляет вспомогательными действиями клавиатурой/мышью.
        """
        if not self.player:
            return

        # Для логики сундуков и взаимодействий
        if not hasattr(self.player, 'keys') or not isinstance(self.player.keys, dict):
            self.player.keys = {}
        self.player.keys['e'] = bool(keys.get('e', False))

        # Выбор режима создания объектов
        if keys.get('1', False):
            self.creation_mode = 'enemy'
        elif keys.get('2', False):
            self.creation_mode = 'trap'
        elif keys.get('3', False):
            self.creation_mode = 'chest'

        # Одноразовые действия (по фронту нажатия)
        action_map = {
            '1': self._create_object_at_player,
            '2': self._create_object_at_player,
            '3': self._create_object_at_player,
            'space': self._attack_nearest_enemy,
            'mouse1': self._attack_nearest_enemy,
        }

        for action_key, action in action_map.items():
            pressed = bool(keys.get(action_key, False))
            was_pressed = bool(self._action_key_state.get(action_key, False))
            if pressed and not was_pressed:
                action()
            self._action_key_state[action_key] = pressed

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
        
        # Удаляем runtime-задачи и маяк смерти
        self._remove_runtime_tasks()
        self._remove_death_beacon()

        # Удаляем маяк выхода и подсказки
        if self.exit_beacon:
            self.exit_beacon.removeNode()
            self.exit_beacon = None
        self.exit_beacon_position = None
        self._clear_exit_hints()
        self._opened_chest_ids.clear()

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
        
        if not self.creation_mode:
            self.creation_mode = random.choice(["enemy", "trap", "chest"])

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
        task_name = f"trap_{id(trap)}"

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
                    self._complete_runtime_task(task_name)
                    return task.done
            return task.cont

        self._register_task_name(task_name)
        self.game.showbase.taskMgr.add(check_trap_trigger, task_name)
    
    def _add_chest_logic(self, chest, x, y, z):
        """Добавление логики сундука"""
        task_name = f"chest_{id(chest)}"

        def check_chest_interaction(task):
            if self.player:
                distance = math.sqrt((self.player.x - x)**2 + (self.player.y - y)**2)
                if distance <= 2.0:  # Радиус взаимодействия
                    # Сундук открывается автоматически при подходе персонажа,
                    # чтобы ИИ мог полноценно проходить лут-цикл без ручного нажатия.
                    self._open_chest(chest, x, y, z)
                    self._complete_runtime_task(task_name)
                    return task.done
            return task.cont

        self._register_task_name(task_name)
        self.game.showbase.taskMgr.add(check_chest_interaction, task_name)
    
    def _open_chest(self, chest, x, y, z):
        """Открытие сундука"""
        chest_id = id(chest)
        if chest_id in self._opened_chest_ids:
            return
        self._opened_chest_ids.add(chest_id)

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
            self._opened_chest_ids.discard(chest_id)
            self._complete_runtime_task(task_name)
            return task.done
            
        task_name = f"remove_chest_{id(chest)}"
        self._register_task_name(task_name)
        self.game.showbase.taskMgr.doMethodLater(2.0, remove_chest, task_name)
    
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
        task_name = "death_beacon_animation"

        def animate_beacon(task):
            if not self.death_beacon:
                self._complete_runtime_task(task_name)
                return task.done
                
            current_time = time.time()
            # Пульсация маяка
            scale = 1.0 + 0.3 * (current_time - start_time) % 2
            self.death_beacon.setScale(scale)
            
            # Вращение
            self.death_beacon.setHpr(0, 0, (current_time - start_time) * 30)
            
            return task.cont
            
        self._register_task_name(task_name)
        self.game.showbase.taskMgr.add(animate_beacon, task_name)
    
    def _remove_death_beacon(self):
        """Удаление маяка смерти"""
        if self.death_beacon:
            self.death_beacon.removeNode()
            self.death_beacon = None
            self.death_position = None
            print("Маяк смерти удален")
