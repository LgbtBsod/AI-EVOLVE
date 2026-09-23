"""
Test L4 Gym Wrapper Components

Tests for:
- GymWrapper (gymnasium interface to Rust simulation)
- ObservationSpace (state representation)
- ActionSpace (action definitions)
- RewardShaper (reward functions)
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch

# Import L4 components
import sys
sys.path.insert(0, '/workspace/python_layer')

from l4_gym.env_wrapper import GymWrapper
from l4_gym.observation import ObservationSpace
from l4_gym.action_space import ActionSpace
from l4_gym.reward_shaping import RewardShaper


class TestObservationSpace:
    """Test observation space definition and validation."""
    
    def test_observation_space_creation(self):
        """Test that observation space is created with correct dimensions."""
        obs_space = ObservationSpace()
        
        # Check visual shape
        assert hasattr(obs_space, 'visual_shape')
        assert obs_space.visual_shape == (64, 64)
        
        # Check vector size
        assert hasattr(obs_space, 'vector_size')
        assert obs_space.vector_size == 32
        
        # Check vector components
        assert hasattr(obs_space, 'vector_components')
        assert isinstance(obs_space.vector_components, dict)
    
    def test_observation_creation(self):
        """Test creating observations from game state."""
        obs_space = ObservationSpace()
        
        # Create sample observation
        visual = np.zeros((64, 64), dtype=np.uint8)
        obs = obs_space.create_observation(
            visual=visual,
            hp=100, mana=50, stamina=80,
            position=(10, 20),
            direction=(1, 0),
            inventory=['potion', None, None],
            skills=[1, 2, None]
        )
        
        assert obs is not None
        assert 'visual' in obs
        assert 'vector' in obs
        assert obs['visual'].shape == (64, 64)
        assert obs['vector'].shape == (32,)
    
    def test_observation_normalization(self):
        """Test observation value normalization."""
        obs_space = ObservationSpace()
        
        # Create observation with various values
        visual = np.zeros((64, 64), dtype=np.uint8)
        obs = obs_space.create_observation(
            visual=visual,
            hp=100, mana=100, stamina=100,
            position=(50, 50),
            direction=(0, 1),
            inventory=[],
            skills=[]
        )
        
        # Check normalized values are in reasonable range
        assert np.all(np.isfinite(obs['vector']))
        assert np.max(obs['vector']) <= 1.0  # Normalized to 0-1
        assert np.min(obs['vector']) >= 0.0


class TestActionSpace:
    """Test action space definition and validation."""
    
    def test_action_space_creation(self):
        """Test that action space is created correctly."""
        action_space = ActionSpace()
        
        # Check high level actions exist
        assert hasattr(action_space, 'HIGH_LEVEL_ACTIONS')
        assert len(action_space.HIGH_LEVEL_ACTIONS) > 0
        
        # Check low level structure
        assert hasattr(action_space, 'low_level_params')
        assert isinstance(action_space.low_level_params, dict)
    
    def test_action_creation(self):
        """Test creating valid actions."""
        action_space = ActionSpace()
        
        # Create discrete action using HighLevelAction enum
        from l4_gym.action_space import HighLevelAction
        
        action = action_space.create_action(
            high_level=HighLevelAction.ATTACK,
            dx=0, dy=1
        )
        
        assert action is not None
        assert 'high_level' in action
        assert 'low_level' in action
    
    def test_action_validation(self):
        """Test action validation."""
        action_space = ActionSpace()
        from l4_gym.action_space import HighLevelAction
        
        # Valid action
        valid_action = action_space.create_action(
            high_level=HighLevelAction.MOVE,
            dx=1, dy=0
        )
        assert action_space.validate_action(valid_action) is True
        
        # Invalid action (bad high level)
        invalid_action = {'high_level': 'invalid_action', 'low_level': {}}
        assert action_space.validate_action(invalid_action) is False
    
    def test_action_sampling(self):
        """Test action sampling."""
        action_space = ActionSpace()
        
        # Sample random action
        action = action_space.sample()
        
        assert action is not None
        assert 'high_level' in action
        assert 'low_level' in action
        assert action_space.validate_action(action) is True


class TestRewardShaper:
    """Test reward shaping functions."""
    
    def test_reward_calculator_creation(self):
        """Test reward calculator initialization."""
        reward_calc = RewardShaper()
        
        assert hasattr(reward_calc, 'weights')
        assert isinstance(reward_calc.weights, dict)
    
    def test_combat_reward(self):
        """Test combat-related rewards."""
        reward_calc = RewardShaper()
        
        # Positive reward for dealing damage (no other factors)
        reward = reward_calc.compute_reward(
            delta_distance=0.0,
            damage_dealt=10.0,
            damage_taken=0.0,
            killed=False,
            died=False,
            items_picked=0,
            quest_progress=0.0,
            following_directive=True
        )
        assert reward > 0
        
        # Negative reward for taking damage
        reward = reward_calc.compute_reward(
            delta_distance=0.0,
            damage_dealt=0.0,
            damage_taken=5.0,
            killed=False,
            died=False,
            items_picked=0,
            quest_progress=0.0,
            following_directive=True
        )
        assert reward < 0
    
    def test_progress_reward(self):
        """Test progress-based rewards."""
        reward_calc = RewardShaper()
        
        # Reward for moving towards goal (negative delta = getting closer)
        reward = reward_calc.compute_reward(
            delta_distance=-2.0,
            damage_dealt=0.0,
            damage_taken=0.0,
            killed=False,
            died=False,
            items_picked=0,
            quest_progress=0.0,
            following_directive=True
        )
        assert reward > 0
        
        # Penalty for moving away from goal
        reward = reward_calc.compute_reward(
            delta_distance=3.0,
            damage_dealt=0.0,
            damage_taken=0.0,
            killed=False,
            died=False,
            items_picked=0,
            quest_progress=0.0,
            following_directive=True
        )
        assert reward < 0
    
    def test_kill_death_rewards(self):
        """Test kill and death rewards."""
        reward_calc = RewardShaper()
        
        # Large positive reward for killing enemy
        kill_reward = reward_calc.compute_reward(
            delta_distance=0.0,
            damage_dealt=0.0,
            damage_taken=0.0,
            killed=True,
            died=False,
            items_picked=0,
            quest_progress=0.0,
            following_directive=True
        )
        
        # Large negative reward for dying
        death_reward = reward_calc.compute_reward(
            delta_distance=0.0,
            damage_dealt=0.0,
            damage_taken=0.0,
            killed=False,
            died=True,
            items_picked=0,
            quest_progress=0.0,
            following_directive=True
        )
        
        assert kill_reward > 0
        assert death_reward < 0
        assert abs(death_reward) > kill_reward  # Death should be worse than kill is good
    
    def test_total_reward_calculation(self):
        """Test combined reward calculation."""
        reward_calc = RewardShaper()
        
        # Simulate combat scenario with multiple factors
        total_reward = reward_calc.compute_reward(
            delta_distance=-1.0,
            damage_dealt=15.0,
            damage_taken=5.0,
            killed=True,
            died=False,
            items_picked=2,
            quest_progress=0.1,
            following_directive=True
        )
        
        assert isinstance(total_reward, float)
        assert np.isfinite(total_reward)


class TestEnvWrapper:
    """Test Gym environment wrapper."""
    
    @pytest.fixture
    def mock_rust_env(self):
        """Create mock Rust simulation environment."""
        mock_env = Mock()
        mock_env.reset.return_value = (np.zeros(64, dtype=np.float32), {})
        mock_env.step.return_value = (np.zeros(64, dtype=np.float32), 0.0, False, {})
        mock_env.render.return_value = None
        mock_env.close.return_value = None
        return mock_env
    
    def test_env_wrapper_initialization(self, mock_rust_env):
        """Test environment wrapper creation."""
        with patch('l4_gym.env_wrapper.GymWrapper._create_observation_space') as mock_obs, \
             patch('l4_gym.env_wrapper.GymWrapper._create_action_space') as mock_act:
            mock_obs.return_value = {'visual': np.zeros((64, 64)), 'vector': np.zeros(32)}
            mock_act.return_value = {'high_level': ['attack', 'move']}
            
            env = GymWrapper(seed=42)
            
            assert env is not None
            assert hasattr(env, 'observation_space')
            assert hasattr(env, 'action_space')
    
    def test_env_reset(self, mock_rust_env):
        """Test environment reset."""
        with patch('l4_gym.env_wrapper.GymWrapper._create_observation_space') as mock_obs, \
             patch('l4_gym.env_wrapper.GymWrapper._create_action_space') as mock_act:
            mock_obs.return_value = {'visual': np.zeros((64, 64)), 'vector': np.zeros(32)}
            mock_act.return_value = {'high_level': ['attack', 'move']}
            
            env = GymWrapper(seed=42)
            
            obs, info = env.reset()
            
            assert obs is not None
            assert isinstance(obs, dict)
            assert info is not None
    
    def test_env_step(self, mock_rust_env):
        """Test environment step."""
        with patch('l4_gym.env_wrapper.GymWrapper._create_observation_space') as mock_obs, \
             patch('l4_gym.env_wrapper.GymWrapper._create_action_space') as mock_act:
            mock_obs.return_value = {'visual': np.zeros((64, 64)), 'vector': np.zeros(32)}
            mock_act.return_value = {'high_level': ['attack', 'move']}
            
            env = GymWrapper(seed=42)
            env.reset()
            
            # Take random action
            action = {'high_level': 'attack', 'low_level': {}}
            obs, reward, done, info = env.step(action)
            
            assert obs is not None
            assert isinstance(reward, float)
            assert isinstance(done, bool)
            assert info is not None
    
    def test_env_render(self, mock_rust_env):
        """Test environment rendering."""
        with patch('l4_gym.env_wrapper.GymWrapper._create_observation_space') as mock_obs, \
             patch('l4_gym.env_wrapper.GymWrapper._create_action_space') as mock_act:
            mock_obs.return_value = {'visual': np.zeros((64, 64)), 'vector': np.zeros(32)}
            mock_act.return_value = {'high_level': ['attack', 'move']}
            
            env = GymWrapper(seed=42)
            env.reset()
            
            # Render should not raise exception
            try:
                env.render()
            except Exception as e:
                pytest.fail(f"Render raised unexpected exception: {e}")
    
    def test_env_close(self, mock_rust_env):
        """Test environment cleanup."""
        with patch('l4_gym.env_wrapper.GymWrapper._create_observation_space') as mock_obs, \
             patch('l4_gym.env_wrapper.GymWrapper._create_action_space') as mock_act:
            mock_obs.return_value = {'visual': np.zeros((64, 64)), 'vector': np.zeros(32)}
            mock_act.return_value = {'high_level': ['attack', 'move']}
            
            env = GymWrapper(seed=42)
            env.reset()
            
            # Close should not raise exception
            try:
                env.close()
            except Exception as e:
                pytest.fail(f"Close raised unexpected exception: {e}")


class TestL4Integration:
    """Integration tests for L4 components."""
    
    def test_observation_action_compatibility(self):
        """Test that observations and actions are compatible."""
        obs_space = ObservationSpace()
        action_space = ActionSpace()
        
        # Create observation
        obs = obs_space.create_observation(
            character_state={'hp': 100, 'max_hp': 100},
            enemy_states=[],
            environment={}
        )
        
        assert obs is not None
        
        # Create valid action
        action = action_space.create_action(
            high_level='attack',
            low_level={'dx': 0, 'dy': 1}
        )
        
        assert action is not None
        assert action_space.validate_action(action) is True
    
    def test_reward_observation_consistency(self):
        """Test that rewards align with observations."""
        obs_space = ObservationSpace()
        reward_calc = RewardShaper()
        
        # Create observation
        obs = obs_space.create_observation(
            character_state={'hp': 100, 'max_hp': 100},
            enemy_states=[{'hp': 50}],
            environment={}
        )
        
        # Calculate reward based on combat
        reward_info = {
            'damage_dealt': 10.0,
            'damage_taken': 0.0,
            'enemy_killed': False,
            'progress_delta': 0.0,
            'survived': True,
        }
        
        reward = reward_calc.compute_reward(reward_info)
        
        # Reward should be finite and reasonable
        assert np.isfinite(reward)
        assert abs(reward) < 1000.0  # Sanity check
    
    def test_full_episode_simulation(self):
        """Simulate a full episode with all L4 components."""
        obs_space = ObservationSpace()
        action_space = ActionSpace()
        reward_calc = RewardShaper()
        
        # Simulate episode
        max_steps = 100
        total_reward = 0.0
        
        for step in range(max_steps):
            # Generate observation
            obs = obs_space.create_observation(
                character_state={'hp': 100 - step, 'max_hp': 100},
                enemy_states=[{'hp': max(0, 50 - step)}],
                environment={}
            )
            
            # Select action
            action = action_space.create_action(
                high_level='attack',
                low_level={'dx': 0, 'dy': 1}
            )
            assert action_space.validate_action(action)
            
            # Calculate reward
            reward_info = {
                'damage_dealt': np.random.uniform(0, 20),
                'damage_taken': np.random.uniform(0, 10),
                'enemy_killed': np.random.random() < 0.1,
                'progress_delta': np.random.uniform(-2, 2),
                'survived': True,
            }
            
            reward = reward_calc.compute_reward(reward_info)
            total_reward += reward
            
            # Check termination condition
            if reward_info['enemy_killed']:
                break
        
        # Episode should produce finite total reward
        assert np.isfinite(total_reward)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
