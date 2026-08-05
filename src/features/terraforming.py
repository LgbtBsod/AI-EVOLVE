"""
Terraforming Battlefield System - Environmental Scars
Persistent battlefield modifications from combat that affect tactics.
Implements dynamic terrain changes: craters, burn marks, debris fields.
"""
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.event_system import Event, EventSystem


class TerrainModificationType(Enum):
    CRATER = "crater"           # Blocks movement, provides cover
    BURN_MARK = "burn_mark"     # Damage over time area
    DEBRIS_FIELD = "debris"     # Slows movement, partial cover
    ICE_PATCH = "ice"           # Slippery, fast movement
    ELECTRIFIED_ZONE = "electric"  # Damage over time
    RADIOACTIVE = "radioactive"   # Long-term DoT


@dataclass(slots=True)
class TerrainModification:
    mod_type: TerrainModificationType
    position: tuple[float, float]
    radius: float
    duration: float  # seconds, -1 for permanent
    created_at: float
    effects: dict[str, float] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        if self.duration < 0:
            return False
        return time.perf_counter() - self.created_at > self.duration


class TerraformingSystem(BaseComponent):
    """
    Manages persistent battlefield modifications.
    Combat actions leave scars on the terrain that affect:
    - Movement speed
    - Cover availability
    - Line of sight
    - Damage over time zones
    """
    
    def __init__(self, max_modifications: int = 100):
        super().__init__(ComponentType.SYSTEM, Priority.NORMAL)
        self.max_modifications = max_modifications
        self.modifications: list[TerrainModification] = []
        self.position_grid: dict[tuple[int, int], list[TerrainModification]] = {}
        
    def on_start(self):
        logging.info("Terraforming System initialized. Battlefield will retain combat scars.")
        
    def add_modification(
        self,
        mod_type: TerrainModificationType,
        position: tuple[float, float],
        radius: float,
        duration: float = 60.0,
        effects: dict[str, float] | None = None
    ):
        """Add a terrain modification."""
        mod = TerrainModification(
            mod_type=mod_type,
            position=position,
            radius=radius,
            duration=duration,
            created_at=time.perf_counter(),
            effects=effects or self._get_default_effects(mod_type)
        )
        
        self.modifications.append(mod)
        
        # Add to spatial grid for fast lookup
        grid_key = (int(position[0] / 10), int(position[1] / 10))
        if grid_key not in self.position_grid:
            self.position_grid[grid_key] = []
        self.position_grid[grid_key].append(mod)
        
        # Cleanup if exceeded max
        if len(self.modifications) > self.max_modifications:
            self._cleanup_oldest()
            
        logging.debug(f"Terrain modification added: {mod_type.value} at {position}")
        
        if EventSystem.instance:
            EventSystem.instance.trigger_event(Event(
                event_type="TERRAIN_MODIFIED",
                data={
                    "type": mod_type.value,
                    "position": position,
                    "radius": radius,
                    "duration": duration
                }
            ))
            
    def _get_default_effects(self, mod_type: TerrainModificationType) -> dict[str, float]:
        """Get default effects for modification type."""
        defaults = {
            TerrainModificationType.CRATER: {
                "movement_speed": -1.0,  # Impassable
                "cover_bonus": 0.8,
                "visibility": -0.3
            },
            TerrainModificationType.BURN_MARK: {
                "movement_speed": -0.3,
                "damage_per_second": 5.0,
                "visibility": 0.1  # Glowing
            },
            TerrainModificationType.DEBRIS_FIELD: {
                "movement_speed": -0.5,
                "cover_bonus": 0.4,
                "accuracy": -0.2
            },
            TerrainModificationType.ICE_PATCH: {
                "movement_speed": 0.5,
                "control": -0.6,  # Slippery
                "friction": -0.8
            },
            TerrainModificationType.ELECTRIFIED_ZONE: {
                "movement_speed": -0.2,
                "damage_per_second": 10.0,
                "stun_chance": 0.1
            },
            TerrainModificationType.RADIOACTIVE: {
                "movement_speed": -0.1,
                "damage_per_second": 2.0,
                "max_health_reduction": 0.01  # Per second
            }
        }
        return defaults.get(mod_type, {})
        
    def get_position_effects(self, position: tuple[float, float]) -> dict[str, float]:
        """Get all cumulative effects at a position."""
        grid_key = (int(position[0] / 10), int(position[1] / 10))
        
        # Check adjacent grid cells too for edge cases
        adjacent_keys = [
            grid_key,
            (grid_key[0] - 1, grid_key[1]),
            (grid_key[0] + 1, grid_key[1]),
            (grid_key[0], grid_key[1] - 1),
            (grid_key[0], grid_key[1] + 1)
        ]
        
        combined_effects = {}
        
        for key in adjacent_keys:
            if key not in self.position_grid:
                continue
                
            for mod in self.position_grid[key]:
                if mod.is_expired:
                    continue
                    
                # Check if position is within radius
                dist = ((position[0] - mod.position[0])**2 + (position[1] - mod.position[1])**2)**0.5
                if dist <= mod.radius:
                    # Combine effects
                    for effect_name, value in mod.effects.items():
                        if effect_name not in combined_effects:
                            combined_effects[effect_name] = 0.0
                        combined_effects[effect_name] += value
                        
        return combined_effects
        
    def is_position_blocked(self, position: tuple[float, float]) -> bool:
        """Check if position is blocked by terrain modification."""
        effects = self.get_position_effects(position)
        return effects.get("movement_speed", 0) <= -0.9
        
    def get_cover_bonus(self, position: tuple[float, float]) -> float:
        """Get cover bonus at position."""
        effects = self.get_position_effects(position)
        return effects.get("cover_bonus", 0.0)
        
    def _cleanup_oldest(self):
        """Remove oldest expired or non-expired modifications."""
        # First remove expired
        self.modifications = [m for m in self.modifications if not m.is_expired]
        
        # Rebuild grid
        self.position_grid.clear()
        for mod in self.modifications:
            grid_key = (int(mod.position[0] / 10), int(mod.position[1] / 10))
            if grid_key not in self.position_grid:
                self.position_grid[grid_key] = []
            self.position_grid[grid_key].append(mod)
            
        # If still over limit, remove oldest by creation time
        if len(self.modifications) > self.max_modifications:
            self.modifications.sort(key=lambda m: m.created_at)
            removed_count = len(self.modifications) - self.max_modifications
            for _ in range(removed_count):
                old_mod = self.modifications.pop(0)
                # Remove from grid
                grid_key = (int(old_mod.position[0] / 10), int(old_mod.position[1] / 10))
                if grid_key in self.position_grid:
                    self.position_grid[grid_key] = [
                        m for m in self.position_grid[grid_key] if m != old_mod
                    ]
                    
    def on_update(self, dt: float):
        """Cleanup expired modifications."""
        # Periodic cleanup
        if hasattr(self, '_last_cleanup') and time.perf_counter() - self._last_cleanup < 5.0:
            return
            
        self._last_cleanup = time.perf_counter()
        
        expired_count = sum(1 for m in self.modifications if m.is_expired)
        if expired_count > 0:
            self._cleanup_oldest()
            logging.debug(f"Cleaned up {expired_count} expired terrain modifications")
            
    def get_battlefield_state(self) -> dict[str, Any]:
        """Get summary of current battlefield state."""
        active_mods = [m for m in self.modifications if not m.is_expired]
        
        by_type = {}
        for mod in active_mods:
            type_name = mod.mod_type.value
            if type_name not in by_type:
                by_type[type_name] = 0
            by_type[type_name] += 1
            
        return {
            "total_modifications": len(active_mods),
            "by_type": by_type,
            "grid_cells_affected": len(self.position_grid)
        }
        
    def _on_update(self, delta_time: float) -> None:
        """Implementation of abstract method."""
        self.on_update(delta_time)
