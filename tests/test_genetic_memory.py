"""Юнит-тесты GeneticMemorySystem (Ancestral Echoes)."""
import random
import time

import pytest

from src.features.genetic_memory import GeneticMemorySystem, MemoryFragment


class Ent:
    def __init__(self, eid="hero"):
        self.id = eid


# --------------------------------------------------------------- record_milestone
class TestRecordMilestone:
    def test_below_threshold_not_recorded(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "slash", 0.69, ["combat"])
        assert gm.memory_pool == []

    def test_at_threshold_recorded(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "slash", 0.7, ["combat"])
        assert len(gm.memory_pool) == 1
        frag = gm.memory_pool[0]
        assert isinstance(frag, MemoryFragment)
        assert frag.ancestor_id == "anc"
        assert frag.skill_name == "slash"
        assert frag.potency == pytest.approx(0.7)
        assert frag.context_tags == ["combat"]

    def test_potency_clamped_to_one(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "slash", 1.5, ["x"])
        assert gm.memory_pool[0].potency == 1.0

    def test_pool_cap_drops_oldest(self):
        gm = GeneticMemorySystem(max_memories=3)
        for i in range(5):
            gm.record_milestone(f"a{i}", f"s{i}", 1.0, ["c"])
        assert len(gm.memory_pool) == 3
        # самые старые (s0, s1) выцвели
        assert [m.skill_name for m in gm.memory_pool] == ["s2", "s3", "s4"]

    def test_low_success_never_touches_cap(self):
        gm = GeneticMemorySystem(max_memories=1)
        gm.record_milestone("a", "weak", 0.1, ["c"])
        gm.record_milestone("b", "strong", 0.9, ["c"])
        assert [m.skill_name for m in gm.memory_pool] == ["strong"]


# --------------------------------------------------------------- trigger_echo
class TestTriggerEcho:
    def test_no_memories_returns_none(self):
        gm = GeneticMemorySystem()
        assert gm.trigger_echo(Ent(), ["combat"]) is None

    def test_context_mismatch_returns_none(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "fireball", 0.8, ["magic"])
        assert gm.trigger_echo(Ent(), ["nope"]) is None
        assert gm.active_echoes == {}

    def test_full_potency_always_triggers(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "fireball", 1.0, ["magic"])
        for _ in range(20):  # potency=1.0 -> random.random() > 1.0 невозможно
            bonus = gm.trigger_echo(Ent(), ["magic"])
            assert bonus is not None
            assert bonus["skill"] == "fireball"
            assert bonus["bonus_value"] == pytest.approx(0.5)  # potency * 0.5
            assert bonus["duration"] == 5.0
            assert "anc" in bonus["message"] and "fireball" in bonus["message"]

    def test_zero_potency_never_triggers(self):
        gm = GeneticMemorySystem()
        # potency ровно 0.0: random() > 0.0 почти всегда True -> нет эха
        frag = MemoryFragment("anc", "ghost", 0.0, time.perf_counter(), ["c"])
        gm.memory_pool.append(frag)
        results = [gm.trigger_echo(Ent(), ["c"]) for _ in range(50)]
        assert all(r is None for r in results)

    def test_picks_strongest_relevant_memory(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("a1", "weak_echo", 0.7, ["combat"])
        gm.record_milestone("a2", "strong_echo", 1.0, ["combat"])
        bonus = gm.trigger_echo(Ent(), ["combat"])
        assert bonus["skill"] == "strong_echo"

    def test_registers_active_echo_by_entity_id(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "skill", 1.0, ["magic"])
        gm.trigger_echo(Ent("e42"), ["magic"])
        assert "e42" in gm.active_echoes

    def test_entity_without_id_goes_to_unknown(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "skill", 1.0, ["magic"])
        gm.trigger_echo(object(), ["magic"])
        assert "unknown" in gm.active_echoes

    def test_trigger_probability_statistical(self):
        gm = GeneticMemorySystem()
        # success_rate 0.5 не проходит порог записи (0.7) -> кладём фрагмент напрямую
        gm.memory_pool.append(MemoryFragment("anc", "skill", 0.5, time.perf_counter(), ["c"]))
        random.seed(123)
        hits = sum(1 for _ in range(400) if gm.trigger_echo(Ent(), ["c"]) is not None)
        # биномиально ~200 +- шум; проверяем широкий разумный диапазон
        assert 120 <= hits <= 280


# --------------------------------------------------------------- on_update expiry
class TestEchoExpiry:
    def test_echo_expires_after_10_seconds(self, monkeypatch):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "skill", 1.0, ["c"])
        gm.trigger_echo(Ent("h"), ["c"])
        assert "h" in gm.active_echoes
        # «перематываем» время: timestamp воспоминания в прошлом на 11 секунд
        gm.active_echoes["h"].timestamp -= 11.0
        gm.on_update(0.016)
        assert gm.active_echoes == {}

    def test_fresh_echo_survives_update(self):
        gm = GeneticMemorySystem()
        gm.record_milestone("anc", "skill", 1.0, ["c"])
        gm.trigger_echo(Ent("h"), ["c"])
        gm.on_update(0.016)
        assert "h" in gm.active_echoes

    def test_internal_update_delegates(self):
        gm = GeneticMemorySystem()
        gm._on_update(0.1)  # не должна падать

    def test_on_start_does_not_crash(self):
        GeneticMemorySystem().on_start()
