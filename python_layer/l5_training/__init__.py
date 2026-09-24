"""
L5 - Обучение (Training Layer)

PyTorch + SB3 (PPO) обучение агентов:
- PPO trainer с batch inference
- Чекпоинты политик персонажа и врагов
- Self-play каркас
- Batch inference для врагов в рантайме
"""

from .ppo_trainer import PPOTrainer, TrainingMonitorCallback
from .checkpoint_manager import CheckpointManager, CheckpointMetadata
from .batch_inference import BatchInferenceEngine, BatchObservation, BatchActions
from .self_play import SelfPlayArena, AgentConfig, run_self_play_training

__all__ = [
    'PPOTrainer',
    'TrainingMonitorCallback',
    'CheckpointManager',
    'CheckpointMetadata',
    'BatchInferenceEngine',
    'BatchObservation',
    'BatchActions',
    'SelfPlayArena',
    'AgentConfig',
    'run_self_play_training',
]
