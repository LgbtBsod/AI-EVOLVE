"""
Plugin Base Class for AI-EVOLVE
All game features/modules should inherit from this.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
import logging

class GamePlugin(ABC):
    """
    Base class for all game plugins/modules.
    Provides lifecycle methods and core integration points.
    """

    def __init__(self, name: str):
        self.name = name
        self.is_initialized = False
        self.logger = logging.getLogger(f"plugin.{name}")
    
    @property
    def dependencies(self) -> List[str]:
        """Return list of plugin dependencies."""
        return []

    @abstractmethod
    def on_init(self, game_core: Any) -> bool:
        """Called when plugin is initialized."""
        pass

    @abstractmethod
    def on_update(self, delta_time: float) -> None:
        """Called every frame/update cycle."""
        pass

    @abstractmethod
    def on_shutdown(self) -> None:
        """Called when plugin is shut down."""
        pass

    def register_events(self, event_system):
        """Register event handlers with the event system."""
        pass

    def get_config(self) -> Dict[str, Any]:
        """Return plugin configuration."""
        return {}

    def initialize(self, game_core: Any = None):
        """Initialize the plugin."""
        if not self.is_initialized:
            self.on_init(game_core)
            self.is_initialized = True

    def shutdown(self):
        """Shutdown the plugin."""
        if self.is_initialized:
            self.on_shutdown()
            self.is_initialized = False
