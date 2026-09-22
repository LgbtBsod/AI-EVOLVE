"""
Achievement System - Система достижений с наградами
Принципы: SOLID, DRY, Python Best Practices
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AchievementTier(Enum):
    BRONZE = 1
    SILVER = 2
    GOLD = 3
    PLATINUM = 4
    DIAMOND = 5


class AchievementCategory(Enum):
    COMBAT = "combat"
    EXPLORATION = "exploration"
    CRAFTING = "crafting"
    QUEST = "quest"
    SOCIAL = "social"
    SPECIAL = "special"


@dataclass
class AchievementReward:
    item_id: Optional[str] = None
    item_count: int = 1
    experience: int = 0
    skill_points: int = 0
    currency: int = 0
    title: Optional[str] = None
    
    def __bool__(self):
        return any([self.item_id, self.experience, self.skill_points, self.currency, self.title])


@dataclass
class Achievement:
    id: str
    name: str
    description: str
    category: AchievementCategory
    tier: AchievementTier
    condition_func_name: str  # Имя функции условия
    reward: AchievementReward
    hidden: bool = False
    repeatable: bool = False
    
    def __post_init__(self):
        if not self.condition_func_name:
            raise ValueError("Condition function name is required")


@dataclass  
class PlayerAchievementProgress:
    achievement_id: str
    progress: float = 0.0
    completed: bool = False
    completed_at: Optional[datetime] = None
    times_completed: int = 0


class AchievementSystem:
    """
    Система достижений с отслеживанием прогресса и наградами
    SSOT для всех достижений
    """
    
    def __init__(self):
        self._achievements: Dict[str, Achievement] = {}
        self._player_progress: Dict[str, Dict[str, PlayerAchievementProgress]] = {}
        self._condition_functions: Dict[str, Callable[[Dict, Dict], float]] = {}
        self._completed_callbacks: List[Callable[[str, str, AchievementReward], None]] = []
        
    def register_achievement(self, achievement: Achievement):
        """Зарегистрировать достижение (SSOT)"""
        if achievement.id in self._achievements:
            logger.warning(f"Achievement {achievement.id} already exists, overwriting")
        self._achievements[achievement.id] = achievement
        logger.debug(f"Registered achievement: {achievement.name}")
    
    def register_condition(self, func_name: str, func: Callable[[Dict, Dict], float]):
        """
        Зарегистрировать функцию условия
        Функция принимает (game_state, player_state) и возвращает прогресс (0.0-1.0 или больше)
        """
        self._condition_functions[func_name] = func
        logger.debug(f"Registered condition function: {func_name}")
    
    def register_completion_callback(self, callback: Callable[[str, str, AchievementReward], None]):
        """Зарегистрировать callback при получении достижения"""
        self._completed_callbacks.append(callback)
    
    def get_achievement(self, achievement_id: str) -> Optional[Achievement]:
        return self._achievements.get(achievement_id)
    
    def _get_player_progress(self, player_id: str, achievement_id: str) -> PlayerAchievementProgress:
        """Получить или создать прогресс игрока"""
        if player_id not in self._player_progress:
            self._player_progress[player_id] = {}
        
        if achievement_id not in self._player_progress[player_id]:
            self._player_progress[player_id][achievement_id] = PlayerAchievementProgress(
                achievement_id=achievement_id
            )
        
        return self._player_progress[player_id][achievement_id]
    
    def check_achievements(self, player_id: str, game_state: Dict, player_state: Dict) -> List[str]:
        """
        Проверить все достижения игрока
        Возвращает список newly completed achievement IDs
        """
        newly_completed = []
        
        for achievement_id, achievement in self._achievements.items():
            progress_obj = self._get_player_progress(player_id, achievement_id)
            
            # Пропуск если уже завершено и не повторяемое
            if progress_obj.completed and not achievement.repeatable:
                continue
            
            # Найти функцию условия
            condition_func = self._condition_functions.get(achievement.condition_func_name)
            if not condition_func:
                logger.warning(f"Condition function {achievement.condition_func_name} not found")
                continue
            
            # Вычислить прогресс
            try:
                progress_value = condition_func(game_state, player_state)
            except Exception as e:
                logger.error(f"Error evaluating condition for {achievement_id}: {e}")
                continue
            
            # Обновить прогресс
            progress_obj.progress = max(progress_obj.progress, progress_value)
            
            # Проверка завершения
            if progress_obj.progress >= 1.0 and not progress_obj.completed:
                progress_obj.completed = True
                progress_obj.completed_at = datetime.now()
                progress_obj.times_completed += 1
                
                # Выдать награду
                self._grant_reward(player_id, achievement.reward)
                
                # Callbacks
                for callback in self._completed_callbacks:
                    try:
                        callback(player_id, achievement_id, achievement.reward)
                    except Exception as e:
                        logger.error(f"Error in completion callback: {e}")
                
                newly_completed.append(achievement_id)
                logger.info(f"Player {player_id} earned achievement: {achievement.name}")
        
        return newly_completed
    
    def _grant_reward(self, player_id: str, reward: AchievementReward):
        """Выдать награду (логика интеграции с другими системами)"""
        if not reward:
            return
        
        log_parts = []
        if reward.experience > 0:
            log_parts.append(f"{reward.experience} XP")
        if reward.skill_points > 0:
            log_parts.append(f"{reward.skill_points} SP")
        if reward.currency > 0:
            log_parts.append(f"{reward.currency} gold")
        if reward.item_id:
            log_parts.append(f"{reward.item_count}x {reward.item_id}")
        if reward.title:
            log_parts.append(f"Title: {reward.title}")
        
        if log_parts:
            logger.info(f"Granted reward to {player_id}: {', '.join(log_parts)}")
    
    def get_player_achievements(self, player_id: str, 
                                 category: Optional[AchievementCategory] = None,
                                 completed_only: bool = False) -> List[Dict]:
        """Получить достижения игрока с фильтрацией"""
        result = []
        player_prog = self._player_progress.get(player_id, {})
        
        for achievement_id, achievement in self._achievements.items():
            # Фильтр по категории
            if category and achievement.category != category:
                continue
            
            progress = player_prog.get(achievement_id)
            
            # Фильтр по завершенности
            if completed_only and (not progress or not progress.completed):
                continue
            
            # Скрытые достижения показываем только если открыты
            if achievement.hidden and (not progress or not progress.completed):
                continue
            
            result.append({
                "id": achievement_id,
                "name": achievement.name,
                "description": achievement.description,
                "category": achievement.category.value,
                "tier": achievement.tier.value,
                "progress": progress.progress if progress else 0.0,
                "completed": progress.completed if progress else False,
                "completed_at": progress.completed_at.isoformat() if progress and progress.completed_at else None,
                "times_completed": progress.times_completed if progress else 0,
                "hidden": achievement.hidden,
                "reward": {
                    "experience": reward.experience if (reward := achievement.reward) else 0,
                    "skill_points": reward.skill_points if reward else 0,
                    "currency": reward.currency if reward else 0,
                    "item": reward.item_id if reward else None,
                    "title": reward.title if reward else None
                }
            })
        
        return result
    
    def get_achievement_stats(self, player_id: str) -> Dict:
        """Получить статистику достижений игрока"""
        player_prog = self._player_progress.get(player_id, {})
        
        total = len(self._achievements)
        completed = sum(1 for p in player_prog.values() if p.completed)
        
        by_category = {}
        for cat in AchievementCategory:
            cat_achievements = [a for a in self._achievements.values() if a.category == cat]
            cat_completed = sum(1 for a in cat_achievements 
                               if player_prog.get(a.id) and player_prog[a.id].completed)
            by_category[cat.value] = {
                "total": len(cat_achievements),
                "completed": cat_completed,
                "percentage": (cat_completed / len(cat_achievements) * 100) if cat_achievements else 0
            }
        
        return {
            "total_achievements": total,
            "completed_achievements": completed,
            "completion_percentage": (completed / total * 100) if total > 0 else 0,
            "by_category": by_category
        }


# Примеры условий
def kill_count_condition(game_state: Dict, player_state: Dict) -> float:
    """Условие: количество убийств"""
    kills = player_state.get("stats", {}).get("kills", 0)
    target = 100  # Цель
    return min(kills / target, 1.0)


def exploration_condition(game_state: Dict, player_state: Dict) -> float:
    """Условие: процент исследованной карты"""
    explored = player_state.get("explored_tiles", 0)
    total = game_state.get("total_tiles", 1000)
    return min(explored / total, 1.0)


def crafting_master_condition(game_state: Dict, player_state: Dict) -> float:
    """Условие: количество скрафченных предметов"""
    crafted = player_state.get("stats", {}).get("items_crafted", 0)
    target = 50
    return min(crafted / target, 1.0)


# Стандартные достижения
DEFAULT_ACHIEVEMENTS = [
    Achievement(
        id="first_blood",
        name="First Blood",
        description="Defeat your first enemy",
        category=AchievementCategory.COMBAT,
        tier=AchievementTier.BRONZE,
        condition_func_name="kill_count_condition",
        reward=AchievementReward(experience=50, currency=10),
        hidden=False
    ),
    Achievement(
        id="slayer",
        name="Monster Slayer",
        description="Defeat 100 enemies",
        category=AchievementCategory.COMBAT,
        tier=AchievementTier.GOLD,
        condition_func_name="kill_count_condition",
        reward=AchievementReward(experience=500, skill_points=5, title="Slayer"),
        hidden=False
    ),
    Achievement(
        id="explorer",
        name="Explorer",
        description="Explore the entire map",
        category=AchievementCategory.EXPLORATION,
        tier=AchievementTier.SILVER,
        condition_func_name="exploration_condition",
        reward=AchievementReward(experience=200, currency=100),
        hidden=False
    ),
    Achievement(
        id="crafting_master",
        name="Crafting Master",
        description="Craft 50 items",
        category=AchievementCategory.CRAFTING,
        tier=AchievementTier.PLATINUM,
        condition_func_name="crafting_master_condition",
        reward=AchievementReward(experience=1000, skill_points=10, title="Master Crafter"),
        hidden=False
    ),
]


def initialize_achievement_system() -> AchievementSystem:
    """Инициализировать систему достижений"""
    system = AchievementSystem()
    
    # Регистрация достижений
    for achievement in DEFAULT_ACHIEVEMENTS:
        system.register_achievement(achievement)
    
    # Регистрация условий
    system.register_condition("kill_count_condition", kill_count_condition)
    system.register_condition("exploration_condition", exploration_condition)
    system.register_condition("crafting_master_condition", crafting_master_condition)
    
    logger.info("Achievement system initialized")
    return system


if __name__ == "__main__":
    # Self-test
    print("Testing Achievement System...")
    system = initialize_achievement_system()
    
    # Mock player state
    game_state = {"total_tiles": 1000}
    player_state = {
        "stats": {"kills": 5, "items_crafted": 10},
        "explored_tiles": 100
    }
    
    # Check achievements (should not complete yet)
    completed = system.check_achievements("player1", game_state, player_state)
    assert len(completed) == 0, f"Should not complete with low stats: {completed}"
    print("✓ No premature completions")
    
    # Max out stats
    player_state["stats"]["kills"] = 150
    player_state["explored_tiles"] = 1000
    player_state["stats"]["items_crafted"] = 100
    
    # Check again
    completed = system.check_achievements("player1", game_state, player_state)
    assert len(completed) > 0, "Should complete some achievements"
    print(f"✓ Achievements completed: {len(completed)}")
    
    # Get stats
    stats = system.get_achievement_stats("player1")
    assert stats["completed_achievements"] > 0
    print(f"✓ Stats: {stats['completed_achievements']}/{stats['total_achievements']}")
    
    # Get list
    achievements = system.get_player_achievements("player1", completed_only=True)
    assert len(achievements) > 0
    print(f"✓ Retrieved {len(achievements)} completed achievements")
    
    print("\n✅ Achievement System Self-Test PASSED")
