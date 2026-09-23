"""Hierarchical Action Space Definition"""

from typing import Dict, Any, List
from enum import Enum

class HighLevelAction(Enum):
    ATTACK = "attack"
    MOVE = "move"
    USE_SKILL = "use_skill"
    USE_ITEM = "use_item"
    WAIT = "wait"

class ActionSpace:
    """
    Hierarchical action space for the agent.
    
    Two levels:
    - High level: Intent (attack, move, use_skill, etc.)
    - Low level: Parameters (target, direction, skill_id, etc.)
    """
    
    HIGH_LEVEL_ACTIONS = list(HighLevelAction)
    
    def __init__(self):
        self.low_level_params = {
            'dx': [-1, 0, 1],
            'dy': [-1, 0, 1],
            'target_id_range': (0, 1000),
            'skill_id_range': (0, 100),
            'item_id_range': (0, 100),
        }
    
    def sample(self) -> Dict[str, Any]:
        """Sample a random action"""
        import random
        
        high_level = random.choice(self.HIGH_LEVEL_ACTIONS)
        
        low_level = {
            'dx': random.choice(self.low_level_params['dx']),
            'dy': random.choice(self.low_level_params['dy']),
            'target_id': random.randint(*self.low_level_params['target_id_range']),
            'skill_id': random.randint(*self.low_level_params['skill_id_range']),
            'item_id': random.randint(*self.low_level_params['item_id_range']),
        }
        
        return {
            'high_level': high_level,
            'low_level': low_level
        }
    
    def create_action(self, 
                     high_level: HighLevelAction,
                     dx: int = 0, dy: int = 0,
                     target_id: int = None,
                     skill_id: int = None,
                     item_id: int = None) -> Dict[str, Any]:
        """Create a specific action"""
        return {
            'high_level': high_level,
            'low_level': {
                'dx': dx,
                'dy': dy,
                'target_id': target_id,
                'skill_id': skill_id,
                'item_id': item_id,
            }
        }
    
    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate action format"""
        if 'high_level' not in action or 'low_level' not in action:
            return False
            
        if action['high_level'] not in self.HIGH_LEVEL_ACTIONS:
            return False
            
        ll = action['low_level']
        if ll['dx'] not in self.low_level_params['dx']:
            return False
        if ll['dy'] not in self.low_level_params['dy']:
            return False
            
        return True
