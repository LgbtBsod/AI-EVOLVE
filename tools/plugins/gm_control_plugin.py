"""
Plugin 7: Game Master Control Plugin
Allows AI Agents (like the LLM) to act as a "Dungeon Master" 
influencing the world without controlling the hero directly.
"""
import logging
from typing import Dict, Any, Optional
from .agent_command_plugin import CommandType

logger = logging.getLogger("GMControlPlugin")

class GMControlPlugin:
    """
    Bridges Dev Probe with GameMaster module.
    Enforces SRP: Can modify World, CANNOT modify Hero Direct Control.
    """
    
    ALLOWED_COMMANDS = {
        'SPAWN_ENEMY', 'SPAWN_LOOT', 'PLACE_TRAP', 
        'CHANGE_WEATHER', 'TRIGGER_EVENT'
    }
    
    def __init__(self, probe_instance):
        self.probe = probe_instance
        self.gm_interface = None # Injected later
        logger.info("GMControlPlugin initialized")
        
    def set_gm_interface(self, gm_interface):
        """Inject GameMaster dependency."""
        self.gm_interface = gm_interface
        
    def execute_world_action(self, action_type: str, params: Dict[str, Any]) -> bool:
        """
        Execute a world-affecting action.
        Returns True if successful, False if blocked (e.g., trying to control hero).
        """
        if action_type not in self.ALLOWED_COMMANDS:
            logger.warning(f"Blocked unauthorized action: {action_type}")
            return False
            
        if not self.gm_interface:
            logger.error("GM Interface not injected!")
            return False
            
        try:
            # Convert to internal command structure
            from src.core.game_master import WorldEventType, WorldCommand
            
            event_type = WorldEventType(action_type.lower())
            cmd = WorldCommand(event_type=event_type, params=params)
            
            self.gm_interface.submit_command(cmd)
            logger.info(f"GM Action Executed: {action_type}")
            return True
        except Exception as e:
            logger.error(f"GM Action Failed: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        if not self.gm_interface:
            return {"status": "disconnected", "pending": 0}
        stats = self.gm_interface.get_stats()
        return {"status": "active", **stats}

    def validate_safety(self, params: Dict) -> bool:
        """Prevent game-breaking states."""
        max_enemies = 50
        if params.get('count', 0) > max_enemies:
            logger.warning(f"Safety cap triggered: count > {max_enemies}")
            return False
        return True
