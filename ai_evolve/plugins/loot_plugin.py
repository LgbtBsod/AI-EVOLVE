"""
LootPlugin - Система генерации лута, сундуков и мимиков.

Поддерживает:
- Процедурную генерацию предметов (Префикс + Основа + Суффикс + Пост-суффикс)
- Генерацию 1000+ вариантов оружия/брони в рамках сессии
- Мимиков (шанс 10%, лут x10 качества)
- Привязку предметов к сессии (удаление сессии = удаление предметов)
- Инвентарь для врагов и игроков
"""

import random
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ai_evolve.core.plugin_base import PluginBase
from ai_evolve.core.event_system import EventSystem


class Rarity(Enum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class ItemType(Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"
    SCROLL = "scroll"
    ACCESSORY = "accessory"


@dataclass
class ItemStats:
    """Статистика предмета."""
    damage: int = 0
    armor: int = 0
    health_bonus: int = 0
    mana_bonus: int = 0
    stamina_bonus: int = 0
    toughness_bonus: int = 0
    crit_chance: float = 0.0
    crit_damage: float = 1.5
    attack_speed: float = 1.0
    cooldown_reduction: float = 0.0
    area_radius: float = 0.0
    summon_count: int = 0
    effect_duration: float = 0.0
    
    # Эффекты
    effects: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "damage": self.damage,
            "armor": self.armor,
            "health_bonus": self.health_bonus,
            "mana_bonus": self.mana_bonus,
            "stamina_bonus": self.stamina_bonus,
            "toughness_bonus": self.toughness_bonus,
            "crit_chance": self.crit_chance,
            "crit_damage": self.crit_damage,
            "attack_speed": self.attack_speed,
            "cooldown_reduction": self.cooldown_reduction,
            "area_radius": self.area_radius,
            "summon_count": self.summon_count,
            "effect_duration": self.effect_duration,
            "effects": self.effects
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ItemStats':
        return cls(**data)


@dataclass
class Item:
    """Предмет с процедурной генерацией."""
    id: str
    session_id: str
    name: str
    item_type: ItemType
    rarity: Rarity
    
    # Части названия
    prefix: Optional[str] = None
    base: str = ""
    suffix: Optional[str] = None
    post_suffix: Optional[str] = None
    
    stats: ItemStats = field(default_factory=ItemStats)
    level_requirement: int = 1
    value: int = 10
    
    # Для мимиков
    is_mimic: bool = False
    mimic_level: int = 1  # Уровень мимика (влияет на множитель лута)
    
    def get_full_name(self) -> str:
        """Собрать полное название предмета."""
        parts = []
        if self.prefix:
            parts.append(self.prefix)
        parts.append(self.base)
        if self.suffix:
            parts.append(self.suffix)
        if self.post_suffix:
            parts.append(self.post_suffix)
        return " ".join(parts)
    
    def get_quality_multiplier(self) -> float:
        """Множитель качества в зависимости от редкости."""
        multipliers = {
            Rarity.COMMON: 1.0,
            Rarity.RARE: 2.5,
            Rarity.EPIC: 5.0,
            Rarity.LEGENDARY: 10.0
        }
        return multipliers.get(self.rarity, 1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "name": self.get_full_name(),
            "item_type": self.item_type.value,
            "rarity": self.rarity.value,
            "prefix": self.prefix,
            "base": self.base,
            "suffix": self.suffix,
            "post_suffix": self.post_suffix,
            "stats": self.stats.to_dict(),
            "level_requirement": self.level_requirement,
            "value": self.value,
            "is_mimic": self.is_mimic,
            "mimic_level": self.mimic_level
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Item':
        stats = ItemStats.from_dict(data.get("stats", {}))
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            name=data["name"],
            item_type=ItemType(data["item_type"]),
            rarity=Rarity(data["rarity"]),
            prefix=data.get("prefix"),
            base=data["base"],
            suffix=data.get("suffix"),
            post_suffix=data.get("post_suffix"),
            stats=stats,
            level_requirement=data.get("level_requirement", 1),
            value=data.get("value", 10),
            is_mimic=data.get("is_mimic", False),
            mimic_level=data.get("mimic_level", 1)
        )


@dataclass
class Chest:
    """Сундук с лутом."""
    id: str
    session_id: str
    x: float
    y: float
    z: float
    
    is_mimic: bool = False
    loot_table: List[Item] = field(default_factory=list)
    opened: bool = False
    
    def generate_loot(self, player_level: int, is_mimic_override: bool = False) -> List[Item]:
        """Сгенерировать лут."""
        if self.opened:
            return []
        
        # Шанс мимика: 10%
        if is_mimic_override or (not self.is_mimic and random.random() < 0.1):
            self.is_mimic = True
            # Мимики дают лут x10 качества
            return self._generate_mimic_loot(player_level)
        
        # Обычный лут
        return self._generate_normal_loot(player_level)
    
    def _generate_normal_loot(self, player_level: int) -> List[Item]:
        """Генерация обычного лута."""
        # TODO: Использовать LootGenerator
        return []
    
    def _generate_mimic_loot(self, player_level: int) -> List[Item]:
        """Генерация лута мимика (x10 качество)."""
        # TODO: Использовать LootGenerator с множителем
        return []
    
    def open(self) -> List[Item]:
        """Открыть сундук."""
        if self.opened:
            return []
        self.opened = True
        return self.loot_table
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "is_mimic": self.is_mimic,
            "loot_table": [item.to_dict() for item in self.loot_table],
            "opened": self.opened
        }


class LootGenerator:
    """Процедурная генерация предметов."""
    
    # Базы данных частей предметов
    PREFIXES = {
        ItemType.WEAPON: ["Легендарный", "Древний", "Проклятый", "Священный", "Тёмный", "Кровавый", "Ледяной", "Огненный"],
        ItemType.ARMOR: ["Непробиваемый", "Зачарованный", "Тяжёлый", "Лёгкий", "Блестящий", "Ржавый", "Магический"],
        ItemType.CONSUMABLE: ["Мощное", "Слабое", "Яркое", "Тёмное"],
        ItemType.SCROLL: ["Древний", "Забытый", "Проклятый", "Священный"],
        ItemType.ACCESSORY: ["Удачливый", "Мудрый", "Быстрый", "Сильный", "Хитрый"]
    }
    
    BASES = {
        ItemType.WEAPON: ["Меч", "Топор", "Кинжал", "Копьё", "Молот", "Лук", "Посох", "Клинок"],
        ItemType.ARMOR: ["Шлем", "Нагрудник", "Поножи", "Перчатки", "Сапоги", "Щит", "Доспех"],
        ItemType.CONSUMABLE: ["Зелье", "Еда", "Эликсир"],
        ItemType.SCROLL: ["Свиток", "Манускрипт", "Гримуар"],
        ItemType.ACCESSORY: ["Кольцо", "Амулет", "Серёжка", "Браслет"]
    }
    
    SUFFIXES = {
        ItemType.WEAPON: ["Огненной смерти", "Ледяного ветра", "Грома", "Яда", "Тьмы", "Света", "Крови"],
        ItemType.ARMOR: ["Защиты", "Сопротивления", "Здоровья", "Маны", "Скорости"],
        ItemType.CONSUMABLE: ["Лечения", "Маны", "Силы"],
        ItemType.SCROLL: ["Огня", "Льда", "Молнии"],
        ItemType.ACCESSORY: ["Удачи", "Мудрости", "Силы", "Ловкости"]
    }
    
    POST_SUFFIXES = {
        ItemType.WEAPON: ["Истинный", "Вечный", "Бесконечный", "Разрушительный"],
        ItemType.ARMOR: ["Неуязвимости", "Бессмертия"],
        Rarity.LEGENDARY: ["Героя", "Бога", "Титана"]
    }
    
    # Базовые эффекты
    EFFECT_TEMPLATES = [
        {"type": "burn", "duration": 3.0, "damage_per_sec": 10},
        {"type": "freeze", "duration": 2.0, "slow_percent": 0.5},
        {"type": "poison", "duration": 5.0, "damage_per_sec": 5},
        {"type": "rage", "duration": 10.0, "damage_mult": 1.5},
        {"type": "haste", "duration": 8.0, "attack_speed_mult": 1.3},
        {"type": "shield", "duration": 5.0, "absorb_amount": 100}
    ]
    
    def __init__(self, session_id: str, seed: Optional[int] = None):
        self.session_id = session_id
        self.seed = seed
        if seed is not None:
            random.seed(seed)
        
        # Кэш сгенерированных предметов для сессии
        self.generated_items: Dict[str, Item] = {}
    
    def generate_item(self, item_type: ItemType, rarity: Rarity, 
                     level: int = 1, force_mimic: bool = False) -> Item:
        """Сгенерировать предмет."""
        import uuid
        
        item_id = str(uuid.uuid4())
        
        # Выбор частей названия
        prefix = random.choice(self.PREFIXES.get(item_type, [])) if rarity != Rarity.COMMON else None
        base = random.choice(self.BASES.get(item_type, ["Предмет"]))
        suffix = random.choice(self.SUFFIXES.get(item_type, [])) if rarity != Rarity.COMMON else None
        
        # Пост-суффикс только для легендарок
        post_suffix = None
        if rarity == Rarity.LEGENDARY:
            post_suffix = random.choice(self.POST_SUFFIXES.get(Rarity.LEGENDARY, []))
        elif item_type in self.POST_SUFFIXES and random.random() < 0.3:
            post_suffix = random.choice(self.POST_SUFFIXES[item_type])
        
        # Генерация статов
        stats = self._generate_stats(item_type, rarity, level)
        
        # Добавление случайных эффектов
        if rarity != Rarity.COMMON:
            num_effects = {
                Rarity.RARE: 1,
                Rarity.EPIC: 2,
                Rarity.LEGENDARY: 3
            }.get(rarity, 0)
            
            for _ in range(num_effects):
                effect = random.choice(self.EFFECT_TEMPLATES).copy()
                # Скалирование эффекта от уровня
                effect["damage_per_sec"] = effect.get("damage_per_sec", 0) * (1 + level * 0.1)
                effect["absorb_amount"] = effect.get("absorb_amount", 0) * (1 + level * 0.1)
                stats.effects.append(effect)
        
        item = Item(
            id=item_id,
            session_id=self.session_id,
            name=f"{prefix or ''} {base} {suffix or ''}".strip(),
            item_type=item_type,
            rarity=rarity,
            prefix=prefix,
            base=base,
            suffix=suffix,
            post_suffix=post_suffix,
            stats=stats,
            level_requirement=level,
            value=self._calculate_value(rarity, level),
            is_mimic=force_mimic
        )
        
        self.generated_items[item_id] = item
        return item
    
    def _generate_stats(self, item_type: ItemType, rarity: Rarity, level: int) -> ItemStats:
        """Сгенерировать статы предмета."""
        base_mult = {
            Rarity.COMMON: 1.0,
            Rarity.RARE: 2.5,
            Rarity.EPIC: 5.0,
            Rarity.LEGENDARY: 10.0
        }.get(rarity, 1.0)
        
        stats = ItemStats()
        
        if item_type == ItemType.WEAPON:
            stats.damage = int(10 * base_mult * (1 + level * 0.2))
            stats.crit_chance = min(0.3 * base_mult, 0.5)
            stats.attack_speed = 1.0 + (0.1 * base_mult)
            
            # Шанс на AoE или суммонинг для легендарок
            if rarity == Rarity.LEGENDARY:
                if random.random() < 0.5:
                    stats.area_radius = 5.0 + (level * 0.5)
                else:
                    stats.summon_count = 1 + (level // 5)
        
        elif item_type == ItemType.ARMOR:
            stats.armor = int(15 * base_mult * (1 + level * 0.2))
            stats.health_bonus = int(50 * base_mult * (1 + level * 0.3))
            stats.toughness_bonus = int(10 * base_mult * (1 + level * 0.2))
        
        elif item_type == ItemType.ACCESSORY:
            stats.mana_bonus = int(30 * base_mult * (1 + level * 0.2))
            stats.stamina_bonus = int(30 * base_mult * (1 + level * 0.2))
            stats.crit_damage = 1.5 + (0.2 * base_mult)
        
        return stats
    
    def _calculate_value(self, rarity: Rarity, level: int) -> int:
        """Рассчитать стоимость предмета."""
        base_values = {
            Rarity.COMMON: 10,
            Rarity.RARE: 50,
            Rarity.EPIC: 200,
            Rarity.LEGENDARY: 1000
        }
        return int(base_values.get(rarity, 10) * (1 + level * 0.5))
    
    def generate_chest_loot(self, chest_level: int, is_mimic: bool = False) -> List[Item]:
        """Сгенерировать лут для сундука."""
        num_items = random.randint(2, 5)
        if is_mimic:
            num_items = random.randint(5, 10)  # Мимики дают больше предметов
        
        loot = []
        for _ in range(num_items):
            # Определение редкости
            rarity_roll = random.random()
            if is_mimic:
                # Мимики имеют лучшие шансы
                if rarity_roll < 0.1:
                    rarity = Rarity.LEGENDARY
                elif rarity_roll < 0.4:
                    rarity = Rarity.EPIC
                elif rarity_roll < 0.7:
                    rarity = Rarity.RARE
                else:
                    rarity = Rarity.COMMON
            else:
                # Обычные шансы
                if rarity_roll < 0.02:
                    rarity = Rarity.LEGENDARY
                elif rarity_roll < 0.1:
                    rarity = Rarity.EPIC
                elif rarity_roll < 0.3:
                    rarity = Rarity.RARE
                else:
                    rarity = Rarity.COMMON
            
            # Определение типа предмета
            item_type = random.choice(list(ItemType))
            
            item = self.generate_item(item_type, rarity, chest_level, force_mimic=False)
            loot.append(item)
        
        return loot


class LootPlugin(PluginBase):
    """Плагин управления лутом и сундуками."""
    
    name = "loot"
    version = "1.0.0"
    description = "Система генерации лута, сундуков и мимиков"
    
    dependencies = ["inventory", "database"]
    
    def __init__(self):
        super().__init__()
        self.generator: Optional[LootGenerator] = None
        self.chests: Dict[str, Chest] = {}
        self.player_inventory: Dict[str, List[Item]] = {}  # session_id -> items
        self.enemy_inventory: Dict[str, List[Item]] = {}  # enemy_id -> items
    
    def initialize(self, config: Dict[str, Any], game_core: Any) -> bool:
        """Инициализация плагина."""
        try:
            self.game_core = game_core
            self.event_system = EventSystem.get_instance()
            
            # Инициализация генератора для текущей сессии
            session_id = config.get("session_id", "default")
            seed = config.get("seed")
            self.generator = LootGenerator(session_id, seed)
            
            # Регистрация обработчиков событий
            self.event_system.subscribe("chest.open", self._on_chest_open)
            self.event_system.subscribe("enemy.kill", self._on_enemy_kill)
            self.event_system.subscribe("session.start", self._on_session_start)
            self.event_system.subscribe("session.end", self._on_session_end)
            
            self.logger.info(f"LootPlugin initialized for session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize LootPlugin: {e}")
            return False
    
    def _on_session_start(self, event_data: Dict[str, Any]):
        """Начало сессии - создание генератора."""
        session_id = event_data.get("session_id")
        seed = event_data.get("seed")
        self.generator = LootGenerator(session_id, seed)
        self.player_inventory[session_id] = []
        self.logger.info(f"New session started: {session_id}")
    
    def _on_session_end(self, event_data: Dict[str, Any]):
        """Конец сессии - очистка предметов."""
        session_id = event_data.get("session_id")
        
        # Удаление всех предметов сессии из БД
        if session_id in self.player_inventory:
            del self.player_inventory[session_id]
        
        # Очистка сундуков
        chests_to_remove = [cid for cid, chest in self.chests.items() 
                          if chest.session_id == session_id]
        for cid in chests_to_remove:
            del self.chests[cid]
        
        self.logger.info(f"Session ended, cleaned up items for {session_id}")
    
    def _on_chest_open(self, event_data: Dict[str, Any]):
        """Открытие сундука."""
        chest_id = event_data.get("chest_id")
        player_id = event_data.get("player_id")
        player_level = event_data.get("player_level", 1)
        
        if chest_id not in self.chests:
            self.logger.warning(f"Chest {chest_id} not found")
            return
        
        chest = self.chests[chest_id]
        loot = chest.open()
        
        if loot:
            # Добавление лута в инвентарь игрока
            session_id = chest.session_id
            if session_id not in self.player_inventory:
                self.player_inventory[session_id] = []
            
            self.player_inventory[session_id].extend(loot)
            
            # Событие получения лута
            self.event_system.emit("loot.received", {
                "player_id": player_id,
                "chest_id": chest_id,
                "items": [item.to_dict() for item in loot],
                "is_mimic": chest.is_mimic
            })
            
            self.logger.info(f"Opened chest {chest_id}, got {len(loot)} items (mimic: {chest.is_mimic})")
    
    def _on_enemy_kill(self, event_data: Dict[str, Any]):
        """Убийство врага - выпадение лута."""
        enemy_id = event_data.get("enemy_id")
        player_id = event_data.get("player_id")
        
        if enemy_id in self.enemy_inventory:
            loot = self.enemy_inventory[enemy_id]
            session_id = event_data.get("session_id")
            
            if session_id not in self.player_inventory:
                self.player_inventory[session_id] = []
            
            self.player_inventory[session_id].extend(loot)
            
            self.event_system.emit("loot.received", {
                "player_id": player_id,
                "enemy_id": enemy_id,
                "items": [item.to_dict() for item in loot]
            })
            
            del self.enemy_inventory[enemy_id]
    
    def create_chest(self, x: float, y: float, z: float, 
                    level: int = 1, force_mimic: bool = False) -> Chest:
        """Создать сундук."""
        import uuid
        
        chest_id = str(uuid.uuid4())
        session_id = self.generator.session_id if self.generator else "default"
        
        chest = Chest(
            id=chest_id,
            session_id=session_id,
            x=x, y=y, z=z,
            is_mimic=force_mimic
        )
        
        # Генерация лута
        if self.generator:
            chest.loot_table = self.generator.generate_chest_loot(level, force_mimic)
        
        self.chests[chest_id] = chest
        self.logger.info(f"Created chest {chest_id} at ({x}, {y}, {z}), mimic: {force_mimic}")
        
        return chest
    
    def equip_item(self, player_id: str, item_id: str, slot: str) -> bool:
        """Экипировать предмет."""
        session_id = self._get_player_session(player_id)
        if not session_id or session_id not in self.player_inventory:
            return False
        
        # Поиск предмета
        item = None
        for i, it in enumerate(self.player_inventory[session_id]):
            if it.id == item_id:
                item = it
                break
        
        if not item:
            return False
        
        # Событие экипировки
        self.event_system.emit("item.equipped", {
            "player_id": player_id,
            "item_id": item_id,
            "slot": slot,
            "item": item.to_dict()
        })
        
        self.logger.info(f"Player {player_id} equipped {item.get_full_name()} in {slot}")
        return True
    
    def use_item(self, player_id: str, item_id: str) -> bool:
        """Использовать предмет (расходник)."""
        session_id = self._get_player_session(player_id)
        if not session_id or session_id not in self.player_inventory:
            return False
        
        # Поиск предмета
        item = None
        for i, it in enumerate(self.player_inventory[session_id]):
            if it.id == item_id:
                item = it
                if it.item_type == ItemType.CONSUMABLE:
                    del self.player_inventory[session_id][i]
                break
        
        if not item:
            return False
        
        # Событие использования
        self.event_system.emit("item.used", {
            "player_id": player_id,
            "item_id": item_id,
            "item": item.to_dict()
        })
        
        self.logger.info(f"Player {player_id} used {item.get_full_name()}")
        return True
    
    def _get_player_session(self, player_id: str) -> Optional[str]:
        """Получить session_id игрока."""
        # В реальной игре это будет приходить из контекста
        for session_id, items in self.player_inventory.items():
            # Упрощённая логика - первый найденный
            return session_id
        return None
    
    def shutdown(self):
        """Завершение работы плагина."""
        self.chests.clear()
        self.player_inventory.clear()
        self.enemy_inventory.clear()
        self.generator = None
        self.logger.info("LootPlugin shutdown complete")
