"""
Python Layer Tests - __init__.py

Test suite for the Python layer of AI-EVOLVE project.
Tests L4-L7 components after refactoring from monolithic architecture.
"""

__version__ = "1.0.0"
__author__ = "AI Core Developer"

# Test categories
TEST_CATEGORIES = {
    "l4_gym": "Gym wrapper, observation spaces, action spaces, rewards",
    "l5_training": "PPO trainer, checkpoints, batch inference, self-play",
    "l6_curriculum": "Curriculum learning, difficulty progression",
    "l7_render": "Rendering, camera, UI overlays",
    "integration": "Cross-layer integration tests",
}

# Required dependencies for testing
TEST_DEPENDENCIES = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "numpy>=1.24.0",
    "gymnasium>=0.28.0",
    "torch>=2.0.0",
]
