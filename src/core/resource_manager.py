"""In-memory resource manager."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


class ResourceManager:
    def __init__(self) -> None:
        self._resources: Dict[str, Any] = {}

    def add(self, key: str, resource: Any) -> None:
        self._resources[key] = resource

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self._resources.get(key, default)

    def load_text(self, key: str, path: str | Path) -> str:
        content = Path(path).read_text(encoding="utf-8")
        self.add(key, content)
        return content

    def clear(self) -> None:
        self._resources.clear()
