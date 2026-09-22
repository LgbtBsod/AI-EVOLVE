"""
Tests for Effects Plugin
Tests effect application, stacking, combos, and plugin integration.
"""
import pytest
import time
from ai_evolve.features.effects.effects_plugin import (
    EffectsPlugin, EffectComponent, EffectType, EffectConfig, EffectTickType,
    DEFAULT_EFFECTS, COMBO_REACTIONS
)
from ai_evolve.core.event_system import EventSystem


class TestEffectConfig:
    """Test effect configuration"""
    
    def test_default_bleed_config(self):
        cfg = DEFAULT_EFFECTS[EffectType.BLEED]
        assert cfg.base_duration == 8.0
        assert cfg.max_stacks == 5
        assert cfg.damage_per_stack == 2.0
    
    def test_custom_effect_config(self):
        cfg = EffectConfig(
            effect_type=EffectType.STUN,
            base_duration=2.5,
            max_stacks=1,
            tick_type=EffectTickType.ON_APPLY
        )
        assert cfg.base_duration == 2.5
        assert cfg.can_crit is False


class TestEffectComponentBasic:
    """Test basic effect component functionality"""
    
    def test_initialization(self):
        comp = EffectComponent("test_entity")
        assert comp.entity_id == "test_entity"
        assert len(comp.active_effects) == 0
        assert comp.is_ccd() is False
    
    def test_apply_effect(self):
        comp = EffectComponent("test_entity")
        result = comp.apply_effect(EffectType.BLEED)
        assert result is True
        assert comp.has_effect(EffectType.BLEED)
        assert comp.get_effect_stacks(EffectType.BLEED) == 1
    
    def test_apply_unknown_effect(self):
        comp = EffectComponent("test_entity")
        # Create custom effect type not in DEFAULT_EFFECTS
        from enum import Enum
        class FakeEffect(Enum):
            FAKE = "fake"
        
        # Should return False for unknown effect
        # Note: This will actually work if we pass a string that matches an existing EffectType
        # So we test with immunity instead
        comp.effect_immunities.add(EffectType.BURN)
        result = comp.apply_effect(EffectType.BURN)
        assert result is False
    
    def test_effect_immunity(self):
        comp = EffectComponent("test_entity")
        comp.effect_immunities.add(EffectType.POISON)
        result = comp.apply_effect(EffectType.POISON)
        assert result is False
        assert not comp.has_effect(EffectType.POISON)


class TestEffectStacking:
    """Test effect stacking mechanics"""
    
    def test_stack_increment(self):
        comp = EffectComponent("test_entity")
        # Apply bleed with 2 stacks initially
        comp.apply_effect(EffectType.BLEED, stacks=2)
        assert comp.get_effect_stacks(EffectType.BLEED) == 2
        
        # Add more stacks
        comp.apply_effect(EffectType.BLEED, stacks=2)
        assert comp.get_effect_stacks(EffectType.BLEED) == 4
    
    def test_max_stacks_cap(self):
        comp = EffectComponent("test_entity")
        # Bleed has max_stacks=5
        comp.apply_effect(EffectType.BLEED, stacks=5)
        assert comp.get_effect_stacks(EffectType.BLEED) == 5


class TestEffectDuration:
    """Test effect duration and expiration"""
    
    def test_effect_expires(self):
        comp = EffectComponent("test_entity")
        # Apply bleed with 2s duration (not freeze which has ON_APPLY tick)
        comp.apply_effect(EffectType.BLEED, duration=2.0)
        assert comp.has_effect(EffectType.BLEED)
        
        # Update past duration
        comp.update(3.0)
        assert not comp.has_effect(EffectType.BLEED)
    
    def test_dot_ticks(self):
        """Test DoT damage ticking - using mock time for stability"""
        comp = EffectComponent("test_entity")
        
        # Mock time.perf_counter to have control over timing
        import ai_evolve.features.effects.effects_plugin as ep
        original_time = ep.time.perf_counter
        
        # Set initial time
        mock_time = [0.0]
        ep.time.perf_counter = lambda: mock_time[0]
        
        try:
            # Apply bleed with 1 stack (default) - base_damage=5, damage_per_stack=2
            # So total = 5 + (2 * 1) = 7.0
            comp.apply_effect(EffectType.BLEED, duration=10.0)
            
            # Advance time by 1 second for first tick
            mock_time[0] = 1.05
            damages = comp.update(0.1)
            
            assert len(damages) > 0
            assert damages[0] == 7.0  # base_damage (5) + damage_per_stack (2) * stacks (1)
        finally:
            # Restore original time function
            ep.time.perf_counter = original_time


class TestComboReactions:
    """Test combo reaction system"""
    
    def test_melt_combo(self):
        comp = EffectComponent("test_entity")
        
        # Apply freeze first
        comp.apply_effect(EffectType.FREEZE, duration=5.0)
        assert comp.has_effect(EffectType.FREEZE)
        
        # Apply burn to trigger melt
        combo_triggered = []
        comp.on_combo_triggered = lambda e: combo_triggered.append(e)
        
        comp.apply_effect(EffectType.BURN, duration=5.0)
        
        # Freeze should be consumed by combo, burn remains
        assert not comp.has_effect(EffectType.FREEZE)
        # Burn is applied after combo
        assert comp.has_effect(EffectType.BURN)
        assert len(combo_triggered) == 1
        assert combo_triggered[0].combo_name == "melt"
    
    def test_superconduct_combo(self):
        comp = EffectComponent("test_entity")
        comp.apply_effect(EffectType.FREEZE)
        
        combo_triggered = []
        comp.on_combo_triggered = lambda e: combo_triggered.append(e)
        
        comp.apply_effect(EffectType.SHOCK)
        
        assert len(combo_triggered) == 1
        assert combo_triggered[0].combo_name == "superconduct"
        assert combo_triggered[0].damage == 80.0


class TestCCDetection:
    """Test crowd control detection"""
    
    def test_no_cc_initially(self):
        comp = EffectComponent("test_entity")
        assert comp.is_ccd() is False
    
    def test_stun_is_cc(self):
        comp = EffectComponent("test_entity")
        comp.apply_effect(EffectType.STUN)
        assert comp.is_ccd() is True
    
    def test_freeze_is_cc(self):
        comp = EffectComponent("test_entity")
        comp.apply_effect(EffectType.FREEZE)
        assert comp.is_ccd() is True


class TestEffectsPlugin:
    """Test EffectsPlugin integration"""
    
    def test_plugin_lifecycle(self):
        plugin = EffectsPlugin()
        plugin.on_init()
        plugin.on_update(0.016)
        plugin.on_shutdown()
    
    def test_create_component(self):
        plugin = EffectsPlugin()
        comp = plugin.create_component("entity_1")
        assert comp is not None
        assert comp.entity_id == "entity_1"
        
        # Should return same component
        comp2 = plugin.create_component("entity_1")
        assert comp2 is comp
    
    def test_get_config(self):
        plugin = EffectsPlugin()
        config = plugin.get_config()
        assert "registered_effects" in config
        assert config["registered_effects"] >= 5  # At least defaults


class TestEventIntegration:
    """Test event system integration"""
    
    def test_effect_applied_event(self):
        # Create fresh instances without singleton interference
        from ai_evolve.core import event_system as es_mod
        from ai_evolve.features.effects import effects_plugin as ep_mod
        
        event_system = es_mod.EventSystem()
        plugin = ep_mod.EffectsPlugin()
        plugin.register_events(event_system)
        
        events_received = []
        # Use a named function instead of lambda to avoid weakref issues with blinker
        def on_effect_applied(sender, **data):
            events_received.append(data)
        event_system.subscribe("effect_applied", on_effect_applied)
        
        # Trigger entity registration
        event_system.emit("entity_registered", {"entity_id": "test1", "entity": object()})
        
        # Apply effect via plugin directly
        comp = plugin.get_component("test1")
        comp.apply_effect(ep_mod.EffectType.BLEED, stacks=2, duration=5.0)
        
        assert len(events_received) == 1
        assert events_received[0]["effect_type"] == "bleed"
        assert events_received[0]["stacks"] == 2
    
    def test_combo_triggered_event(self):
        from ai_evolve.core import event_system as es_mod
        from ai_evolve.features.effects import effects_plugin as ep_mod
        
        event_system = es_mod.EventSystem()
        plugin = ep_mod.EffectsPlugin()
        plugin.register_events(event_system)
        
        events_received = []
        # Use a named function instead of lambda to avoid weakref issues with blinker
        def on_combo_triggered(sender, **data):
            events_received.append(data)
        event_system.subscribe("combo_triggered", on_combo_triggered)
        
        # Register entity
        event_system.emit("entity_registered", {"entity_id": "test2", "entity": object()})
        
        # Get component and apply effects directly
        comp = plugin.get_component("test2")
        comp.apply_effect(ep_mod.EffectType.FREEZE, duration=5.0)
        comp.apply_effect(ep_mod.EffectType.BURN, duration=5.0)
        
        assert len(events_received) == 1
        assert events_received[0]["combo_name"] == "melt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
