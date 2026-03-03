"""Adapter for bridging EventSystem to event-bus like API."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .event_system import EventPriority, EventSystem


class EventBusAdapter:
    def __init__(self, event_system: EventSystem):
        self._event_system = event_system

    def on(self, event_type: str, handler: Callable, priority: Optional[Any] = None) -> bool:
        prio = priority if isinstance(priority, EventPriority) else EventPriority.NORMAL
        subscriber_id = getattr(handler, "__name__", "subscriber")
        return self._event_system.subscribe(event_type, handler, subscriber_id, prio)

    def emit(self, event_type: str, data: Optional[Dict[str, Any]] = None, priority: Optional[Any] = None) -> bool:
        prio = priority if isinstance(priority, EventPriority) else EventPriority.NORMAL
        return self._event_system.emit_event(event_type, data or {}, "event_bus_adapter", prio)
