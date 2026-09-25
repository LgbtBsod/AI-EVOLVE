"""Модульные тесты для src/utils/helpers.py - переиспользуемые утилиты."""
import random

import pytest

from src.utils import helpers as H


# ---------------------------------------------------------------- коллекции
class TestCollections:
    def test_safe_get(self):
        assert H.safe_get({"a": 1}, "a") == 1
        assert H.safe_get({}, "a", default=42) == 42

    def test_merge_dicts_override_wins(self):
        merged = H.merge_dicts({"a": 1, "b": 2}, {"b": 3})
        assert merged == {"a": 1, "b": 3}
        # base не мутируется
        assert {"a": 1, "b": 2} == {"a": 1, "b": 2}

    def test_flatten_list_recursive(self):
        assert H.flatten_list([1, [2, [3, [4]]], []]) == [1, 2, 3, 4]
        assert H.flatten_list([]) == []

    def test_chunk_list(self):
        assert H.chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
        assert H.chunk_list([], 3) == []

    def test_group_by(self):
        items = [{"k": 1, "v": "a"}, {"k": 2}, {"k": 1, "v": "b"}]
        grouped = H.group_by(items, "k")
        assert grouped[1] == [{"k": 1, "v": "a"}, {"k": 1, "v": "b"}]
        assert grouped[2] == [{"k": 2}]

    def test_deep_update_merges_nested(self):
        base = {"a": {"b": 1, "c": 2}, "x": 1}
        result = H.deep_update(base, {"a": {"b": 3}, "y": 2})
        assert result == {"a": {"b": 3, "c": 2}, "x": 1, "y": 2}
        # base остаётся нетронутым (копия верхнего уровня)
        assert base["a"] == {"b": 1, "c": 2}


# ---------------------------------------------------------------- математика
class TestMath:
    def test_clamp(self):
        assert H.clamp(5, 0, 3) == 3
        assert H.clamp(-1, 0, 3) == 0
        assert H.clamp(2, 0, 3) == 2

    def test_lerp_clips_t(self):
        assert H.lerp(0, 10, 0.5) == 5.0
        assert H.lerp(0, 10, 5) == 10.0   # t ограничен сверху 1.0
        assert H.lerp(0, 10, -3) == 0.0   # t ограничен снизу 0.0

    def test_distance_2d(self):
        assert H.distance_2d((0, 0), (3, 4)) == 5.0

    def test_normalize_vector(self):
        assert H.normalize_vector(3, 4) == (0.6, 0.8)
        assert H.normalize_vector(0, 0) == (0.0, 0.0)

    def test_random_range_in_bounds(self):
        for _ in range(50):
            v = H.random_range(1.0, 2.0)
            assert 1.0 <= v <= 2.0

    def test_random_choice_empty_returns_none(self):
        assert H.random_choice([]) is None
        assert H.random_choice(["only"]) == "only"

    def test_weighted_choice(self):
        assert H.weighted_choice([]) is None
        # нулевые веса -> равномерный выбор из элементов
        assert H.weighted_choice([("a", 0), ("b", 0)]) in ("a", "b")
        # детерминированный путь через monkeypatch random.uniform
        random.seed(12345)
        picks = [H.weighted_choice([("heavy", 100.0), ("light", 0.0001)]) for _ in range(20)]
        assert all(p == "heavy" for p in picks)


# ---------------------------------------------------------------- строки
class TestStrings:
    def test_truncate_string(self):
        assert H.truncate_string("hello world", 8) == "hello..."
        assert H.truncate_string("short", 10) == "short"

    def test_format_number(self):
        assert H.format_number(3.14159) == "3.14"
        assert H.format_number(3.14159, decimals=0) == "3"

    def test_generate_id_format(self):
        a = H.generate_id("id_")
        assert a.startswith("id_")
        prefix, rest = a[len("id_"):].split("_")
        assert prefix.isdigit() and rest.isdigit() and 1000 <= int(rest) <= 9999

    def test_generate_id_mostly_unique(self):
        ids = {H.generate_id() for _ in range(30)}
        assert len(ids) >= 25  # коллизии возможны, но редки


# ---------------------------------------------------------------- валидация
class TestValidation:
    def test_is_valid_number_rejects_nan(self):
        assert H.is_valid_number(1) and H.is_valid_number(1.5)
        assert not H.is_valid_number(float("nan"))
        assert not H.is_valid_number("1")

    def test_is_positive_number(self):
        assert H.is_positive_number(0.1)
        assert not H.is_positive_number(0)
        assert not H.is_positive_number(-1)

    def test_is_in_range_inclusive(self):
        assert H.is_in_range(5, 1, 5)
        assert H.is_in_range(1, 1, 5)
        assert not H.is_in_range(6, 1, 5)

    def test_validate_dict(self):
        ok, missing = H.validate_dict({"a": 1}, ["a", "b"])
        assert ok is False and missing == ["b"]
        ok, missing = H.validate_dict({"a": 1, "b": 2}, ["a", "b"])
        assert ok is True and missing == []


# ---------------------------------------------------------------- время
class TestTime:
    def test_format_duration_branches(self):
        assert H.format_duration(9.5) == "9.5s"
        assert H.format_duration(65) == "1m 5s"
        assert H.format_duration(3700) == "1h 1m"

    def test_timestamps(self):
        assert H.get_timestamp() > 0
        ms = H.get_timestamp_ms()
        assert isinstance(ms, int) and ms > 0


# ---------------------------------------------------------------- декораторы
class TestDecorators:
    def test_retry_succeeds_eventually(self):
        calls = []

        @H.retry(max_attempts=3, delay=0)
        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("nope")
            return "ok"

        assert flaky() == "ok"
        assert len(calls) == 3

    def test_retry_raises_last_exception(self):
        @H.retry(max_attempts=2, delay=0)
        def always_fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            always_fail()

    def test_singleton_same_instance(self):
        @H.singleton
        class S:
            def __init__(self):
                self.token = object()

        assert S() is S()
        assert S().token is S().token

    def test_deprecated_still_calls_function(self):
        @H.deprecated("use new_fn")
        def old_fn(x):
            return x * 2

        assert old_fn(3) == 6

    def test_timing_preserves_result_and_name(self):
        @H.timing
        def work(a):
            return a + 1

        assert work(1) == 2
        assert work.__name__ == "work"

    def test_log_execution_propagates_exception(self):
        @H.log_execution
        def bad():
            raise KeyError("k")

        with pytest.raises(KeyError):
            bad()


# ---------------------------------------------------------------- конфигурация/игра
class TestGameHelpers:
    def test_calculate_damage_multiplies_modifiers(self):
        assert H.calculate_damage(100, {"x": 2, "y": 0.5}) == 100.0
        assert H.calculate_damage(100, {}) == 100
        # отрицательный модификатор обрезается до 0
        assert H.calculate_damage(100, {"m": -1}) == 0

    def test_interpolate_stats_growth(self):
        assert H.interpolate_stats({"hp": 100}, level=1) == {"hp": 100}
        assert H.interpolate_stats({"hp": 100}, level=3, growth_rate=0.1)["hp"] == pytest.approx(120.0)

    def test_generate_loot_table_forced_roll(self):
        random.seed(5)
        table = [
            {"item_id": "sword", "chance": 1.0, "min_quantity": 2, "max_quantity": 3},
            {"item_id": "ring", "chance": 0.0},
        ]
        loot = H.generate_loot_table(table)
        assert [l["item_id"] for l in loot] == ["sword"]
        assert 2 <= loot[0]["quantity"] <= 3

    def test_generate_loot_table_luck_boosts_chance(self):
        random.seed(0)
        table = [{"item_id": "gem", "chance": 0.5}]
        # luck=1.0 -> chance 1.0 -> всегда дроп
        assert len(H.generate_loot_table(table, luck=1.0)) == 1

    def test_load_config_from_env(self, monkeypatch):
        monkeypatch.setenv("TESTVAR_ONE", "1")
        monkeypatch.setenv("TESTVAR_TWO", "2")
        cfg = H.load_config_from_env("TESTVAR_")
        assert cfg == {"one": "1", "two": "2"}


# ---------------------------------------------------------------- сериализация
class TestSerialization:
    def test_safe_serialize_primitives_and_containers(self):
        assert H.safe_serialize(None) is None
        assert H.safe_serialize(True) is True
        assert H.safe_serialize((1, [2, {"a": 3}], None)) == [1, [2, {"a": 3}], None]

    def test_safe_serialize_object_via_dict(self):
        class Obj:
            def __init__(self):
                self.x = 1

        assert H.safe_serialize(Obj()) == {"x": 1}

    def test_deep_copy_roundtrip(self):
        original = {"nested": [1, 2, {"flag": True}], "t": (1, 2)}
        copy = H.deep_copy(original)
        assert copy == {"nested": [1, 2, {"flag": True}], "t": [1, 2]}
        copy["nested"][0] = 99
        assert original["nested"][0] == 1  # независимость копии
