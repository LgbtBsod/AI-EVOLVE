#!/usr/bin/env python3
"""Утилиты для проекта AI-EVOLVE - переиспользуемые функции"""

import logging
import math
import random
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

# ============================================================================
# КОЛЛЕКЦИИ
# ============================================================================

def safe_get(dictionary: dict, key: str, default: Any = None) -> Any:
    """Безопасное получение значения из словаря"""
    return dictionary.get(key, default)

def merge_dicts(base: dict, override: dict) -> dict:
    """Слияние словарей с приоритетом override"""
    result = base.copy()
    result.update(override)
    return result

def flatten_list(nested_list: list[Any]) -> list[Any]:
    """Рекурсивное выравнивание списка"""
    result = []
    for item in nested_list:
        if isinstance(item, list):
            result.extend(flatten_list(item))
        else:
            result.append(item)
    return result

def chunk_list(lst: list[T], size: int) -> list[list[T]]:
    """Разбиение списка на части"""
    return [lst[i:i + size] for i in range(0, len(lst), size)]

def group_by(items: list[dict], key: str) -> dict[Any, list]:
    """Группировка списка словарей по ключу"""
    grouped = defaultdict(list)
    for item in items:
        grouped[item.get(key)].append(item)
    return dict(grouped)

# ============================================================================
# МАТЕМАТИКА
# ============================================================================

def clamp(value: float, min_value: float, max_value: float) -> float:
    """Ограничение значения диапазоном"""
    return max(min_value, min(max_value, value))

def lerp(start: float, end: float, t: float) -> float:
    """Линейная интерполяция"""
    return start + (end - start) * clamp(t, 0.0, 1.0)

def distance_2d(pos1: tuple[float, float], pos2: tuple[float, float]) -> float:
    """Расстояние между двумя точками в 2D"""
    dx = pos2[0] - pos1[0]
    dy = pos2[1] - pos1[1]
    return math.sqrt(dx * dx + dy * dy)

def normalize_vector(x: float, y: float) -> tuple[float, float]:
    """Нормализация вектора"""
    length = math.sqrt(x * x + y * y)
    if length == 0:
        return (0.0, 0.0)
    return (x / length, y / length)

def random_range(min_val: float, max_val: float) -> float:
    """Случайное число в диапазоне"""
    return random.uniform(min_val, max_val)

def random_choice(items: list[T]) -> T | None:
    """Случайный выбор из списка"""
    if not items:
        return None
    return random.choice(items)

def weighted_choice(items: list[tuple[T, float]]) -> T | None:
    """Взвешенный случайный выбор"""
    if not items:
        return None
    total_weight = sum(weight for _, weight in items)
    if total_weight == 0:
        return random.choice([item for item, _ in items])
    
    r = random.uniform(0, total_weight)
    current = 0
    for item, weight in items:
        current += weight
        if r <= current:
            return item
    return items[-1][0]

# ============================================================================
# СТРОКИ
# ============================================================================

def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Обрезка строки с суффиксом"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def format_number(num: float, decimals: int = 2) -> str:
    """Форматирование числа"""
    return f"{num:.{decimals}f}"

def generate_id(prefix: str = "") -> str:
    """Генерация уникального ID"""
    timestamp = int(time.perf_counter() * 1000)
    random_suffix = random.randint(1000, 9999)
    return f"{prefix}{timestamp}_{random_suffix}"

# ============================================================================
# ВАЛИДАЦИЯ
# ============================================================================

def is_valid_number(value: Any) -> bool:
    """Проверка на число"""
    return isinstance(value, (int, float)) and not math.isnan(value)

def is_positive_number(value: Any) -> bool:
    """Проверка на положительное число"""
    return is_valid_number(value) and value > 0

def is_in_range(value: float, min_val: float, max_val: float) -> bool:
    """Проверка попадания в диапазон"""
    return min_val <= value <= max_val

def validate_dict(data: dict, required_keys: list[str]) -> tuple[bool, list[str]]:
    """Валидация словаря на наличие обязательных ключей"""
    missing_keys = [key for key in required_keys if key not in data]
    return len(missing_keys) == 0, missing_keys

# ============================================================================
# ВРЕМЯ
# ============================================================================

def get_timestamp() -> float:
    """Получение текущей метки времени"""
    return time.perf_counter()

def get_timestamp_ms() -> int:
    """Получение текущей метки времени в миллисекундах"""
    return int(time.perf_counter() * 1000)

def format_duration(seconds: float) -> str:
    """Форматирование длительности"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

# ============================================================================
# ДЕКОРАТОРЫ
# ============================================================================

def retry(max_attempts: int = 3, delay: float = 1.0):
    """Декоратор повторных попыток"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Попытка {attempt + 1}/{max_attempts} не удалась: {e}")
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

def timing(func: Callable) -> Callable:
    """Декоратор замера времени выполнения"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        logger.debug(f"{func.__name__} выполнено за {end_time - start_time:.4f}s")
        return result
    return wrapper

def singleton(cls: type) -> Callable:
    """Декоратор синглтона"""
    instances = {}
    lock = threading.Lock()
    
    @wraps(cls)
    def get_instance(*args, **kwargs):
        with lock:
            if cls not in instances:
                instances[cls] = cls(*args, **kwargs)
            return instances[cls]
    return get_instance

def deprecated(message: str = ""):
    """Декоратор устаревших функций"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            warning_msg = f"Функция {func.__name__} устарела"
            if message:
                warning_msg += f": {message}"
            logger.warning(warning_msg)
            return func(*args, **kwargs)
        return wrapper
    return decorator

# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================

def setup_logging(level: int = logging.INFO, log_file: str | None = None) -> None:
    """Настройка логирования"""
    handlers = [logging.StreamHandler()]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

def log_execution(func: Callable) -> Callable:
    """Декоратор логирования выполнения"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"Вызов {func.__name__} с аргументами: {args}, {kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} вернул: {result}")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} выбросил исключение: {e}")
            raise
    return wrapper

# ============================================================================
# АСИНХРОННОСТЬ (ПОТОКИ)
# ============================================================================

class ThreadPool:
    """Простой пул потоков"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.tasks = []
        self.lock = threading.Lock()
        
    def submit(self, func: Callable, *args, **kwargs) -> threading.Thread:
        """Отправка задачи в пул"""
        thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        thread.start()
        return thread
    
    def map(self, func: Callable, items: list[Any]) -> list[Any]:
        """Параллельное выполнение функции на списке"""
        results = []
        threads = []
        
        for item in items:
            thread = self.submit(lambda x: results.append(func(x)), item)
            threads.append(thread)
        
        for thread in threads:
            thread.join()
        
        return results

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

def load_config_from_env(prefix: str = "") -> dict[str, str]:
    """Загрузка конфигурации из переменных окружения"""
    import os
    config = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            config_key = key[len(prefix):].lower()
            config[config_key] = value
    return config

def deep_update(base: dict, update: dict) -> dict:
    """Глубокое обновление словаря"""
    result = base.copy()
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_update(result[key], value)
        else:
            result[key] = value
    return result

# ============================================================================
# ИГРОВЫЕ УТИЛИТЫ
# ============================================================================

def calculate_damage(base_damage: float, modifiers: dict[str, float]) -> float:
    """Расчёт урона с модификаторами"""
    damage = base_damage
    for modifier_name, modifier_value in modifiers.items():
        damage *= modifier_value
    return max(0, damage)

def interpolate_stats(base_stats: dict[str, float], level: int, growth_rate: float = 0.1) -> dict[str, float]:
    """Интерполяция характеристик по уровню"""
    result = {}
    for stat_name, base_value in base_stats.items():
        result[stat_name] = base_value * (1 + growth_rate * (level - 1))
    return result

def generate_loot_table(items: list[dict], luck: float = 0.0) -> list[dict]:
    """Генерация таблицы лута с учётом удачи"""
    loot = []
    for item in items:
        chance = item.get('chance', 0.0) * (1 + luck)
        if random.random() < chance:
            quantity = random.randint(
                item.get('min_quantity', 1),
                item.get('max_quantity', 1)
            )
            loot.append({
                'item_id': item['item_id'],
                'quantity': quantity
            })
    return loot

# ============================================================================
# СЕРИАЛИЗАЦИЯ
# ============================================================================

def safe_serialize(obj: Any) -> Any:
    """Безопасная сериализация объекта"""
    if obj is None:
        return None
    elif isinstance(obj, (int, float, str, bool)):
        return obj
    elif isinstance(obj, dict):
        return {k: safe_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [safe_serialize(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        return safe_serialize(obj.__dict__)
    else:
        return str(obj)

def deep_copy(obj: Any) -> Any:
    """Глубокое копирование через сериализацию"""
    import json
    return json.loads(json.dumps(safe_serialize(obj)))
