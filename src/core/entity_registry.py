"""Global entity registry utilities."""
from __future__ import annotations

from threading import RLock
from typing import Any, Dict, Optional

_lock = RLock()
_registry: Dict[str, Any] = {}


def register_entity(entity_id: str, entity_obj: Any) -> None:
    with _lock:
        _registry[entity_id] = entity_obj


def unregister_entity(entity_id: str) -> None:
    with _lock:
        _registry.pop(entity_id, None)


def get_entity(entity_id: str) -> Optional[Any]:
    with _lock:
        return _registry.get(entity_id)


def clear() -> None:
    with _lock:
        _registry.clear()
