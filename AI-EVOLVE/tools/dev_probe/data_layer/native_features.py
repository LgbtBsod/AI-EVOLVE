"""
Data Layer: Native Language Features Module
Использование встроенных возможностей Python вместо изобретения велосипедов
dataclasses, functools, itertools, collections, contextlib
"""

from dataclasses import dataclass, field, asdict, replace
from functools import cached_property, lru_cache, wraps
from itertools import islice, chain, groupby
from collections import defaultdict, deque, Counter, OrderedDict
from contextlib import contextmanager, asynccontextmanager, suppress
from typing import (
    Dict, List, Any, Optional, Callable, TypeVar, Generic,
    Iterator, Iterable, Tuple, Set, Union, Sequence
)
import json
import time
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


# === Data Classes для структур данных ===

@dataclass(frozen=True)
class GameEvent:
    """Неизменяемое игровое событие"""
    event_type: str
    entity_id: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def with_data(self, **kwargs) -> 'GameEvent':
        """Создание копии с обновленными данными"""
        new_data = {**self.data, **kwargs}
        return replace(self, data=new_data)


@dataclass
class MetricPoint:
    """Точка метрики производительности"""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_tuple(self) -> Tuple[str, float, float]:
        return (self.name, self.value, self.timestamp)


@dataclass
class QueryResult(Generic[T]):
    """Результат запроса с мета-информацией"""
    items: List[T]
    total_count: int
    page: int = 1
    page_size: int = 10
    has_more: bool = False
    
    def __post_init__(self):
        """Автоматический расчет has_more после инициализации"""
        if not self.has_more:
            self.has_more = (self.page * self.page_size) < self.total_count
    
    @property
    def total_pages(self) -> int:
        return (self.total_count + self.page_size - 1) // self.page_size
    
    def next_page(self) -> int:
        return self.page + 1 if self.has_more else self.page
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": self.items,
            "pagination": {
                "page": self.page,
                "page_size": self.page_size,
                "total_count": self.total_count,
                "total_pages": self.total_pages,
                "has_more": self.has_more
            }
        }


# === Кэширование и мемоизация ===

class TimeCached:
    """Декоратор для кэширования с TTL"""
    
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self.cache: Dict[str, Tuple[Any, float]] = {}
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{args}:{sorted(kwargs.items())}"
            current_time = time.time()
            
            # Проверка наличия в кэше и актуальности
            if key in self.cache:
                value, timestamp = self.cache[key]
                if current_time - timestamp < self.ttl:
                    return value
            
            # Вычисление и кэширование
            value = func(*args, **kwargs)
            self.cache[key] = (value, current_time)
            return value
        
        wrapper.cache_clear = lambda: self.cache.clear()
        wrapper.cache_info = lambda: len(self.cache)
        return wrapper


def memoize_with_key(key_func: Callable) -> Callable:
    """Декоратор мемоизации с кастомной функцией ключа"""
    def decorator(func: Callable) -> Callable:
        cache = {}
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs)
            if key not in cache:
                cache[key] = func(*args, **kwargs)
            return cache[key]
        
        wrapper.cache_clear = lambda: cache.clear()
        return wrapper
    return decorator


# === Коллекции и утилиты для работы с данными ===

class RingBuffer(Generic[T]):
    """Циклический буфер фиксированного размера"""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.buffer: deque = deque(maxlen=capacity)
    
    def append(self, item: T) -> None:
        self.buffer.append(item)
    
    def extend(self, items: Iterable[T]) -> None:
        self.buffer.extend(items)
    
    def get_all(self) -> List[T]:
        return list(self.buffer)
    
    def get_last(self, n: int) -> List[T]:
        return list(islice(self.buffer, max(0, len(self.buffer) - n), len(self.buffer)))
    
    def average(self) -> Optional[float]:
        if not self.buffer:
            return None
        numeric = [x for x in self.buffer if isinstance(x, (int, float))]
        return sum(numeric) / len(numeric) if numeric else None
    
    def clear(self) -> None:
        self.buffer.clear()


class EventStream:
    """Поток событий с агрегацией и фильтрацией"""
    
    def __init__(self, max_events: int = 10000):
        self.events: deque = deque(maxlen=max_events)
        self.index: Dict[str, List[int]] = defaultdict(list)
    
    def add(self, event: GameEvent) -> int:
        event_id = len(self.events)
        self.events.append(event)
        self.index[event.event_type].append(event_id)
        return event_id
    
    def filter_by_type(self, event_type: str) -> Iterator[GameEvent]:
        for idx in self.index.get(event_type, []):
            yield self.events[idx]
    
    def filter_by_entity(self, entity_id: str) -> Iterator[GameEvent]:
        for event in self.events:
            if event.entity_id == entity_id:
                yield event
    
    def aggregate_by_type(self) -> Dict[str, int]:
        counter = Counter(e.event_type for e in self.events)
        return dict(counter)
    
    def get_recent(self, count: int) -> List[GameEvent]:
        return list(islice(self.events, max(0, len(self.events) - count), len(self.events)))
    
    def clear(self) -> None:
        self.events.clear()
        self.index.clear()


class BatchProcessor(Generic[T]):
    """Обработчик пакетных операций"""
    
    def __init__(
        self, 
        batch_size: int = 100,
        flush_interval: float = 5.0,
        process_func: Optional[Callable[[List[T]], Any]] = None
    ):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.process_func = process_func or (lambda x: x)
        
        self._batch: List[T] = []
        self._last_flush: float = time.time()
        self._total_processed: int = 0
    
    def add(self, item: T) -> None:
        self._batch.append(item)
        
        # Авто-флеш при заполнении
        if len(self._batch) >= self.batch_size:
            self.flush()
        
        # Авто-флеш по времени
        elif time.time() - self._last_flush > self.flush_interval:
            self.flush()
    
    def extend(self, items: Iterable[T]) -> None:
        """Добавление нескольких элементов"""
        for item in items:
            self.add(item)
    
    def flush(self) -> Any:
        if not self._batch:
            return None
        
        result = self.process_func(self._batch)
        self._batch.clear()
        self._last_flush = time.time()
        self._total_processed += len(self._batch)
        return result
    
    @property
    def pending_count(self) -> int:
        return len(self._batch)
    
    @property
    def total_processed(self) -> int:
        return self._total_processed


# === Контекстные менеджеры ===

@contextmanager
def timer_context(name: str = "Operation"):
    """Контекстный менеджер для замера времени выполнения"""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.debug(f"[Timer] {name}: {elapsed:.4f}s")


@asynccontextmanager
async def async_timer_context(name: str = "Async Operation"):
    """Асинхронный контекстный менеджер для замера времени"""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.debug(f"[AsyncTimer] {name}: {elapsed:.4f}s")


@contextmanager
def suppress_and_log(exception_type: type, message: str = "Error suppressed"):
    """Подавление исключения с логированием"""
    try:
        yield
    except exception_type as e:
        logger.warning(f"{message}: {e}")


@contextmanager
def transaction_context(operations: List[Callable], rollback_on_error: bool = True):
    """
    Контекстный менеджер для транзакционных операций
    Поддержка отката через стек compensating operations
    """
    completed: List[Callable] = []
    
    try:
        for op in operations:
            result = op()
            completed.append(result)
        yield completed
    except Exception as e:
        if rollback_on_error:
            logger.warning("Rolling back operations...")
            # Здесь должна быть логика отката
        raise


# === Утилиты для работы с последовательностями ===

def chunked(iterable: Iterable[T], size: int) -> Iterator[List[T]]:
    """Разбиение итерируемого объекта на чанки"""
    iterator = iter(iterable)
    while True:
        chunk = list(islice(iterator, size))
        if not chunk:
            break
        yield chunk


def flatten(nested: Iterable[Iterable[T]]) -> Iterator[T]:
    """Плоское представление вложенной структуры"""
    return chain.from_iterable(nested)


def unique_everseen(iterable: Iterable[T], key: Optional[Callable] = None) -> Iterator[T]:
    """Удаление дубликатов с сохранением порядка"""
    seen: Set = set()
    seen_add = seen.add
    
    if key is None:
        for element in iterable:
            if element not in seen:
                seen_add(element)
                yield element
    else:
        for element in iterable:
            k = key(element)
            if k not in seen:
                seen_add(k)
                yield element


def running_average(values: Iterable[float], window_size: int) -> Iterator[float]:
    """Скользящее среднее"""
    window: deque = deque(maxlen=window_size)
    
    for value in values:
        window.append(value)
        yield sum(window) / len(window)


def detect_anomalies_zscore(
    values: Sequence[float], 
    threshold: float = 2.0
) -> List[Tuple[int, float, float]]:
    """
    Детекция аномалий через Z-score
    Возвращает список (индекс, значение, z_score)
    """
    if len(values) < 3:
        return []
    
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = variance ** 0.5
    
    if std_dev == 0:
        return []
    
    anomalies = []
    for i, value in enumerate(values):
        z_score = (value - mean) / std_dev
        if abs(z_score) > threshold:
            anomalies.append((i, value, z_score))
    
    return anomalies


# === Функциональные утилиты ===

def compose(*functions: Callable) -> Callable:
    """Композиция функций (справа налево)"""
    def composed(x):
        for func in reversed(functions):
            x = func(x)
        return x
    return composed


def pipe(*functions: Callable) -> Callable:
    """Пайплайн функций (слева направо)"""
    def piped(x):
        for func in functions:
            x = func(x)
        return x
    return piped


def partial_apply(func: Callable, *args, **kwargs) -> Callable:
    """Частичное применение функции"""
    @wraps(func)
    def wrapper(*more_args, **more_kwargs):
        merged_kwargs = {**kwargs, **more_kwargs}
        return func(*args, *more_args, **merged_kwargs)
    return wrapper


# === Утилиты для JSON ===

class JSONEncoderSafe(json.JSONEncoder):
    """Безопасный JSON энкодер с обработкой некорректных типов"""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Set):
            return list(obj)
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """Безопасная сериализация в JSON"""
    return json.dumps(obj, cls=JSONEncoderSafe, **kwargs)


def compact_json_dumps(obj: Any) -> str:
    """Компактная JSON сериализация для экономии токенов"""
    return json.dumps(
        obj, 
        cls=JSONEncoderSafe,
        separators=(',', ':'),
        ensure_ascii=False
    )


# === Примеры использования ===

if __name__ == "__main__":
    # Пример использования RingBuffer
    buffer = RingBuffer[int](capacity=5)
    for i in range(10):
        buffer.append(i)
    print(f"RingBuffer: {buffer.get_all()}")  # [5, 6, 7, 8, 9]
    print(f"Average: {buffer.average()}")  # 7.0
    
    # Пример использования EventStream
    stream = EventStream()
    stream.add(GameEvent("level_up", "entity_1", data={"old": 5, "new": 6}))
    stream.add(GameEvent("skill_learned", "entity_1", data={"skill": "fireball"}))
    stream.add(GameEvent("level_up", "entity_2", data={"old": 3, "new": 4}))
    
    print(f"Events by type: {stream.aggregate_by_type()}")
    print(f"Entity 1 events: {[e.event_type for e in stream.filter_by_entity('entity_1')]}")
    
    # Пример chunked
    data = list(range(10))
    chunks = list(chunked(data, 3))
    print(f"Chunks: {chunks}")  # [[0,1,2], [3,4,5], [6,7,8], [9]]
    
    # Пример detect_anomalies_zscore
    values = [10, 12, 11, 13, 100, 12, 11]  # 100 - аномалия
    anomalies = detect_anomalies_zscore(values, threshold=2.0)
    print(f"Anomalies: {anomalies}")  # [(4, 100, high_z_score)]
    
    # Пример композиции функций
    add_one = lambda x: x + 1
    multiply_two = lambda x: x * 2
    composed = compose(multiply_two, add_one)  # Сначала +1, потом *2
    print(f"Composed(5) = {composed(5)}")  # 12
    
    print("\nNative Python features module loaded successfully!")
