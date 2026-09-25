"""Модульные тесты для src/features/cc_system.py - Stagger / Break / контроль."""
import pytest

from src.features.cc_system import (
    BreakState,
    CCEffect,
    CCType,
    CharacterCCStats,
    StaggerBar,
    StatusEffectManager,
)


def make_manager(**stat_kwargs):
    defaults = {"stagger_max": 500.0, "stagger_regen": 10.0}
    defaults.update(stat_kwargs)
    return StatusEffectManager(CharacterCCStats(**defaults))


class TestStaggerBar:
    def test_accumulates_until_break(self):
        bar = StaggerBar(current=0.0, max_stagger=100.0)
        assert bar.add_damage(60) is False
        assert bar.current == 60.0
        assert bar.add_damage(40) is True          # ровно на границе -> break
        assert bar.current == 100.0                # не переполняется

    def test_resist_multiplier_scales_incoming(self):
        bar = StaggerBar(current=0.0, max_stagger=100.0, stagger_resist_mult=0.5)
        assert bar.add_damage(150) is False        # 150*0.5 = 75
        assert bar.current == 75.0

    def test_reset(self):
        bar = StaggerBar(current=42.0, max_stagger=100.0)
        bar.reset()
        assert bar.current == 0.0

    def test_break_duration_formula(self):
        # 0.5 + (max/50)*0.1
        assert StaggerBar(current=0, max_stagger=500).get_break_duration() == pytest.approx(1.5)
        assert StaggerBar(current=0, max_stagger=1000).get_break_duration() == pytest.approx(2.5)
        # резист длительности умножает
        bar = StaggerBar(current=0, max_stagger=500, break_duration_resist=0.5)
        assert bar.get_break_duration() == pytest.approx(0.75)


class TestCCEffectTick:
    def test_tick_expires(self):
        eff = CCEffect(type=CCType.STUN, duration=1.0, remaining=1.0, source_id="x")
        assert eff.tick(0.5) is False
        assert eff.remaining == pytest.approx(0.5)
        assert eff.tick(0.5) is True               # ровно истёк


class TestBreakFlow:
    def test_break_triggers_and_clears_effects(self):
        m = make_manager(stagger_max=100.0, stagger_regen=0.0)
        m.apply_cc(CCType.SLOW, 5.0)
        assert len(m.active_effects) == 1
        m.take_stagger_damage(100)
        assert m.break_state == BreakState.BROKEN
        # формула: 0.5 + (max_stagger/50)*0.1 = 0.5 + 0.2 = 0.7
        assert m.break_timer == pytest.approx(0.7)
        assert m.active_effects == []               # брейк снимает мелкие контроли
        assert m.stagger.current == 0.0             # шкала сброшена

    def test_cc_ignored_while_broken(self):
        m = make_manager(stagger_max=100.0, stagger_regen=0.0)
        m.take_stagger_damage(100)
        m.apply_cc(CCType.STUN, 3.0)
        assert m.active_effects == []               # отдельный таймер не создаётся
        assert m.get_current_status() == CCType.STUN  # но брейк сам ведёт себя как стан

    def test_no_stagger_damage_while_broken(self):
        m = make_manager(stagger_max=100.0, stagger_regen=0.0)
        m.take_stagger_damage(100)
        timer_at_break = m.break_timer
        m.take_stagger_damage(50)                   # уже сломлен - игнор
        assert m.break_timer == timer_at_break
        assert m.stagger.current == 0.0

    def test_break_ends_after_timer(self):
        m = make_manager(stagger_max=100.0, stagger_regen=0.0)
        m.take_stagger_damage(100)
        m.update(m.break_timer + 0.01)
        assert m.break_state == BreakState.NORMAL


class TestDamageMods:
    def test_broken_target_takes_plus_15(self):
        m = make_manager(stagger_max=100.0, stagger_regen=0.0)
        m.take_stagger_damage(100)
        assert m.take_damage_with_cc_mods(1000.0) == pytest.approx(1150.0)

    def test_cc_resist_applies_when_effected_not_broken(self):
        m = make_manager(cc_resist_flat=10.0, cc_resist_percent=0.2)
        m.apply_cc(CCType.STUN, 5.0)
        # (110 - 10) * (1 - 0.2) = 80
        assert m.take_damage_with_cc_mods(110.0) == pytest.approx(80.0)

    def test_clean_target_full_damage(self):
        m = make_manager(cc_resist_flat=10.0, cc_resist_percent=0.2)
        assert m.take_damage_with_cc_mods(110.0) == 110.0


class TestStatusesAndResists:
    def test_priority_stun_over_slow(self):
        m = make_manager()
        m.apply_cc(CCType.SLOW, 5.0)
        m.apply_cc(CCType.STUN, 1.0)
        assert m.get_current_status() == CCType.STUN
        assert m.is_cc_immobilized() is True

    def test_slow_alone_not_immobilizing(self):
        m = make_manager()
        m.apply_cc(CCType.SLOW, 5.0)
        assert m.get_current_status() == CCType.SLOW
        assert m.is_cc_immobilized() is False

    def test_no_effects_status_none(self):
        m = make_manager()
        assert m.get_current_status() is None
        assert m.is_cc_immobilized() is False

    def test_duration_resist_shortens_effect(self):
        m = make_manager(cc_duration_resist=0.5)
        m.apply_cc(CCType.SLOW, 4.0)
        assert m.active_effects[0].duration == pytest.approx(2.0)

    def test_full_resist_immune(self):
        m = make_manager(cc_duration_resist=0.0)
        m.apply_cc(CCType.STUN, 4.0)
        assert m.active_effects == []

    def test_micro_stun_sets_interrupt_flag(self):
        m = make_manager()
        m.apply_cc(CCType.MICRO_STUN, 0.2)
        assert m.is_interrupted is True
        assert m.is_cc_immobilized() is True

    def test_effects_expire_via_update(self):
        m = make_manager()
        m.apply_cc(CCType.SLOW, 1.0)
        m.update(1.01)
        assert m.active_effects == []
        assert m.get_current_status() is None

    def test_stagger_regen_decays_bar(self):
        m = make_manager(stagger_max=500.0, stagger_regen=10.0)
        m.take_stagger_damage(100)
        m.update(1.0)
        assert m.stagger.current == pytest.approx(90.0)
        m.update(20.0)                              # regen не уходит в минус
        assert m.stagger.current == 0.0

    def test_stagger_resist_stat_halves_bar_damage(self):
        m = make_manager(stagger_max=100.0, stagger_resist=0.5, stagger_regen=0.0)
        m.take_stagger_damage(150)                  # 150*0.5 = 75 < 100
        assert m.break_state == BreakState.NORMAL
        assert m.stagger.current == pytest.approx(75.0)
