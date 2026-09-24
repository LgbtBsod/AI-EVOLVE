"""
Crafting System - Создание предметов из ресурсов
Принципы: SOLID, DRY, Python Best Practices
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CraftResult(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CRITICAL_SUCCESS = "critical_success"
    INSUFFICIENT_RESOURCES = "insufficient_resources"
    RECIPE_LOCKED = "recipe_locked"


@dataclass
class Recipe:
    id: str
    name: str
    required_items: Dict[str, int]
    result_item: str
    result_count: int = 1
    skill_required: int = 0
    unlock_condition: Optional[str] = None
    critical_chance: float = 0.05
    
    def __post_init__(self):
        if self.critical_chance < 0 or self.critical_chance > 1:
            raise ValueError("Critical chance must be between 0 and 1")


@dataclass
class CraftingSkill:
    level: int = 1
    experience: int = 0
    recipes_unlocked: List[str] = field(default_factory=list)
    
    EXP_PER_LEVEL_BASE = 100
    MAX_LEVEL = 100
    
    def get_exp_for_next_level(self) -> int:
        return int(self.EXP_PER_LEVEL_BASE * (1.1 ** self.level))
    
    def add_experience(self, amount: int) -> bool:
        """Добавить опыт, вернуть True если уровень повышен"""
        self.experience += amount
        leveled_up = False
        
        while self.experience >= self.get_exp_for_next_level() and self.level < self.MAX_LEVEL:
            self.experience -= self.get_exp_for_next_level()
            self.level += 1
            leveled_up = True
            logger.info(f"Crafting skill leveled up to {self.level}")
            
        return leveled_up


class CraftingSystem:
    """
    Система крафта с поддержкой рецептов, навыков и критического успеха
    SSOT для всех операций крафта
    """
    
    def __init__(self):
        self._recipes: Dict[str, Recipe] = {}
        self._player_skills: Dict[str, CraftingSkill] = {}  # key: player_id
        self._crafting_history: List[Dict] = []
        
    def register_recipe(self, recipe: Recipe):
        """Зарегистрировать рецепт (SSOT)"""
        if recipe.id in self._recipes:
            logger.warning(f"Recipe {recipe.id} already exists, overwriting")
        self._recipes[recipe.id] = recipe
        logger.debug(f"Registered recipe: {recipe.name}")
    
    def get_recipe(self, recipe_id: str) -> Optional[Recipe]:
        return self._recipes.get(recipe_id)
    
    def get_player_skill(self, player_id: str) -> CraftingSkill:
        """Получить или создать навык крафта для игрока"""
        if player_id not in self._player_skills:
            self._player_skills[player_id] = CraftingSkill()
        return self._player_skills[player_id]
    
    def can_craft(self, player_id: str, recipe_id: str, inventory: Dict[str, int]) -> Tuple[bool, str]:
        """Проверить возможность крафта"""
        recipe = self.get_recipe(recipe_id)
        if not recipe:
            return False, f"Recipe {recipe_id} not found"
        
        skill = self.get_player_skill(player_id)
        if skill.level < recipe.skill_required:
            return False, f"Skill level {skill.level} < required {recipe.skill_required}"
        
        if recipe.unlock_condition and recipe.id not in skill.recipes_unlocked:
            return False, f"Recipe {recipe.name} is locked"
        
        for item, count in recipe.required_items.items():
            if inventory.get(item, 0) < count:
                return False, f"Insufficient {item}: have {inventory.get(item, 0)}, need {count}"
        
        return True, "Ready to craft"
    
    def craft(self, player_id: str, recipe_id: str, inventory: Dict[str, int]) -> Tuple[CraftResult, Dict]:
        """
        Выполнить крафт
        Returns: (result, details)
        """
        can_do, reason = self.can_craft(player_id, recipe_id, inventory)
        if not can_do:
            if "Insufficient" in reason:
                return CraftResult.INSUFFICIENT_RESOURCES, {"reason": reason}
            elif "locked" in reason.lower():
                return CraftResult.RECIPE_LOCKED, {"reason": reason}
            return CraftResult.FAILURE, {"reason": reason}
        
        recipe = self.get_recipe(recipe_id)
        skill = self.get_player_skill(player_id)
        
        # Расчет шансов
        import random
        crit_roll = random.random()
        is_critical = crit_roll < recipe.critical_chance
        
        # Потребление ресурсов
        consumed = {}
        for item, count in recipe.required_items.items():
            consumed[item] = count
        
        # Результат
        result_count = recipe.result_count
        if is_critical:
            result_count *= 2  # Критический успех удваивает результат
            result = CraftResult.CRITICAL_SUCCESS
            exp_gain = 150
        else:
            result = CraftResult.SUCCESS
            exp_gain = 100
        
        # Повышение навыка
        leveled_up = skill.add_experience(exp_gain)
        
        # Запись в историю
        log_entry = {
            "player_id": player_id,
            "recipe_id": recipe_id,
            "result": result.value,
            "is_critical": is_critical,
            "output_count": result_count,
            "consumed": consumed,
            "leveled_up": leveled_up
        }
        self._crafting_history.append(log_entry)
        
        output = {recipe.result_item: result_count}
        
        logger.info(f"Crafted {recipe.name}: {result.value}, output: {output}")
        
        return result, {
            "output": output,
            "consumed": consumed,
            "is_critical": is_critical,
            "experience_gained": exp_gain,
            "leveled_up": leveled_up
        }
    
    def unlock_recipe(self, player_id: str, recipe_id: str):
        """Разблокировать рецепт для игрока"""
        skill = self.get_player_skill(player_id)
        if recipe_id in self._recipes and recipe_id not in skill.recipes_unlocked:
            skill.recipes_unlocked.append(recipe_id)
            logger.info(f"Unlocked recipe {recipe_id} for player {player_id}")
    
    def get_history(self, player_id: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Получить историю крафта"""
        history = self._crafting_history
        if player_id:
            history = [h for h in history if h["player_id"] == player_id]
        return history[-limit:]


# Стандартные рецепты
DEFAULT_RECIPES = [
    Recipe(
        id="health_potion",
        name="Health Potion",
        required_items={"herb": 3, "water": 1},
        result_item="health_potion",
        result_count=1,
        skill_required=1
    ),
    Recipe(
        id="iron_sword",
        name="Iron Sword",
        required_items={"iron_ore": 5, "coal": 2},
        result_item="iron_sword",
        result_count=1,
        skill_required=5,
        critical_chance=0.1
    ),
    Recipe(
        id="magic_staff",
        name="Magic Staff",
        required_items={"wood": 3, "crystal": 2, "essence": 1},
        result_item="magic_staff",
        result_count=1,
        skill_required=10,
        critical_chance=0.15
    ),
]


def initialize_crafting_system() -> CraftingSystem:
    """Инициализировать систему с базовыми рецептами"""
    system = CraftingSystem()
    for recipe in DEFAULT_RECIPES:
        system.register_recipe(recipe)
    logger.info("Crafting system initialized with default recipes")
    return system


if __name__ == "__main__":
    # Self-test
    print("Testing Crafting System...")
    system = initialize_crafting_system()
    
    # Test crafting
    inventory = {"herb": 10, "water": 5, "iron_ore": 10, "coal": 5}
    
    result, details = system.craft("player1", "health_potion", inventory)
    assert result == CraftResult.SUCCESS, f"Expected SUCCESS, got {result}"
    assert details["output"]["health_potion"] == 1
    print(f"✓ Basic craft: {result.value}")
    
    # Test critical
    for _ in range(20):  # Try to trigger crit
        result, details = system.craft("player1", "health_potion", inventory)
        if result == CraftResult.CRITICAL_SUCCESS:
            print(f"✓ Critical success triggered!")
            break
    
    # Test insufficient resources
    result, details = system.craft("player1", "iron_sword", {"iron_ore": 1})
    assert result == CraftResult.INSUFFICIENT_RESOURCES
    print("✓ Insufficient resources handled")
    
    print("\n✅ Crafting System Self-Test PASSED")
