"""
Plugin: Session Content Generator
Генерация уникального контента сессии: предметы, навыки, свитки, лут
Каждая сессия генерирует уникальный набор доступного контента
"""

import random
import hashlib
import time
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from .base import DevProbePlugin, PluginReport


@dataclass
class ItemTemplate:
    """Шаблон предмета"""
    item_id: str
    name: str
    item_type: str  # weapon, armor, consumable, scroll, material
    rarity: str  # common, uncommon, rare, epic, legendary
    base_stats: Dict[str, float] = field(default_factory=dict)
    effects: List[str] = field(default_factory=list)
    min_level: int = 1
    source_types: List[str] = field(default_factory=list)  # chest, enemy, quest, vendor


@dataclass
class SkillTemplate:
    """Шаблон навыка"""
    skill_id: str
    name: str
    skill_type: str  # active, passive, ultimate
    element: str  # physical, fire, water, earth, air, dark, light
    base_power: float = 0.0
    cooldown: float = 0.0
    mana_cost: int = 0
    min_level: int = 1
    required_stats: Dict[str, int] = field(default_factory=dict)


@dataclass
class SessionContent:
    """Контент игровой сессии"""
    session_id: str
    seed: int
    generated_items: Dict[str, ItemTemplate] = field(default_factory=dict)
    generated_skills: Dict[str, SkillTemplate] = field(default_factory=dict)
    loot_tables: Dict[str, List[Dict]] = field(default_factory=dict)
    quest_rewards: Dict[str, Dict] = field(default_factory=dict)
    unique_modifiers: List[str] = field(default_factory=list)  # Уникальные модификаторы сессии


class SessionContentPlugin(DevProbePlugin):
    """Плагин генерации контента сессии"""
    
    name = "session_content_generator"
    version = "1.0.0"
    description = "Генерация уникального контента для каждой игровой сессии"
    dependencies = []
    
    # Базовые данные для генерации
    ITEM_PREFIXES = {
        "weapon": ["Rusty", "Sharp", "Deadly", "Merciless", "Divine"],
        "armor": ["Worn", "Sturdy", "Reinforced", "Impenetrable", "Celestial"],
        "consumable": ["Small", "Moderate", "Large", "Greater", "Supreme"],
        "scroll": ["Tattered", "Ancient", "Glowing", "Arcane", "Mythical"]
    }
    
    ITEM_SUFFIXES = {
        "weapon": ["Dagger", "Sword", "Axe", "Mace", "Staff", "Bow"],
        "armor": ["Cloth", "Leather", "Mail", "Plate", "Shield"],
        "consumable": ["Potion", "Elixir", "Balm", "Draught", "Tonic"],
        "scroll": ["Scroll of Fire", "Scroll of Ice", "Scroll of Lightning", "Scroll of Healing", "Scroll of Protection"]
    }
    
    SKILL_NAMES = {
        "fire": ["Flame Strike", "Fireball", "Inferno", "Pyroblast", "Meteor"],
        "water": ["Water Jet", "Healing Wave", "Ice Lance", "Tsunami", "Frozen Orb"],
        "earth": ["Stone Skin", "Earthquake", "Rock Spike", "Mountain Force", "Crystal Shield"],
        "air": ["Wind Slash", "Lightning Bolt", "Tornado", "Thunder Storm", "Gale Force"],
        "physical": ["Power Strike", "Cleave", "Execute", "Rampage", "Berserker Rage"],
        "dark": ["Shadow Bolt", "Drain Life", "Fear", "Dark Pact", "Soul Harvest"],
        "light": ["Holy Smite", "Divine Light", "Purify", "Resurrection", "Heaven's Wrath"]
    }
    
    RARITY_WEIGHTS = {
        "common": 50,
        "uncommon": 30,
        "rare": 15,
        "epic": 4,
        "legendary": 1
    }
    
    def __init__(self, core):
        super().__init__(core)
        self.session_content: Optional[SessionContent] = None
        self.config = {
            "num_base_items": 50,  # Количество базовых предметов
            "num_base_skills": 30,  # Количество базовых навыков
            "enable_unique_modifiers": True,
            "loot_randomization": True,
            "seed_from_session": True  # Использовать session_id как seed
        }
    
    def initialize(self, context: Any) -> bool:
        if not super().initialize(context):
            return False
        
        # Генерация контента при инициализации
        self.generate_session_content()
        
        context.add_log(
            "INFO",
            f"Session content generated: {len(self.session_content.generated_items)} items, "
            f"{len(self.session_content.generated_skills)} skills",
            category="content_generation"
        )
        
        return True
    
    def generate_session_content(self, seed: Optional[int] = None):
        """Генерация уникального контента сессии"""
        if seed is None:
            if self.config["seed_from_session"]:
                # Использование session_id как seed для воспроизводимости
                seed = int(hashlib.md5(self.core.session_id.encode()).hexdigest()[:8], 16)
            else:
                seed = random.randint(0, 2**32 - 1)
        
        random.seed(seed)
        
        self.session_content = SessionContent(
            session_id=self.core.session_id,
            seed=seed
        )
        
        # Генерация предметов
        self._generate_items()
        
        # Генерация навыков
        self._generate_skills()
        
        # Генерация таблиц лута
        self._generate_loot_tables()
        
        # Генерация наград за квесты
        self._generate_quest_rewards()
        
        # Генерация уникальных модификаторов сессии
        if self.config["enable_unique_modifiers"]:
            self._generate_unique_modifiers()
        
        # Сброс seed для других операций
        random.seed()
    
    def _generate_items(self):
        """Генерация предметов сессии"""
        num_items = self.config["num_base_items"]
        
        for i in range(num_items):
            item_type = random.choice(["weapon", "armor", "consumable", "scroll"])
            rarity = self._weighted_choice(self.RARITY_WEIGHTS)
            
            prefix_list = self.ITEM_PREFIXES[item_type]
            suffix_list = self.ITEM_SUFFIXES[item_type]
            
            prefix = random.choice(prefix_list)
            suffix = random.choice(suffix_list)
            
            item_id = f"item_{self.session_content.session_id}_{i}"
            name = f"{prefix} {suffix}"
            
            # Генерация статов в зависимости от редкости
            rarity_mult = {"common": 1.0, "uncommon": 1.5, "rare": 2.0, "epic": 3.0, "legendary": 5.0}[rarity]
            
            base_stats = {}
            if item_type == "weapon":
                base_stats["damage"] = round(random.uniform(10, 50) * rarity_mult, 1)
                base_stats["attack_speed"] = round(random.uniform(0.8, 2.0), 2)
            elif item_type == "armor":
                base_stats["defense"] = round(random.uniform(15, 75) * rarity_mult, 1)
                base_stats["durability"] = int(random.uniform(100, 500) * rarity_mult)
            elif item_type == "consumable":
                base_stats["heal_amount"] = round(random.uniform(50, 200) * rarity_mult, 1)
                base_stats["duration"] = random.uniform(5, 30)
            
            # Определение источников появления
            source_types = []
            if rarity in ["common", "uncommon"]:
                source_types.extend(["chest", "enemy", "vendor"])
            if rarity in ["rare", "epic"]:
                source_types.extend(["chest", "quest", "boss"])
            if rarity == "legendary":
                source_types = ["unique_boss", "legendary_quest"]
            
            item = ItemTemplate(
                item_id=item_id,
                name=name,
                item_type=item_type,
                rarity=rarity,
                base_stats=base_stats,
                min_level=random.randint(1, max(1, int(rarity_mult * 5))),
                source_types=source_types
            )
            
            self.session_content.generated_items[item_id] = item
    
    def _generate_skills(self):
        """Генерация навыков сессии"""
        num_skills = self.config["num_base_skills"]
        elements = list(self.SKILL_NAMES.keys())
        
        for i in range(num_skills):
            element = random.choice(elements)
            skill_names = self.SKILL_NAMES[element]
            skill_name = random.choice(skill_names)
            
            skill_id = f"skill_{self.session_content.session_id}_{i}"
            
            skill_type = random.choice(["active", "passive", "ultimate"])
            base_power = random.uniform(50, 200) if skill_type != "passive" else 0
            cooldown = random.uniform(0, 30) if skill_type == "active" else 0
            if skill_type == "ultimate":
                cooldown = random.uniform(60, 180)
            
            mana_cost = int(base_power * random.uniform(0.5, 1.5)) if skill_type != "passive" else 0
            
            skill = SkillTemplate(
                skill_id=skill_id,
                name=f"{element.capitalize()} {skill_name}",
                skill_type=skill_type,
                element=element,
                base_power=round(base_power, 1),
                cooldown=round(cooldown, 1),
                mana_cost=mana_cost,
                min_level=random.randint(1, 15)
            )
            
            self.session_content.generated_skills[skill_id] = skill
    
    def _generate_loot_tables(self):
        """Генерация таблиц лута"""
        # Лут из сундуков
        chest_loot = []
        for item_id, item in self.session_content.generated_items.items():
            if "chest" in item.source_types:
                weight = self.RARITY_WEIGHTS.get(item.rarity, 1)
                chest_loot.append({
                    "item_id": item_id,
                    "weight": weight,
                    "min_count": 1,
                    "max_count": 3 if item.item_type == "consumable" else 1
                })
        
        self.session_content.loot_tables["chest"] = chest_loot
        
        # Лут из врагов
        enemy_loot = []
        for item_id, item in self.session_content.generated_items.items():
            if "enemy" in item.source_types:
                weight = self.RARITY_WEIGHTS.get(item.rarity, 1) * 0.5  # Реже из врагов
                enemy_loot.append({
                    "item_id": item_id,
                    "weight": weight,
                    "min_count": 1,
                    "max_count": 1
                })
        
        self.session_content.loot_tables["enemy"] = enemy_loot
        
        # Лут из боссов
        boss_loot = []
        for item_id, item in self.session_content.generated_items.items():
            if "boss" in item.source_types or "unique_boss" in item.source_types:
                weight = self.RARITY_WEIGHTS.get(item.rarity, 1) * 2  # Чаще из боссов
                boss_loot.append({
                    "item_id": item_id,
                    "weight": weight,
                    "min_count": 1,
                    "max_count": 5
                })
        
        self.session_content.loot_tables["boss"] = boss_loot
    
    def _generate_quest_rewards(self):
        """Генерация наград за квесты"""
        quest_types = ["main_story", "side_quest", "daily", "weekly", "legendary"]
        
        for quest_type in quest_types:
            rewards = {
                "items": [],
                "skills": [],
                "experience": 0,
                "gold": 0
            }
            
            # Награда опытом
            xp_base = {"main_story": 500, "side_quest": 200, "daily": 100, "weekly": 500, "legendary": 2000}[quest_type]
            rewards["experience"] = random.randint(xp_base, xp_base * 2)
            
            # Награда золотом
            gold_base = {"main_story": 100, "side_quest": 50, "daily": 20, "weekly": 200, "legendary": 1000}[quest_type]
            rewards["gold"] = random.randint(gold_base, gold_base * 3)
            
            # Предметы в награду
            for item_id, item in self.session_content.generated_items.items():
                if "quest" in item.source_types or (quest_type == "legendary" and item.rarity == "legendary"):
                    if random.random() < 0.3:
                        rewards["items"].append({"item_id": item_id, "count": 1})
            
            # Навыки в награду (для важных квестов)
            if quest_type in ["main_story", "legendary"]:
                for skill_id, skill in self.session_content.generated_skills.items():
                    if skill.min_level <= 10 and random.random() < 0.2:
                        rewards["skills"].append({"skill_id": skill_id, "source": f"quest_{quest_type}"})
            
            self.session_content.quest_rewards[quest_type] = rewards
    
    def _generate_unique_modifiers(self):
        """Генерация уникальных модификаторов сессии"""
        modifier_pool = [
            "double_xp_weekend", "increased_drop_rate", "reduced_vendor_prices",
            "bonus_skill_points", "extra_chest_spawns", "elite_enemy_boost",
            "crafting_discount", "faster_mount_speed", "increased_reputation_gain"
        ]
        
        # Выбор 2-4 случайных модификаторов для сессии
        num_modifiers = random.randint(2, 4)
        self.session_content.unique_modifiers = random.sample(modifier_pool, num_modifiers)
    
    def _weighted_choice(self, weights_dict: Dict[str, int]) -> str:
        """Выбор элемента с учетом весов"""
        items = list(weights_dict.keys())
        weights = list(weights_dict.values())
        return random.choices(items, weights=weights)[0]
    
    def execute(self, context: Any) -> Dict[str, Any]:
        """Выполнение плагина - валидация сгенерированного контента"""
        start_time = time.time()
        
        results = {
            "items_generated": len(self.session_content.generated_items),
            "skills_generated": len(self.session_content.generated_skills),
            "loot_tables_count": len(self.session_content.loot_tables),
            "quest_rewards_count": len(self.session_content.quest_rewards),
            "unique_modifiers": len(self.session_content.unique_modifiers),
            "validation_errors": [],
            "execution_time_sec": 0
        }
        
        # Валидация предметов
        for item_id, item in self.session_content.generated_items.items():
            if not item.name:
                results["validation_errors"].append(f"Item {item_id} has no name")
            if not item.base_stats and item.item_type != "scroll":
                results["validation_errors"].append(f"Item {item_id} has no stats")
            if not item.source_types:
                results["validation_errors"].append(f"Item {item_id} has no sources")
        
        # Валидация навыков
        for skill_id, skill in self.session_content.generated_skills.items():
            if not skill.name:
                results["validation_errors"].append(f"Skill {skill_id} has no name")
            if skill.skill_type == "active" and skill.cooldown <= 0:
                results["validation_errors"].append(f"Skill {skill_id} has invalid cooldown")
        
        # Проверка таблиц лута
        for table_name, loot_table in self.session_content.loot_tables.items():
            if not loot_table:
                results["validation_errors"].append(f"Loot table '{table_name}' is empty")
            total_weight = sum(item["weight"] for item in loot_table)
            if total_weight <= 0:
                results["validation_errors"].append(f"Loot table '{table_name}' has zero total weight")
        
        results["execution_time_sec"] = round(time.time() - start_time, 3)
        
        if results["validation_errors"]:
            for error in results["validation_errors"]:
                context.add_anomaly(
                    "content_validation_error",
                    "MEDIUM",
                    error
                )
        
        context.add_log(
            "INFO",
            f"Content validation completed: {len(results['validation_errors'])} errors",
            category="content_generation"
        )
        
        return results
    
    def get_item_by_id(self, item_id: str) -> Optional[ItemTemplate]:
        """Получение предмета по ID"""
        return self.session_content.generated_items.get(item_id)
    
    def get_skill_by_id(self, skill_id: str) -> Optional[SkillTemplate]:
        """Получение навыка по ID"""
        return self.session_content.generated_skills.get(skill_id)
    
    def roll_loot(self, loot_table_name: str, num_rolls: int = 1) -> List[Dict]:
        """Бросок таблицы лута"""
        if not self.session_content or loot_table_name not in self.session_content.loot_tables:
            return []
        
        loot_table = self.session_content.loot_tables[loot_table_name]
        if not loot_table:
            return []
        
        results = []
        total_weight = sum(item["weight"] for item in loot_table)
        
        for _ in range(num_rolls):
            roll = random.uniform(0, total_weight)
            current = 0
            
            for loot_item in loot_table:
                current += loot_item["weight"]
                if roll <= current:
                    count = random.randint(loot_item["min_count"], loot_item["max_count"])
                    results.append({
                        "item_id": loot_item["item_id"],
                        "count": count
                    })
                    break
        
        return results
    
    def get_report(self, context: Any) -> Dict:
        """Генерация отчета плагина"""
        base_report = super().get_report(context)
        
        # Статистика по редкости предметов
        rarity_distribution = {}
        for item in self.session_content.generated_items.values():
            r = item.rarity
            rarity_distribution[r] = rarity_distribution.get(r, 0) + 1
        
        # Статистика по типам навыков
        skill_type_dist = {}
        for skill in self.session_content.generated_skills.values():
            st = skill.skill_type
            skill_type_dist[st] = skill_type_dist.get(st, 0) + 1
        
        # Статистика по элементам
        element_dist = {}
        for skill in self.session_content.generated_skills.values():
            e = skill.element
            element_dist[e] = element_dist.get(e, 0) + 1
        
        base_report.update({
            "session_seed": self.session_content.seed,
            "items_by_rarity": rarity_distribution,
            "skills_by_type": skill_type_dist,
            "skills_by_element": element_dist,
            "unique_session_modifiers": self.session_content.unique_modifiers,
            "config": self.config
        })
        
        return base_report
    
    def cleanup(self, context: Any):
        """Очистка"""
        if self.session_content:
            self.session_content.generated_items.clear()
            self.session_content.generated_skills.clear()
            self.session_content.loot_tables.clear()
            self.session_content.quest_rewards.clear()
            self.session_content.unique_modifiers.clear()
        super().cleanup(context)
