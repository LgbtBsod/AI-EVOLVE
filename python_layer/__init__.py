"""
Python Layer for AI Evolve

Layers:
- L7: Player-Trainer (Panda3D rendering, scene editor)
- L6: Curriculum (agent evaluation, advisor)
- L5: Learning (PyTorch, PPO, self-play)
- L4: Gym Wrapper (Python ↔ Rust interface)
"""

__version__ = "0.1.0"

from .l4_gym import GymWrapper
from .l5_learning import PPOTrainer
from .l6_curriculum import Evaluator
from .l7_trainer import SceneEditor

__all__ = [
    "GymWrapper",
    "PPOTrainer",
    "Evaluator",
    "SceneEditor",
]
