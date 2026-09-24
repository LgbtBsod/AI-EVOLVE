"""
AI-EVOLVE Core Event System
Centralized event bus using blinker signals.
Allows decoupled communication between modules/plugins.
"""
from blinker import signal
from typing import Callable, Any, Dict

class EventSystem:
    """
    Core Event System.
    Manages game events and allows modules to subscribe/publish.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._signals: Dict[str, Any] = {}
        return cls._instance
    
    def get_signal(self, event_name: str):
        """Get or create a signal for an event."""
        if event_name not in self._signals:
            self._signals[event_name] = signal(event_name)
        return self._signals[event_name]
    
    def subscribe(self, event_name: str, handler: Callable, sender: Any = None):
        """Subscribe a handler to an event."""
        sig = self.get_signal(event_name)
        sig.connect(handler, sender=sender)
    
    # Alias for compatibility with old code
    def on(self, event_name: str, handler: Callable, sender: Any = None):
        """Subscribe a handler to an event (alias for subscribe)."""
        self.subscribe(event_name, handler, sender)
    
    def unsubscribe(self, event_name: str, handler: Callable, sender: Any = None):
        """Unsubscribe a handler from an event."""
        if event_name in self._signals:
            sig = self._signals[event_name]
            sig.disconnect(handler, sender=sender)
    
    # Alias for compatibility with old code
    def off(self, event_name: str, handler: Callable, sender: Any = None):
        """Unsubscribe a handler from an event (alias for unsubscribe)."""
        self.unsubscribe(event_name, handler, sender)
    
    def emit(self, event_name: str, data: Dict = None, sender: Any = None):
        """Emit an event with optional data."""
        sig = self.get_signal(event_name)
        sig.send(sender, **(data or {}))
    
    def clear(self):
        """Clear all signals (for testing)."""
        for sig in self._signals.values():
            sig.receivers.clear()
    
    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (for testing)."""
        cls._instance = None
    
    @classmethod
    def get_instance(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_context(self, key: str):
        """Get context data (for plugin integration)."""
        # Placeholder for context - will be implemented in GameCore
        return getattr(self, f'_ctx_{key}', None)
    
    def set_context(self, key: str, value: Any):
        """Set context data (for plugin integration)."""
        setattr(self, f'_ctx_{key}', value)


# Global instance
event_system = EventSystem()
