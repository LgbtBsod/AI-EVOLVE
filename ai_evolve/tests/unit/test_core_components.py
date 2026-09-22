"""
Unit Tests for AI-EVOLVE Core Components
"""
import pytest
from ai_evolve.core.event_system import EventSystem, event_system
from ai_evolve.db.database_core import DatabaseCore, db_core, GameEntity
from ai_evolve.core.plugin_base import GamePlugin
from ai_evolve.core.plugin_manager import PluginManager

class TestEventSystem:
    """Tests for EventSystem."""
    
    def setup_method(self):
        """Reset event system before each test."""
        event_system.clear()
    
    def test_singleton_instance(self):
        """Test that EventSystem is a singleton."""
        es1 = EventSystem()
        es2 = EventSystem()
        assert es1 is es2
    
    def test_subscribe_and_emit(self):
        """Test subscribing to and emitting events."""
        received_data = {}
        
        def handler(sender, **data):
            received_data.update(data)
        
        event_system.subscribe("test_event", handler)
        event_system.emit("test_event", {"key": "value"})
        
        assert received_data == {"key": "value"}
    
    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        call_count = [0]
        
        def handler(sender, **data):
            call_count[0] += 1
        
        event_system.subscribe("test_event", handler)
        event_system.emit("test_event")
        assert call_count[0] == 1
        
        event_system.unsubscribe("test_event", handler)
        event_system.emit("test_event")
        assert call_count[0] == 1  # Should not increase
    
    def test_multiple_handlers(self):
        """Test multiple handlers for same event."""
        results = []
        
        def handler1(sender, **data):
            results.append(1)
        
        def handler2(sender, **data):
            results.append(2)
        
        event_system.subscribe("test_event", handler1)
        event_system.subscribe("test_event", handler2)
        event_system.emit("test_event")
        
        assert 1 in results and 2 in results

class TestDatabaseCore:
    """Tests for DatabaseCore."""
    
    def setup_method(self):
        """Reset database before each test."""
        db_core.clear_db()
    
    def test_singleton_instance(self):
        """Test that DatabaseCore is a singleton."""
        db1 = DatabaseCore()
        db2 = DatabaseCore()
        assert db1 is db2
    
    def test_init_db(self):
        """Test database initialization."""
        db_core.init_db()
        # Should not raise exception
    
    def test_insert_and_query(self):
        """Test inserting and querying data."""
        with db_core.get_session() as session:
            entity = GameEntity(name="TestEntity", entity_type="enemy", health=150.0)
            session.add(entity)
        
        with db_core.get_session() as session:
            result = session.query(GameEntity).filter_by(name="TestEntity").first()
            assert result is not None
            assert result.health == 150.0
    
    def test_bulk_insert(self):
        """Test bulk insert operation."""
        data = [
            {"name": f"Entity{i}", "entity_type": "enemy", "health": 100.0}
            for i in range(5)
        ]
        db_core.bulk_insert(GameEntity, data)
        
        with db_core.get_session() as session:
            count = session.query(GameEntity).count()
            assert count == 5
    
    def test_transaction_rollback(self):
        """Test that transactions rollback on error."""
        try:
            with db_core.get_session() as session:
                entity = GameEntity(name="TempEntity", entity_type="test")
                session.add(entity)
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        with db_core.get_session() as session:
            result = session.query(GameEntity).filter_by(name="TempEntity").first()
            assert result is None  # Should be rolled back

class MockPlugin(GamePlugin):
    """Mock plugin for testing."""
    
    def __init__(self, name="mock"):
        super().__init__(name)
        self.init_called = False
        self.update_called = False
        self.shutdown_called = False
        self.update_delta = 0
    
    def on_init(self):
        self.init_called = True
    
    def on_update(self, delta_time: float):
        self.update_called = True
        self.update_delta = delta_time
    
    def on_shutdown(self):
        self.shutdown_called = True

class TestPluginManager:
    """Tests for PluginManager."""
    
    def setup_method(self):
        """Reset components before each test."""
        event_system.clear()
        self.pm = PluginManager(event_system)
    
    def test_register_plugin(self):
        """Test plugin registration."""
        plugin = MockPlugin("test_plugin")
        self.pm.register_plugin(plugin)
        
        assert self.pm.get_plugin("test_plugin") is plugin
    
    def test_duplicate_registration_raises(self):
        """Test that duplicate registration raises error."""
        plugin = MockPlugin("test_plugin")
        self.pm.register_plugin(plugin)
        
        with pytest.raises(ValueError):
            self.pm.register_plugin(plugin)
    
    def test_initialize_all(self):
        """Test initializing all plugins."""
        plugin = MockPlugin("test_plugin")
        self.pm.register_plugin(plugin)
        self.pm.initialize_all()
        
        assert plugin.init_called
        assert plugin.is_initialized
    
    def test_update_all(self):
        """Test updating all plugins."""
        plugin = MockPlugin("test_plugin")
        self.pm.register_plugin(plugin)
        self.pm.initialize_all()
        self.pm.update_all(0.016)
        
        assert plugin.update_called
        assert plugin.update_delta == 0.016
    
    def test_shutdown_all(self):
        """Test shutting down all plugins."""
        plugin = MockPlugin("test_plugin")
        self.pm.register_plugin(plugin)
        self.pm.initialize_all()
        self.pm.shutdown_all()
        
        assert plugin.shutdown_called
        assert not plugin.is_initialized
    
    def test_plugin_order_on_shutdown(self):
        """Test that plugins shutdown in reverse order."""
        shutdown_order = []
        
        class OrderPlugin(MockPlugin):
            def on_shutdown(self):
                shutdown_order.append(self.name)
                super().on_shutdown()
        
        p1 = OrderPlugin("plugin1")
        p2 = OrderPlugin("plugin2")
        p3 = OrderPlugin("plugin3")
        
        self.pm.register_plugin(p1)
        self.pm.register_plugin(p2)
        self.pm.register_plugin(p3)
        self.pm.initialize_all()
        self.pm.shutdown_all()
        
        assert shutdown_order == ["plugin3", "plugin2", "plugin1"]
