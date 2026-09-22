"""
Game Master Module (Player Influence Layer)
SRP: Handles player-driven world changes (traps, enemies, loot)
Constraint: CANNOT directly control the Hero entity.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
import uuid
from collections import deque

logger = logging.getLogger("GameMaster")

class WorldEventType(Enum):
    SPAWN_ENEMY = "spawn_enemy"
    SPAWN_LOOT = "spawn_loot"
    PLACE_TRAP = "place_trap"
    CHANGE_WEATHER = "change_weather"
    TRIGGER_EVENT = "trigger_event"

@dataclass
class WorldCommand:
    event_type: WorldEventType
    params: Dict[str, Any]
    source: str = "player"
    timestamp: float = field(default_factory=lambda: 0.0)

class GameMaster:
    """
    SSOT for World State modifications initiated by the Player.
    Decoupled from Hero logic.
    """
    def __init__(self, entity_manager):
        self.entity_manager = entity_manager
        self.command_queue: deque = deque(maxlen=1000)
        self.history: List[WorldCommand] = []
        
    def submit_command(self, cmd: WorldCommand):
        """Thread-safe command submission."""
        logger.info(f"GM Command Received: {cmd.event_type.value}")
        self.command_queue.append(cmd)
        self.history.append(cmd)
        
    def process_queue(self, dt: float):
        """Execute pending world changes."""
        processed = 0
        while self.command_queue:
            cmd = self.command_queue.popleft()
            self._execute(cmd)
            processed += 1
        return processed

    def _execute(self, cmd: WorldCommand):
        try:
            if cmd.event_type == WorldEventType.SPAWN_ENEMY:
                self._spawn_enemy(cmd.params)
            elif cmd.event_type == WorldEventType.SPAWN_LOOT:
                self._spawn_loot(cmd.params)
            elif cmd.event_type == WorldEventType.PLACE_TRAP:
                self._place_trap(cmd.params)
            elif cmd.event_type == WorldEventType.CHANGE_WEATHER:
                self._change_weather(cmd.params)
            elif cmd.event_type == WorldEventType.TRIGGER_EVENT:
                self._trigger_event(cmd.params)
            else:
                logger.error(f"Unknown GM event: {cmd.event_type}")
        except Exception as e:
            logger.error(f"GM Execution failed: {e}", exc_info=True)

    def _spawn_enemy(self, params: Dict):
        enemy_id = str(uuid.uuid4())
        logger.info(f"[GM] Spawning enemy {enemy_id} at {params.get('pos')}")
        # TODO: Integrate with EntityManager
        # self.entity_manager.create_entity(...) 

    def _spawn_loot(self, params: Dict):
        logger.info(f"[GM] Spawning loot: {params.get('type')} at {params.get('pos')}")

    def _place_trap(self, params: Dict):
        logger.info(f"[GM] Placing trap: {params.get('type')} at {params.get('pos')}")

    def _change_weather(self, params: Dict):
        logger.info(f"[GM] Weather changed to: {params.get('condition')}")

    def _trigger_event(self, params: Dict):
        logger.info(f"[GM] Triggering event: {params.get('event_name')}")

    def get_stats(self) -> Dict:
        return {
            "pending_commands": len(self.command_queue),
            "total_events": len(self.history)
        }
