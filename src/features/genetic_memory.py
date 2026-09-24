"""
Genetic Memory System - Ancestral Echoes
Allows entities to access skills/memories of their ancestors.
"""
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

from src.core.architecture import BaseComponent, ComponentType, Priority


@dataclass(slots=True)
class MemoryFragment:
    ancestor_id: str
    skill_name: str
    potency: float  # 0.0 to 1.0
    timestamp: float
    context_tags: list[str] = field(default_factory=list)

class GeneticMemorySystem(BaseComponent):
    """
    Stores and retrieves ancestral memories.
    Implements 'Ancestral Echo' mechanic where past successes influence current behavior.
    """
    def __init__(self, max_memories: int = 50):
        super().__init__(ComponentType.SYSTEM, Priority.HIGH)
        self.max_memories = max_memories
        self.memory_pool: list[MemoryFragment] = []
        self.active_echoes: dict[str, MemoryFragment] = {}
        
    def on_start(self):
        logging.info("Genetic Memory System initialized. Listening for evolutionary milestones.")
        
    def record_milestone(self, entity_id: str, skill: str, success_rate: float, context: list[str]):
        """Record a significant achievement to be passed down."""
        if success_rate < 0.7:  # Only remember significant successes
            return
            
        fragment = MemoryFragment(
            ancestor_id=entity_id,
            skill_name=skill,
            potency=min(success_rate, 1.0),
            timestamp=time.perf_counter(),
            context_tags=context
        )
        
        self.memory_pool.append(fragment)
        if len(self.memory_pool) > self.max_memories:
            # Oldest memories fade
            self.memory_pool.pop(0)
            
        self.logger.debug(f"Memory recorded: {skill} from {entity_id}")

    def trigger_echo(self, current_entity: Any, context: list[str]) -> dict[str, Any] | None:
        """
        Attempt to trigger an ancestral echo based on current context.
        Returns bonus stats if successful.
        """
        relevant_memories = [
            m for m in self.memory_pool 
            if any(tag in m.context_tags for tag in context)
        ]
        
        if not relevant_memories:
            return None
            
        # Pick the strongest memory
        best_memory = max(relevant_memories, key=lambda m: m.potency)
        
        # Chance to trigger depends on potency
        if random.random() > best_memory.potency:
            return None
            
        self.active_echoes[current_entity.id if hasattr(current_entity, 'id') else 'unknown'] = best_memory
        
        bonus = {
            "skill": best_memory.skill_name,
            "bonus_value": best_memory.potency * 0.5,  # Up to 50% bonus
            "duration": 5.0,  # seconds
            "message": f"Echo of {best_memory.ancestor_id}: {best_memory.skill_name} activated!"
        }
        
        self.logger.info(f"ANCESTRAL ECHO: {bonus['message']}")
        return bonus

    def on_update(self, dt: float):
        # Fade out active echoes
        to_remove = []
        current_time = time.perf_counter()
        for eid, memory in self.active_echoes.items():
            if current_time - memory.timestamp > 10.0: # Simple expiration for demo
                to_remove.append(eid)
        
        for eid in to_remove:
            del self.active_echoes[eid]
            
    def _on_update(self, delta_time: float) -> None:
        """Implementation of abstract method."""
        self.on_update(delta_time)
