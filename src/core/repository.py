"""Repository primitives used by architecture components."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class DataType(Enum):
    GENERIC = "generic"
    STATE = "state"
    ENTITY = "entity"


class StorageType(Enum):
    MEMORY = "memory"


@dataclass
class Repository:
    repository_id: str
    data_type: DataType = DataType.GENERIC
    storage_type: StorageType = StorageType.MEMORY
    _storage: Dict[str, Any] = field(default_factory=dict)

    def store(self, key: str, data: Any) -> bool:
        self._storage[key] = data
        return True

    def retrieve(self, key: str) -> Optional[Any]:
        return self._storage.get(key)

    def delete(self, key: str) -> bool:
        return self._storage.pop(key, None) is not None

    def clear(self) -> bool:
        self._storage.clear()
        return True


class RepositoryManager:
    def __init__(self) -> None:
        self._repositories: Dict[str, Repository] = {}

    def create_repository(self, repository_id: str, data_type: DataType = DataType.GENERIC,
                          storage_type: StorageType = StorageType.MEMORY) -> Repository:
        repo = Repository(repository_id, data_type, storage_type)
        self._repositories[repository_id] = repo
        return repo

    def get_repository(self, repository_id: str) -> Optional[Repository]:
        return self._repositories.get(repository_id)
