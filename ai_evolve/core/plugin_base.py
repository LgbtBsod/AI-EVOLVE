"""
Plugin Base Class for AI-EVOLVE
All game features/modules should inherit from this.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging

class PluginBase(ABC):
    """
    Base class for all game plugins/modules.
    Provides lifecycle methods and core integration points.
    """

    name = "base_plugin"
    version = "1.0.0"
    description = "Base plugin class"
    
    def __init__(self):
        self.is_initialized = False
        self.game_core: Optional[Any] = None
        self.event_system = None
        self.logger = logging.getLogger(f"plugin.{self.name}")
    
    @property
    def dependencies(self) -> List[str]:
        """Return list of plugin dependencies."""
        return []

    @abstractmethod
    def initialize(self, config: Dict[str, Any], game_core: Any) -> bool:
        """Called when plugin is initialized."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Called when plugin is shut down."""
        pass

    def update(self, delta_time: float) -> None:
        """Called every frame/update cycle."""
        pass

    def register_events(self, event_system):
        """Register event handlers with the event system."""
        pass

    def get_config(self) -> Dict[str, Any]:
        """Return plugin configuration."""
        return {}


class GamePlugin(PluginBase):
    """
    Legacy alias for PluginBase - kept for backward compatibility.
    """
    pass
