"""
Python Layer for AI Evolve

Layers:
- L7: Render (Panda3D rendering, scene editor)
- L6: Curriculum (agent evaluation, advisor)
- L5: Training (PyTorch, PPO, self-play)
- L4: Gym Wrapper (Python ↔ Rust interface)
"""

__version__ = "0.1.0"

# Lazy imports to avoid circular dependencies
def __getattr__(name):
    if name == "GymWrapper":
        from .l4_gym import GymWrapper
        return GymWrapper
    elif name == "PPOTrainer":
        from .l5_training import PPOTrainer
        return PPOTrainer
    elif name == "Evaluator":
        from .l6_curriculum import Evaluator
        return Evaluator
    elif name == "SceneEditor":
        from .l7_render import SceneEditor
        return SceneEditor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "GymWrapper",
    "PPOTrainer",
    "Evaluator",
    "SceneEditor",
]
