"""
Morale & Panic System
AI units experience morale changes affecting combat performance.
"""
import random
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.event_system import EventSystem, Event

class MoraleState(Enum):
    HEROIC = "heroic"      # +30% performance
    HIGH = "high"          # +15%
    NORMAL = "normal"      # 0%
    WAVERING = "waver"     # -15%
    PANICKED = "panicked"  # -40%, may flee
    BROKEN = "broken"      # -70%, will flee

@dataclass
class MoraleStats:
    current_morale: float  # 0.0 to 100.0
    max_morale: float
    morale_decay: float    # per second
    morale_recovery: float # per second
    state: MoraleState

class MoraleSystem(BaseComponent):
    """
    Manages unit morale. High casualties or surprise attacks lower morale.
    Victories and leadership boost it.
    """
    def __init__(self):
        super().__init__(ComponentType.SYSTEM, Priority.NORMAL)
        self.unit_morale: Dict[str, MoraleStats] = {}
        
    def on_start(self):
        logging.info("Morale System initialized.")
        
    def register_unit(self, unit_id: str, base_morale: float = 80.0):
        """Register a new unit with initial morale."""
        self.unit_morale[unit_id] = MoraleStats(
            current_morale=base_morale,
            max_morale=100.0,
            morale_decay=0.5,  # Slow natural decay
            morale_recovery=1.0,
            state=MoraleState.NORMAL
        )
        
    def apply_morale_change(self, unit_id: str, change: float, reason: str):
        """Apply immediate morale change."""
        if unit_id not in self.unit_morale:
            return
            
        stats = self.unit_morale[unit_id]
        old_state = stats.state
        
        stats.current_morale = max(0.0, min(stats.max_morale, stats.current_morale + change))
        
        # Update state based on thresholds
        if stats.current_morale >= 90:
            stats.state = MoraleState.HEROIC
        elif stats.current_morale >= 65:
            stats.state = MoraleState.HIGH
        elif stats.current_morale >= 35:
            stats.state = MoraleState.NORMAL
        elif stats.current_morale >= 15:
            stats.state = MoraleState.WAVERING
        elif stats.current_morale > 0:
            stats.state = MoraleState.PANICKED
        else:
            stats.state = MoraleState.BROKEN
            
        if old_state != stats.state:
            logging.info(f"Unit {unit_id} morale changed to {stats.state.value} ({reason})")
            
            # Broadcast event for AI behavior adjustment
            if EventSystem.instance:
                EventSystem.instance.trigger_event(Event(
                    event_type="MORALE_CHANGED",
                    data={
                        "unit_id": unit_id,
                        "state": stats.state.value,
                        "morale": stats.current_morale,
                        "reason": reason
                    }
                ))
                
    def get_performance_modifier(self, unit_id: str) -> float:
        """Get combat performance modifier based on morale."""
        if unit_id not in self.unit_morale:
            return 0.0
            
        state = self.unit_morale[unit_id].state
        modifiers = {
            MoraleState.HEROIC: 0.3,
            MoraleState.HIGH: 0.15,
            MoraleState.NORMAL: 0.0,
            MoraleState.WAVERING: -0.15,
            MoraleState.PANICKED: -0.4,
            MoraleState.BROKEN: -0.7
        }
        return modifiers.get(state, 0.0)
        
    def should_flee(self, unit_id: str) -> bool:
        """Check if unit should flee due to low morale."""
        if unit_id not in self.unit_morale:
            return False
        state = self.unit_morale[unit_id].state
        return state in [MoraleState.PANICKED, MoraleState.BROKEN]
        
    def on_update(self, dt: float):
        """Passive morale recovery/decay."""
        for unit_id, stats in self.unit_morale.items():
            # Natural recovery if not in combat (simplified)
            if stats.state in [MoraleState.NORMAL, MoraleState.HIGH]:
                stats.current_morale = min(stats.max_morale, stats.current_morale + stats.morale_recovery * dt)
            else:
                # Decay faster when already low
                stats.current_morale = max(0.0, stats.current_morale - stats.morale_decay * dt)
                
            # Re-evaluate state
            old_state = stats.state
            if stats.current_morale >= 90:
                stats.state = MoraleState.HEROIC
            elif stats.current_morale >= 65:
                stats.state = MoraleState.HIGH
            elif stats.current_morale >= 35:
                stats.state = MoraleState.NORMAL
            elif stats.current_morale >= 15:
                stats.state = MoraleState.WAVERING
            elif stats.current_morale > 0:
                stats.state = MoraleState.PANICKED
            else:
                stats.state = MoraleState.BROKEN
                
            if old_state != stats.state and EventSystem.instance:
                EventSystem.instance.trigger_event(Event(
                    event_type="MORALE_CHANGED",
                    data={"unit_id": unit_id, "state": stats.state.value, "morale": stats.current_morale, "reason": "passive_change"}
                ))

    def _on_update(self, delta_time: float) -> None:
        """Implementation of abstract method."""
        self.on_update(delta_time)
