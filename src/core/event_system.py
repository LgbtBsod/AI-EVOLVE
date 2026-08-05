#!/usr/bin/env python3
"""Event System using blinker library.

Refactored for Python 3.14 Best Practices:
- Replaced custom event system with blinker (Don't Reinvent The Wheel)
- Added from __future__ import annotations
- Using typing.Self for method chaining
- Added @override decorator where applicable
- Type hints updated to Python 3.10+ style
- Removed O(n²) behavior, using blinker's optimized signal dispatch
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from blinker import Namespace, Signal

logger = logging.getLogger(__name__)

# Create a namespace for our signals
event_namespace = Namespace()


# ============================================================================
# EVENT TYPES
# ============================================================================

class EventType(Enum):
    """Event types."""
    SYSTEM = "system"
    GAME = "game"
    UI = "ui"
    AUDIO = "audio"
    NETWORK = "network"
    DEBUG = "debug"


class EventPriority(Enum):
    """Event priorities."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventState(Enum):
    """Event states."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass(slots=True, kw_only=True)
class EventData:
    """Event data container (optimized with __slots__)."""
    event_id: str
    event_type: str
    event_data: dict[str, Any]
    source: str
    timestamp: float = field(default_factory=time.perf_counter)
    priority: EventPriority = EventPriority.NORMAL
    state: EventState = EventState.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_message: str | None = None


@dataclass(slots=True, kw_only=True)
class EventStats:
    """Event system statistics."""
    events_processed: int = 0
    events_failed: int = 0
    handlers_registered: int = 0
    subscriptions_active: int = 0


# ============================================================================
# EVENT SYSTEM
# ============================================================================

class EventSystem:
    """
    Event System wrapper around blinker library.
    
    This provides a simple API while leveraging the powerful 
    blinker library for signal/event dispatch.
    
    Example:
        >>> event_system = EventSystem()
        >>> event_system.on("game.event", lambda sender, event: print(event))
        >>> event_system.emit("game.event", {"key": "value"})
    """
    
    def __init__(self, max_history_size: int = 1000) -> None:
        self._signals: dict[str, Signal] = {}
        self._subscriptions: dict[str, list[tuple[str, Callable]]] = {}
        self._event_history: list[EventData] = []
        self._max_history_size = max_history_size
        self._is_running = False
        self._lock = threading.RLock()
        
        self._stats = EventStats()
        
        logger.info("EventSystem initialized with blinker")
    
    def initialize(self) -> bool:
        """Initialize the event system."""
        try:
            self._is_running = True
            logger.info("EventSystem successfully initialized")
            return True
        except Exception as e:
            logger.exception("Error initializing EventSystem: %s", e)
            return False
    
    def shutdown(self) -> bool:
        """Shutdown the event system."""
        try:
            self._is_running = False
            # Disconnect all signals
            for signal in self._signals.values():
                signal.disconnect()
            self._signals.clear()
            self._subscriptions.clear()
            logger.info("EventSystem successfully shutdown")
            return True
        except Exception as e:
            logger.exception("Error shutting down EventSystem: %s", e)
            return False
    
    def emit(
        self, 
        event_type: str, 
        event_data: dict[str, Any], 
        source: str = "system",
        priority: EventPriority = EventPriority.NORMAL
    ) -> bool:
        """Emit an event (O(1) dispatch via blinker)."""
        try:
            event = EventData(
                event_id=f"{event_type}_{int(time.perf_counter() * 1000)}",
                event_type=event_type,
                event_data=event_data,
                source=source,
                priority=priority
            )
            
            # Get or create signal
            signal = self._get_or_create_signal(event_type)
            
            with self._lock:
                # Add to history
                if len(self._event_history) >= self._max_history_size:
                    self._event_history.pop(0)
                self._event_history.append(event)
                
                # Update stats
                self._stats.subscriptions_active = sum(len(subs) for subs in self._subscriptions.values())
            
            # Dispatch event via blinker (thread-safe by default)
            # Note: blinker only calls handlers connected with sender=signal when sender matches
            event.state = EventState.PROCESSING
            try:
                # Send with signal as sender to match the connection
                signal.send(signal, event=event)
                event.state = EventState.COMPLETED
                self._stats.events_processed += 1
            except Exception as e:
                event.state = EventState.FAILED
                event.error_message = str(e)
                self._stats.events_failed += 1
                logger.exception("Error dispatching event %s: %s", event_type, e)
                return False
            
            logger.debug("Event %s emitted from %s", event_type, source)
            return True
            
        except Exception as e:
            logger.exception("Error emitting event %s: %s", event_type, e)
            return False
    
    def on(
        self, 
        event_type: str, 
        handler: Callable[[Any, EventData], None], 
        subscriber_id: str = "unknown",
        priority: EventPriority = EventPriority.NORMAL
    ) -> Self:
        """Subscribe to an event."""
        try:
            signal = self._get_or_create_signal(event_type)
            
            # Wrap handler to track subscriptions and adapt to blinker's signature
            def wrapped_handler(sender: Any, **kwargs: Any) -> None:
                try:
                    event = kwargs.get('event')
                    if event:
                        # Call user handler - always pass sender and event as positional args
                        # Users should define handlers as: handler(sender, event) or handler(sender, **kwargs)
                        handler(sender, event)
                except Exception as e:
                    logger.exception("Error in handler %s for %s: %s", subscriber_id, event_type, e)
                    raise
            
            # Connect to signal
            signal.connect(wrapped_handler, sender=signal, weak=False)
            
            with self._lock:
                if event_type not in self._subscriptions:
                    self._subscriptions[event_type] = []
                self._subscriptions[event_type].append((subscriber_id, wrapped_handler))
                self._stats.handlers_registered += 1
                self._stats.subscriptions_active = sum(len(subs) for subs in self._subscriptions.values())
            
            logger.debug("Subscribed to %s from %s", event_type, subscriber_id)
            return self
            
        except Exception as e:
            logger.exception("Error subscribing to %s: %s", event_type, e)
            return self
    
    def off(self, event_type: str, subscriber_id: str) -> Self:
        """Unsubscribe from an event."""
        try:
            with self._lock:
                if event_type in self._subscriptions:
                    # Find and disconnect handler
                    for sub_id, handler in self._subscriptions[event_type]:
                        if sub_id == subscriber_id:
                            signal = self._signals.get(event_type)
                            if signal:
                                signal.disconnect(handler)
                    
                    # Remove from subscriptions
                    self._subscriptions[event_type] = [
                        sub for sub in self._subscriptions[event_type]
                        if sub[0] != subscriber_id
                    ]
                    
                    if not self._subscriptions[event_type]:
                        del self._subscriptions[event_type]
                    
                    self._stats.subscriptions_active = sum(len(subs) for subs in self._subscriptions.values())
            
            logger.debug("Unsubscribed from %s for %s", event_type, subscriber_id)
            return self
            
        except Exception as e:
            logger.exception("Error unsubscribing from %s: %s", event_type, e)
            return self
    
    def subscribe(
        self, 
        event_type: str, 
        handler: Callable[[Any, EventData], None], 
        subscriber_id: str = "unknown",
        priority: EventPriority = EventPriority.NORMAL
    ) -> Self:
        """Alias for on()."""
        return self.on(event_type, handler, subscriber_id, priority)
    
    def unsubscribe(self, event_type: str, subscriber_id: str) -> Self:
        """Alias for off()."""
        return self.off(event_type, subscriber_id)
    
    def _get_or_create_signal(self, event_type: str) -> Signal:
        """Get or create a signal for an event type."""
        if event_type not in self._signals:
            self._signals[event_type] = event_namespace.signal(event_type)
        return self._signals[event_type]
    
    def process_events(self, max_events: int = 100) -> int:
        """Process events in current thread (for tests)."""
        # With blinker, events are processed synchronously on emit
        # This method is kept for API compatibility
        return 0
    
    def get_stats(self) -> dict[str, Any]:
        """Get system statistics."""
        with self._lock:
            return {
                'events_processed': self._stats.events_processed,
                'events_failed': self._stats.events_failed,
                'handlers_registered': self._stats.handlers_registered,
                'subscriptions_active': self._stats.subscriptions_active,
                'queue_size': 0,  # No queue with blinker
                'history_size': len(self._event_history),
                'is_running': self._is_running
            }
    
    def clear_history(self) -> Self:
        """Clear event history."""
        with self._lock:
            self._event_history.clear()
            logger.info("Event history cleared")
        return self
    
    def get_event_history(
        self, 
        event_type: str | None = None,
        limit: int = 100
    ) -> list[EventData]:
        """Get event history."""
        with self._lock:
            if event_type:
                filtered_events = [
                    e for e in self._event_history 
                    if e.event_type == event_type
                ]
            else:
                filtered_events = list(self._event_history)
            
            return filtered_events[-limit:]
