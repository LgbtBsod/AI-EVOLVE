"""
Test L5 Training Components

Tests for:
- PPOTrainer (Proximal Policy Optimization)
- CheckpointManager (model versioning and saving)
- BatchInference (optimized batch prediction)
- SelfPlay (self-play arena with Elo rating)
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio
import os
import tempfile
import json

# Import L5 components
import sys
sys.path.insert(0, '/workspace/python_layer')

from l5_training.ppo_trainer import PPOTrainer, TrainingConfig
from l5_training.checkpoint_manager import CheckpointManager, CheckpointInfo
from l5_training.batch_inference import BatchInferenceEngine, InferenceRequest
from l5_training.self_play import SelfPlayArena, Player, EloCalculator


class TestTrainingConfig:
    """Test training configuration."""
    
    def test_config_creation(self):
        """Test default configuration creation."""
        config = TrainingConfig()
        
        assert config.learning_rate > 0
        assert config.gamma > 0 and config.gamma <= 1
        assert config.gae_lambda > 0 and config.gae_lambda <= 1
        assert config.clip_epsilon > 0
        assert config.epochs > 0
        assert config.batch_size > 0
    
    def test_config_custom_values(self):
        """Test configuration with custom values."""
        config = TrainingConfig(
            learning_rate=0.001,
            gamma=0.99,
            gae_lambda=0.95,
            clip_epsilon=0.2,
            epochs=10,
            batch_size=64
        )
        
        assert config.learning_rate == 0.001
        assert config.gamma == 0.99
        assert config.gae_lambda == 0.95
        assert config.clip_epsilon == 0.2
        assert config.epochs == 10
        assert config.batch_size == 64


class TestPPOTrainer:
    """Test PPO trainer functionality."""
    
    @pytest.fixture
    def mock_policy_network(self):
        """Create mock policy network."""
        mock_net = Mock()
        mock_net.parameters.return_value = []
        return mock_net
    
    @pytest.fixture
    def mock_value_network(self):
        """Create mock value network."""
        mock_net = Mock()
        mock_net.parameters.return_value = []
        return mock_net
    
    def test_trainer_initialization(self, mock_policy_network, mock_value_network):
        """Test PPO trainer initialization."""
        config = TrainingConfig()
        
        trainer = PPOTrainer(
            policy_network=mock_policy_network,
            value_network=mock_value_network,
            config=config
        )
        
        assert trainer is not None
        assert trainer.config == config
    
    def test_compute_advantage(self, mock_policy_network, mock_value_network):
        """Test advantage computation."""
        config = TrainingConfig()
        trainer = PPOTrainer(
            policy_network=mock_policy_network,
            value_network=mock_value_network,
            config=config
        )
        
        # Create sample rewards and values
        rewards = np.array([1.0, 0.0, -1.0, 0.5, 0.0])
        values = np.array([0.5, 0.3, -0.2, 0.4, 0.1])
        next_value = 0.0
        
        advantages = trainer.compute_advantage(rewards, values, next_value)
        
        assert advantages is not None
        assert len(advantages) == len(rewards)
        assert np.all(np.isfinite(advantages))
    
    def test_compute_ppo_loss(self, mock_policy_network, mock_value_network):
        """Test PPO loss computation."""
        config = TrainingConfig()
        trainer = PPOTrainer(
            policy_network=mock_policy_network,
            value_network=mock_value_network,
            config=config
        )
        
        # Sample data
        old_log_probs = np.array([-0.5, -0.3, -0.7])
        advantages = np.array([1.0, 0.5, -0.5])
        
        loss = trainer.compute_ppo_loss(old_log_probs, advantages)
        
        assert loss is not None
        assert np.isfinite(loss)
        assert loss >= 0  # Loss should be non-negative
    
    def test_update_policy(self, mock_policy_network, mock_value_network):
        """Test policy update step."""
        config = TrainingConfig()
        trainer = PPOTrainer(
            policy_network=mock_policy_network,
            value_network=mock_value_network,
            config=config
        )
        
        # Create sample batch
        batch = {
            'observations': np.random.randn(10, 64).astype(np.float32),
            'actions': np.random.randint(0, 5, 10),
            'rewards': np.random.randn(10).astype(np.float32),
            'old_log_probs': np.random.randn(10).astype(np.float32),
            'values': np.random.randn(10).astype(np.float32),
        }
        
        # Update should not raise exception
        try:
            loss = trainer.update_policy(batch)
            assert loss is not None
        except Exception as e:
            pytest.fail(f"Policy update raised unexpected exception: {e}")
    
    def test_training_step(self, mock_policy_network, mock_value_network):
        """Test complete training step."""
        config = TrainingConfig()
        trainer = PPOTrainer(
            policy_network=mock_policy_network,
            value_network=mock_value_network,
            config=config
        )
        
        # Simulate collecting trajectory
        trajectory = {
            'observations': [np.random.randn(64).astype(np.float32) for _ in range(10)],
            'actions': [np.random.randint(0, 5) for _ in range(10)],
            'rewards': [np.random.randn() for _ in range(10)],
        }
        
        # Training step should not raise exception
        try:
            metrics = trainer.training_step(trajectory)
            assert isinstance(metrics, dict)
        except Exception as e:
            pytest.fail(f"Training step raised unexpected exception: {e}")


class TestCheckpointManager:
    """Test checkpoint management."""
    
    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create temporary checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_checkpoint_manager_init(self, temp_checkpoint_dir):
        """Test checkpoint manager initialization."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        
        assert manager.checkpoint_dir == temp_checkpoint_dir
        assert manager.max_checkpoints > 0
    
    def test_save_checkpoint(self, temp_checkpoint_dir):
        """Test saving checkpoint."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        
        # Create mock model state
        model_state = {'layer1.weight': np.random.randn(10, 10)}
        optimizer_state = {'param1': np.random.randn(5)}
        metrics = {'loss': 0.5, 'accuracy': 0.8}
        
        # Save checkpoint
        checkpoint_info = manager.save_checkpoint(
            model_state=model_state,
            optimizer_state=optimizer_state,
            metrics=metrics,
            episode=100
        )
        
        assert checkpoint_info is not None
        assert checkpoint_info.episode == 100
        assert os.path.exists(checkpoint_info.filepath)
    
    def test_load_checkpoint(self, temp_checkpoint_dir):
        """Test loading checkpoint."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        
        # Save first
        model_state = {'layer1.weight': np.random.randn(10, 10)}
        optimizer_state = {'param1': np.random.randn(5)}
        metrics = {'loss': 0.5}
        
        saved_info = manager.save_checkpoint(
            model_state=model_state,
            optimizer_state=optimizer_state,
            metrics=metrics,
            episode=100
        )
        
        # Load back
        loaded = manager.load_checkpoint(saved_info.filepath)
        
        assert loaded is not None
        assert 'model_state' in loaded
        assert 'optimizer_state' in loaded
        assert 'metrics' in loaded
    
    def test_get_latest_checkpoint(self, temp_checkpoint_dir):
        """Test getting latest checkpoint."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        
        # Initially no checkpoints
        latest = manager.get_latest_checkpoint()
        assert latest is None
        
        # Save some checkpoints
        for episode in [50, 100, 150]:
            manager.save_checkpoint(
                model_state={},
                optimizer_state={},
                metrics={},
                episode=episode
            )
        
        # Get latest
        latest = manager.get_latest_checkpoint()
        assert latest is not None
        assert latest.episode == 150
    
    def test_cleanup_old_checkpoints(self, temp_checkpoint_dir):
        """Test cleanup of old checkpoints."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir, max_checkpoints=2)
        
        # Save 5 checkpoints
        for episode in range(5):
            manager.save_checkpoint(
                model_state={},
                optimizer_state={},
                metrics={},
                episode=episode * 50
            )
        
        # Should only keep last 2
        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) <= 2


class TestBatchInferenceEngine:
    """Test batch inference engine."""
    
    @pytest.fixture
    def mock_model(self):
        """Create mock model for inference."""
        mock_net = Mock()
        mock_net.eval.return_value = mock_net
        return mock_net
    
    def test_inference_engine_init(self, mock_model):
        """Test inference engine initialization."""
        engine = BatchInferenceEngine(model=mock_model, batch_size=32)
        
        assert engine.batch_size == 32
        assert engine.device is not None
    
    def test_batch_prediction(self, mock_model):
        """Test batch prediction."""
        engine = BatchInferenceEngine(model=mock_model, batch_size=32)
        
        # Mock model output
        mock_output = torch.tensor(np.random.randn(32, 5))
        mock_model.return_value = mock_output
        
        # Create batch input
        batch_input = np.random.randn(32, 64).astype(np.float32)
        
        # Run inference
        predictions = engine.predict(batch_input)
        
        assert predictions is not None
        assert len(predictions) == 32
    
    def test_async_inference(self, mock_model):
        """Test asynchronous inference."""
        engine = BatchInferenceEngine(model=mock_model, batch_size=32)
        
        async def run_test():
            request = InferenceRequest(
                observations=np.random.randn(10, 64).astype(np.float32)
            )
            
            result = await engine.predict_async(request)
            return result
        
        # Run async test
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(run_test())
            assert result is not None
        finally:
            loop.close()
    
    def test_queue_management(self, mock_model):
        """Test inference queue management."""
        engine = BatchInferenceEngine(model=mock_model, batch_size=32, max_queue_size=10)
        
        # Queue should have max size
        assert engine.max_queue_size == 10
        
        # Add requests to queue
        for i in range(5):
            request = InferenceRequest(
                observations=np.random.randn(10, 64).astype(np.float32)
            )
            engine.add_to_queue(request)
        
        # Check queue size
        assert engine.queue_size() == 5


class TestSelfPlayArena:
    """Test self-play arena."""
    
    def test_arena_initialization(self):
        """Test self-play arena initialization."""
        arena = SelfPlayArena()
        
        assert arena is not None
        assert hasattr(arena, 'players')
    
    def test_player_creation(self):
        """Test player creation."""
        player = Player(
            player_id="test_player",
            elo_rating=1200,
            model_version="v1.0"
        )
        
        assert player.player_id == "test_player"
        assert player.elo_rating == 1200
        assert player.model_version == "v1.0"
    
    def test_elo_calculator(self):
        """Test Elo rating calculation."""
        calc = EloCalculator(k_factor=32)
        
        # Player A (1500) beats Player B (1400)
        new_rating_a = calc.calculate_new_rating(
            current_rating=1500,
            opponent_rating=1400,
            actual_score=1.0  # Win
        )
        
        new_rating_b = calc.calculate_new_rating(
            current_rating=1400,
            opponent_rating=1500,
            actual_score=0.0  # Loss
        )
        
        # Winner should gain rating, loser should lose
        assert new_rating_a > 1500
        assert new_rating_b < 1400
    
    def test_self_play_match(self):
        """Test running a self-play match."""
        arena = SelfPlayArena()
        
        # Add two players
        player1 = Player(player_id="agent_v1", elo_rating=1200)
        player2 = Player(player_id="agent_v2", elo_rating=1300)
        
        arena.add_player(player1)
        arena.add_player(player2)
        
        # Simulate match result
        match_result = {
            'winner': "agent_v1",
            'loser': "agent_v2",
            'reward_difference': 5.0
        }
        
        # Update ratings
        arena.update_ratings(match_result)
        
        # Check ratings updated
        p1 = arena.get_player("agent_v1")
        p2 = arena.get_player("agent_v2")
        
        assert p1.elo_rating > 1200
        assert p2.elo_rating < 1300
    
    def test_leaderboard(self):
        """Test leaderboard generation."""
        arena = SelfPlayArena()
        
        # Add multiple players with different ratings
        players = [
            Player(player_id=f"agent_{i}", elo_rating=1000 + i * 100)
            for i in range(5)
        ]
        
        for player in players:
            arena.add_player(player)
        
        # Get leaderboard
        leaderboard = arena.get_leaderboard(top_n=3)
        
        assert len(leaderboard) == 3
        # Should be sorted by rating (descending)
        assert leaderboard[0].elo_rating >= leaderboard[1].elo_rating
        assert leaderboard[1].elo_rating >= leaderboard[2].elo_rating


class TestL5Integration:
    """Integration tests for L5 components."""
    
    def test_training_with_checkpoints(self):
        """Test training loop with checkpointing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            config = TrainingConfig(epochs=1, batch_size=16)
            
            mock_policy = Mock()
            mock_policy.parameters.return_value = []
            
            mock_value = Mock()
            mock_value.parameters.return_value = []
            
            trainer = PPOTrainer(
                policy_network=mock_policy,
                value_network=mock_value,
                config=config
            )
            
            checkpoint_mgr = CheckpointManager(checkpoint_dir=tmpdir)
            
            # Simulate training
            for episode in range(5):
                # Fake training step
                trajectory = {
                    'observations': [np.random.randn(64) for _ in range(10)],
                    'actions': [np.random.randint(0, 5) for _ in range(10)],
                    'rewards': [np.random.randn() for _ in range(10)],
                }
                
                # Save checkpoint every episode
                checkpoint_mgr.save_checkpoint(
                    model_state={'episode': episode},
                    optimizer_state={},
                    metrics={'reward': np.random.randn()},
                    episode=episode
                )
            
            # Verify checkpoints exist
            checkpoints = checkpoint_mgr.list_checkpoints()
            assert len(checkpoints) > 0
    
    def test_self_play_with_inference(self):
        """Test self-play with batch inference."""
        mock_model = Mock()
        
        arena = SelfPlayArena()
        engine = BatchInferenceEngine(model=mock_model, batch_size=16)
        
        # Add player
        player = Player(player_id="test_agent", elo_rating=1200)
        arena.add_player(player)
        
        # Simulate inference for action selection
        obs = np.random.randn(1, 64).astype(np.float32)
        request = InferenceRequest(observations=obs)
        
        # Should not raise exception
        try:
            engine.add_to_queue(request)
            assert engine.queue_size() == 1
        except Exception as e:
            pytest.fail(f"Integration test failed: {e}")


# Import torch for tests that need it
try:
    import torch
except ImportError:
    torch = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
