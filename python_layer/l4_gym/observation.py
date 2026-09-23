"""Observation Space Definition"""

import numpy as np
from typing import Dict, Any

class ObservationSpace:
    """
    Hybrid observation space for the agent.
    
    Combines visual (CNN) and vector (MLP) channels.
    """
    
    def __init__(self):
        self.visual_shape = (64, 64)  # Grayscale
        self.vector_size = 32
        
        # Vector components breakdown
        self.vector_components = {
            'stats': slice(0, 4),      # HP, mana, stamina, energy
            'position': slice(4, 6),   # x, y (normalized)
            'direction': slice(6, 8),  # dx, dy
            'inventory': slice(8, 16), # One-hot for slots
            'skills': slice(16, 24),   # Available skills mask
            'enemies': slice(24, 28),  # Nearest enemy (rel_x, rel_y, hp)
            'items': slice(28, 30),    # Nearest item (rel_x, rel_y)
            'emotions': slice(30, 32), # fear, aggression
        }
    
    def create_observation(self, 
                          visual: np.ndarray,
                          hp: float, mana: float, stamina: float,
                          position: tuple, direction: tuple,
                          inventory: list, skills: list,
                          nearest_enemy: dict = None,
                          nearest_item: tuple = None,
                          emotions: tuple = (0, 0)) -> Dict[str, np.ndarray]:
        """Create a full observation from game state"""
        
        # Visual channel
        vis_obs = visual.astype(np.uint8)
        
        # Vector channel
        vec_obs = np.zeros(self.vector_size, dtype=np.float32)
        
        # Stats (normalized to 0-1)
        vec_obs[self.vector_components['stats']] = [hp/100, mana/100, stamina/100, 0]
        
        # Position (normalized to world size)
        vec_obs[self.vector_components['position']] = [position[0]/100, position[1]/100]
        
        # Direction
        vec_obs[self.vector_components['direction']] = direction
        
        # Inventory (one-hot)
        for i, item in enumerate(inventory[:8]):
            if item is not None:
                vec_obs[self.vector_components['inventory'].start + i] = 1
        
        # Skills mask
        for i, skill in enumerate(skills[:8]):
            if skill is not None:
                vec_obs[self.vector_components['skills'].start + i] = 1
        
        # Nearest enemy
        if nearest_enemy:
            vec_obs[self.vector_components['enemies']] = [
                nearest_enemy.get('rel_x', 0) / 50,
                nearest_enemy.get('rel_y', 0) / 50,
                nearest_enemy.get('hp', 0) / 100,
                0
            ]
        
        # Nearest item
        if nearest_item:
            vec_obs[self.vector_components['items']] = [
                nearest_item[0] / 50,
                nearest_item[1] / 50
            ]
        
        # Emotions
        vec_obs[self.vector_components['emotions']] = emotions
        
        return {
            'visual': vis_obs,
            'vector': vec_obs
        }
