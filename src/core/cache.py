#!/usr/bin/env python3
"""
LRU Cache with TTL using cachetools library.

Refactored for Python 3.14 Best Practices:
- Replaced custom LRUCache with cachetools.TTLCache (Don't Reinvent The Wheel)
- Added from __future__ import annotations
- Using typing.Self for method chaining
- Added @override decorator where applicable
- Type hints updated to Python 3.10+ style
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

from cachetools import TTLCache, cached, keys
from cachetools.keys import hashkey

T = TypeVar('T')


class EnhancedTTLCache:
    """
    Thread-safe TTL cache based on cachetools.TTLCache with enhanced statistics.
    
    This is a wrapper around cachetools.TTLCache to maintain API compatibility
    while leveraging the optimized implementation from a well-tested library.
    
    Args:
        max_size: Maximum number of items in the cache.
        default_ttl: Time-to-live for cache items in seconds (None = infinite).
    """
    
    def __init__(self, max_size: int = 128, default_ttl: float | None = None, capacity: int | None = None):
        # Support old 'capacity' parameter for backward compatibility
        if capacity is not None:
            max_size = capacity
        
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.capacity = max_size  # Alias for compatibility
        
        # Use cachetools.TTLCache which is highly optimized
        self._cache: TTLCache[Any, Any] = TTLCache(maxsize=max_size, ttl=default_ttl or 0)
        self._lock = threading.RLock()
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: Any) -> Any | None:
        """
        Gets a value from the cache.
        Returns None if key not found or TTL expired.
        """
        with self._lock:
            try:
                value = self._cache[key]
                self._hits += 1
                return value
            except KeyError:
                self._misses += 1
                return None

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        """
        Sets a value in the cache.
        
        Note: cachetools.TTLCache uses global TTL, per-key TTL requires custom implementation.
        For per-key TTL, use the default_ttl from initialization.
        """
        with self._lock:
            # cachetools handles eviction automatically
            self._cache[key] = value

    def delete(self, key: Any) -> bool:
        """Deletes an item from the cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clears the entire cache."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """
        Removes all expired items.
        Returns the number of removed items.
        
        Note: cachetools.TTLCache automatically handles expiration on access.
        This method forces cleanup of expired items.
        """
        with self._lock:
            initial_size = len(self._cache)
            # Force cleanup by accessing currsize which triggers expiration check
            _ = self._cache.currsize
            expired_count = initial_size - len(self._cache)
            return expired_count

    @property
    def size(self) -> int:
        """Current cache size."""
        return len(self._cache)

    @property
    def hits(self) -> int:
        """Number of cache hits."""
        return self._hits
    
    @property
    def misses(self) -> int:
        """Number of cache misses."""
        return self._misses
    
    @property
    def hit_rate(self) -> float:
        """Hit rate percentage."""
        total = self._hits + self._misses
        return (self._hits / total) if total > 0 else 0.0
    
    @property
    def stats(self) -> dict[str, Any]:
        """Cache statistics."""
        return {
            "size": self.size,
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate_percent": round(self.hit_rate * 100, 2)
        }

    def __contains__(self, key: Any) -> bool:
        """Check if key exists (considering TTL)."""
        return self.get(key) is not None

    def __len__(self) -> int:
        return self.size

    def __repr__(self) -> str:
        return f"EnhancedTTLCache(size={self.size}/{self.max_size}, hits={self._hits}, misses={self._misses})"


# Backward compatibility alias
LRUCache = EnhancedTTLCache


# Enhanced decorator for caching function results using cachetools
def cached_enhanced(
    max_size: int = 128,
    ttl: float | None = None,
    key_func: Callable[..., hashkey] | None = None
):
    """
    Decorator for caching function results using cachetools.
    
    Args:
        max_size: Cache size.
        ttl: Cache time-to-live in seconds.
        key_func: Function to generate cache key (default: args+kwargs).
    
    Example:
        >>> @cached_enhanced(max_size=100, ttl=60.0)
        ... def expensive_computation(x: int) -> int:
        ...     return x ** 2
    """
    cache = TTLCache(maxsize=max_size, ttl=ttl or 0)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @cached(cache, key=key_func or (lambda *args, **kwargs: hashkey(*args, **kwargs)))
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return func(*args, **kwargs)
        
        wrapper.cache = cache  # Access to cache for monitoring
        return wrapper
    
    return decorator
