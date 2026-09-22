"""
Skill Tree System - Дерево навыков с зависимостями
Принципы: SOLID, DRY, Python Best Practices
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SkillType(Enum):
    PASSIVE = "passive"      # Пассивный бонус
    ACTIVE = "active"        # Активный навык (требует использования)
    TRIGGER = "trigger"      # Срабатывает при условии


class SkillTier(Enum):
    BASIC = 1
    ADVANCED = 2
    MASTER = 3
    LEGENDARY = 4


@dataclass
class SkillNode:
    id: str
    name: str
    description: str
    skill_type: SkillType
    tier: SkillTier
    prerequisites: List[str] = field(default_factory=list)
    max_level: int = 5
    bonuses: Dict[str, float] = field(default_factory=dict)  # e.g., {"damage": 0.1, "speed": 0.05}
    unlock_cost: int = 1  # Очки навыков
    
    def __post_init__(self):
        if not self.prerequisites:
            self.prerequisites = []


@dataclass
class PlayerSkillProgress:
    node_id: str
    level: int = 0
    unlocked: bool = False
    
    def can_upgrade(self) -> bool:
        return self.unlocked and self.level < self._get_max_level()
    
    def _get_max_level(self) -> int:
        # Будет установлено из SkillNode
        return 5


class SkillTree:
    """
    Система дерева навыков с зависимостями
    SSOT для всех навыков игрока
    """
    
    def __init__(self, tree_name: str = "default"):
        self.tree_name = tree_name
        self._nodes: Dict[str, SkillNode] = {}
        self._player_progress: Dict[str, Dict[str, PlayerSkillProgress]] = {}  # player_id -> {node_id: progress}
        
    def add_node(self, node: SkillNode):
        """Добавить узел навыка (SSOT)"""
        if node.id in self._nodes:
            logger.warning(f"Skill node {node.id} already exists, overwriting")
        self._nodes[node.id] = node
        logger.debug(f"Added skill node: {node.name}")
    
    def get_node(self, node_id: str) -> Optional[SkillNode]:
        return self._nodes.get(node_id)
    
    def get_all_nodes(self) -> Dict[str, SkillNode]:
        return self._nodes.copy()
    
    def _get_player_progress(self, player_id: str, node_id: str) -> PlayerSkillProgress:
        """Получить или создать прогресс игрока для узла"""
        if player_id not in self._player_progress:
            self._player_progress[player_id] = {}
        
        if node_id not in self._player_progress[player_id]:
            node = self.get_node(node_id)
            if node:
                self._player_progress[player_id][node_id] = PlayerSkillProgress(
                    node_id=node_id,
                    level=0,
                    unlocked=False
                )
        
        return self._player_progress[player_id].get(node_id)
    
    def can_unlock(self, player_id: str, node_id: str) -> tuple[bool, str]:
        """Проверить возможность разблокировки навыка"""
        node = self.get_node(node_id)
        if not node:
            return False, f"Skill node {node_id} not found"
        
        progress = self._get_player_progress(player_id, node_id)
        if progress.unlocked:
            return False, "Skill already unlocked"
        
        # Проверка зависимостей
        for prereq_id in node.prerequisites:
            prereq_progress = self._get_player_progress(player_id, prereq_id)
            if not prereq_progress or not prereq_progress.unlocked:
                prereq_node = self.get_node(prereq_id)
                prereq_name = prereq_node.name if prereq_node else prereq_id
                return False, f"Prerequisite {prereq_name} not unlocked"
            
            # Проверка уровня зависимости (требуется мастер для продвинутых)
            if node.tier.value > prereq_node.tier.value:
                if prereq_progress.level < prereq_node.max_level:
                    return False, f"Prerequisite {prereq_node.name} must be max level"
        
        return True, "Can unlock"
    
    def unlock_skill(self, player_id: str, node_id: str, skill_points: int) -> tuple[bool, str]:
        """Разблокировать навык"""
        can_do, reason = self.can_unlock(player_id, node_id)
        if not can_do:
            return False, reason
        
        node = self.get_node(node_id)
        if skill_points < node.unlock_cost:
            return False, f"Not enough skill points: need {node.unlock_cost}, have {skill_points}"
        
        progress = self._get_player_progress(player_id, node_id)
        progress.unlocked = True
        progress.level = 1  # Начальный уровень
        
        logger.info(f"Player {player_id} unlocked skill: {node.name}")
        return True, f"Unlocked {node.name}"
    
    def upgrade_skill(self, player_id: str, node_id: str) -> tuple[bool, str]:
        """Улучшить навык на 1 уровень"""
        node = self.get_node(node_id)
        if not node:
            return False, f"Skill node {node_id} not found"
        
        progress = self._get_player_progress(player_id, node_id)
        if not progress or not progress.unlocked:
            return False, "Skill not unlocked"
        
        if progress.level >= node.max_level:
            return False, "Skill already at max level"
        
        progress.level += 1
        logger.info(f"Player {player_id} upgraded {node.name} to level {progress.level}")
        return True, f"Upgraded to level {progress.level}"
    
    def get_active_bonuses(self, player_id: str) -> Dict[str, float]:
        """Получить все активные бонусы игрока"""
        bonuses: Dict[str, float] = {}
        
        player_skills = self._player_progress.get(player_id, {})
        for node_id, progress in player_skills.items():
            if progress.unlocked and progress.level > 0:
                node = self.get_node(node_id)
                if node:
                    # Пропорционально уровню
                    level_ratio = progress.level / node.max_level
                    for stat, value in node.bonuses.items():
                        if stat not in bonuses:
                            bonuses[stat] = 0
                        bonuses[stat] += value * level_ratio
        
        return bonuses
    
    def get_skill_tree_state(self, player_id: str) -> Dict:
        """Получить полное состояние дерева навыков"""
        state = {
            "tree_name": self.tree_name,
            "skills": {}
        }
        
        player_skills = self._player_progress.get(player_id, {})
        for node_id, node in self._nodes.items():
            progress = player_skills.get(node_id)
            state["skills"][node_id] = {
                "name": node.name,
                "description": node.description,
                "type": node.skill_type.value,
                "tier": node.tier.value,
                "unlocked": progress.unlocked if progress else False,
                "level": progress.level if progress else 0,
                "max_level": node.max_level,
                "prerequisites": node.prerequisites,
                "bonuses": node.bonuses
            }
        
        return state


# Пример дерева навыков
def create_combat_skill_tree() -> SkillTree:
    """Создать боевое дерево навыков"""
    tree = SkillTree("combat")
    
    # Базовые навыки
    tree.add_node(SkillNode(
        id="basic_attack",
        name="Basic Attack Training",
        description="Increases basic attack damage",
        skill_type=SkillType.PASSIVE,
        tier=SkillTier.BASIC,
        max_level=5,
        bonuses={"damage": 0.1},
        unlock_cost=1
    ))
    
    tree.add_node(SkillNode(
        id="power_strike",
        name="Power Strike",
        description="Unlocks powerful charged attack",
        skill_type=SkillType.ACTIVE,
        tier=SkillTier.BASIC,
        prerequisites=["basic_attack"],
        max_level=3,
        bonuses={"crit_chance": 0.05},
        unlock_cost=2
    ))
    
    # Продвинутые
    tree.add_node(SkillNode(
        id="combo_master",
        name="Combo Master",
        description="Chain attacks together",
        skill_type=SkillType.PASSIVE,
        tier=SkillTier.ADVANCED,
        prerequisites=["power_strike"],
        max_level=5,
        bonuses={"attack_speed": 0.08, "damage": 0.05},
        unlock_cost=3
    ))
    
    tree.add_node(SkillNode(
        id="counter_attack",
        name="Counter Attack",
        description="Automatic counter when dodging",
        skill_type=SkillType.TRIGGER,
        tier=SkillTier.ADVANCED,
        prerequisites=["basic_attack"],
        max_level=3,
        bonuses={"counter_damage": 0.15},
        unlock_cost=2
    ))
    
    # Мастер
    tree.add_node(SkillNode(
        id="blade_dance",
        name="Blade Dance",
        description="Ultimate combat technique",
        skill_type=SkillType.ACTIVE,
        tier=SkillTier.MASTER,
        prerequisites=["combo_master", "counter_attack"],
        max_level=1,
        bonuses={"damage": 0.5, "attack_speed": 0.2},
        unlock_cost=5
    ))
    
    # Легендарный
    tree.add_node(SkillNode(
        id="weapon_mastery",
        name="Weapon Mastery",
        description="Legendary weapon techniques",
        skill_type=SkillType.PASSIVE,
        tier=SkillTier.LEGENDARY,
        prerequisites=["blade_dance"],
        max_level=1,
        bonuses={"damage": 1.0, "crit_chance": 0.25, "crit_damage": 0.5},
        unlock_cost=10
    ))
    
    logger.info("Combat skill tree created")
    return tree


if __name__ == "__main__":
    # Self-test
    print("Testing Skill Tree System...")
    tree = create_combat_skill_tree()
    
    # Test unlocking
    can_unlock, reason = tree.can_unlock("player1", "basic_attack")
    assert can_unlock, f"Should be able to unlock basic: {reason}"
    
    success, msg = tree.unlock_skill("player1", "basic_attack", 1)
    assert success, f"Failed to unlock: {msg}"
    print(f"✓ Unlocked: {msg}")
    
    # Test upgrade
    success, msg = tree.upgrade_skill("player1", "basic_attack")
    assert success
    print(f"✓ Upgraded: {msg}")
    
    # Test prerequisites
    can_unlock, reason = tree.can_unlock("player1", "blade_dance")
    assert not can_unlock
    print(f"✓ Prerequisites enforced: {reason}")
    
    # Test bonuses
    bonuses = tree.get_active_bonuses("player1")
    assert "damage" in bonuses
    print(f"✓ Active bonuses: {bonuses}")
    
    # Test state
    state = tree.get_skill_tree_state("player1")
    assert "skills" in state
    print(f"✓ Skill tree state retrieved")
    
    print("\n✅ Skill Tree System Self-Test PASSED")
