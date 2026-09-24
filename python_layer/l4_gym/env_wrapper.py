"""Gym Environment Wrapper for Rust Core"""

import numpy as np
from typing import Tuple, List, Dict, Any, Optional

class GymWrapper:
    """
    OpenAI Gym compatible wrapper for Rust simulation environment.
    
    Interfaces with rust_core via PyO3 bindings.
    """
    
    def __init__(self, seed: int, config: Optional[Dict] = None):
        self.seed = seed
        self.config = config or {}
        
        # Try to import Rust core (will fail until built)
        try:
            from rust_core import PySimulationEnv
            self.env = PySimulationEnv.new(seed)
            self._rust_available = True
        except ImportError:
            self.env = None
            self._rust_available = False
            
        # Define spaces
        self.observation_space = self._create_observation_space()
        self.action_space = self._create_action_space()
        
        self.current_obs = None
        self.done = False
        
    def _create_observation_space(self) -> Dict[str, np.ndarray]:
        """Create hybrid observation space (visual + vector)"""
        return {
            'visual': np.zeros((64, 64), dtype=np.uint8),  # Grayscale
            'vector': np.zeros(32, dtype=np.float32),  # HP, position, inventory, etc.
        }
    
    def _create_action_space(self) -> Dict[str, Any]:
        """Create hierarchical action space"""
        return {
            'high_level': ['attack', 'move', 'use_skill', 'use_item', 'wait'],
            'low_level': {
                'dx': (-1, 0, 1),
                'dy': (-1, 0, 1),
                'target_id': int,
                'skill_id': int,
            }
        }
    
    def reset(self) -> Tuple[np.ndarray, Dict]:
        """Reset environment and return initial observation"""
        if self._rust_available:
            # Call Rust env.reset()
            pass
        
        self.done = False
        obs = self._get_dummy_observation()
        self.current_obs = obs
        return obs, {}
    
    def step(self, actions: Dict) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Take a step in the environment.
        
        Args:
            actions: Dict with 'high_level' and 'low_level' keys
            
        Returns:
            observation, reward, done, info
        """
        if not self._rust_available:
            return self._dummy_step(actions)
            
        # Convert Python actions to Rust format
        rust_actions = self._convert_actions(actions)
        
        # Call Rust step
        obs, reward, done, info = self.env.step(rust_actions)
        
        self.current_obs = obs
        self.done = done
        return obs, reward, done, info
    
    def step_batch(self, actions_list: List[Dict]) -> Tuple[List, List, List, List]:
        """Batch step for ML training (releases GIL in Rust)"""
        if not self._rust_available:
            return [self._dummy_step(a) for a in actions_list]
            
        rust_actions = [self._convert_actions(a) for a in actions_list]
        return self.env.step_batch(rust_actions)
    
    def _convert_actions(self, action: Dict) -> List:
        """Convert Python action dict to Rust action format"""
        # Placeholder - will be implemented with proper PyO3 types
        return []
    
    def _get_dummy_observation(self) -> Dict[str, np.ndarray]:
        """Return dummy observation when Rust is not available"""
        return {
            'visual': np.zeros((64, 64), dtype=np.uint8),
            'vector': np.zeros(32, dtype=np.float32),
        }
    
    def _dummy_step(self, action: Dict) -> Tuple[Dict, float, bool, Dict]:
        """Dummy step for testing without Rust"""
        return self._get_dummy_observation(), 0.0, False, {}
    
    def render(self, mode='human'):
        """Render the environment (delegated to L7)"""
        pass
    
    def close(self):
        """Clean up resources"""
        pass
