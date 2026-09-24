"""
Tests for Dev Probe Framework
"""
import pytest
from unittest.mock import Mock, MagicMock
import time

from ai_evolve.tools.dev_probe_framework import (
    DevProbeFramework,
    DevProbePlugin,
    ProbeEvent,
    EntityState,
    ProbeFrame,
    StatsCollectorPlugin,
    ScreenshotManagerPlugin,
    AnomalyDetectorPlugin,
)


class TestProbeEvent:
    """Test ProbeEvent dataclass."""
    
    def test_create_event_minimal(self):
        event = ProbeEvent(event_type="test_event", timestamp=1.0)
        assert event.event_type == "test_event"
        assert event.timestamp == 1.0
        assert event.data == {}
        assert event.entity_id is None
        assert event.kind is None
    
    def test_create_event_full(self):
        event = ProbeEvent(
            event_type="death",
            timestamp=5.5,
            data={"damage": 100},
            entity_id="enemy_123",
            kind="kill"
        )
        assert event.event_type == "death"
        assert event.timestamp == 5.5
        assert event.data == {"damage": 100}
        assert event.entity_id == "enemy_123"
        assert event.kind == "kill"


class TestEntityState:
    """Test EntityState dataclass."""
    
    def test_create_entity_state(self):
        state = EntityState(
            entity_id="player_1",
            entity_type="hero",
            is_player=True,
            health=80.0,
            max_health=100.0,
            position=(10.0, 20.0),
            is_alive=True
        )
        assert state.entity_id == "player_1"
        assert state.is_player is True
        assert state.health == 80.0
        assert state.position == (10.0, 20.0)
        assert state.is_alive is True
        assert state.metadata == {}


class TestDevProbePlugin:
    """Test DevProbePlugin base class."""
    
    def test_plugin_requires_name(self):
        class TestPlugin(DevProbePlugin):
            @property
            def name(self):
                return "test_plugin"
        
        plugin = TestPlugin()
        assert plugin.name == "test_plugin"
    
    def test_plugin_default_hooks(self):
        class TestPlugin(DevProbePlugin):
            @property
            def name(self):
                return "test_plugin"
        
        plugin = TestPlugin()
        framework = Mock()
        
        # All hooks should exist and not raise
        plugin.on_init(framework)
        plugin.on_pre_run(Mock(), {})
        plugin.on_sample(Mock(), [], 0.0)
        plugin.on_event(Mock())
        plugin.on_screenshot("path.png", "test", 1)
        plugin.on_post_run({})
        plugin.on_shutdown()


class TestDevProbeFramework:
    """Test DevProbeFramework."""
    
    def test_framework_init(self):
        framework = DevProbeFramework()
        assert framework.plugins == {}
        assert framework._plugin_order == []
        assert framework._is_running is False
    
    def test_register_plugin(self):
        framework = DevProbeFramework()
        
        class TestPlugin(DevProbePlugin):
            @property
            def name(self):
                return "test"
        
        plugin = TestPlugin()
        framework.register_plugin(plugin)
        
        assert "test" in framework.plugins
        assert framework._plugin_order == ["test"]
    
    def test_duplicate_plugin_raises(self):
        framework = DevProbeFramework()
        
        class TestPlugin(DevProbePlugin):
            @property
            def name(self):
                return "test"
        
        plugin = TestPlugin()
        framework.register_plugin(plugin)
        
        with pytest.raises(ValueError, match="already registered"):
            framework.register_plugin(TestPlugin())
    
    def test_unregister_plugin(self):
        framework = DevProbeFramework()
        
        class TestPlugin(DevProbePlugin):
            @property
            def name(self):
                return "test"
            
            def on_shutdown(self):
                self.shutdown_called = True
        
        plugin = TestPlugin()
        framework.register_plugin(plugin)
        framework.unregister_plugin("test")
        
        assert "test" not in framework.plugins
        assert hasattr(plugin, 'shutdown_called')
    
    def test_set_adapters(self):
        framework = DevProbeFramework()
        
        entities_func = Mock()
        combat_func = Mock()
        
        framework.set_entity_adapter(entities_func)
        framework.set_combat_adapter(combat_func)
        
        assert framework.get_entities_func == entities_func
        assert framework.get_combat_system_func == combat_func
    
    def test_event_detection_death(self):
        framework = DevProbeFramework()
        
        prev_entities = [
            EntityState(
                entity_id="enemy_1",
                entity_type="enemy",
                is_player=False,
                health=50.0,
                max_health=100.0,
                position=(0, 0),
                is_alive=True
            )
        ]
        
        curr_entities = [
            EntityState(
                entity_id="enemy_1",
                entity_type="enemy",
                is_player=False,
                health=0.0,
                max_health=100.0,
                position=(0, 0),
                is_alive=False
            )
        ]
        
        events = framework._detect_events(prev_entities, curr_entities, 1.0)
        
        assert len(events) == 1
        assert events[0].event_type == "entity_death"
        assert events[0].entity_id == "enemy_1"
        assert events[0].kind == "death"
    
    def test_event_detection_spawn(self):
        framework = DevProbeFramework()
        
        prev_entities = []
        curr_entities = [
            EntityState(
                entity_id="enemy_new",
                entity_type="enemy",
                is_player=False,
                health=100.0,
                max_health=100.0,
                position=(5, 5),
                is_alive=True
            )
        ]
        
        events = framework._detect_events(prev_entities, curr_entities, 1.0)
        
        assert len(events) == 1
        assert events[0].event_type == "entity_spawn"
        assert events[0].entity_id == "enemy_new"
    
    def test_event_detection_low_hp(self):
        framework = DevProbeFramework()
        
        prev_entities = [
            EntityState(
                entity_id="player_1",
                entity_type="hero",
                is_player=True,
                health=50.0,
                max_health=100.0,
                position=(0, 0),
                is_alive=True
            )
        ]
        
        curr_entities = [
            EntityState(
                entity_id="player_1",
                entity_type="hero",
                is_player=True,
                health=20.0,  # Below 25% threshold
                max_health=100.0,
                position=(0, 0),
                is_alive=True
            )
        ]
        
        events = framework._detect_events(prev_entities, curr_entities, 1.0)
        
        assert len(events) == 1
        assert events[0].event_type == "low_hp"
        assert events[0].data["percent"] == 0.2
    
    def test_notify_plugins_event(self):
        framework = DevProbeFramework()
        
        class EventTrackingPlugin(DevProbePlugin):
            @property
            def name(self):
                return "tracker"
            
            def __init__(self):
                self.events_received = []
            
            def on_event(self, event):
                self.events_received.append(event)
        
        plugin = EventTrackingPlugin()
        framework.register_plugin(plugin)
        
        event = ProbeEvent(event_type="test", timestamp=1.0)
        framework._notify_plugins_event(event)
        
        assert len(plugin.events_received) == 1
        assert plugin.events_received[0] == event
    
    def test_get_summary_empty(self):
        framework = DevProbeFramework()
        summary = framework.get_summary()
        
        assert summary["total_frames"] == 0
        assert summary["total_events"] == 0
        assert summary["events"] == []
        assert summary["frames"] == []


class TestStatsCollectorPlugin:
    """Test StatsCollectorPlugin."""
    
    def test_plugin_name(self):
        plugin = StatsCollectorPlugin()
        assert plugin.name == "stats_collector"
    
    def test_track_death_event(self):
        plugin = StatsCollectorPlugin()
        
        event = ProbeEvent(event_type="entity_death", timestamp=1.0)
        plugin.on_event(event)
        
        assert plugin.stats["deaths"] == 1
    
    def test_track_damage_event(self):
        plugin = StatsCollectorPlugin()
        
        event = ProbeEvent(
            event_type="combat_damage_dealt",
            timestamp=1.0,
            data={"damage": 50}
        )
        plugin.on_event(event)
        
        assert plugin.stats["total_damage_taken"] == 50


class TestScreenshotManagerPlugin:
    """Test ScreenshotManagerPlugin."""
    
    def test_plugin_name(self, tmp_path):
        plugin = ScreenshotManagerPlugin(str(tmp_path))
        assert plugin.name == "screenshot_manager"
    
    def test_screenshot_on_trigger_event(self, tmp_path):
        plugin = ScreenshotManagerPlugin(str(tmp_path), trigger_events=["death"])
        
        event = ProbeEvent(event_type="death", timestamp=1.0)
        plugin.on_event(event)
        
        assert plugin.screenshots_taken == 1
    
    def test_no_screenshot_on_non_trigger(self, tmp_path):
        plugin = ScreenshotManagerPlugin(str(tmp_path), trigger_events=["death"])
        
        event = ProbeEvent(event_type="spawn", timestamp=1.0)
        plugin.on_event(event)
        
        assert plugin.screenshots_taken == 0


class TestAnomalyDetectorPlugin:
    """Test AnomalyDetectorPlugin."""
    
    def test_plugin_name(self):
        plugin = AnomalyDetectorPlugin()
        assert plugin.name == "anomaly_detector"
    
    def test_detect_hp_freeze(self):
        plugin = AnomalyDetectorPlugin()
        
        # Create entity with frozen HP
        entities = [
            EntityState(
                entity_id="frozen_enemy",
                entity_type="enemy",
                is_player=False,
                health=50.0,
                max_health=100.0,
                position=(0, 0),
                is_alive=True
            )
        ]
        
        # Simulate multiple samples with same HP
        for i in range(6):
            metrics = plugin.on_sample(Mock(), entities, float(i))
        
        assert len(plugin.anomalies) >= 1
        assert plugin.anomalies[-1]["type"] == "hp_freeze"
    
    def test_detect_instant_death(self):
        plugin = AnomalyDetectorPlugin()
        
        # First sample - healthy
        healthy_entity = EntityState(
            entity_id="target",
            entity_type="enemy",
            is_player=False,
            health=100.0,
            max_health=100.0,
            position=(0, 0),
            is_alive=True
        )
        plugin.on_sample(Mock(), [healthy_entity], 0.0)
        
        # Second sample - nearly dead (>80% drop)
        damaged_entity = EntityState(
            entity_id="target",
            entity_type="enemy",
            is_player=False,
            health=15.0,  # 85% drop
            max_health=100.0,
            position=(0, 0),
            is_alive=True
        )
        metrics = plugin.on_sample(Mock(), [damaged_entity], 1.0)
        
        assert len(plugin.anomalies) >= 1
        assert plugin.anomalies[-1]["type"] == "instant_death"
    
    def test_summary_includes_anomalies(self):
        plugin = AnomalyDetectorPlugin()
        summary = {"status": "completed"}
        
        plugin.anomalies = [{"type": "test", "timestamp": 1.0}]
        plugin.on_post_run(summary)
        
        assert "anomalies" in summary
        assert summary["anomaly_count"] == 1


class TestIntegration:
    """Integration tests for framework with plugins."""
    
    def test_framework_with_multiple_plugins(self):
        framework = DevProbeFramework()
        
        stats_plugin = StatsCollectorPlugin()
        anomaly_plugin = AnomalyDetectorPlugin()
        
        framework.register_plugin(stats_plugin)
        framework.register_plugin(anomaly_plugin)
        
        assert len(framework.plugins) == 2
        assert "stats_collector" in framework.plugins
        assert "anomaly_detector" in framework.plugins
    
    def test_mock_game_run_short(self):
        """Test framework run with mock game."""
        framework = DevProbeFramework()
        
        # Setup mock game
        mock_game = Mock()
        
        # Setup entity adapter
        def get_entities(game):
            return [
                (Mock(entity_id="player", health=100, max_health=100, x=0, y=0, enemy_type=None, is_alive=lambda: True), True),
                (Mock(entity_id="enemy", health=50, max_health=100, x=10, y=10, enemy_type="basic", is_alive=lambda: True), False),
            ]
        
        framework.set_entity_adapter(get_entities)
        
        # Add plugin
        stats_plugin = StatsCollectorPlugin()
        framework.register_plugin(stats_plugin)
        
        # Run short probe (no actual game loop)
        # We can't fully test run() without a real game, but we can test setup
        assert framework.get_entities_func is not None
        assert len(framework.plugins) == 1
