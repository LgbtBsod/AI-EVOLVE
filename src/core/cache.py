"""
LRU Cache with TTL
Кэширование с вытеснением наименее используемых элементов и временем жизни.
Применяется для оптимизации AttributeSystem и других тяжелых вычислений.
"""
import time
import threading
from typing import Any, Dict, Optional, Tuple
from collections import OrderedDict


class LRUCache:
    """
    Потокобезопасный LRU кэш с поддержкой TTL (Time To Live).
    
    Args:
        max_size: Максимальное количество элементов в кэше.
        default_ttl: Время жизни элемента в секундах (None = бесконечно).
    """
    
    def __init__(self, max_size: int = 128, default_ttl: Optional[float] = None, capacity: Optional[int] = None):
        # Поддержка старого параметра capacity для обратной совместимости
        if capacity is not None:
            max_size = capacity
        
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.capacity = max_size  # Алиас для совместимости
        
        self._cache: OrderedDict[Any, Tuple[Any, float]] = OrderedDict()
        self._lock = threading.RLock()
        
        # Статистика
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: Any) -> Optional[Any]:
        """
        Получает значение из кэша.
        Возвращает None, если ключ не найден или истекло время жизни.
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, expiry = self._cache[key]
            
            # Проверка TTL
            if expiry is not None and time.time() > expiry:
                del self._cache[key]
                self._misses += 1
                return None
            
            # Перемещаем в конец (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        """
        Устанавливает значение в кэш.
        """
        with self._lock:
            # Если ключ уже есть, обновляем и перемещаем в конец
            if key in self._cache:
                self._cache.move_to_end(key)
            
            # Вычисляем время истечения
            expiry = None
            if ttl is not None or self.default_ttl is not None:
                expiry = time.time() + (ttl if ttl is not None else self.default_ttl)
            
            self._cache[key] = (value, expiry)
            
            # Вытеснение старых элементов при превышении размера
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

    def delete(self, key: Any) -> bool:
        """Удаляет элемент из кэша."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Очищает весь кэш."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """
        Удаляет все истекшие элементы.
        Возвращает количество удаленных элементов.
        """
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, (_, expiry) in self._cache.items()
                if expiry is not None and now > expiry
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            return len(expired_keys)

    @property
    def size(self) -> int:
        """Текущий размер кэша."""
        return len(self._cache)

    @property
    def hits(self) -> int:
        """Количество попаданий."""
        return self._hits
    
    @property
    def misses(self) -> int:
        """Количество промахов."""
        return self._misses
    
    @property
    def hit_rate(self) -> float:
        """Процент попаданий."""
        total = self._hits + self._misses
        return (self._hits / total) if total > 0 else 0.0
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Статистика кэша."""
        return {
            "size": self.size,
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate_percent": round(self.hit_rate * 100, 2)
        }

    def __contains__(self, key: Any) -> bool:
        """Проверка наличия ключа (с учетом TTL)."""
        return self.get(key) is not None

    def __len__(self) -> int:
        return self.size

    def __repr__(self) -> str:
        return f"LRUCache(size={self.size}/{self.max_size}, hits={self._hits}, misses={self._misses})"


# Декоратор для кэширования функций
def cached(
    max_size: int = 128,
    ttl: Optional[float] = None,
    key_func: Optional[callable] = None
):
    """
    Декоратор для кэширования результатов функции.
    
    Args:
        max_size: Размер кэша.
        ttl: Время жизни кэша.
        key_func: Функция для генерации ключа (по умолчанию args+kwargs).
    """
    cache = LRUCache(max_size=max_size, default_ttl=ttl)
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Генерация ключа
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = str((args, sorted(kwargs.items())))
            
            result = cache.get(key)
            if result is not None:
                return result
            
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result
        
        wrapper.cache = cache  # Доступ к кэшу для мониторинга
        return wrapper
    
    return decorator
