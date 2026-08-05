#!/usr/bin/env python3
"""
Простая система крафта для создания базовых предметов
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CraftResult(Enum):
    """Результат крафта"""
    SUCCESS = "success"
    FAILURE = "failure"
    CRITICAL_SUCCESS = "critical_success"  # Бонусный предмет
    INSUFFICIENT_MATERIALS = "insufficient_materials"


@dataclass
class Recipe:
    """Рецепт крафта"""
    recipe_id: str
    name: str
    required_materials: dict[str, int]  # {item_id: quantity}
    result_item: str
    result_quantity: int = 1
    craft_time: float = 2.0  # секунды
    required_skill: float = 0.0  # требуемый уровень навыка крафта
    experience_reward: float = 10.0


@dataclass
class CraftResultData:
    """Результат попытки крафта"""
    result: CraftResult
    items_created: list[str] = field(default_factory=list)
    message: str = ""
    experience_gained: float = 0.0


class CraftingSystem:
    """
    Система крафта с простыми рецептами
    """
    
    def __init__(self):
        # База рецептов
        self.recipes: dict[str, Recipe] = {}
        
        # Навыки игрока
        self.crafting_skill: float = 0.0  # 0.0 - 1.0
        self.crafting_experience: float = 0.0
        
        # История крафта
        self.crafting_history: list[CraftResultData] = []
        
        # Инициализация базовых рецептов
        self._initialize_basic_recipes()
    
    def _initialize_basic_recipes(self):
        """Инициализировать базовые рецепты"""
        basic_recipes = [
            Recipe(
                recipe_id="health_potion",
                name="Зелье здоровья",
                required_materials={"herb": 2, "water": 1},
                result_item="health_potion",
                result_quantity=1,
                craft_time=2.0,
                experience_reward=5.0
            ),
            Recipe(
                recipe_id="mana_potion",
                name="Зелье маны",
                required_materials={"crystal": 2, "water": 1},
                result_item="mana_potion",
                result_quantity=1,
                craft_time=2.5,
                experience_reward=7.0
            ),
            Recipe(
                recipe_id="simple_trap",
                name="Простая ловушка",
                required_materials={"wood": 3, "rope": 1},
                result_item="trap_simple",
                result_quantity=1,
                craft_time=3.0,
                experience_reward=10.0
            ),
            Recipe(
                recipe_id="torch",
                name="Факел",
                required_materials={"wood": 1, "oil": 1},
                result_item="torch",
                result_quantity=1,
                craft_time=1.5,
                experience_reward=3.0
            ),
            Recipe(
                recipe_id="basic_armor",
                name="Простая броня",
                required_materials={"leather": 5, "thread": 2},
                result_item="armor_basic",
                result_quantity=1,
                craft_time=5.0,
                required_skill=0.3,
                experience_reward=20.0
            ),
            Recipe(
                recipe_id="basic_weapon",
                name="Простое оружие",
                required_materials={"wood": 3, "stone": 2},
                result_item="weapon_basic",
                result_quantity=1,
                craft_time=4.0,
                required_skill=0.2,
                experience_reward=15.0
            )
        ]
        
        for recipe in basic_recipes:
            self.recipes[recipe.recipe_id] = recipe
    
    def add_recipe(self, recipe: Recipe):
        """Добавить новый рецепт"""
        self.recipes[recipe.recipe_id] = recipe
    
    def craft_item(self, recipe_id: str, 
                   inventory: dict[str, int],
                   player_skill: float = 0.0) -> CraftResultData:
        """
        Создать предмет по рецепту
        
        Args:
            recipe_id: ID рецепта
            inventory: Инвентарь игрока {item_id: quantity}
            player_skill: Навык крафта игрока
        
        Returns:
            CraftResultData с результатом крафта
        """
        if recipe_id not in self.recipes:
            return CraftResultData(
                result=CraftResult.FAILURE,
                message=f"Рецепт '{recipe_id}' не найден"
            )
        
        recipe = self.recipes[recipe_id]
        
        # Проверка требования к навыку
        effective_skill = max(player_skill, self.crafting_skill)
        if effective_skill < recipe.required_skill:
            return CraftResultData(
                result=CraftResult.FAILURE,
                message=f"Недостаточный навык крафта (требуется {recipe.required_skill:.2f})"
            )
        
        # Проверка материалов
        missing_materials = []
        for material_id, required_qty in recipe.required_materials.items():
            available_qty = inventory.get(material_id, 0)
            if available_qty < required_qty:
                missing_materials.append(f"{material_id}: {required_qty - available_qty}")
        
        if missing_materials:
            return CraftResultData(
                result=CraftResult.INSUFFICIENT_MATERIALS,
                message=f"Недостаточно материалов: {', '.join(missing_materials)}"
            )
        
        # Расчет шанса успеха и критического успеха
        skill_bonus = (effective_skill - recipe.required_skill) * 0.5 if effective_skill > recipe.required_skill else 0.0
        base_success_chance = 0.8 + skill_bonus
        critical_chance = 0.1 + skill_bonus * 0.3
        
        import random
        roll = random.random()
        
        if roll < base_success_chance:
            # Успех!
            items_created = [recipe.result_item] * recipe.result_quantity
            
            # Проверка на критический успех
            if random.random() < critical_chance:
                items_created.append(recipe.result_item)  # Бонусный предмет
                result = CraftResult.CRITICAL_SUCCESS
                message = f"Критический успех! Создано {len(items_created)} x {recipe.name}"
            else:
                result = CraftResult.SUCCESS
                message = f"Успешно создано: {recipe.name}"
            
            result_data = CraftResultData(
                result=result,
                items_created=items_created,
                message=message,
                experience_gained=recipe.experience_reward * (1.2 if result == CraftResult.CRITICAL_SUCCESS else 1.0)
            )
            
            # Обновление опыта крафта
            self.crafting_experience += result_data.experience_gained
            self._update_crafting_skill()
            
            # Добавление в историю
            self.crafting_history.append(result_data)
            
            return result_data
        else:
            # Провал
            result_data = CraftResultData(
                result=CraftResult.FAILURE,
                message="Крафт не удался! Материалы потеряны."
            )
            self.crafting_history.append(result_data)
            return result_data
    
    def _update_crafting_skill(self):
        """Обновить навык крафта на основе опыта"""
        # Простая формула: skill = min(1.0, experience / 1000)
        self.crafting_skill = min(1.0, self.crafting_experience / 1000.0)
    
    def get_recipe_info(self, recipe_id: str) -> Recipe | None:
        """Получить информацию о рецепте"""
        return self.recipes.get(recipe_id)
    
    def get_all_recipes(self) -> list[Recipe]:
        """Получить все рецепты"""
        return list(self.recipes.values())
    
    def can_craft(self, recipe_id: str, inventory: dict[str, int], 
                  player_skill: float = 0.0) -> bool:
        """Проверить можно ли создать предмет"""
        result = self.craft_item(recipe_id, inventory, player_skill)
        return result.result in [CraftResult.SUCCESS, CraftResult.CRITICAL_SUCCESS]
    
    def get_crafting_statistics(self) -> dict[str, Any]:
        """Получить статистику крафта"""
        stats = {
            'total_attempts': len(self.crafting_history),
            'success_count': 0,
            'failure_count': 0,
            'critical_success_count': 0,
            'total_experience': self.crafting_experience,
            'current_skill': self.crafting_skill
        }
        
        for record in self.crafting_history:
            if record.result == CraftResult.SUCCESS:
                stats['success_count'] += 1
            elif record.result == CraftResult.CRITICAL_SUCCESS:
                stats['success_count'] += 1
                stats['critical_success_count'] += 1
            elif record.result == CraftResult.FAILURE:
                stats['failure_count'] += 1
        
        return stats
    
    def clear_history(self):
        """Очистить историю крафта"""
        self.crafting_history.clear()
