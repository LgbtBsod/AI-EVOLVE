#!/usr/bin/env python3
"""
Enemy entity with data-driven stats and component-based architecture.

REFACTORING: 
- Lazy Panda3D imports for headless testing
- HealthComponent integration for damage handling
- Stats loaded from JSON configs via StatsLoader
"""

import itertools
import logging
import math
import random
import time

# Lazy import for headless testing support
try:
    from panda3d.core import CardMaker
    PANDA3D_AVAILABLE = True
except ImportError:
    PANDA3D_AVAILABLE = False
    CardMaker = None

from ..core.stats_loader import StatsLoader
from ..core.validation import CombatStats
from ..systems.combat.components import HealthComponent
from ..ui.health_bar import HealthBar

logger = logging.getLogger(__name__)

# Monotonic, never reused - see the matching comment in entities/character.py.
_enemy_id_counter = itertools.count(1)

class EnhancedEnemy:
    """Улучшенный класс врага с правильным рендерингом"""

    def __init__(self, game, x=0, y=0, z=0, enemy_type="slime", level=None, color=None):
        self.game = game
        self.x = x
        self.y = y
        self.z = z
        self.enemy_type = enemy_type
        
        # Загружаем статы врага из конфига (data-driven approach)
        stats_loader = StatsLoader.get_instance()
        
        # Если уровень не указан, используем уровень из конфига для этого типа
        if level is None:
            enemy_data = stats_loader.get_enemy_stats(enemy_type)
            level = enemy_data.get("level", 1)
        
        self.level = level
        enemy_stats = stats_loader.get_enemy_stats(enemy_type, level)
        
        # Применяем статы из конфига
        self.max_health = enemy_stats.get("health", 50)
        self.health = self.max_health
        self.physical_damage = enemy_stats.get("damage", 10)
        self.defense = enemy_stats.get("defense", 2)
        self.experience_reward = enemy_stats.get("exp_reward", 20)
        self.move_speed = enemy_stats.get("speed", 4.0)
        
        # Размер и цвет на основе типа (визуальные параметры)
        self._setup_visuals(enemy_type, color)
        
        # ID сущности для систем
        self.entity_id = f"enemy_{next(_enemy_id_counter)}"
        
        # AI состояние
        self.state = "idle"  # idle, chasing, attacking, dead
        self.target = None
        self.last_attack_time = 0
        self.attack_cooldown = 1.0
        
        # Движение и зоны обнаружения/атаки
        # Зона отслеживания должна быть заметно больше, чтобы враги
        # реагировали на появление героя в заметном радиусе.
        self.detection_range = 20.0
        self.attack_range = 2.0

        # Точка спавна используется как центр области блуждания
        self.spawn_x = self.x
        self.spawn_y = self.y
        
        # Компонент здоровья для интеграции с новой боевой системой
        self._health_component = HealthComponent(
            name=f"enemy_{self.entity_id}",
            max_health=self.max_health
        )
        
    def _setup_visuals(self, enemy_type: str, color: tuple | None) -> None:
        """Настройка визуальных параметров (размер, цвет) на основе типа врага"""
        # Визуальные параметры - не влияют на баланс
        visuals = {
            "slime": {"size": 0.6, "color": (0.2, 0.8, 0.2, 1)},      # Зеленый
            "goblin": {"size": 0.8, "color": (0.3, 0.6, 0.3, 1)},     # Темно-зеленый
            "orc": {"size": 1.4, "color": (0.4, 0.5, 0.4, 1)},        # Серо-зеленый
            "skeleton": {"size": 0.9, "color": (0.9, 0.9, 0.85, 1)},  # Костяной
            "dragon": {"size": 2.5, "color": (0.8, 0.2, 0.1, 1)},     # Красно-оранжевый
            "boss_demon": {"size": 3.0, "color": (0.5, 0.1, 0.1, 1)}, # Темно-красный
            # Legacy types for backwards compatibility
            "basic": {"size": 0.8, "color": (1, 0, 0, 1)},
            "strong": {"size": 1.2, "color": (0.8, 0.2, 0.2, 1)},
            "elite": {"size": 1.5, "color": (0.6, 0.1, 0.6, 1)},
            "boss": {"size": 2.0, "color": (0.3, 0.1, 0.1, 1)},
        }
        
        visual_data = visuals.get(enemy_type, {"size": 0.8, "color": (1, 0, 0, 1)})
        self.size = visual_data["size"]
        self.color = color if color else visual_data["color"]
        self.node = None
        self.health_bar = None
        
        # Дополнительные характеристики (дефолтные, в формате 0-1)
        self.critical_chance = 0.05   # 5% шанс крита
        self.critical_damage = 1.5    # 150% множитель (1.5)
        self.dodge_chance = 0.0       # 0% шанс уворота
        self.magic_resistance = 0.0   # 0% магическая защита
        
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

        self.health_bar = HealthBar(width=self.size * 1.1)
        self.health_bar.create(self.node, z_offset=self.size * 1.9 + 0.3)

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
            
            # Двигаемся с учетом скорости (с модификаторами эффектов, если есть)
            move_distance = self.get_effective_move_speed() * dt
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
                logger.info("Enemy dodged!")
                return False
        
        self.health = max(0, self.health - actual_damage)
        if self.health <= 0:
            self.state = "dead"
        return self.health <= 0
        
    def is_alive(self):
        """Проверка, жив ли враг"""
        return self.health > 0 and self.state != "dead"
    
    # навыки по типу врага; боссы получают свои из lua_content/bosses.lua
    TYPE_SKILLS = {"elite": ("war_cry", "crushing_blow"), "strong": ("crushing_blow",),
                   "skeleton": ("venom_spit",), "goblin": ("venom_spit",)}

    def attack(self, target):
        """Атака цели: навык по типу (если готов) или удар оружием - через единый
        менеджер эффектов; без него (тесты) - прежний путь через CombatSystem."""
        manager = getattr(self.game, "effect_manager", None)
        if manager is not None and manager.state(self) is not None:
            for skill in getattr(self, "skills", None) or self.TYPE_SKILLS.get(self.enemy_type, ()):
                if manager.ability(skill) is not None and manager.cast(self, skill, target).ok:
                    return True
            result = manager.cast(self, "weapon_attack", target)
            return result.ok and any(not h.is_dodged for h in result.hits)
        current_time = time.time()
        if current_time - self.last_attack_time >= self.attack_cooldown and self.is_alive():
            # Проверяем расстояние до цели
            distance = self.get_distance_to(target)
            
            if distance <= self.attack_range:
                combat_system = getattr(self.game, "combat_system", None)
                if not combat_system:
                    logger.warning("No combat_system on game object, attack skipped")
                    return False

                # Сильные враги (elite/boss) накладывают замедление на удачном
                # попадании - демонстрирует подключение EffectSystem к бою и
                # даёт "прокачке" смысл: слабых hit-and-run противников это
                # не задевает, тяжёлых стоит опасаться отдельно.
                on_hit_effect = "slow_debuff" if self.enemy_type in ("elite", "boss") else None
                damage_info = combat_system.execute_attack(self, target, on_hit_effect=on_hit_effect)
                self.last_attack_time = current_time

                if damage_info.is_dodged:
                    logger.info("Player dodged the enemy's attack!")
                else:
                    crit_note = " (critical!)" if damage_info.is_critical else ""
                    logger.info(f"Enemy attacked player for {damage_info.damage:.1f} damage!{crit_note}")
                return not damage_info.is_dodged
        return False

    def get_combat_stats(self) -> CombatStats:
        """Боевые характеристики в формате, ожидаемом CombatSystem.

        Проходят через EffectSystem.get_modified_stat(), если она доступна
        через game.effect_system - см. аналогичный комментарий в
        Character.get_combat_stats()."""
        effects = getattr(self.game, "effect_system", None)

        def mod(stat_type: str, base_value: float) -> float:
            if effects is None:
                return base_value
            return effects.get_modified_stat(self.entity_id, stat_type, base_value)

        # Получаем текущее здоровье из HealthComponent
        current_health = self._health.current_health if hasattr(self, '_health') and self._health else self.max_health
        max_health = self._health.max_health if hasattr(self, '_health') and self._health else self.max_health
        
        # Возвращаем полный CombatStats со всеми полями для совместимости с combat_system.py
        return CombatStats(
            health=current_health,
            max_health=max_health,
            damage=mod("physical_damage", self.physical_damage),
            defense=mod("defense", self.defense),
            speed=self.move_speed,
            # Добавляем недостающие поля для совместимости с формулами боя
            physical_damage=mod("physical_damage", self.physical_damage),
            magical_damage=mod("magical_damage", getattr(self, 'magical_damage', 5.0)),
            attack_speed=mod("attack_speed", getattr(self, 'attack_speed', 1.0)),
            critical_chance=mod("critical_chance", getattr(self, 'critical_chance', 0.0)),
            critical_damage=mod("critical_damage", getattr(self, 'critical_damage', 1.5)),
            dodge_chance=mod("dodge_chance", getattr(self, 'dodge_chance', 0.0)),
            block_chance=mod("block_chance", getattr(self, 'block_chance', 0.0)),
            magic_resistance=mod("magic_resistance", getattr(self, 'magic_resistance', 0.0)),
            accuracy=mod("accuracy", getattr(self, 'accuracy', 0.8)),
            initiative=mod("initiative", getattr(self, 'initiative', 10.0)),
            range=getattr(self, 'attack_range', 2.0),
            damage_modifier=mod("damage_modifier", getattr(self, 'damage_modifier', 1.0)),
            defense_modifier=mod("defense_modifier", getattr(self, 'defense_modifier', 1.0)),
            speed_modifier=mod("speed_modifier", getattr(self, 'speed_modifier', 1.0)),
        )

    def get_effective_move_speed(self) -> float:
        """Скорость передвижения с учётом эффектов (например slow_debuff)."""
        effects = getattr(self.game, "effect_system", None)
        if effects is None:
            return self.move_speed
        return effects.get_modified_stat(self.entity_id, "speed", self.move_speed)

    def apply_level_bonus(self, bonus_levels: int) -> None:
        """Масштабирует уровень/характеристики врага под сложность,
        растущую со временем (main_game_scene._enemy_level_bonus) - без этого
        враг в конце долгой партии ничем не отличается от заспавненного в
        первую секунду. Зовётся один раз, сразу после create_enemy()."""
        if bonus_levels <= 0:
            return
        self.level += bonus_levels
        growth = 1.15 ** bonus_levels
        self.max_health = int(self.max_health * growth)
        self.health = self.max_health
        self.physical_damage = int(self.physical_damage * (1.10 ** bonus_levels))
        self.defense += bonus_levels
        self.experience_reward = int(self.experience_reward * (1.20 ** bonus_levels))
    
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
            # Игрок вне зоны обнаружения — враг блуждает в пределах локальной области
            self.state = "idle"
            self._wander(dt)

    def _wander(self, dt):
        """Простое блуждание врага в пределах 10×10 вокруг точки спавна."""
        import random
        max_offset = 5.0  # от спавна по каждой оси

        # Не каждый кадр меняем направление, чтобы движение было плавным
        if random.random() < 0.1:
            dx = random.uniform(-1.0, 1.0)
            dy = random.uniform(-1.0, 1.0)

            # Предлагаемую позицию ограничиваем рамками 10×10 вокруг спавна
            proposed_x = self.x + dx * self.move_speed * dt
            proposed_y = self.y + dy * self.move_speed * dt

            clamped_x = max(self.spawn_x - max_offset, min(self.spawn_x + max_offset, proposed_x))
            clamped_y = max(self.spawn_y - max_offset, min(self.spawn_y + max_offset, proposed_y))

            self.move_to(clamped_x, clamped_y)
    
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
        if self.health_bar:
            self.health_bar.destroy()
            self.health_bar = None
        if self.node:
            self.node.removeNode()
            self.node = None
