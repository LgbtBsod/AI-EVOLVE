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
    
    def initialize_all(self):
        """Initialize all registered plugins."""
        for name in self._plugin_order:
            self.plugins[name].initialize()
    
    def update_all(self, delta_time: float):
        """Update all initialized plugins."""
        for name in self._plugin_order:
            plugin = self.plugins[name]
            if plugin.is_initialized:
                plugin.on_update(delta_time)
    
    def shutdown_all(self):
        """Shutdown all plugins."""
        for name in reversed(self._plugin_order):
            self.plugins[name].shutdown()
    
    def get_plugin(self, name: str) -> GamePlugin:
        """Get a plugin by name."""
        return self.plugins.get(name)
    
    def unregister_plugin(self, name: str):
        """Unregister a plugin."""
        if name in self.plugins:
            self.plugins[name].shutdown()
            del self.plugins[name]
            self._plugin_order.remove(name)
