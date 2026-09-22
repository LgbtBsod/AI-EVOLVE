"""
Plugin Manager for AI-EVOLVE
Handles loading, initialization, and lifecycle of game plugins.
"""
from typing import Dict, List, Type
from ai_evolve.core.plugin_base import GamePlugin
from ai_evolve.core.event_system import EventSystem

class PluginManager:
    """
    Manages all game plugins/modules.
    Handles registration, initialization, update, and shutdown.
    """
    
    def __init__(self, event_system: EventSystem):
        self.event_system = event_system
        self.plugins: Dict[str, GamePlugin] = {}
        self._plugin_order: List[str] = []
    
    def register_plugin(self, plugin: GamePlugin):
        """Register a plugin with the manager."""
        if plugin.name in self.plugins:
            raise ValueError(f"Plugin '{plugin.name}' already registered")
        
        self.plugins[plugin.name] = plugin
        self._plugin_order.append(plugin.name)
        plugin.register_events(self.event_system)
    
    def initialize_all(self) -> bool:
        """Initialize all registered plugins."""
        for name in self._plugin_order:
            plugin = self.plugins[name]
            if not plugin.is_initialized:
                try:
                    plugin.initialize(None)  # Use initialize method which sets is_initialized
                except Exception as e:
                    self.plugins[name].logger.error(f"Failed to initialize: {e}")
                    return False
        return True
    
    def update_all(self, delta_time: float):
        """Update all initialized plugins."""
        for name in self._plugin_order:
            plugin = self.plugins[name]
            if plugin.is_initialized:
                plugin.on_update(delta_time)
    
    def shutdown_all(self):
        """Shutdown all plugins."""
        for name in reversed(self._plugin_order):
            plugin = self.plugins[name]
            if plugin.is_initialized:
                plugin.shutdown()
    
    def get_plugin(self, name: str) -> GamePlugin:
        """Get a plugin by name."""
        return self.plugins.get(name)
    
    def unregister_plugin(self, name: str):
        """Unregister a plugin."""
        if name in self.plugins:
            self.plugins[name].shutdown()
            del self.plugins[name]
            self._plugin_order.remove(name)
    
    def get_state(self) -> dict:
        """Get the combined state of all plugins for saving."""
        state = {}
        for name in self._plugin_order:
            plugin = self.plugins[name]
            if hasattr(plugin, 'get_state') and callable(getattr(plugin, 'get_state')):
                try:
                    state[name] = plugin.get_state()
                except Exception as e:
                    plugin.logger.warning(f"Failed to get state from {name}: {e}")
            else:
                # Store basic initialization state if no get_state method
                state[name] = {"initialized": plugin.is_initialized}
        return state
    
    def set_state(self, state: dict) -> bool:
        """Restore state to all plugins from a save."""
        success = True
        for name, plugin_state in state.items():
            if name in self.plugins:
                plugin = self.plugins[name]
                if hasattr(plugin, 'set_state') and callable(getattr(plugin, 'set_state')):
                    try:
                        plugin.set_state(plugin_state)
                    except Exception as e:
                        plugin.logger.error(f"Failed to set state for {name}: {e}")
                        success = False
        return success
