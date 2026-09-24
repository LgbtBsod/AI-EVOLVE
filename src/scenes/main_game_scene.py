#!/usr/bin/env python3

import logging
import math
import random
import time

from panda3d.core import CardMaker, TransparencyAttrib

logger = logging.getLogger(__name__)

class LootBagTarget:
    """Мешок добычи как цель ИИ героя (x, y как у сундука)."""

    def __init__(self, bag):
        self.x, self.y = bag["x"], bag["y"]


class EnhancedGameScene:
    """Улучшенная игровая сцена с правильным рендерингом"""
    
    def __init__(self, game, dev_mode: bool = False):
        self.game = game
        self.dev_mode = dev_mode
        self.player = None
        self.enemies = []
        self.hud = None
        self.world_objects = []
        self.is_paused = False

        # Настройки мира.
        # Полноразмерная карта (50 * 100) огромна относительно скорости героя (8/с) —
        # первая встреча с врагом занимает минуты. dev_mode даёт компактную карту
        # для быстрой итерации при разработке/тестировании.
        self.world_size = (50 * 8) if dev_mode else (50 * 100)
        self.enemy_spawn_rate = 0.1  # Вероятность появления врага за кадр
        self.max_enemies = 10

        # Время
        self.last_enemy_spawn = 0
        self.enemy_spawn_interval = 1.5 if dev_mode else 3.0  # Интервал между появлениями врагов

        # Сложность врагов растёт со временем автоматически (не только через
        # _advance_to_next_level по действию игрока) - раньше уровень
        # EnhancedEnemy был фиксирован типом (basic=1/strong=3/elite=5/boss=10)
        # и никогда не менялся: враг, заспавненный на 10-й минуте партии,
        # ничем не отличался от заспавненного в первую секунду.
        self.world_start_time = time.time()
        # +1 уровень врагам за каждые N минут сессии (lua_content/world.lua -> progression)
        self.enemy_level_up_interval = 60.0 * self._minutes_per_enemy_level()
        
        # Система создания объектов игроком
        self.player_created_objects = []
        self.player_spawns = 0          # сколько врагов создал игрок (клавиша 1) за сессию
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
        self.echo_point_reach_distance = 1.0  # точка эхо-тропы считается пройденной
        self.echo_refresh_interval = 1.0
        self.last_echo_refresh_time = 0.0
        self._runtime_task_names = set()
        self._opened_chest_ids = set()

        # Единый менеджер эффектов (удары, навыки, зелья, предметы) и инвентари
        self.effects = None
        self.hero_inventory = None
        self.hero_inventory_brain = None
        self.enemy_brains = {}          # id(enemy) -> InventoryBrain (элиты, боссы)
        self.enemy_inventories = {}     # id(enemy) -> Inventory
        self.allies = []                # призванные союзники героя
        self.loot_bags = []             # {"x", "y", "gold", "items", "node"}
        self.messages = []              # (время, текст) - лента событий для HUD
        self.game_time = 0.0
        self.rng = random

        # Мир из 80 уровней, боссы, циклы (новая игра+), прогрессия героя
        self.plan = None
        self.level_info = None
        self.cycle = 0                  # сколько раз мир пройден целиком
        self.boss_queue = []            # боссы уровня по очереди (финал: Люцифер, затем Орден Узла)
        self.active_bosses = []
        self.victories = 0
        self.hero_growth = None
        self._kill_times = []
        self._close_call = False
        self._telegraph_watch = {}
        self._exit_block_logged = False

        # Враги учатся против героя: общая память тактик (бандит rust_core) и мозги врагов
        self.tactics = None
        self.combat_brains = {}         # entity_id врага -> EnemyBrain
        self.attack_slots = None        # очередь на удар по герою (3 ближних + 2 дальних)
        
    def enter(self):
        """Вход в игровую сцену"""
        logger.info("Entering enhanced game scene...")

        from src.effects.abilities import load_abilities
        from src.effects.manager import EffectManager
        self.effects = EffectManager(world=self, abilities=load_abilities())
        self.game.effect_manager = self.effects
        self.effects.register_event_handler(self._on_hit)
        from src.gameplay.tactics import TacticsMemory, memory_path
        self.tactics = TacticsMemory(memory_path())
        from src.gameplay.enemy_ai import AttackSlots
        from src.gameplay.progression import progression
        self.attack_slots = AttackSlots(**(progression().get("attack_slots") or {}))

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
        self._start_level()
        
        # Настраиваем камеру
        self._setup_camera()
        
        logger.info("Enhanced game scene initialized!")
        
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
        import random

        from panda3d.core import CardMaker

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
        import random

        from panda3d.core import CardMaker

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
        import random

        from panda3d.core import CardMaker

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
        self._equip_hero()

    def _equip_hero(self):
        """Регистрация героя в менеджере эффектов, инвентарь и стартовый набор."""
        from src.gameplay.inventory import Inventory, InventoryBrain
        from src.gameplay.items import catalog
        if self.effects is None or self.player is None:
            return
        self.effects.register(self.player, "hero")
        player = self.player
        self.hero_inventory = Inventory(
            player, capacity=20, gold=20,
            on_change=lambda inv: self.effects.equip(player, inv.equipped.values()))
        self.hero_inventory_brain = InventoryBrain(self.hero_inventory, role=player.character_class)
        player.inventory = self.hero_inventory
        from src.gameplay.progression import HeroGrowth
        self.hero_growth = HeroGrowth(player.character_class)
        from src.gameplay.hero_mind import HeroMind, mind_path
        player.mind = HeroMind(player, mind_path(), inventory_brain=self.hero_inventory_brain)
        cat = catalog()
        weapon = {"mage": "apprentice_staff", "rogue": "worn_dagger"}.get(player.character_class, "rusty_sword")
        for item_id in (weapon, "leather_armor", "health_potion", "health_potion"):
            item = cat.get(item_id)
            if item is not None:
                self.hero_inventory.add(item)
                if item.equippable:
                    self.hero_inventory.equip(item)

    # ---------------------------------------------------------------- мир для менеджера эффектов
    def clamp_position(self, x, y):
        """Не выходить за стены карты (рывки, отбрасывания)."""
        half = self.world_size / 2 - 1.0
        return max(-half, min(half, x)), max(-half, min(half, y))

    def entities(self):
        """Все сущности мира (для способностей по площади)."""
        out = [self.player] if self.player is not None else []
        return out + list(self.enemies) + list(self.allies)

    def visible_enemies(self, observer):
        """Враги, которых observer замечает (обзор и стелс - менеджер эффектов)."""
        if self.effects is None or self.effects.state(observer) is None:
            return list(self.enemies)
        return [e for e in self.enemies if self.effects.can_see(observer, e)]

    def spawn_summon(self, kind, x, y, faction, level, owner):
        """Призыв (операция summon): враг на стороне призвавшего."""
        from src.gameplay.world import make_enemy
        creature = make_enemy(self.game, kind, max(1, int(level)), x, y, self._plan())
        if getattr(self.game, "render", None) is not None:
            creature.create_enemy()
        creature.summoned_by = owner
        if faction == "hero":
            self.allies.append(creature)
            if self.effects is not None:
                self.effects.register(creature, "hero")
        else:
            self._register_enemy(creature)
            self.enemies.append(creature)
        self.log_message(f"призван {kind}")
        return creature

    def _register_enemy(self, enemy):
        """Враг в менеджере эффектов + снаряжение по таблице добычи (элиты и боссы пьют зелья)."""
        if self.effects is None:
            return
        from src.gameplay.inventory import Inventory, InventoryBrain
        from src.gameplay.loot import outfit
        from src.gameplay.progression import perk_effects
        self.effects.register(enemy, "monsters")
        from src.gameplay.enemy_ai import EnemyBrain
        enemy.brain = EnemyBrain(enemy, self.effects, self.tactics, self.rng, others=lambda: self.enemies,
                                 slots=self.attack_slots)
        self.combat_brains[str(enemy.entity_id)] = enemy.brain
        inv = Inventory(enemy, capacity=8,
                        on_change=lambda inv, e=enemy: self.effects.equip(e, inv.equipped.values()))
        outfit(inv, getattr(enemy, "loot_class", enemy.enemy_type), self.rng)
        if getattr(enemy, "attributes", None):
            self.effects.set_perks(enemy, perk_effects(enemy.attributes))
        enemy.inventory = inv
        self.enemy_inventories[id(enemy)] = inv
        if inv.bag or inv.equipped:
            self.enemy_brains[id(enemy)] = InventoryBrain(inv, role="monster", heal_at=0.3)

    def _on_hit(self, info):
        """Каждое попадание менеджера -> счёт схватки у мозга врага (для памяти тактик)."""
        if self.player is None:
            return
        hero_id = str(self.player.entity_id)
        mind = getattr(self.player, "mind", None)
        if mind is not None:
            mind.note_hit(info, hero_id)
        for key in (info.source, info.target):
            brain = self.combat_brains.get(key)
            if brain is not None:
                brain.note_hit(info, hero_id)

    def _forget_enemy(self, enemy, hero_died=False):
        """Враг покидает мир: итог его схватки - в память тактик, снять с менеджера."""
        brain = self.combat_brains.pop(str(getattr(enemy, "entity_id", "")), None)
        if brain is not None:
            brain.finish(hero_died=hero_died)
        if self.effects is not None:
            self.effects.unregister(enemy)

    def log_message(self, text):
        self.messages.append((self.game_time, text))
        del self.messages[:-50]
        
    def _create_hud(self):
        """Создание HUD"""
        from src.ui.hud import EnhancedHUD
        
        self.hud = EnhancedHUD(self.game)
        self.hud.create_hud()
        
    @staticmethod
    def _minutes_per_enemy_level() -> float:
        try:
            from src.gameplay.progression import progression
            return float(progression()["minutes_per_enemy_level"])
        except Exception:
            return 5.0

    def _plan(self):
        if self.plan is None:
            from src.gameplay.world import world_plan
            self.plan = world_plan()
        return self.plan

    def enemy_level(self) -> int:
        """Уровень мира + бонус за пройденные циклы + 1 за каждые N минут сессии."""
        from src.gameplay.progression import progression
        return (self.current_level + int(progression()["cycle_level_bonus"]) * self.cycle
                + self._current_enemy_level_bonus())

    def _spawn_enemy(self, enemy_type, x, y, player_created=False):
        """Враг из бестиария (или босс) с уровнем по правилам прогрессии."""
        from src.gameplay.world import make_enemy
        enemy = make_enemy(self.game, enemy_type, self.enemy_level(), x, y, self._plan())
        if getattr(self.game, "render", None) is not None:
            enemy.create_enemy()
        self._register_enemy(enemy)
        self.enemies.append(enemy)
        if player_created:
            self.player_created_objects.append(enemy)
            self.player_spawns += 1
        return enemy

    # ---------------------------------------------------------------- уровни и боссы
    def _start_level(self):
        plan = self._plan()
        self.level_info = info = plan.info(self.current_level)
        self.boss_queue = plan.final_sequence(self.current_level) if info.boss else []
        self.active_bosses = []
        self._exit_block_logged = False
        cycle = f" (цикл {self.cycle + 1})" if self.cycle else ""
        self.log_message(f"Уровень {self.current_level}: {info.name}{cycle}")
        if self.boss_queue:
            self._spawn_next_boss()

    def _spawn_next_boss(self):
        if not self.boss_queue:
            return None
        boss_type = self.boss_queue.pop(0)
        ex, ey, _ez = self.exit_beacon_position or (0.0, 0.0, 0.0)
        # страж выхода; Люцифер вмёрз прямо в озеро у выхода
        offset = 0.0 if boss_type == "lucifer" else 4.0
        boss = self._spawn_enemy(boss_type, ex + offset, ey + offset)
        boss.is_boss = True
        self.active_bosses.append(boss)
        line = (getattr(boss, "dialog", {}) or {}).get("spawn")
        self.log_message(f"{getattr(boss, 'display_name', boss_type)}" + (f": «{line}»" if line else " появляется"))
        return boss

    def _on_boss_death(self, boss):
        from src.gameplay.progression import xp_for
        line = (getattr(boss, "dialog", {}) or {}).get("death")
        if line:
            self.log_message(f"{getattr(boss, 'display_name', boss.enemy_type)}: «{line}»")
        self._award("boss_kill", "Босс повержен")
        if boss in self.active_bosses:
            self.active_bosses.remove(boss)
        if self.boss_queue:
            self._spawn_next_boss()
        elif not self.active_bosses:
            if self.level_info is not None and self.level_info.is_final:
                self._complete_cycle()
            else:
                self.log_message("Путь к выходу открыт")

    def _complete_cycle(self):
        """Финал пройден: мир собирается заново, враги становятся сильнее (новая игра+)."""
        self.victories += 1
        self.cycle += 1
        self.log_message(f"Цикл {self.cycle} завершён. Мир собран заново - и враги помнят тебя.")
        if hasattr(self.game, "state_manager") and self.game.state_manager is not None:
            try:
                self.game.state_manager.set_state("game_phase", "cycle_complete")
            except Exception:
                pass
        self.current_level = 0
        self._advance_to_next_level(award=False)

    def _award(self, activity, text=""):
        """Опыт только за активности (lua_content/world.lua -> progression.xp)."""
        from src.gameplay.progression import xp_for
        amount = xp_for(activity)
        if amount and self.player is not None:
            self.player.add_experience(amount)
            if text:
                self.log_message(f"{text} +{amount} опыта")

    def _update_hero_progress(self):
        """Очки характеристик героя, перки, «уроки» от ран."""
        from src.gameplay.progression import perk_effects
        player = self.player
        if player is None or self.hero_growth is None:
            return
        frac = player.health / max(1.0, player.max_health)
        if frac < 0.3 and not self._close_call:
            self._close_call = True
            self.hero_growth.note_close_call()
        elif frac > 0.6:
            self._close_call = False
        if getattr(player, "attribute_points", 0) > 0:
            spent = self.hero_growth.spend(player)
            if self.effects is not None:
                self.effects.set_perks(player, perk_effects(player.attributes))
                st = self.effects.state(player)
                if st is not None:
                    st.refresh(self.effects.now)
            names = {"strength": "силы", "agility": "ловкости", "intelligence": "интеллекта", "vitality": "живучести",
                     "wisdom": "мудрости", "endurance": "выносливости", "luck": "удачи", "charisma": "харизмы"}
            self.log_message(f"Уровень {player.level}: " + ", ".join(f"+{int(v)} {names.get(a, a)}" for a, v in spent.items()))

    def _track_tricks(self):
        """Трюки героя: ушёл из круга навыка босса, серия убийств, убийство на грани."""
        if self.effects is None or self.player is None:
            return
        px, py = self.player.x, self.player.y
        live = {id(tg): tg for tg in self.effects.telegraphs}
        for key, tg in live.items():
            if key not in self._telegraph_watch:
                self._telegraph_watch[key] = (tg, math.hypot(px - tg.x, py - tg.y) <= tg.radius)
        for key in [k for k in self._telegraph_watch if k not in live]:
            tg, was_inside = self._telegraph_watch.pop(key)
            if was_inside and self.player.is_alive() and math.hypot(px - tg.x, py - tg.y) > tg.radius:
                self._award("trick_dodge", f"Трюк: ушёл из-под «{tg.ability.get('name', tg.ability['id'])}»")

    def _on_hero_kill(self):
        now = self.game_time
        self._kill_times = [t for t in self._kill_times if now - t <= 2.0] + [now]
        if len(self._kill_times) == 2:
            self._award("trick_multikill", "Трюк: двойное убийство")
        if self.player is not None and self.player.health < 0.2 * self.player.max_health:
            self._award("trick_clutch", "Трюк: убийство на грани")

    def _current_enemy_level_bonus(self) -> int:
        """Сколько дополнительных уровней получает враг, спавнящийся ПРЯМО
        СЕЙЧАС - растёт автоматически с течением времени партии (см.
        world_start_time/enemy_level_up_interval в __init__), независимо от
        current_level (который меняется только через _advance_to_next_level
        по действию игрока - маяк выхода)."""
        elapsed = time.time() - self.world_start_time
        return int(elapsed / self.enemy_level_up_interval)

    def _spawn_initial_enemies(self):
        """Создание начальных врагов"""

        # Создаем несколько врагов на удалённых позициях по краям арены,
        # чтобы игрок сначала двигался, а не сразу вступал в бой.
        enemy_positions = [
            (self.world_size * 0.3, self.world_size * 0.3, 0.5),
            (-self.world_size * 0.3, self.world_size * 0.3, 0.5),
            (self.world_size * 0.3, -self.world_size * 0.3, 0.5),
            (-self.world_size * 0.3, -self.world_size * 0.3, 0.5)
        ]

        plan = self._plan()
        for i, (x, y, z) in enumerate(enemy_positions):
            self._spawn_enemy(plan.pick_enemy(self.current_level, self.rng, elite_chance=0.0 if i < 2 else 0.3), x, y)
            
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
            except KeyError:
                # Задача уже удалена или не существует
                logger.debug(f"Задача {task_name} уже удалена")
            except Exception as e:
                logger.warning(f"Не удалось удалить задачу {task_name}: {e}")
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
        self.game_time += dt
        if self.effects is not None:
            self.effects.update(dt)
        self._update_inventories(dt)
        self._update_hero_progress()
        self._track_tricks()
            
        # Обновляем игрока
        if self.player and self.player.is_alive():
            # Обновляем кулдаун атаки
            if self.player.attack_cooldown > 0:
                self.player.attack_cooldown -= dt
            self.player.attack_cooldown = max(self.player.attack_cooldown, 0)

            # Восстанавливаем характеристики.
            # Реген применяется только живому игроку - иначе он безусловно
            # тянет health выше 0 каждый кадр и is_alive() мерцает обратно
            # в True сразу после смерти (герой "оживает" сам и продолжает
            # драться вместо честной смерти).
            self.player.health = min(self.player.max_health, self.player.health + self.player.health_regen * dt)
            self.player.mana = min(self.player.max_mana, self.player.mana + self.player.mana_regen * dt)
            self.player.stamina = min(self.player.max_stamina, self.player.stamina + self.player.stamina_regen * dt)

            if self.player.health_bar:
                self.player.health_bar.update(self.player.health / self.player.max_health)

            # Разум героя: стойка на низком HP (учится, стоит ли давить)
            mind = getattr(self.player, "mind", None)
            if mind is not None and self.effects is not None:
                mind.update(dt, bool(self.visible_enemies(self.player)), self.effects.now)

            # Обновляем ИИ персонажа
            self._consume_reached_echo_points()
            ai_known_exits = list(self.known_exit_positions) + list(self.echo_trail_points)
            self.player.update_ai(
                self.visible_enemies(self.player),
                self._get_interactive_items(),
                dt,
                exit_position=self.exit_beacon_position,
                vision_range=getattr(self.player, "vision_range", self.player_vision_range),
                known_exit_positions=ai_known_exits,
                hint_positions=self._get_hint_positions()
            )

            # Автоматическое использование скилов
            self.player.use_skill_automatically(self.visible_enemies(self.player), dt)
        elif self.player and self.player.health_bar:
            self.player.health_bar.update(0.0)

        # Обновляем врагов
        for enemy in self.enemies[:]:  # Используем копию списка для безопасного удаления
            if enemy.is_alive():
                enemy.update_ai(self.player, dt)
                if enemy.health_bar:
                    enemy.health_bar.update(enemy.health / enemy.max_health)
            else:
                # Удаляем мертвых врагов и начисляем опыт за победу.
                # enemy.experience_reward уже существовал у EnhancedEnemy, но
                # нигде не читался - убийства не давали опыта вообще.
                if self.player:
                    self.player.add_experience(getattr(enemy, "experience_reward", 0))
                    self._on_hero_kill()
                self._drop_enemy_loot(enemy)
                if getattr(enemy, "is_boss", False):
                    self._on_boss_death(enemy)
                self._forget_enemy(enemy)
                enemy.destroy()
                # смерть последнего босса могла уже пересобрать мир (новый уровень/цикл)
                if enemy in self.enemies:
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
        """Список интерактивных объектов для AI: сундуки и мешки добычи."""
        chests = []
        for obj in self.player_created_objects:
            if hasattr(obj, 'getName') and obj.getName() == 'chest':
                chests.append(obj)
        return chests + [LootBagTarget(bag) for bag in self.loot_bags]

    # ---------------------------------------------------------------- инвентари и добыча
    def _update_inventories(self, dt):
        """Решения ИИ по инвентарю: зелья, экипировка, карты (герой и враги)."""
        if self.effects is None:
            return
        if self.player is not None and self.player.is_alive() and self.hero_inventory_brain is not None:
            before = len(self.hero_inventory.log)
            self.hero_inventory_brain.update(
                dt, lambda item: self.effects.use_item(self.player, item), self._learn_from_item)
            for line in self.hero_inventory.log[before:]:
                self.log_message(f"Герой {line}")
        for enemy in self.enemies:
            brain = self.enemy_brains.get(id(enemy))
            if brain is not None and enemy.is_alive():
                act = brain.update(dt, lambda item, e=enemy: self.effects.use_item(e, item))
                if act and act.startswith("potion"):
                    self.log_message(f"{enemy.enemy_type} выпил зелье")
        self._pickup_loot_bags()

    def _learn_from_item(self, item):
        """Карта или артефакт: знание о выходе."""
        reveals = (item.knowledge or {}).get("reveals")
        if reveals == "exit":
            self._register_exit_knowledge(precise=True)
            self.log_message(f"{item.name}: выход отмечен")
        elif reveals in ("exit_region", "exit_direction"):
            self._register_exit_knowledge(precise=False)
            self.log_message(f"{item.name}: направление к выходу")

    def _drop_enemy_loot(self, enemy):
        from src.gameplay.loot import enemy_drop
        inv = self.enemy_inventories.pop(id(enemy), None)
        self.enemy_brains.pop(id(enemy), None)
        if inv is None or getattr(enemy, "summoned_by", None) is not None:
            return
        gold, items = enemy_drop(inv, getattr(enemy, "loot_class", enemy.enemy_type), self.rng)
        if gold <= 0 and not items:
            return
        bag = {"x": enemy.x, "y": enemy.y, "gold": gold, "items": items, "node": None}
        if getattr(self.game, "render", None) is not None:
            node = self.game.render.attachNewNode("loot")
            self._create_visible_cube(node, "loot_bag", 0, 0, 0.2, 0.5, 0.5, 0.4, (0.9, 0.75, 0.2, 1))
            node.setPos(enemy.x, enemy.y, 0.1)
            bag["node"] = node
        self.loot_bags.append(bag)

    def _pickup_loot_bags(self):
        if self.player is None or not self.player.is_alive():
            return
        for bag in self.loot_bags[:]:
            if math.hypot(self.player.x - bag["x"], self.player.y - bag["y"]) > 2.0:
                continue
            self.hero_inventory.gold += bag["gold"]
            taken = [it for it in bag["items"] if self.hero_inventory.add(it)]
            names = ", ".join(it.name for it in taken)
            self.log_message(f"Добыча: {bag['gold']} золота" + (f", {names}" if names else ""))
            if bag["node"] is not None:
                bag["node"].removeNode()
            self.loot_bags.remove(bag)


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
            
            # Кольцо 30-50 от героя (за краем его обзора): раньше враги появлялись
            # у стен карты в ~160 и почти никогда не встречали героя
            px, py = (self.player.x, self.player.y) if self.player is not None else (0.0, 0.0)
            ang = random.uniform(0.0, 2 * math.pi)
            dist = random.uniform(30.0, 50.0)
            x, y = self.clamp_position(px + dist * math.cos(ang), py + dist * math.sin(ang))
            
            # Тип врага - из акта текущего уровня (lua_content/world.lua)
            self._spawn_enemy(self._plan().pick_enemy(self.current_level, self.rng,
                                                     elite_chance=self._plan().elite_chance(self.enemy_level())), x, y)

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
                self._award("hint", "Карта найдена")

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
                self._award("hint", "NPC подсказал путь")
                lore = self._plan().lore_line(self.current_level, self.rng)
                if lore:
                    self.log_message(f"NPC: «{lore}»")
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

    def _consume_reached_echo_points(self):
        """Точки эхо-тропы - путевые: достигнутая точка убирается.

        ИИ идёт к БЛИЖАЙШЕЙ известной точке выхода. Когда выход известен точно,
        тропа больше не перестраивается (_refresh_echo_trail_guidance), и раньше
        первая точка тропы навсегда оставалась ближайшей: герой доходил до неё
        (move_towards останавливается в 0.1u) и стоял в seeking_exit вечно."""
        if not self.echo_trail_points or not self.player:
            return
        px, py = self.player.x, self.player.y
        keep_points, keep_nodes = [], []
        nodes_aligned = len(self.echo_trail_nodes) == len(self.echo_trail_points)
        for idx, (tx, ty) in enumerate(self.echo_trail_points):
            node = self.echo_trail_nodes[idx] if nodes_aligned else None
            if math.hypot(px - tx, py - ty) <= self.echo_point_reach_distance:
                if node is not None and hasattr(node, "removeNode"):
                    node.removeNode()
                continue
            keep_points.append((tx, ty))
            if node is not None:
                keep_nodes.append(node)
        if len(keep_points) != len(self.echo_trail_points):
            self.echo_trail_points = keep_points
            if nodes_aligned:
                self.echo_trail_nodes = keep_nodes

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
            alive = [b for b in self.active_bosses if b.is_alive()]
            if alive or self.boss_queue:
                if not self._exit_block_logged:
                    who = getattr(alive[0], "display_name", "босс") if alive else "страж"
                    self.log_message(f"Выход охраняет {who}")
                    self._exit_block_logged = True
                return
            self._advance_to_next_level()

    def _advance_to_next_level(self, award=True):
        """Переводит сцену на следующий уровень без пересоздания всего состояния игры."""
        if award and self.current_level >= 1:
            self._award("exit", "Уровень пройден")
        if self.level_info is not None and self.level_info.is_final and award:
            return  # на финальном уровне выход - это победа над цепочкой боссов
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
        self._start_level()

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
            self._forget_enemy(enemy)
            enemy.destroy()
        if self.tactics is not None:
            self.tactics.save()

        self.enemies = remaining_enemies
        self.active_bosses = [b for b in self.active_bosses if b in remaining_enemies]
            
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
        elif keys.get('4', False):
            self.creation_mode = 'boss'

        # Одноразовые действия (по фронту нажатия)
        action_map = {
            '1': self._create_object_at_player,
            '2': self._create_object_at_player,
            '3': self._create_object_at_player,
            '4': self._create_object_at_player,
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
        if self.tactics is not None:
            self.tactics.save()
        if self.player is not None and getattr(self.player, "mind", None) is not None:
            self.player.mind.save()
        if getattr(self.game, "effect_manager", None) is self.effects:
            self.game.effect_manager = None
        for bag in self.loot_bags:
            if bag["node"] is not None:
                bag["node"].removeNode()
        self.loot_bags.clear()

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

        logger.info("Enhanced game scene exited!")
    
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
        elif self.creation_mode == "boss":
            self._create_boss_at(x, y, z)
            
        logger.debug(f"Created {self.creation_mode} at position ({x:.1f}, {y:.1f})")
    
    def _create_enemy_at(self, x, y, z):
        """Создание врага в указанной позиции (игрок-режиссёр: враги текущего акта)"""
        self._spawn_enemy(self._plan().pick_enemy(self.current_level, self.rng, elite_chance=self._plan().elite_chance(self.enemy_level())), x, y,
                          player_created=True)

    def _create_boss_at(self, x, y, z):
        """Клавиша 4: босс текущего акта рядом с героем."""
        act = self._plan().act_for(self.current_level)
        boss_type = act.get("boss") if self.rng.random() < 0.5 else act.get("miniboss")
        boss = self._spawn_enemy(boss_type or act.get("boss"), x, y, player_created=True)
        boss.is_boss = True
        self.active_bosses.append(boss)
        self.log_message(f"{getattr(boss, 'display_name', boss_type)} призван режиссёром")
    
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
        """Добавление логики ловушки: шанс обезвредить вместо срабатывания.

        Шанс растёт с уровнем персонажа (5% база + 5% за уровень, потолок
        75% - ловушка не должна становиться гарантированно безопасной).
        Раньше подход к ловушке всегда означал урон - "обезвреженные
        ловушки" как источник опыта были невозможны в принципе."""
        task_name = f"trap_{id(trap)}"

        def check_trap_trigger(task):
            if self.player:
                distance = math.sqrt((self.player.x - x)**2 + (self.player.y - y)**2)
                if distance <= 1.5:  # Радиус срабатывания
                    disarm_chance = min(0.75, 0.05 + 0.05 * self.player.level)
                    if random.random() < disarm_chance:
                        self.player.add_experience(15)
                        logger.info(f"Trap disarmed! (chance was {disarm_chance:.0%}) +15 XP")
                    else:
                        self.player.take_damage(20, "physical")
                        logger.info(f"Trap triggered! (disarm chance was {disarm_chance:.0%})")
                    # Ловушка исчезает в любом случае - обезврежена или сработала
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

        # Даем игроку награду.
        # Раньше experience просто рос напрямую - experience_to_next_level
        # ни с чем не сравнивался, level-up никогда не происходил.
        if self.player:
            self.player.add_experience(50)
            self.player.health = min(self.player.max_health, self.player.health + 25)
            logger.info("Chest opened! Received: 50 XP, 25 HP")
            if self.hero_inventory is not None:
                from src.gameplay.loot import loot_tables, roll_loot
                gold, items = roll_loot(loot_tables().get("chest") or {}, self.rng)
                self.hero_inventory.gold += gold
                taken = [it for it in items if self.hero_inventory.add(it)]
                self.log_message(f"Сундук: {gold} золота" + (", " + ", ".join(it.name for it in taken) if taken else ""))
        
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
            # Враги, что были в схватке, запоминают: эта тактика убила героя
            for brain in list(self.combat_brains.values()):
                if brain.engaged_at is not None:
                    brain.finish(hero_died=True)
            if self.tactics is not None:
                self.tactics.save()
            mind = getattr(self.player, "mind", None)
            if mind is not None:
                mind.update(0.0, True, self.effects.now if self.effects else 0.0)
                mind.save()
            # Сохраняем позицию смерти
            self.death_position = (self.player.x, self.player.y, self.player.z)
            
            # Создаем маяк смерти
            self._create_death_beacon()
            
            # Переходим к экрану смерти
            if hasattr(self.game, 'state_manager'):
                self.game.state_manager.set_state("game_phase", "death")
    
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
            
            logger.info(f"Death beacon created at position {self.death_position}")
            
        except Exception as e:
            logger.error(f"Error creating death beacon: {e}", exc_info=True)
    
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
            logger.info("Death beacon removed")
