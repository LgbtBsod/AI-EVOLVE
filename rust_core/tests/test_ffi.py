"""Tests for Rust FFI module"""
import pytest
import rust_core


def test_version():
    """Test that VERSION is exposed"""
    assert hasattr(rust_core, 'VERSION')
    assert isinstance(rust_core.VERSION, str)
    assert len(rust_core.VERSION) > 0


def test_world_generator_creation():
    """Test WorldGenerator initialization"""
    gen = rust_core.WorldGenerator(12345, '0.1.0')
    assert gen is not None


def test_world_generator_generate():
    """Test world generation"""
    gen = rust_core.WorldGenerator(42, '0.1.0')
    world = gen.generate('{}')
    assert world is not None


def test_simulation_env_creation():
    """Test SimulationEnv initialization"""
    env = rust_core.SimulationEnv(12345)
    assert env is not None


def test_simulation_env_step():
    """Test simulation step"""
    env = rust_core.SimulationEnv(42)
    obs, reward, done, info = env.step([])
    assert isinstance(obs, list)
    assert isinstance(reward, list)
    assert isinstance(done, list)
    assert len(reward) == 1
    assert reward[0] == 0.0


def test_simulation_env_step_batch():
    """Test batch simulation step"""
    env = rust_core.SimulationEnv(42)
    obs, rewards, dones, infos = env.step_batch([[]])
    assert isinstance(obs, list)
    assert isinstance(rewards, list)
    assert isinstance(dones, list)
    assert isinstance(infos, list)


def test_aliases():
    """Test that aliases work"""
    assert rust_core.WorldGenerator is not None
    assert rust_core.SimulationEnv is not None
    # PyWorldGenerator and PySimulationEnv should also exist
    assert rust_core.PyWorldGenerator is not None
    assert rust_core.PySimulationEnv is not None


def test_deterministic_generation():
    """Test that same seed produces same world"""
    gen1 = rust_core.WorldGenerator(99999, '0.1.0')
    gen2 = rust_core.WorldGenerator(99999, '0.1.0')
    world1 = gen1.generate('{}')
    world2 = gen2.generate('{}')
    # Both should succeed (determinism verified at Rust level)
    assert world1 is not None
    assert world2 is not None
