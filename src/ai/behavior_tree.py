"""
AI Behavior Tree System for Autonomous Agents
Implements GOAP-like decision making with Behavior Trees
"""
from enum import Enum
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
import logging
import random
from collections import deque

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Status of a behavior tree node"""
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


@dataclass
class Blackboard:
    """Shared memory for behavior tree nodes"""
    data: Dict[str, Any] = field(default_factory=dict)
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
    
    def has(self, key: str) -> bool:
        return key in self.data
    
    def clear(self) -> None:
        self.data.clear()


class BTNode:
    """Base class for Behavior Tree nodes"""
    
    def __init__(self, name: str = ""):
        self.name = name
        self.children: List['BTNode'] = []
    
    def execute(self, blackboard: Blackboard) -> NodeStatus:
        raise NotImplementedError
    
    def add_child(self, child: 'BTNode') -> 'BTNode':
        self.children.append(child)
        return self


class Action(BTNode):
    """Leaf node that performs an action"""
    
    def __init__(self, name: str, action_func: Callable[[Blackboard], bool]):
        super().__init__(name)
        self.action_func = action_func
    
    def execute(self, blackboard: Blackboard) -> NodeStatus:
        try:
            if self.action_func(blackboard):
                return NodeStatus.SUCCESS
            else:
                return NodeStatus.FAILURE
        except Exception as e:
            logger.error(f"Action {self.name} failed: {e}")
            return NodeStatus.FAILURE


class Condition(BTNode):
    """Leaf node that checks a condition"""
    
    def __init__(self, name: str, condition_func: Callable[[Blackboard], bool]):
        super().__init__(name)
        self.condition_func = condition_func
    
    def execute(self, blackboard: Blackboard) -> NodeStatus:
        try:
            if self.condition_func(blackboard):
                return NodeStatus.SUCCESS
            else:
                return NodeStatus.FAILURE
        except Exception as e:
            logger.error(f"Condition {self.name} failed: {e}")
            return NodeStatus.FAILURE


class Selector(BTNode):
    """Runs children until one succeeds"""
    
    def execute(self, blackboard: Blackboard) -> NodeStatus:
        for child in self.children:
            status = child.execute(blackboard)
            if status != NodeStatus.FAILURE:
                return status
        return NodeStatus.FAILURE


class Sequence(BTNode):
    """Runs children until one fails"""
    
    def execute(self, blackboard: Blackboard) -> NodeStatus:
        for child in self.children:
            status = child.execute(blackboard)
            if status != NodeStatus.SUCCESS:
                return status
        return NodeStatus.SUCCESS


class Repeater(BTNode):
    """Repeats child execution N times or forever"""
    
    def __init__(self, name: str = "Repeater", max_iterations: int = -1):
        super().__init__(name)
        self.max_iterations = max_iterations
    
    def execute(self, blackboard: Blackboard) -> NodeStatus:
        iterations = 0
        while self.max_iterations == -1 or iterations < self.max_iterations:
            if len(self.children) == 0:
                return NodeStatus.FAILURE
            
            status = self.children[0].execute(blackboard)
            if status == NodeStatus.FAILURE:
                return NodeStatus.FAILURE
            
            iterations += 1
        
        return NodeStatus.SUCCESS


@dataclass
class AgentState:
    """State of an AI agent"""
    health: float = 100.0
    mana: float = 50.0
    stamina: float = 80.0
    position: tuple = (0, 0)
    target: Optional[tuple] = None
    enemies_nearby: bool = False
    loot_available: bool = False
    is_hungry: bool = False
    faction_relations: Dict[str, float] = field(default_factory=dict)


class AIAgent:
    """Autonomous AI Agent with Behavior Tree"""
    
    def __init__(self, agent_id: str, agent_type: str = "default"):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.state = AgentState()
        self.blackboard = Blackboard()
        self.root: Optional[BTNode] = None
        self.current_action: str = "idle"
        self.action_history: deque = deque(maxlen=100)
        
        self._setup_behavior_tree()
    
    def _setup_behavior_tree(self) -> None:
        """Setup the behavior tree for this agent"""
        # Root selector: chooses between different behavior modes
        self.root = Selector("Root")
        
        # 1. Emergency behavior (low health)
        emergency_seq = Sequence("Emergency")
        emergency_seq.add_child(
            Condition("IsLowHealth", lambda bb: bb.get("health", 100) < 30)
        )
        emergency_seq.add_child(
            Action("Flee", self._action_flee)
        )
        self.root.add_child(emergency_seq)
        
        # 2. Combat behavior
        combat_seq = Sequence("Combat")
        combat_seq.add_child(
            Condition("HasEnemy", lambda bb: bb.get("enemies_nearby", False))
        )
        combat_selector = Selector("CombatActions")
        
        # Attack if strong enough
        attack_seq = Sequence("Attack")
        attack_seq.add_child(
            Condition("CanWin", lambda bb: bb.get("health", 100) > bb.get("enemy_health", 100) * 0.5)
        )
        attack_seq.add_child(
            Action("Attack", self._action_attack)
        )
        combat_selector.add_child(attack_seq)
        
        # Defensive stance
        combat_selector.add_child(
            Action("Defend", self._action_defend)
        )
        
        combat_seq.add_child(combat_selector)
        self.root.add_child(combat_seq)
        
        # 3. Resource gathering
        gather_seq = Sequence("Gather")
        gather_seq.add_child(
            Condition("LootAvailable", lambda bb: bb.get("loot_available", False))
        )
        gather_seq.add_child(
            Action("CollectLoot", self._action_collect_loot)
        )
        self.root.add_child(gather_seq)
        
        # 4. Exploration
        explore_seq = Sequence("Explore")
        explore_seq.add_child(
            Action("FindTarget", self._action_find_target)
        )
        explore_seq.add_child(
            Action("MoveToTarget", self._action_move)
        )
        self.root.add_child(explore_seq)
        
        # 5. Idle
        self.root.add_child(
            Action("Idle", self._action_idle)
        )
    
    # Action implementations
    def _action_flee(self, blackboard: Blackboard) -> bool:
        logger.info(f"[{self.agent_id}] Fleeing from danger!")
        self.current_action = "fleeing"
        self.state.position = (self.state.position[0] - 10, self.state.position[1] - 10)
        blackboard.set("enemies_nearby", False)
        self._log_action("flee")
        return True
    
    def _action_attack(self, blackboard: Blackboard) -> bool:
        logger.info(f"[{self.agent_id}] Attacking enemy!")
        self.current_action = "attacking"
        # Simulate attack
        damage = random.randint(10, 25)
        blackboard.set("last_damage_dealt", damage)
        self._log_action(f"attack_{damage}")
        return True
    
    def _action_defend(self, blackboard: Blackboard) -> bool:
        logger.info(f"[{self.agent_id}] Taking defensive stance!")
        self.current_action = "defending"
        self.state.stamina = min(100, self.state.stamina + 10)
        self._log_action("defend")
        return True
    
    def _action_collect_loot(self, blackboard: Blackboard) -> bool:
        logger.info(f"[{self.agent_id}] Collecting loot!")
        self.current_action = "collecting"
        blackboard.set("loot_available", False)
        blackboard.set("loot_collected", blackboard.get("loot_collected", 0) + 1)
        self._log_action("collect_loot")
        return True
    
    def _action_find_target(self, blackboard: Blackboard) -> bool:
        logger.info(f"[{self.agent_id}] Finding new target...")
        self.current_action = "searching"
        x = random.randint(-100, 100)
        y = random.randint(-100, 100)
        blackboard.set("target", (x, y))
        self.state.target = (x, y)
        self._log_action(f"find_target_{x}_{y}")
        return True
    
    def _action_move(self, blackboard: Blackboard) -> bool:
        target = blackboard.get("target")
        if not target:
            return False
        
        logger.info(f"[{self.agent_id}] Moving to {target}")
        self.current_action = "moving"
        # Simulate movement
        self.state.position = target
        blackboard.set("target", None)
        self._log_action(f"move_to_{target[0]}_{target[1]}")
        return True
    
    def _action_idle(self, blackboard: Blackboard) -> bool:
        logger.debug(f"[{self.agent_id}] Idling...")
        self.current_action = "idle"
        self.state.stamina = min(100, self.state.stamina + 5)
        return True
    
    def _log_action(self, action: str) -> None:
        self.action_history.append({
            "timestamp": len(self.action_history),
            "action": action,
            "state": {
                "health": self.state.health,
                "position": self.state.position
            }
        })
    
    def tick(self) -> str:
        """Execute one tick of the behavior tree"""
        # Sync state to blackboard
        self.blackboard.set("health", self.state.health)
        self.blackboard.set("mana", self.state.mana)
        self.blackboard.set("stamina", self.state.stamina)
        self.blackboard.set("enemies_nearby", self.state.enemies_nearby)
        self.blackboard.set("loot_available", self.state.loot_available)
        
        if self.root:
            status = self.root.execute(self.blackboard)
            return f"{self.current_action} ({status.value})"
        
        return "no_tree"
    
    def get_state_summary(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "type": self.agent_type,
            "current_action": self.current_action,
            "health": self.state.health,
            "position": self.state.position,
            "actions_taken": len(self.action_history)
        }


def create_agent(agent_type: str = "warrior") -> AIAgent:
    """Factory function to create different agent types"""
    agent = AIAgent(f"agent_{random.randint(1000, 9999)}", agent_type)
    
    if agent_type == "warrior":
        agent.state.health = 150.0
        agent.state.stamina = 100.0
    elif agent_type == "mage":
        agent.state.health = 80.0
        agent.state.mana = 150.0
    elif agent_type == "rogue":
        agent.state.health = 100.0
        agent.state.stamina = 120.0
    
    return agent


if __name__ == "__main__":
    # Test the AI system
    logging.basicConfig(level=logging.INFO)
    
    print("=== AI Behavior Tree Test ===")
    
    # Create agents
    warrior = create_agent("warrior")
    mage = create_agent("mage")
    rogue = create_agent("rogue")
    
    agents = [warrior, mage, rogue]
    
    # Simulate ticks
    for tick in range(10):
        print(f"\n--- Tick {tick + 1} ---")
        for agent in agents:
            # Random events
            if random.random() < 0.3:
                agent.state.enemies_nearby = True
            if random.random() < 0.2:
                agent.state.loot_available = True
            if random.random() < 0.1:
                agent.state.health -= 10
            
            result = agent.tick()
            print(f"{agent.agent_type}: {result}")
        
        print("\nAgent States:")
        for agent in agents:
            summary = agent.get_state_summary()
            print(f"  {summary['type']}: {summary['current_action']} @ {summary['position']}")
    
    print("\n=== Test Complete ===")
