"""Модульные тесты для src/core/rng_manager.py - детерминированный RNG."""
import random

import pytest

from src.core.rng_manager import (
    RNGConfig,
    RNGManager,
    get_default_rng,
    reset_default_rng,
    set_default_rng,
)


class TestDeterminism:
    def test_same_seed_same_sequence(self):
        a = RNGManager(RNGConfig(seed=123))
        b = RNGManager(RNGConfig(seed=123))
        assert [a.random() for _ in range(10)] == [b.random() for _ in range(10)]

    def test_matches_stdlib_random(self):
        mgr = RNGManager(RNGConfig(seed=42))
        ref = random.Random(42)
        assert [mgr.random() for _ in range(5)] == [ref.random() for _ in range(5)]

    def test_reseed_restarts_sequence(self):
        mgr = RNGManager(RNGConfig(seed=7))
        first = [mgr.random() for _ in range(3)]
        mgr.reseed(7)
        assert [mgr.random() for _ in range(3)] == first
        assert mgr._config.seed == 7

    def test_reset_uses_original_seed(self):
        mgr = RNGManager(RNGConfig(seed=99))
        before = mgr.random()
        for _ in range(10):
            mgr.random()
        mgr.reset()
        assert mgr.random() == before

    def test_non_deterministic_mode_differs(self):
        a = RNGManager(RNGConfig(use_deterministic=False))
        b = RNGManager(RNGConfig(use_deterministic=False))
        # теоретически возможны совпадения, но 8 float из разных Random() почти наверняка различаются
        assert [a.random() for _ in range(8)] != [b.random() for _ in range(8)]


class TestDistributions:
    def test_randint_inclusive_bounds(self):
        mgr = RNGManager(RNGConfig(seed=1))
        values = {mgr.randint(1, 6) for _ in range(200)}
        assert values == set(range(1, 7))

    def test_uniform_range(self):
        mgr = RNGManager(RNGConfig(seed=2))
        for _ in range(100):
            assert 5.0 <= mgr.uniform(5.0, 10.0) <= 10.0

    def test_choice_matches_reference_stream(self):
        seq = ["a", "b", "c", "d"]
        mgr = RNGManager(RNGConfig(seed=5))
        ref = random.Random(5)
        assert [mgr.choice(seq) for _ in range(10)] == [ref.choice(seq) for _ in range(10)]

    def test_choice_empty_raises(self):
        with pytest.raises(ValueError):
            RNGManager().choice([])

    def test_choices_weights_and_k(self):
        mgr = RNGManager(RNGConfig(seed=3))
        out = mgr.choices(["x", "y"], weights=[1000, 0], k=5)
        assert out == ["x"] * 5
        assert len(mgr.choices([1, 2, 3], k=7)) == 7

    def test_sample_unique_count(self):
        mgr = RNGManager(RNGConfig(seed=4))
        s = mgr.sample(range(100), 10)
        assert len(s) == len(set(s)) == 10

    def test_shuffle_permutation(self):
        mgr = RNGManager(RNGConfig(seed=6))
        lst = list(range(10))
        mgr.shuffle(lst)
        assert sorted(lst) == list(range(10))

    def test_randrange_step(self):
        mgr = RNGManager(RNGConfig(seed=8))
        assert mgr.randrange(10) in range(10)
        assert mgr.randrange(0, 10, 2) in range(0, 10, 2)

    def test_gauss_returns_float(self):
        mgr = RNGManager(RNGConfig(seed=9))
        v = mgr.gauss(0.0, 1.0)
        assert isinstance(v, float)


class TestRandBool:
    def test_zero_chance_always_false(self):
        mgr = RNGManager(RNGConfig(seed=1))
        assert not any(mgr.randbool(0.0) for _ in range(50))

    def test_one_chance_always_true(self):
        mgr = RNGManager(RNGConfig(seed=1))
        assert all(mgr.randbool(1.0) for _ in range(50))

    def test_half_chance_reasonable(self):
        mgr = RNGManager(RNGConfig(seed=123))
        hits = sum(mgr.randbool(0.5) for _ in range(1000))
        assert 400 <= hits <= 600


class TestStateAndClone:
    def test_state_roundtrip(self):
        mgr = RNGManager(RNGConfig(seed=11))
        state = mgr.state
        a = mgr.random()
        mgr.state = state
        assert mgr.random() == a

    def test_clone_continues_same_stream(self):
        mgr = RNGManager(RNGConfig(seed=12))
        clone = mgr.clone()
        assert clone.random() == mgr.random()
        assert clone is not mgr


class TestCryptoSafe:
    def test_crypto_safe_produces_valid_values(self):
        mgr = RNGManager(RNGConfig(crypto_safe=True))
        assert 0.0 <= mgr.random() < 1.0
        assert mgr.randint(1, 6) in range(1, 7)
        assert mgr.choice([1, 2, 3]) in (1, 2, 3)
        assert len(mgr.sample([1, 2, 3, 4], 2)) == 2
        lst = [1, 2, 3]
        mgr.shuffle(lst)
        assert sorted(lst) == [1, 2, 3]
        assert mgr.randrange(5) in range(5)
        assert mgr.randrange(0, 10, 2) in range(0, 10, 2)


class TestGlobalSingleton:
    def setup_method(self):
        self._saved = get_default_rng()

    def teardown_method(self):
        set_default_rng(self._saved)

    def test_get_default_is_singleton(self):
        assert get_default_rng() is get_default_rng()

    def test_reset_default_changes_seed(self):
        reset_default_rng(7)
        d = get_default_rng()
        assert d.random() == random.Random(7).random()

    def test_set_default_overrides(self):
        custom = RNGManager(RNGConfig(seed=555))
        set_default_rng(custom)
        assert get_default_rng() is custom
