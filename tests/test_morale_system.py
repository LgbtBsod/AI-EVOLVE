"""Юнит-тесты системы морали и паники (src/features/morale_system.py).

Покрывает: регистрацию юнитов, пороги состояний, модификаторы производительности,
решение о бегстве, пассивный распад/восстановление и рассылку событий MORALE_CHANGED
через внедрённую шину EventSystem.
"""
import pytest

from src.core.event_system import EventSystem
from src.features.morale_system import MoraleState, MoraleStats, MoraleSystem


@pytest.fixture()
def bus():
    return EventSystem()


@pytest.fixture()
def ms(bus):
    system = MoraleSystem(event_bus=bus)
    system.register_unit("u1", base_morale=80.0)
    return system


class TestRegistration:
    def test_register_defaults(self, ms):
        stats = ms.unit_morale["u1"]
        assert isinstance(stats, MoraleStats)
        assert stats.current_morale == 80.0
        assert stats.max_morale == 100.0
        assert stats.morale_decay == 0.5
        assert stats.morale_recovery == 1.0
        assert stats.state == MoraleState.NORMAL

    def test_register_custom_base(self, ms):
        ms.register_unit("u2", base_morale=95.0)
        # регистрация НЕ пересчитывает состояние (остается NORMAL до первого изменения)
        assert ms.unit_morale["u2"].current_morale == 95.0
        assert ms.unit_morale["u2"].state == MoraleState.NORMAL

    def test_unknown_unit_actions_are_noops(self, ms):
        ms.apply_morale_change("ghost", -50, "test")  # не должно упасть
        assert ms.get_performance_modifier("ghost") == 0.0
        assert ms.should_flee("ghost") is False


class TestStateThresholds:
    @pytest.mark.parametrize(
        "morale,expected",
        [
            (100.0, MoraleState.HEROIC),
            (90.0, MoraleState.HEROIC),   # граница включительно
            (89.99, MoraleState.HIGH),
            (65.0, MoraleState.HIGH),
            (64.99, MoraleState.NORMAL),
            (35.0, MoraleState.NORMAL),
            (34.99, MoraleState.WAVERING),
            (15.0, MoraleState.WAVERING),
            (14.99, MoraleState.PANICKED),
            (0.01, MoraleState.PANICKED),
            (0.0, MoraleState.BROKEN),
        ],
    )
    def test_thresholds(self, ms, morale, expected):
        delta = morale - ms.unit_morale["u1"].current_morale
        ms.apply_morale_change("u1", delta, "tune")
        assert ms.unit_morale["u1"].state == expected

    def test_clamp_to_max(self, ms):
        ms.apply_morale_change("u1", +999, "buff")
        assert ms.unit_morale["u1"].current_morale == 100.0

    def test_clamp_to_zero(self, ms):
        ms.apply_morale_change("u1", -999, "catastrophe")
        assert ms.unit_morale["u1"].current_morale == 0.0
        assert ms.unit_morale["u1"].state == MoraleState.BROKEN


class TestPerformanceModifier:
    @pytest.mark.parametrize(
        "state,modifier",
        [
            (MoraleState.HEROIC, 0.3),
            (MoraleState.HIGH, 0.15),
            (MoraleState.NORMAL, 0.0),
            (MoraleState.WAVERING, -0.15),
            (MoraleState.PANICKED, -0.4),
            (MoraleState.BROKEN, -0.7),
        ],
    )
    def test_modifiers(self, ms, state, modifier):
        ms.unit_morale["u1"].state = state
        assert ms.get_performance_modifier("u1") == pytest.approx(modifier)


class TestShouldFlee:
    @pytest.mark.parametrize(
        "state,flees",
        [
            (MoraleState.HEROIC, False),
            (MoraleState.HIGH, False),
            (MoraleState.NORMAL, False),
            (MoraleState.WAVERING, False),
            (MoraleState.PANICKED, True),
            (MoraleState.BROKEN, True),
        ],
    )
    def test_flee_decision(self, ms, state, flees):
        ms.unit_morale["u1"].state = state
        assert ms.should_flee("u1") is flees


class TestPassiveUpdate:
    def test_recovery_in_normal_state(self, ms):
        ms.unit_morale["u1"].state = MoraleState.NORMAL
        ms.unit_morale["u1"].current_morale = 50.0
        ms.on_update(2.0)  # recovery 1.0/s
        assert ms.unit_morale["u1"].current_morale == pytest.approx(52.0)

    def test_decay_in_low_state(self, ms):
        ms.unit_morale["u1"].state = MoraleState.WAVERING
        ms.unit_morale["u1"].current_morale = 30.0
        ms.on_update(1.0)  # decay 0.5/s
        assert ms.unit_morale["u1"].current_morale == pytest.approx(29.5)

    def test_decay_does_not_go_negative(self, ms):
        ms.unit_morale["u1"].state = MoraleState.PANICKED
        ms.unit_morale["u1"].current_morale = 0.1
        ms.on_update(10.0)
        assert ms.unit_morale["u1"].current_morale == 0.0
        assert ms.unit_morale["u1"].state == MoraleState.BROKEN

    def test_recovery_capped_at_max(self, ms):
        ms.unit_morale["u1"].state = MoraleState.HIGH
        ms.unit_morale["u1"].current_morale = 99.5
        ms.on_update(5.0)
        assert ms.unit_morale["u1"].current_morale == 100.0

    def test_low_state_decays_to_normal_boundary(self, ms):
        # WAVERING НЕ восстанавливается пассивно — декейрит на 0.5/с
        ms.unit_morale["u1"].state = MoraleState.WAVERING
        ms.unit_morale["u1"].current_morale = 34.9
        ms.on_update(1.0)
        assert ms.unit_morale["u1"].current_morale == pytest.approx(34.4)
        assert ms.unit_morale["u1"].state == MoraleState.WAVERING

    def test_high_state_recovers_into_heroic(self, ms):
        # HIGH восстанавливается и может перейти в HEROIC (>=90)
        ms.unit_morale["u1"].state = MoraleState.HIGH
        ms.unit_morale["u1"].current_morale = 89.5
        ms.on_update(1.0)  # +1.0 -> 90.5 -> HEROIC
        assert ms.unit_morale["u1"].state == MoraleState.HEROIC

    def test_abstract_on_update_delegates(self, ms):
        ms.unit_morale["u1"].state = MoraleState.NORMAL
        ms.unit_morale["u1"].current_morale = 50.0
        ms._on_update(1.0)
        assert ms.unit_morale["u1"].current_morale == pytest.approx(51.0)


class TestEventBroadcast:
    def test_event_emitted_on_state_change(self, ms, bus):
        received = []
        bus.on("MORALE_CHANGED", lambda sender, ev: received.append(ev.event_data), "t")
        ms.apply_morale_change("u1", -50, "casualties")  # 80->30: NORMAL->WAVERING
        assert len(received) == 1
        payload = received[0]
        assert payload == {
            "unit_id": "u1",
            "state": "waver",
            "morale": 30.0,
            "reason": "casualties",
        }

    def test_no_event_when_state_unchanged(self, ms, bus):
        received = []
        bus.on("MORALE_CHANGED", lambda sender, ev: received.append(ev), "t")
        ms.apply_morale_change("u1", -5, "scratch")  # 80->75, оба HIGH? нет: 75>=65 HIGH vs NORMAL
        # 80 NORMAL (не пересчитано при регистрации) -> 75 HIGH: смена есть.
        # Проверим гарантированно без смены: ещё -5 -> 70 остаётся HIGH
        n = len(received)
        ms.apply_morale_change("u1", -5, "scratch2")  # 75->70: HIGH->HIGH
        assert len(received) == n

    def test_passive_change_emits_event(self, ms, bus):
        received = []
        bus.on("MORALE_CHANGED", lambda sender, ev: received.append(ev.event_data), "t")
        ms.unit_morale["u1"].state = MoraleState.PANICKED
        ms.unit_morale["u1"].current_morale = 0.2
        ms.on_update(1.0)  # decay 0.5 -> 0.0? нет: max(0, 0.2-0.5)=0.0 -> BROKEN
        assert len(received) == 1
        assert received[0]["reason"] == "passive_change"
        assert received[0]["state"] == "broken"

    def test_works_without_event_bus(self):
        ms = MoraleSystem()  # event_bus=None — падать не должно
        ms.register_unit("solo", 80.0)
        ms.apply_morale_change("solo", -70, "ambush")  # 80->10: PANICKED
        assert ms.unit_morale["solo"].state == MoraleState.PANICKED
        ms.on_update(1.0)
