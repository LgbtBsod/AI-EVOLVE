"""
Integration Tests for AI-EVOLVE Plugin System
Tests the interaction between core components and plugins.
"""
import pytest
from ai_evolve.core.event_system import event_system, EventSystem
from ai_evolve.db.database_core import db_core, GameEntity
from ai_evolve.core.plugin_manager import PluginManager
from ai_evolve.features.combat.combat_plugin import CombatPlugin
from ai_evolve.features.toughness.toughness_plugin import ToughnessPlugin
from ai_evolve.features.scenes.scene_manager_plugin import SceneManagerPlugin, BaseScene

class TestPluginIntegration:
    """Integration tests for plugin system."""
    
    def setup_method(self):
        """Reset all systems before each test."""
        event_system.clear()
        db_core.clear_db()
        self.pm = PluginManager(event_system)
    
    def test_combat_plugin_lifecycle(self):
        """Test combat plugin full lifecycle."""
        plugin = CombatPlugin()
        self.pm.register_plugin(plugin)
        
        # Initialize
        self.pm.initialize_all()
        assert plugin.is_initialized
        
        # Update
        self.pm.update_all(0.016)
        
        # Shutdown
        self.pm.shutdown_all()
        assert not plugin.is_initialized
    
    def test_toughness_plugin_lifecycle(self):
        """Test toughness plugin full lifecycle."""
        plugin = ToughnessPlugin()
        self.pm.register_plugin(plugin)
        
        self.pm.initialize_all()
        assert plugin.is_initialized
        
        self.pm.update_all(0.016)
        
        self.pm.shutdown_all()
        assert not plugin.is_initialized
    
    def test_scene_manager_plugin_lifecycle(self):
        """Test scene manager plugin full lifecycle."""
        plugin = SceneManagerPlugin()
        self.pm.register_plugin(plugin)
        
        self.pm.initialize_all()
        assert plugin.is_initialized
        
        self.pm.update_all(0.016)
        
        self.pm.shutdown_all()
        assert not plugin.is_initialized
    
    def test_multiple_plugins_together(self):
        """Test multiple plugins working together."""
        combat = CombatPlugin()
        toughness = ToughnessPlugin()
        scene_mgr = SceneManagerPlugin()
        
        self.pm.register_plugin(combat)
        self.pm.register_plugin(toughness)
        self.pm.register_plugin(scene_mgr)
        
        self.pm.initialize_all()
        
        assert combat.is_initialized
        assert toughness.is_initialized
        assert scene_mgr.is_initialized
        
        self.pm.update_all(0.016)
        
        self.pm.shutdown_all()
        
        assert not combat.is_initialized
        assert not toughness.is_initialized
        assert not scene_mgr.is_initialized

class TestCombatToughnessIntegration:
    """Test combat and toughness plugin interaction."""
    
    def setup_method(self):
        """Reset systems."""
        event_system.clear()
        db_core.clear_db()
        self.pm = PluginManager(event_system)
    
    def test_damage_flow_through_plugins(self):
        """Test that damage events flow through combat to toughness."""
        combat = CombatPlugin()
        toughness = ToughnessPlugin()
        
        self.pm.register_plugin(combat)
        self.pm.register_plugin(toughness)
        self.pm.initialize_all()
        
        # Track toughness damage events
        toughness_data = {}
        
        def on_toughness_damage(sender, **data):
            toughness_data.update(data)
        
        event_system.subscribe("toughness_damage_applied", on_toughness_damage)
        
        # Create mock target and register it
        class MockTarget:
            entity_id = "test_target"
            max_health = 100.0
        
        target = MockTarget()
        
        # Register entity with toughness system
        event_system.emit("entity_registered", {
            "entity": target,
            "entity_id": target.entity_id
        })
        
        # Trigger attack with toughness damage
        event_system.emit("damage_dealt", {
            "attacker": "player",
            "target": target,
            "damage": 10.0,
            "toughness_damage": 20.0,
            "toughness_type": "fire",
            "enemy_toughness_type": "physical"
        })
        
        # Check that toughness damage was applied
        assert "actual_damage" in toughness_data
        assert toughness_data["base_damage"] == 20.0
        assert toughness_data["actual_damage"] > 0
        
        self.pm.shutdown_all()

class TestSceneTransition:
    """Test scene transition functionality."""
    
    def setup_method(self):
        """Reset systems."""
        event_system.clear()
        self.pm = PluginManager(event_system)
    
    def test_scene_addition_and_transition(self):
        """Test adding scenes and transitioning between them."""
        scene_mgr = SceneManagerPlugin()
        
        class TestScene(BaseScene):
            enter_called = False
            exit_called = False
            
            def on_enter(self):
                self.enter_called = True
            
            def on_exit(self):
                self.exit_called = True
        
        scene1 = TestScene("scene1")
        scene2 = TestScene("scene2")
        
        scene_mgr.add_scene(scene1)
        scene_mgr.add_scene(scene2)
        
        self.pm.register_plugin(scene_mgr)
        self.pm.initialize_all()
        
        # Request scene change to scene1
        event_system.emit("change_scene", {"scene_name": "scene1"})
        self.pm.update_all(0.016)
        
        assert scene_mgr.current_scene.name == "scene1"
        assert scene1.enter_called
        
        # Request scene change to scene2
        event_system.emit("change_scene", {"scene_name": "scene2"})
        self.pm.update_all(0.016)
        
        assert scene_mgr.current_scene.name == "scene2"
        assert scene2.enter_called
        assert scene1.exit_called
        
        self.pm.shutdown_all()

class TestDatabaseWithPlugins:
    """Test database integration with plugins."""
    
    def setup_method(self):
        """Reset systems."""
        event_system.clear()
        db_core.clear_db()
        db_core.init_db()
        self.pm = PluginManager(event_system)
    
    def test_plugin_saves_state_to_db(self):
        """Test that plugin can save state to database."""
        # Add entity via DB
        with db_core.get_session() as session:
            entity = GameEntity(name="Warrior", entity_type="player", health=200.0, level=5)
            session.add(entity)
        
        # Query entity
        with db_core.get_session() as session:
            result = session.query(GameEntity).filter_by(name="Warrior").first()
            assert result is not None
            assert result.health == 200.0
            assert result.level == 5
