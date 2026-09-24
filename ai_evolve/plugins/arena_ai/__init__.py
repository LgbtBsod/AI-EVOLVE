"""
AI Arena Behaviors Plugin
Implements advanced group tactics for arena combat:
- Flanking maneuvers
- Focus fire coordination
- Defensive formations
- Dynamic role assignment (Tank, DPS, Support)
"""

from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import math

from ai_evolve.core.plugin_base import GamePlugin
from ai_evolve.core.event_system import EventSystem
from ai_evolve.plugins.entity_components import EntityComponentsPlugin, Component


class CombatRole(Enum):
    TANK = "tank"
    DPS = "dps"
    SUPPORT = "support"
    LEADER = "leader"


class FormationType(Enum):
    SPREAD = "spread"
    CLUSTER = "cluster"
    LINE = "line"
    CIRCLE = "circle"
    FLANK = "flank"


@dataclass
class GroupTacticsData:
    """Component for entities participating in group tactics"""
    role: CombatRole = CombatRole.DPS
    formation: FormationType = FormationType.SPREAD
    group_id: Optional[str] = None
    target_priority: str = "closest"  # closest, weakest, strongest, leader
    flanking_angle: float = 0.0  # radians from main threat direction
    coordination_radius: float = 5.0
    last_sync_time: float = 0.0
    active_tactic: Optional[str] = None
    
    # Coordination state
    is_flanking: bool = False
    is_focusing_fire: bool = False
    is_defending: bool = False
    protected_target: Optional[int] = None  # Entity ID being protected


class GroupTacticsComponent(Component):
    """Component enabling group tactical behavior"""
    
    def __init__(self, entity_id: int, **kwargs):
        super().__init__(entity_id)
        self.data = GroupTacticsData(**kwargs)
    
    def update(self, delta_time: float, game_state: dict):
        """Update tactical decisions"""
        pass  # Implemented in AI system


class ArenaAIPlugin(GamePlugin):
    """
    Plugin for advanced arena AI behaviors with group tactics
    """
    
    name = "arena_ai"
    version = "1.0.0"
    description = "Advanced AI behaviors for arena combat with group tactics"
    
    dependencies = ["entity_components", "combat"]
    
    def __init__(self):
        super().__init__()
        self.event_system: Optional[EventSystem] = None
        self.entity_plugin: Optional[EntityComponentsPlugin] = None
        
        # Group management
        self.groups: Dict[str, List[int]] = {}  # group_id -> [entity_ids]
        self.entity_groups: Dict[int, str] = {}  # entity_id -> group_id
        
        # Tactical state
        self.active_tactics: Dict[str, dict] = {}  # tactic_id -> state
        self.threat_map: Dict[int, List[int]] = {}  # target_id -> [threatening_entity_ids]
        
        # Configuration
        self.config = {
            "min_group_size": 2,
            "max_group_size": 8,
            "coordination_update_interval": 0.5,
            "flanking_success_chance": 0.3,
            "focus_fire_damage_bonus": 1.5,
            "formation_tolerance": 1.0,
        }
    
    def initialize(self, config: dict = None):
        """Initialize the plugin"""
        if config:
            self.config.update(config)
        
        self.event_system = EventSystem.get_instance()
        
        # Register event handlers
        self.event_system.connect("on_combat_start", self._on_combat_start)
        self.event_system.connect("on_entity_spawned", self._on_entity_spawned)
        self.event_system.connect("on_entity_death", self._on_entity_death)
        self.event_system.connect("on_update", self._on_update)
        
        self.logger.info("ArenaAIPlugin initialized")
    
    def shutdown(self):
        """Cleanup plugin resources"""
        if self.event_system:
            self.event_system.disconnect("on_combat_start", self._on_combat_start)
            self.event_system.disconnect("on_entity_spawned", self._on_entity_spawned)
            self.event_system.disconnect("on_entity_death", self._on_entity_death)
            self.event_system.disconnect("on_update", self._on_update)
        
        self.groups.clear()
        self.entity_groups.clear()
        self.active_tactics.clear()
        self.threat_map.clear()
        
        self.logger.info("ArenaAIPlugin shut down")
    
    def update(self, delta_time: float):
        """Update AI tactics"""
        self._update_threat_assessment()
        self._update_group_formations(delta_time)
        self._execute_active_tactics(delta_time)
    
    def create_group(self, entity_ids: List[int], group_id: Optional[str] = None) -> str:
        """Create a tactical group from entities"""
        if len(entity_ids) < self.config["min_group_size"]:
            self.logger.warning(f"Too few entities for group: {len(entity_ids)}")
            return ""
        
        if group_id is None:
            group_id = f"group_{len(self.groups) + 1}"
        
        # Assign roles based on entity stats
        self._assign_roles(entity_ids)
        
        # Register group
        self.groups[group_id] = entity_ids
        for entity_id in entity_ids:
            self.entity_groups[entity_id] = group_id
            
            # Add component if not exists
            if self.entity_plugin:
                entity = self.entity_plugin.get_entity(entity_id)
                if entity and not entity.has_component("group_tactics"):
                    entity.add_component("group_tactics", GroupTacticsComponent(
                        entity_id,
                        group_id=group_id
                    ))
        
        self.logger.info(f"Created tactical group {group_id} with {len(entity_ids)} entities")
        return group_id
    
    def dissolve_group(self, group_id: str):
        """Dissolve a tactical group"""
        if group_id in self.groups:
            entity_ids = self.groups.pop(group_id)
            for entity_id in entity_ids:
                self.entity_groups.pop(entity_id, None)
                
                # Remove component
                if self.entity_plugin:
                    entity = self.entity_plugin.get_entity(entity_id)
                    if entity and entity.has_component("group_tactics"):
                        entity.remove_component("group_tactics")
            
            # Cancel active tactics
            tactics_to_remove = [
                tid for tid, state in self.active_tactics.items()
                if state.get("group_id") == group_id
            ]
            for tid in tactics_to_remove:
                self._cancel_tactic(tid)
            
            self.logger.info(f"Dissolved tactical group {group_id}")
    
    def execute_tactic(self, tactic_name: str, group_id: str, 
                      target_ids: List[int], **kwargs) -> Optional[str]:
        """Execute a tactical maneuver"""
        if group_id not in self.groups:
            self.logger.error(f"Group {group_id} not found")
            return None
        
        tactic_id = f"{tactic_name}_{group_id}_{len(self.active_tactics)}"
        
        tactic_state = {
            "id": tactic_id,
            "name": tactic_name,
            "group_id": group_id,
            "targets": target_ids,
            "start_time": self.event_system.get_time() if self.event_system else 0,
            "status": "active",
            **kwargs
        }
        
        self.active_tactics[tactic_id] = tactic_state
        
        # Assign specific roles for this tactic
        entity_ids = self.groups[group_id]
        self._assign_tactic_roles(tactic_name, entity_ids, target_ids, tactic_state)
        
        self.logger.info(f"Executing tactic {tactic_name} for group {group_id}")
        return tactic_id
    
    def _assign_roles(self, entity_ids: List[int]):
        """Assign combat roles to entities based on their stats"""
        if not self.entity_plugin:
            return
        
        # Simple heuristic: tankiest = tank, highest dmg = dps, rest = support
        entity_stats = []
        for eid in entity_ids:
            entity = self.entity_plugin.get_entity(eid)
            if entity:
                stats = {
                    "entity_id": eid,
                    "health": getattr(entity, 'health', 100),
                    "max_health": getattr(entity, 'max_health', 100),
                    "damage": getattr(entity, 'damage', 10),
                }
                entity_stats.append(stats)
        
        if not entity_stats:
            return
        
        # Sort by tankiness (health)
        entity_stats.sort(key=lambda x: x["max_health"], reverse=True)
        
        # Assign roles
        if len(entity_stats) >= 1:
            entity_stats[0]["role"] = CombatRole.TANK
        if len(entity_stats) >= 2:
            entity_stats[-1]["role"] = CombatRole.LEADER if len(entity_stats) > 2 else CombatRole.DPS
        if len(entity_stats) >= 3:
            # Assign support to entity with medium stats
            mid_idx = len(entity_stats) // 2
            entity_stats[mid_idx]["role"] = CombatRole.SUPPORT
        
        # Apply roles
        for stats in entity_stats:
            entity = self.entity_plugin.get_entity(stats["entity_id"])
            if entity and entity.has_component("group_tactics"):
                comp = entity.get_component("group_tactics")
                comp.data.role = stats["role"]
    
    def _assign_tactic_roles(self, tactic_name: str, entity_ids: List[int], 
                            target_ids: List[int], tactic_state: dict):
        """Assign specific roles for a tactic"""
        if not self.entity_plugin:
            return
        
        if tactic_name == "flank":
            # Split into main force and flankers
            flanker_count = max(1, len(entity_ids) // 3)
            for i, eid in enumerate(entity_ids):
                entity = self.entity_plugin.get_entity(eid)
                if entity and entity.has_component("group_tactics"):
                    comp = entity.get_component("group_tactics")
                    comp.data.is_flanking = i < flanker_count
                    comp.data.flanking_angle = (i * 2 * math.pi / flanker_count) if comp.data.is_flanking else 0
        
        elif tactic_name == "focus_fire":
            # All entities focus on primary target
            primary_target = target_ids[0] if target_ids else None
            for eid in entity_ids:
                entity = self.entity_plugin.get_entity(eid)
                if entity and entity.has_component("group_tactics"):
                    comp = entity.get_component("group_tactics")
                    comp.data.is_focusing_fire = True
                    comp.data.target_priority = "same_as_leader"
        
        elif tactic_name == "defend":
            # Tanks protect squishies
            tanks = []
            squishies = []
            for eid in entity_ids:
                entity = self.entity_plugin.get_entity(eid)
                if entity and entity.has_component("group_tactics"):
                    comp = entity.get_component("group_tactics")
                    if comp.data.role == CombatRole.TANK:
                        tanks.append(eid)
                    else:
                        squishies.append(eid)
                        comp.data.is_defending = True
            
            # Assign protection targets
            for i, squishy_id in enumerate(squishies):
                if tanks:
                    protector_id = tanks[i % len(tanks)]
                    entity = self.entity_plugin.get_entity(squishy_id)
                    if entity and entity.has_component("group_tactics"):
                        comp = entity.get_component("group_tactics")
                        comp.data.protected_target = protector_id
    
    def _update_threat_assessment(self):
        """Update threat map based on entity positions and actions"""
        # Simplified: in real implementation, would check aggro tables, damage dealt, etc.
        pass
    
    def _update_group_formations(self, delta_time: float):
        """Maintain group formations"""
        current_time = self.event_system.get_time() if self.event_system else 0
        
        for group_id, entity_ids in list(self.groups.items()):
            if len(entity_ids) < self.config["min_group_size"]:
                continue
            
            # Get group center
            positions = []
            for eid in entity_ids:
                if self.entity_plugin:
                    entity = self.entity_plugin.get_entity(eid)
                    if entity and hasattr(entity, 'position'):
                        positions.append(entity.position)
            
            if not positions:
                continue
            
            # Calculate formation positions based on type
            # (Implementation would send movement commands to entities)
    
    def _execute_active_tactics(self, delta_time: float):
        """Execute active tactical maneuvers"""
        tactics_to_complete = []
        
        for tactic_id, state in self.active_tactics.items():
            if state["status"] != "active":
                continue
            
            # Check completion conditions
            if self._check_tactic_completion(state):
                state["status"] = "completed"
                tactics_to_complete.append(tactic_id)
                self._on_tactic_completed(tactic_id, state)
            elif self._check_tactic_failure(state):
                state["status"] = "failed"
                tactics_to_complete.append(tactic_id)
                self._on_tactic_failed(tactic_id, state)
        
        # Cleanup completed tactics
        for tactic_id in tactics_to_complete:
            self.active_tactics.pop(tactic_id, None)
    
    def _check_tactic_completion(self, tactic_state: dict) -> bool:
        """Check if a tactic has completed successfully"""
        # Simplified logic - real implementation would check specific conditions
        return False
    
    def _check_tactic_failure(self, tactic_state: dict) -> bool:
        """Check if a tactic has failed"""
        # Check if group members are dead
        group_id = tactic_state.get("group_id")
        if group_id and group_id in self.groups:
            alive_count = len([
                eid for eid in self.groups[group_id]
                if self.entity_plugin and self.entity_plugin.get_entity(eid)
            ])
            return alive_count == 0
        return True
    
    def _on_tactic_completed(self, tactic_id: str, state: dict):
        """Handle successful tactic completion"""
        self.logger.info(f"Tactic {state['name']} completed successfully")
        
        # Emit event
        if self.event_system:
            self.event_system.emit("on_tactic_completed", tactic_id=tactic_id, state=state)
    
    def _on_tactic_failed(self, tactic_id: str, state: dict):
        """Handle tactic failure"""
        self.logger.warning(f"Tactic {state['name']} failed")
        
        # Emit event
        if self.event_system:
            self.event_system.emit("on_tactic_failed", tactic_id=tactic_id, state=state)
    
    def _cancel_tactic(self, tactic_id: str):
        """Cancel an active tactic"""
        if tactic_id in self.active_tactics:
            state = self.active_tactics.pop(tactic_id)
            state["status"] = "cancelled"
            self.logger.info(f"Tactic {state['name']} cancelled")
    
    # Event handlers
    def _on_combat_start(self, **kwargs):
        """Handle combat start - organize groups"""
        pass
    
    def _on_entity_spawned(self, entity_id: int, **kwargs):
        """Handle entity spawn"""
        pass
    
    def _on_entity_death(self, entity_id: int, **kwargs):
        """Handle entity death - update groups"""
        if entity_id in self.entity_groups:
            group_id = self.entity_groups[entity_id]
            if group_id in self.groups:
                self.groups[group_id].remove(entity_id)
                
                # Dissolve if too small
                if len(self.groups[group_id]) < self.config["min_group_size"]:
                    self.dissolve_group(group_id)
    
    def _on_update(self, delta_time: float, **kwargs):
        """Handle game update"""
        self.update(delta_time)


# Export for plugin manager
__all__ = ["ArenaAIPlugin", "GroupTacticsComponent", "CombatRole", "FormationType"]
