"""
Plugin Base Class for AI-EVOLVE
All game features/modules should inherit from this.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any

class GamePlugin(ABC):
    """
    Base class for all game plugins/modules.
    Provides lifecycle methods and core integration points.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.is_initialized = False
    
    @abstractmethod
    def on_init(self):
        """Called when plugin is initialized."""
        pass
    
    @abstractmethod
    def on_update(self, delta_time: float):
        """Called every frame/update cycle."""
        pass
    
    @abstractmethod
    def on_shutdown(self):
        """Called when plugin is shut down."""
        pass
    
    def register_events(self, event_system):
        """Register event handlers with the event system."""
        pass
    
    def get_config(self) -> Dict[str, Any]:
        """Return plugin configuration."""
        return {}
    
    def initialize(self):
        """Initialize the plugin."""
        if not self.is_initialized:
            self.on_init()
            self.is_initialized = True
    
    def shutdown(self):
        """Shutdown the plugin."""
        if self.is_initialized:
            self.on_shutdown()
            self.is_initialized = False
