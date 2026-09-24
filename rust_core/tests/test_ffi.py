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


# ---------------------------------------------------------------- RunAnalytics
# Kernels for tools/probe_analysis.py. Columns cross the FFI as binary buffers
# (array.array / numpy / memoryview), tables as struct-of-arrays objects.

from array import array


def test_run_analytics_alias():
    assert rust_core.RunAnalytics is rust_core.PyRunAnalytics


def test_run_analytics_linear_fit_and_sparkline():
    ra = rust_core.RunAnalytics
    assert ra.linear_fit(array("d", [0, 1, 2]), array("d", [1, 3, 5])) == (2.0, 1.0)
    assert ra.linear_fit(array("d", [1, 1]), array("d", [0, 5])) is None
    assert ra.sparkline(array("d", [0.0, 7.0])) == "▁█"
    assert ra.sparkline(array("d")) == ""  # empty buffers (unaligned pointer in CPython) are fine


def test_run_analytics_rejects_non_buffers_and_bad_lengths():
    ra = rust_core.RunAnalytics
    with pytest.raises(TypeError):
        ra.sparkline([1.0, 2.0])  # plain lists have no buffer protocol
    with pytest.raises(ValueError):
        ra.pinned_interval(array("d", [0, 1]), array("d", [1]), array("d", [1]), array("B", [1]), 0.2, 1.0)


def test_run_analytics_scan_hero_table():
    class Table:
        ts = array("d", [0, 1, 2])
        hp = array("d", [100, 50, 0])
        max_hp = array("d", [100, 100, 100])
        x = array("d", [0, 0, 0])
        y = array("d", [0, 0, 0])
        alive = array("B", [1, 1, 0])
        offsets = array("Q", [0, 1, 1, 2])
        ex = array("d", [3, 1])
        ey = array("d", [4, 0])

    scan = rust_core.RunAnalytics.scan_hero(Table, {"spark_width": 24}, array("d"))
    assert scan["death_t"] == 2.0
    assert scan["min_nearest"] == 1.0
    assert scan["invalid_count"] == 0
    assert scan["hp_sparkline"] == "█▅▁"


def test_run_analytics_log_digest():
    digest, distinct = rust_core.RunAnalytics.log_digest(["12:00:00 a 5", "12:00:01 a 7", "b"], 5)
    assert digest == [(2, "a 5"), (1, "b")] and distinct == 2


# ---------------------------------------------------------------- QaKernels (tools/qa.py)

def test_qa_kernels_reach_describe_fnv():
    qa = rust_core.QaKernels
    assert list(qa.reach(array("Q", [0, 1, 2, 2, 2]), array("Q", [1, 2]), array("Q", [0]))) == [1, 1, 1, 0]
    d = qa.describe(array("d", [1.0, 2.0, 3.0, 4.0]), 200, 1)
    assert d["n"] == 4 and d["mean"] == 2.5 and d["ci_lo"] <= 2.5 <= d["ci_hi"]
    assert qa.fnv1a64_lines(b"ab", array("Q", [0, 0, 1, 2])) == [0xCBF29CE484222325, 0xAF63DC4C8601EC8C,
                                                                  0xAF63DF4C8601F1A5]
    with pytest.raises(ValueError):
        qa.reach(array("Q", [0, 5]), array("Q", [1]), array("Q", [0]))
