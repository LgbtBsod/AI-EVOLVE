"""
Circuit Breaker Pattern
Защита системы от каскадных сбоев при вызове ненадежных внешних сервисов или операций.
Реализует состояния: CLOSED (норма), OPEN (сбой), HALF_OPEN (проверка).
"""
import threading
import time
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any


class CircuitState(Enum):
    CLOSED = "closed"      # Нормальная работа
    OPEN = "open"          # Сбой, запросы блокируются
    HALF_OPEN = "half_open" # Проверка восстановления


class CircuitBreakerError(Exception):
    """Ошибка: цепь разомкнута."""


class CircuitBreaker:
    """
    Паттерн Circuit Breaker.
    
    Args:
        failure_threshold: Порог ошибок для размыкания цепи.
        recovery_timeout: Время ожидания перед попыткой восстановления (сек).
        expected_exceptions: Кортеж исключений, которые считаются сбоями.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exceptions: tuple = (Exception,)
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.RLock()
        
        # Статистика
        self._success_count = 0
        self._total_calls = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Проверяем, не истекло ли время восстановления
                if self._last_failure_time and \
                   time.perf_counter() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._failure_count = 0
            return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Выполняет функцию с защитой Circuit Breaker.
        """
        with self._lock:
            self._total_calls += 1
            current_state = self.state
            
            if current_state == CircuitState.OPEN:
                raise CircuitBreakerError(
                    f"Circuit is OPEN. Last failure at {self._last_failure_time}"
                )
        
        try:
            result = func(*args, **kwargs)
            
            with self._lock:
                self._on_success()
            
            return result
            
        except self.expected_exceptions:
            with self._lock:
                self._on_failure()
            raise

    def _on_success(self):
        """Обработка успешного вызова."""
        self._success_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def _on_failure(self):
        """Обработка сбоя."""
        self._failure_count += 1
        self._last_failure_time = time.perf_counter()
        
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
    
    def reset(self):
        """Сброс состояния цепи."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    @property
    def stats(self) -> dict:
        """Статистика работы."""
        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "threshold": self.failure_threshold
        }


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    expected_exceptions: tuple = (Exception,)
):
    """
    Декоратор для защиты функций Circuit Breaker'ом.
    """
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exceptions=expected_exceptions
    )
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        wrapper.circuit_breaker = breaker  # Доступ к экземпляру для тестов/мониторинга
        return wrapper
    
    return decorator
