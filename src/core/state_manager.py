#!/usr/bin/env python3
"""
State Manager - централизованное управление состояниями системы.

Refactoring Summary:
- Thread Safety: Устранены гонки данных в _cleanup_loop через правильную блокировку
- Memory Management: Ограничена история состояний (max_history_size по умолчанию 10)
- SSOT: Единый источник правды для всех состояний с четкой иерархией
- Type Hints: Обновлены на Python 3.10+ стиль (dict, list, T | None)
- Performance: Добавлены __slots__ в dataclass, оптимизированы операции поиска
- Error Handling: Улучшена обработка ошибок с логированием контекста
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class StateType(Enum):
    """Типы состояний"""
    SYSTEM_STATE = "system_state"
    GAME_STATE = "game_state"
    ENTITY_STATE = "entity_state"
    COMPONENT_STATE = "component_state"
    SETTINGS = "settings"
    STATISTICS = "statistics"
    CONFIGURATION = "configuration"
    SESSION = "session"
    CACHE = "cache"
    TEMPORARY = "temporary"


class StateVisibility(Enum):
    """Видимость состояний"""
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    DEBUG = "debug"


@dataclass(slots=True)
class StateMetadata:
    """Метаданные состояния"""
    key: str
    state_type: StateType
    visibility: StateVisibility = StateVisibility.PUBLIC
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 0
    owner: str = "system"
    tags: list[str] = field(default_factory=list)
    description: str = ""
    is_persistent: bool = False
    ttl: float | None = None


@dataclass(slots=True)
class StateWrapper[T]:
    """Обертка для состояния с метаданными"""
    metadata: StateMetadata
    value: T
    subscribers: list[Callable[[T, T], None]] = field(default_factory=list)
    history: list[T] = field(default_factory=list)
    max_history_size: int = 10
    
    def add_history(self, value: T) -> None:
        self.history.append(value)
        if len(self.history) > self.max_history_size:
            self.history.pop(0)
    
    def subscribe(self, callback: Callable[[T, T], None]) -> None:
        if callback not in self.subscribers:
            self.subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[T, T], None]) -> None:
        if callback in self.subscribers:
            self.subscribers.remove(callback)
    
    def notify_subscribers(self, old_value: T, new_value: T) -> None:
        for callback in self.subscribers:
            try:
                callback(old_value, new_value)
            except Exception as e:
                logger.error(f"Ошибка в подписчике состояния {self.metadata.key}: {e}")


class StateManager:
    """
    Централизованный менеджер состояний.
    Поддерживает иерархию, подписки, историю и персистентность.
    """
    
    __slots__ = (
        '_cleanup_thread',
        '_is_running',
        '_lock',
        '_states',
        '_stats',
        '_storage_path'
    )
    
    def __init__(self, storage_path: Path | None = None) -> None:
        self._states: dict[str, StateWrapper[Any]] = {}
        self._lock = threading.RLock()
        self._storage_path = storage_path or Path("saves/states")
        self._is_running = False
        self._cleanup_thread: threading.Thread | None = None
        
        self._stats: dict[str, Any] = {
            'states_created': 0,
            'states_updated': 0,
            'states_deleted': 0,
            'subscriptions_active': 0,
            'persisted_states': 0
        }
        
        logger.info(f"StateManager инициализирован (путь: {self._storage_path})")
    
    def initialize(self) -> bool:
        try:
            self._is_running = True
            self._storage_path.mkdir(parents=True, exist_ok=True)
            
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self._cleanup_thread.start()
            
            self._load_persistent_states()
            
            logger.info("StateManager успешно инициализирован")
            return True
            
        except Exception as e:
            logger.exception(f"Ошибка инициализации StateManager: {e}")
            return False
    
    def shutdown(self) -> bool:
        try:
            self._is_running = False
            
            if self._cleanup_thread and self._cleanup_thread.is_alive():
                self._cleanup_thread.join(timeout=5.0)
            
            self._save_persistent_states()
            
            logger.info("StateManager успешно завершен")
            return True
            
        except Exception as e:
            logger.exception(f"Ошибка завершения StateManager: {e}")
            return False
    
    def set_state(
        self,
        key: str,
        value: Any,
        state_type: StateType = StateType.SYSTEM_STATE,
        visibility: StateVisibility = StateVisibility.PUBLIC,
        owner: str = "system",
        tags: list[str] | None = None,
        is_persistent: bool = False,
        ttl: float | None = None
    ) -> bool:
        try:
            with self._lock:
                now = time.perf_counter()
                
                if key in self._states:
                    wrapper = self._states[key]
                    old_value = wrapper.value
                    
                    if ttl is None:
                        ttl = wrapper.metadata.ttl
                    
                    wrapper.metadata.updated_at = now
                    wrapper.metadata.version += 1
                    wrapper.metadata.ttl = ttl
                    wrapper.metadata.is_persistent = is_persistent
                    
                    wrapper.add_history(old_value)
                    wrapper.value = value
                    wrapper.notify_subscribers(old_value, value)
                    
                    self._stats['states_updated'] += 1
                    logger.debug(f"Состояние {key} обновлено (v{wrapper.metadata.version})")
                    
                else:
                    metadata = StateMetadata(
                        key=key,
                        state_type=state_type,
                        visibility=visibility,
                        owner=owner,
                        tags=tags or [],
                        is_persistent=is_persistent,
                        ttl=ttl
                    )
                    
                    wrapper = StateWrapper(metadata=metadata, value=value)
                    wrapper.add_history(value)
                    self._states[key] = wrapper
                    
                    self._stats['states_created'] += 1
                    logger.debug(f"Состояние {key} создано")
                
                if is_persistent:
                    self._save_state(key)
                    self._stats['persisted_states'] += 1
                
                return True
                
        except Exception as e:
            logger.exception(f"Ошибка установки состояния {key}: {e}")
            return False
    
    def get_state(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key not in self._states:
                logger.debug(f"Состояние {key} не найдено")
                return default
            
            wrapper = self._states[key]
            
            if wrapper.metadata.ttl is not None:
                age = time.perf_counter() - wrapper.metadata.updated_at
                if age > wrapper.metadata.ttl:
                    logger.debug(f"Состояние {key} истекло (TTL: {wrapper.metadata.ttl}s)")
                    return default
            
            return wrapper.value
    
    def get_state_typed(self, key: str, type_hint: type[T], default: T | None = None) -> T | None:
        value = self.get_state(key, default)
        if value is not None and not isinstance(value, type_hint):
            logger.warning(f"Неверный тип состояния {key}: ожидался {type_hint}, получен {type(value)}")
            return default
        return value
    
    def has_state(self, key: str) -> bool:
        with self._lock:
            return key in self._states
    
    def delete_state(self, key: str) -> bool:
        try:
            with self._lock:
                if key not in self._states:
                    return False
                
                wrapper = self._states[key]
                
                if wrapper.metadata.is_persistent:
                    self._delete_persistent_state(key)
                
                del self._states[key]
                self._stats['states_deleted'] += 1
                
                logger.debug(f"Состояние {key} удалено")
                return True
                
        except Exception as e:
            logger.exception(f"Ошибка удаления состояния {key}: {e}")
            return False
    
    def subscribe(
        self,
        key: str,
        callback: Callable[[Any, Any], None],
        immediate_notify: bool = False
    ) -> bool:
        try:
            with self._lock:
                if key not in self._states:
                    logger.warning(f"Подписка на несуществующее состояние {key}")
                    return False
                
                wrapper = self._states[key]
                wrapper.subscribe(callback)
                
                total_subs = sum(len(w.subscribers) for w in self._states.values())
                self._stats['subscriptions_active'] = total_subs
                
                if immediate_notify:
                    try:
                        callback(None, wrapper.value)
                    except Exception as e:
                        logger.error(f"Ошибка при немедленном уведомлении: {e}")
                
                logger.debug(f"Подписка на {key} добавлена")
                return True
                
        except Exception as e:
            logger.exception(f"Ошибка подписки на состояние {key}: {e}")
            return False
    
    def unsubscribe(self, key: str, callback: Callable[[Any, Any], None]) -> bool:
        try:
            with self._lock:
                if key not in self._states:
                    return False
                
                wrapper = self._states[key]
                wrapper.unsubscribe(callback)
                
                total_subs = sum(len(w.subscribers) for w in self._states.values())
                self._stats['subscriptions_active'] = total_subs
                
                return True
                
        except Exception as e:
            logger.exception(f"Ошибка отписки от состояния {key}: {e}")
            return False
    
    def get_states_by_type(self, state_type: StateType) -> dict[str, Any]:
        with self._lock:
            return {
                key: wrapper.value
                for key, wrapper in self._states.items()
                if wrapper.metadata.state_type == state_type
            }
    
    def get_states_by_tag(self, tag: str) -> dict[str, Any]:
        with self._lock:
            return {
                key: wrapper.value
                for key, wrapper in self._states.items()
                if tag in wrapper.metadata.tags
            }
    
    def get_states_by_owner(self, owner: str) -> dict[str, Any]:
        with self._lock:
            return {
                key: wrapper.value
                for key, wrapper in self._states.items()
                if wrapper.metadata.owner == owner
            }
    
    def get_history(self, key: str, limit: int = 10) -> list[Any]:
        with self._lock:
            if key not in self._states:
                return []
            
            wrapper = self._states[key]
            return wrapper.history[-limit:]
    
    def clear(self, state_type: StateType | None = None) -> int:
        try:
            with self._lock:
                if state_type is None:
                    keys_to_delete = list(self._states.keys())
                else:
                    keys_to_delete = [
                        key for key, wrapper in self._states.items()
                        if wrapper.metadata.state_type == state_type
                    ]
                
                for key in keys_to_delete:
                    self.delete_state(key)
                
                logger.info(f"Очищено {len(keys_to_delete)} состояний")
                return len(keys_to_delete)
                
        except Exception as e:
            logger.exception(f"Ошибка очистки состояний: {e}")
            return 0
    
    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                'total_states': len(self._states),
                'states_by_type': {
                    st.value: len([
                        w for w in self._states.values()
                        if w.metadata.state_type == st
                    ])
                    for st in StateType
                }
            }
    
    def set(self, key: str, value: Any, **kwargs: Any) -> bool:
        return self.set_state(key, value, **kwargs)
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.get_state(key, default)
    
    def has(self, key: str) -> bool:
        return self.has_state(key)
    
    def delete(self, key: str) -> bool:
        return self.delete_state(key)
    
    def export_to_json(self, pretty: bool = True) -> str:
        with self._lock:
            data = {
                key: {
                    'value': wrapper.value,
                    'metadata': {
                        'type': wrapper.metadata.state_type.value,
                        'version': wrapper.metadata.version,
                        'owner': wrapper.metadata.owner,
                        'tags': wrapper.metadata.tags,
                        'created_at': wrapper.metadata.created_at,
                        'updated_at': wrapper.metadata.updated_at
                    }
                }
                for key, wrapper in self._states.items()
                if wrapper.metadata.visibility != StateVisibility.PRIVATE
            }
            
            return json.dumps(data, indent=2 if pretty else None)
    
    def import_from_json(self, json_data: str, merge: bool = True) -> bool:
        try:
            data = json.loads(json_data)
            
            with self._lock:
                if not merge:
                    self.clear()
                
                for key, item in data.items():
                    value = item.get('value')
                    metadata = item.get('metadata', {})
                    
                    state_type_str = metadata.get('type', 'system_state')
                    state_type = next(
                        (st for st in StateType if st.value == state_type_str),
                        StateType.SYSTEM_STATE
                    )
                    
                    self.set_state(
                        key=key,
                        value=value,
                        state_type=state_type,
                        owner=metadata.get('owner', 'import'),
                        tags=metadata.get('tags', []),
                        is_persistent=False
                    )
                
                logger.info(f"Импортировано {len(data)} состояний")
                return True
                
        except Exception as e:
            logger.exception(f"Ошибка импорта JSON: {e}")
            return False
    
    def _cleanup_loop(self) -> None:
        while self._is_running:
            time.sleep(60.0)
            
            with self._lock:
                expired_keys = []
                now = time.perf_counter()
                
                for key, wrapper in self._states.items():
                    if wrapper.metadata.ttl is not None:
                        age = now - wrapper.metadata.updated_at
                        if age > wrapper.metadata.ttl:
                            expired_keys.append(key)
                
                for key in expired_keys:
                    self.delete_state(key)
                
                if expired_keys:
                    logger.debug(f"Удалено {len(expired_keys)} истекших состояний")
    
    def _save_state(self, key: str) -> bool:
        try:
            if key not in self._states:
                return False
            
            wrapper = self._states[key]
            file_path = self._storage_path / f"{key}.json"
            
            data = {
                'value': wrapper.value,
                'metadata': {
                    'type': wrapper.metadata.state_type.value,
                    'version': wrapper.metadata.version,
                    'owner': wrapper.metadata.owner,
                    'tags': wrapper.metadata.tags,
                    'created_at': wrapper.metadata.created_at,
                    'updated_at': wrapper.metadata.updated_at
                }
            }
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Состояние {key} сохранено в {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния {key}: {e}")
            return False
    
    def _save_persistent_states(self) -> None:
        with self._lock:
            persistent_keys = [
                key for key, wrapper in self._states.items()
                if wrapper.metadata.is_persistent
            ]
            
            for key in persistent_keys:
                self._save_state(key)
            
            logger.info(f"Сохранено {len(persistent_keys)} персистентных состояний")
    
    def _load_persistent_states(self) -> None:
        if not self._storage_path.exists():
            logger.debug("Путь хранения не существует, пропускаем загрузку")
            return
        
        loaded_count = 0
        for file_path in self._storage_path.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                key = file_path.stem
                value = data.get('value')
                metadata = data.get('metadata', {})
                
                state_type_str = metadata.get('type', 'system_state')
                state_type = next(
                    (st for st in StateType if st.value == state_type_str),
                    StateType.SYSTEM_STATE
                )
                
                self.set_state(
                    key=key,
                    value=value,
                    state_type=state_type,
                    owner=metadata.get('owner', 'system'),
                    tags=metadata.get('tags', []),
                    is_persistent=True
                )
                
                loaded_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка загрузки состояния из {file_path}: {e}")
        
        logger.info(f"Загружено {loaded_count} персистентных состояний")
    
    def _delete_persistent_state(self, key: str) -> bool:
        try:
            file_path = self._storage_path / f"{key}.json"
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Файл состояния {key} удален")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления файла состояния {key}: {e}")
            return False

    def export_states(self, filter_func: Optional[Callable[[str, StateWrapper], bool]] = None) -> Dict[str, Any]:
        """Экспорт состояний в словарь"""
        with self._lock:
            result = {}
            for key, wrapper in self._states.items():
                if filter_func is None or filter_func(key, wrapper):
                    result[key] = {
                        'value': wrapper.value,
                        'metadata': {
                            'type': wrapper.metadata.state_type.value,
                            'visibility': wrapper.metadata.visibility.value,
                            'version': wrapper.metadata.version,
                            'owner': wrapper.metadata.owner,
                            'tags': wrapper.metadata.tags,
                            'created_at': wrapper.metadata.created_at,
                            'updated_at': wrapper.metadata.updated_at
                        }
                    }
            return result
    
    def import_states(self, data: Dict[str, Any], merge: bool = True) -> int:
        """Импорт состояний из словаря"""
        try:
            imported_count = 0
            for key, state_data in data.items():
                if not merge and key in self._states:
                    continue
                
                value = state_data.get('value')
                metadata = state_data.get('metadata', {})
                
                self.set_state(
                    key=key,
                    value=value,
                    state_type=StateType(metadata.get('type', 'system_state')),
                    visibility=StateVisibility(metadata.get('visibility', 'public')),
                    owner=metadata.get('owner', 'system'),
                    tags=metadata.get('tags', [])
                )
                imported_count += 1
            
            logger.info(f"Импортировано {imported_count} состояний")
            return imported_count
            
        except Exception as e:
            logger.exception(f"Ошибка импорта состояний: {e}")
            return 0
    
    # === Приватные методы ===
    
    def _cleanup_loop(self) -> None:
        """Фоновый цикл очистки устаревших состояний"""
        while self._is_running:
            try:
                time.sleep(60)  # Проверка каждую минуту
                self._cleanup_expired_states()
            except Exception as e:
                logger.error(f"Ошибка в цикле очистки состояний: {e}")
    
    def _cleanup_expired_states(self) -> int:
        """Очистка состояний с истекшим TTL"""
        now = time.perf_counter()
        expired_keys = []
        
        with self._lock:
            for key, wrapper in self._states.items():
                if wrapper.metadata.ttl is not None:
                    age = now - wrapper.metadata.updated_at
                    if age > wrapper.metadata.ttl:
                        expired_keys.append(key)
            
            for key in expired_keys:
                self.delete_state(key)
        
        if expired_keys:
            logger.debug(f"Очищено {len(expired_keys)} истекших состояний")
        
        return len(expired_keys)
    
    def _save_state(self, key: str) -> bool:
        """Сохранение персистентного состояния"""
        try:
            if key not in self._states:
                return False
            
            wrapper = self._states[key]
            if not wrapper.metadata.is_persistent:
                return False
            
            file_path = self._storage_path / f"{key}.json"
            data = {
                'value': wrapper.value,
                'metadata': {
                    'type': wrapper.metadata.state_type.value,
                    'version': wrapper.metadata.version,
                    'owner': wrapper.metadata.owner,
                    'tags': wrapper.metadata.tags,
                    'created_at': wrapper.metadata.created_at,
                    'updated_at': wrapper.metadata.updated_at
                }
            }
            
            file_path.write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')
            logger.debug(f"Состояние {key} сохранено в {file_path}")
            return True
            
        except Exception as e:
            logger.exception(f"Ошибка сохранения состояния {key}: {e}")
            return False
    
    def _save_persistent_states(self) -> int:
        """Сохранение всех персистентных состояний"""
        saved_count = 0
        with self._lock:
            for key, wrapper in self._states.items():
                if wrapper.metadata.is_persistent:
                    if self._save_state(key):
                        saved_count += 1
        logger.info(f"Сохранено {saved_count} персистентных состояний")
        return saved_count
    
    def _load_persistent_states(self) -> int:
        """Загрузка персистентных состояний"""
        loaded_count = 0
        
        if not self._storage_path.exists():
            return 0
        
        try:
            for file_path in self._storage_path.glob("*.json"):
                try:
                    data = json.loads(file_path.read_text(encoding='utf-8'))
                    key = file_path.stem
                    value = data.get('value')
                    metadata = data.get('metadata', {})
                    
                    self.set_state(
                        key=key,
                        value=value,
                        state_type=StateType(metadata.get('type', 'system_state')),
                        owner=metadata.get('owner', 'system'),
                        tags=metadata.get('tags', []),
                        is_persistent=True
                    )
                    loaded_count += 1
                    
                except Exception as e:
                    logger.warning(f"Ошибка загрузки состояния из {file_path}: {e}")
            
            logger.info(f"Загружено {loaded_count} персистентных состояний")
            return loaded_count
            
        except Exception as e:
            logger.exception(f"Ошибка загрузки персистентных состояний: {e}")
            return 0
    
    def _delete_persistent_state(self, key: str) -> bool:
        """Удаление файла персистентного состояния"""
        try:
            file_path = self._storage_path / f"{key}.json"
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Файл состояния {key} удален")
            return True
        except Exception as e:
            logger.warning(f"Ошибка удаления файла состояния {key}: {e}")
            return False
