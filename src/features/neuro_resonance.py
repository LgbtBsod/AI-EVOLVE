"""
Neuro Resonance System - Allied Synchronization
Allows allied AI units to synchronize their neural networks for coordinated tactics.
Implements group consciousness mechanics where nearby allies share information and bonuses.
"""
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.event_system import Event, EventSystem


class ResonanceState(Enum):
    NONE = "none"
    WEAK = "weak"       # 2-3 units, +5% sync
    MODERATE = "moderate"  # 4-6 units, +15% sync
    STRONG = "strong"   # 7+ units, +30% sync
    PERFECT = "perfect" # Full squad sync, +50% sync, shared vision


@dataclass(slots=True)
class ResonanceLink:
    """Represents a neural link between two units."""
    unit_a: str
    unit_b: str
    strength: float  # 0.0 to 1.0
    established_at: float
    last_sync: float


@dataclass(slots=True)
class ResonanceStats:
    current_resonance: float  # 0.0 to 100.0
    state: ResonanceState
    linked_units: set[str]
    shared_vision: bool
    coordination_bonus: float


class NeuroResonanceSystem(BaseComponent):
    """
    Manages neural resonance between allied units.
    Units close together form resonance links, sharing:
    - Vision information
    - Tactical data (enemy positions, threats)
    - Combat bonuses (coordination, reaction time)
    """
    
    def __init__(self, max_links_per_unit: int = 5, sync_range: float = 50.0):
        super().__init__(ComponentType.SYSTEM, Priority.HIGH)
        self.max_links_per_unit = max_links_per_unit
        self.sync_range = sync_range
        
        self.unit_resonance: dict[str, ResonanceStats] = {}
        self.resonance_links: list[ResonanceLink] = []
        self.squad_groups: dict[str, set[str]] = {}  # squad_id -> unit_ids
        
    def on_start(self):
        logging.info("Neuro Resonance System initialized. Ready for squad synchronization.")
        
    def register_unit(self, unit_id: str, squad_id: str | None = None):
        """Register a unit for resonance tracking."""
        self.unit_resonance[unit_id] = ResonanceStats(
            current_resonance=0.0,
            state=ResonanceState.NONE,
            linked_units=set(),
            shared_vision=False,
            coordination_bonus=0.0
        )
        
        if squad_id:
            if squad_id not in self.squad_groups:
                self.squad_groups[squad_id] = set()
            self.squad_groups[squad_id].add(unit_id)
            
        logging.debug(f"Unit {unit_id} registered for resonance tracking.")
        
    def update_unit_position(self, unit_id: str, position: tuple):
        """Update unit position for proximity calculations."""
        # Store position for resonance calculation
        if not hasattr(self, '_unit_positions'):
            self._unit_positions = {}
        self._unit_positions[unit_id] = position
        
    def _calculate_distance(self, pos_a: tuple, pos_b: tuple) -> float:
        """Calculate Euclidean distance between two positions."""
        return ((pos_a[0] - pos_b[0])**2 + (pos_a[1] - pos_b[1])**2)**0.5
        
    def establish_link(self, unit_a: str, unit_b: str) -> bool:
        """Establish a resonance link between two units."""
        if unit_a not in self.unit_resonance or unit_b not in self.unit_resonance:
            return False
            
        stats_a = self.unit_resonance[unit_a]
        stats_b = self.unit_resonance[unit_b]
        
        # Check max links
        if len(stats_a.linked_units) >= self.max_links_per_unit:
            return False
        if len(stats_b.linked_units) >= self.max_links_per_unit:
            return False
            
        # Check if already linked
        if unit_b in stats_a.linked_units:
            return False
            
        # Create link
        link = ResonanceLink(
            unit_a=unit_a,
            unit_b=unit_b,
            strength=1.0,
            established_at=time.perf_counter(),
            last_sync=time.perf_counter()
        )
        
        self.resonance_links.append(link)
        stats_a.linked_units.add(unit_b)
        stats_b.linked_units.add(unit_a)
        
        logging.debug(f"Resonance link established: {unit_a} <-> {unit_b}")
        return True
        
    def update_resonance_state(self, unit_id: str):
        """Update resonance state based on linked units."""
        if unit_id not in self.unit_resonance:
            return
            
        stats = self.unit_resonance[unit_id]
        linked_count = len(stats.linked_units)
        
        # Determine state based on link count
        old_state = stats.state
        if linked_count == 0:
            stats.state = ResonanceState.NONE
            stats.coordination_bonus = 0.0
        elif linked_count <= 2:
            stats.state = ResonanceState.WEAK
            stats.coordination_bonus = 0.05
        elif linked_count <= 5:
            stats.state = ResonanceState.MODERATE
            stats.coordination_bonus = 0.15
        elif linked_count <= 8:
            stats.state = ResonanceState.STRONG
            stats.coordination_bonus = 0.30
        else:
            stats.state = ResonanceState.PERFECT
            stats.coordination_bonus = 0.50
            stats.shared_vision = True
            
        # Calculate resonance percentage
        stats.current_resonance = min(100.0, linked_count * 10.0)
        
        if old_state != stats.state:
            logging.info(f"Unit {unit_id} resonance changed to {stats.state.value}")
            
            if EventSystem.instance:
                EventSystem.instance.trigger_event(Event(
                    event_type="RESONANCE_CHANGED",
                    data={
                        "unit_id": unit_id,
                        "state": stats.state.value,
                        "resonance": stats.current_resonance,
                        "bonus": stats.coordination_bonus
                    }
                ))
                
    def get_shared_information(self, unit_id: str) -> dict[str, Any]:
        """Get information shared through resonance links."""
        if unit_id not in self.unit_resonance:
            return {}
            
        stats = self.unit_resonance[unit_id]
        shared_data = {
            "enemy_positions": [],
            "threats": [],
            "allied_positions": [],
            "tactical_advantages": []
        }
        
        # Gather data from linked units
        for linked_id in stats.linked_units:
            if hasattr(self, '_unit_tactical_data') and linked_id in self._unit_tactical_data:
                data = self._unit_tactical_data[linked_id]
                shared_data["enemy_positions"].extend(data.get("enemies", []))
                shared_data["threats"].extend(data.get("threats", []))
                
        return shared_data
        
    def get_combat_bonus(self, unit_id: str) -> dict[str, float]:
        """Get combat bonuses from resonance."""
        if unit_id not in self.unit_resonance:
            return {}
            
        stats = self.unit_resonance[unit_id]
        
        return {
            "accuracy": stats.coordination_bonus * 0.5,
            "reaction_speed": stats.coordination_bonus,
            "damage": stats.coordination_bonus * 0.3,
            "defense": stats.coordination_bonus * 0.2
        }
        
    def on_update(self, dt: float):
        """Update resonance links and states."""
        current_time = time.perf_counter()
        
        # Update link strengths based on distance
        if hasattr(self, '_unit_positions'):
            for link in self.resonance_links[:]:
                if link.unit_a not in self._unit_positions or link.unit_b not in self._unit_positions:
                    continue
                    
                dist = self._calculate_distance(
                    self._unit_positions[link.unit_a],
                    self._unit_positions[link.unit_b]
                )
                
                if dist > self.sync_range:
                    # Weaken link
                    link.strength -= dt * 0.1
                    if link.strength <= 0:
                        # Break link
                        self._break_link(link)
                else:
                    # Strengthen link
                    link.strength = min(1.0, link.strength + dt * 0.05)
                    link.last_sync = current_time
                    
        # Update all unit resonance states
        for unit_id in list(self.unit_resonance.keys()):
            self.update_resonance_state(unit_id)
            
    def _break_link(self, link: ResonanceLink):
        """Break a resonance link."""
        if link in self.resonance_links:
            self.resonance_links.remove(link)
            
        if link.unit_a in self.unit_resonance:
            self.unit_resonance[link.unit_a].linked_units.discard(link.unit_b)
        if link.unit_b in self.unit_resonance:
            self.unit_resonance[link.unit_b].linked_units.discard(link.unit_a)
            
        logging.debug(f"Resonance link broken: {link.unit_a} <-> {link.unit_b}")
        
    def _on_update(self, delta_time: float) -> None:
        """Implementation of abstract method."""
        self.on_update(delta_time)
