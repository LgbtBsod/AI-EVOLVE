#!/usr/bin/env python3
"""
Unit Tests for Advanced Toughness Plugin

Tests the new toughness system with:
- Stance states (NORMAL, WEAKENED, BROKEN, RECOVERING)
- Elemental effectiveness
- Cumulative max toughness increase on break
- Damage multipliers based on stance state
"""

import pytest
import time
from ai_evolve.features.toughness.toughness_plugin import (
    ToughnessPlugin,
    ToughnessComponent,
    ToughnessConfig,
    ToughnessBreakEvent,
    ToughnessRecoveryEvent,
    StanceState,
    ELEMENTAL_EFFECTIVENESS
)


class TestToughnessConfig:
    """Test ToughnessConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ToughnessConfig()
        assert config.max_toughness == 100.0
        assert config.recovery_rate == 10.0
        assert config.recovery_delay == 3.0
        assert config.break_duration == 5.0
        assert config.damage_taken_multiplier_broken == 0.25
        assert config.toughness_from_hp_ratio == 0.05
        assert config.max_toughness_cap_ratio == 0.2
        assert config.auto_recover_on_break_end is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = ToughnessConfig(
            max_toughness=200.0,
            recovery_rate=20.0,
            break_duration=10.0
        )
        assert config.max_toughness == 200.0
        assert config.recovery_rate == 20.0
        assert config.break_duration == 10.0


class TestToughnessComponentBasic:
    """Basic tests for ToughnessComponent."""
    
    @pytest.fixture
    def component(self):
        """Create a basic toughness component."""
        config = ToughnessConfig()
        comp = ToughnessComponent("test_entity", config, max_health=500.0)
        yield comp
    
    def test_initialization(self, component):
        """Test component initialization."""
        assert component.entity_id == "test_entity"
        assert component.current_toughness == 100.0
        assert component.max_toughness == 100.0
        assert component.state == StanceState.NORMAL
        assert component.break_count == 0
        assert not component.is_broken
    
    def test_damage_multiplier_normal(self, component):
        """Test damage multiplier in normal state."""
        assert component.damage_multiplier == 1.0
    
    def test_reset(self, component):
        """Test component reset."""
        component.take_toughness_damage(50.0)
        assert component.current_toughness == 50.0
        
        component.reset()
        assert component.current_toughness == 100.0
        assert component.break_count == 0
        assert component.state == StanceState.NORMAL


class TestToughnessDamage:
    """Tests for toughness damage mechanics."""
    
    @pytest.fixture
    def component(self):
        config = ToughnessConfig()
        return ToughnessComponent("test", config, max_health=500.0)
    
    def test_basic_damage(self, component):
        """Test basic toughness damage."""
        result = component.take_toughness_damage(30.0)
        assert result == 30.0
        assert component.current_toughness == 70.0
    
    def test_damage_cannot_exceed_current(self, component):
        """Test that damage cannot reduce toughness below 0."""
        component.take_toughness_damage(150.0)
        assert component.current_toughness == 0.0
    
    def test_zero_damage(self, component):
        """Test zero damage."""
        result = component.take_toughness_damage(0.0)
        assert result == 0.0
        assert component.current_toughness == 100.0
    
    def test_no_damage_when_broken(self, component):
        """Test that no damage is applied when already broken."""
        component.take_toughness_damage(200.0)  # Break
        assert component.state == StanceState.BROKEN
        
        result = component.take_toughness_damage(50.0)
        assert result == 0.0
        assert component.current_toughness == 0.0


class TestToughnessStates:
    """Tests for stance state transitions."""
    
    @pytest.fixture
    def component(self):
        config = ToughnessConfig()
        return ToughnessComponent("test", config, max_health=500.0)
    
    def test_weakened_state(self, component):
        """Test transition to WEAKENED state (below 25%)."""
        component.take_toughness_damage(76.0)  # Remaining: 24%
        assert component.state == StanceState.WEAKENED
        assert component.damage_multiplier == 1.125  # +12.5%
    
    def test_weakened_not_triggered_above_25(self, component):
        """Test that WEAKENED is not triggered at exactly 25%."""
        component.take_toughness_damage(75.0)  # Remaining: exactly 25%
        assert component.state == StanceState.NORMAL
    
    def test_broken_state_triggers(self, component):
        """Test transition to BROKEN state."""
        component.take_toughness_damage(100.0)
        assert component.state == StanceState.BROKEN
        assert component.is_broken
        assert component.break_count == 1
    
    def test_broken_damage_multiplier(self, component):
        """Test damage multiplier in BROKEN state."""
        component.take_toughness_damage(100.0)
        assert component.damage_multiplier == 1.25  # +25%


class TestElementalEffectiveness:
    """Tests for elemental effectiveness system."""
    
    @pytest.fixture
    def component(self):
        config = ToughnessConfig()
        return ToughnessComponent("test", config, max_health=500.0)
    
    def test_universal_type(self, component):
        """Test universal type pierces everything."""
        result = component.take_toughness_damage(
            50.0,
            toughness_type="universal",
            enemy_toughness_type="physical"
        )
        assert result == 50.0  # 1.0 multiplier
    
    def test_fire_vs_ice(self, component):
        """Test fire vs ice (2.0 effectiveness)."""
        result = component.take_toughness_damage(
            50.0,
            toughness_type="fire",
            enemy_toughness_type="ice"
        )
        assert result == 100.0  # 2.0 multiplier
    
    def test_ice_vs_fire(self, component):
        """Test ice vs fire (0.5 effectiveness)."""
        result = component.take_toughness_damage(
            50.0,
            toughness_type="ice",
            enemy_toughness_type="fire"
        )
        assert result == 25.0  # 0.5 multiplier
    
    def test_quantum_vs_imaginary(self, component):
        """Test quantum vs imaginary (0.5 effectiveness)."""
        result = component.take_toughness_damage(
            50.0,
            toughness_type="quantum",
            enemy_toughness_type="imaginary"
        )
        assert result == 25.0  # 0.5 multiplier


class TestToughnessBreakMechanics:
    """Tests for break progression mechanics."""
    
    @pytest.fixture
    def component(self):
        config = ToughnessConfig(
            max_toughness=100.0,
            toughness_from_hp_ratio=0.05,  # 5% per break
            max_toughness_cap_ratio=0.2     # Max 20% of HP
        )
        return ToughnessComponent("test", config, max_health=500.0)
    
    def test_break_increases_count(self, component):
        """Test that break increases break count."""
        component.take_toughness_damage(100.0)
        assert component.break_count == 1
    
    def test_break_increases_max_toughness(self, component):
        """Test that break increases max toughness from HP."""
        initial_max = component.max_toughness
        component.take_toughness_damage(100.0)
        
        # Bonus = 500 HP * 0.05 = 25
        expected_new_max = initial_max + 25.0
        assert component.max_toughness == expected_new_max
    
    def test_break_max_cap(self, component):
        """Test that max toughness is capped at 20% of HP."""
        # Break multiple times
        for i in range(6):
            component.take_toughness_damage(200.0)
            # Wait for break to end (simulated)
            component._break_start_time -= 10.0  # Fake time passing
            component.update(0.1)
        
        # Max = base + (500 * 0.2) = 100 + 100 = 200
        max_allowed = 100.0 + (500.0 * 0.2)
        assert component.max_toughness <= max_allowed


class TestToughnessRecovery:
    """Tests for toughness recovery mechanics."""
    
    @pytest.fixture
    def component(self):
        config = ToughnessConfig(
            recovery_rate=10.0,
            recovery_delay=1.0,
            break_duration=0.5  # Short break for testing
        )
        return ToughnessComponent("test", config, max_health=500.0)
    
    def test_recovery_delay(self, component):
        """Test recovery delay after damage."""
        component.take_toughness_damage(50.0)
        
        # Immediately update - should not recover yet
        component.update(0.5)
        assert component.current_toughness == 50.0
    
    def test_full_recovery_after_break(self, component):
        """Test full recovery after break ends."""
        component.take_toughness_damage(100.0)
        assert component.current_toughness == 0.0
        
        # Wait for break to end
        time.sleep(0.6)
        component.update(0.1)
        
        # Should be fully recovered
        assert component.current_toughness == component.max_toughness
        assert component.state == StanceState.NORMAL


class TestToughnessPlugin:
    """Tests for ToughnessPlugin integration."""
    
    def test_plugin_lifecycle(self):
        """Test plugin lifecycle."""
        plugin = ToughnessPlugin()
        
        assert not plugin.is_initialized
        plugin.initialize()  # Use initialize() which sets the flag
        assert plugin.is_initialized
        
        plugin.on_update(0.016)
        
        plugin.shutdown()
        assert not plugin.is_initialized
        assert len(plugin.components) == 0
    
    def test_create_component(self):
        """Test creating components through plugin."""
        plugin = ToughnessPlugin()
        plugin.on_init()
        
        component = plugin.create_component("entity1", max_health=200.0)
        assert component.entity_id == "entity1"
        assert component.max_toughness == 100.0
        
        # Getting same component returns existing
        component2 = plugin.get_component("entity1")
        assert component is component2
        
        plugin.on_shutdown()
    
    def test_plugin_config(self):
        """Test plugin configuration."""
        plugin = ToughnessPlugin()
        config = plugin.get_config()
        
        assert "default_max_toughness" in config
        assert "recovery_rate" in config
        assert "break_duration" in config
        assert config["active_components"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
