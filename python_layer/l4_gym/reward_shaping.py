"""Reward Shaping Functions"""

from typing import Dict, List, Optional
import numpy as np

class RewardShaper:
    """
    Reward shaping for RL training.
    
    Multiple reward channels that can be logged separately
    and combined with different weights.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Default weights
        self.weights = {
            'progress': 1.0,      # Distance towards goal
            'combat_damage': 0.5, # Damage dealt
            'combat_taken': -0.3, # Damage received
            'kill': 2.0,          # Enemy killed
            'death': -5.0,        # Agent died
            'pickup': 0.2,        # Item picked up
            'quest': 3.0,         # Quest completed
            'time_penalty': -0.01, # Per step penalty
            'directive_bonus': 1.0, # Following player directive
        }
        
        # Override with config
        self.weights.update(self.config.get('weights', {}))
        
        # Channels for logging
        self.channels = {
            'progress': 0.0,
            'combat': 0.0,
            'resources': 0.0,
            'quest': 0.0,
            'time': 0.0,
            'directive': 0.0,
        }
    
    def compute_reward(self, 
                      delta_distance: float,
                      damage_dealt: float,
                      damage_taken: float,
                      killed: bool,
                      died: bool,
                      items_picked: int,
                      quest_progress: float,
                      following_directive: bool) -> float:
        """
        Compute total reward from multiple channels.
        
        Returns:
            Total reward value
        """
        # Reset channels
        self.channels = {k: 0.0 for k in self.channels}
        
        # Progress reward
        self.channels['progress'] = delta_distance * self.weights['progress']
        
        # Combat rewards
        combat_reward = (
            damage_dealt * self.weights['combat_damage'] +
            damage_taken * self.weights['combat_taken'] +
            (self.weights['kill'] if killed else 0) +
            (self.weights['death'] if died else 0)
        )
        self.channels['combat'] = combat_reward
        
        # Resource rewards
        self.channels['resources'] = items_picked * self.weights['pickup']
        
        # Quest rewards
        self.channels['quest'] = quest_progress * self.weights['quest']
        
        # Time penalty
        self.channels['time'] = self.weights['time_penalty']
        
        # Directive bonus
        self.channels['directive'] = (
            self.weights['directive_bonus'] if following_directive else 0
        )
        
        # Sum all channels
        total = sum(self.channels.values())
        
        return total
    
    def get_channel_log(self) -> Dict[str, float]:
        """Get reward channels for logging"""
        return self.channels.copy()
    
    def reset(self):
        """Reset channel accumulators"""
        self.channels = {k: 0.0 for k in self.channels}
