"""
Централизованный менеджер случайных чисел для воспроизводимости тестов и геймплея.
Использует dependency injection для внедрения в системы.

Python 3.14 compatible.
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar('T')


@dataclass(slots=True)
class RNGConfig:
    """Конфигурация RNG с поддержкой детерминизма."""
    seed: int | None = None
    use_deterministic: bool = True  # True для тестов, False для продакшена
    crypto_safe: bool = False  # Использовать secrets для криптографически стойких чисел


class RNGManager:
    """
    Централизованный менеджер случайных чисел.
    
    Преимущества:
    - Воспроизводимость багов через seed
    - Детерминированное тестирование
    - Единая точка контроля для всех систем
    - Поддержка как deterministic, так и crypto-safe режимов
    """
    
    __slots__ = ('_config', '_fallback_rng', '_rng')
    
    def __init__(self, config: RNGConfig | None = None) -> None:
        self._config = config or RNGConfig()
        self._rng = random.Random(self._config.seed) if self._config.use_deterministic else random.Random()
        self._fallback_rng = secrets.SystemRandom() if self._config.crypto_safe else None
    
    def reseed(self, seed: int) -> None:
        """Пересоздать RNG с новым seed для воспроизводимости."""
        self._rng = random.Random(seed)
        self._config.seed = seed
    
    def reset(self) -> None:
        """Сбросить RNG к исходному состоянию."""
        if self._config.seed is not None:
            self.reseed(self._config.seed)
        else:
            self._rng = random.Random()
    
    def random(self) -> float:
        """Вернуть случайное float в диапазоне [0.0, 1.0)."""
        if self._fallback_rng and self._config.crypto_safe:
            return self._fallback_rng.random()
        return self._rng.random()
    
    def randint(self, a: int, b: int) -> int:
        """Вернуть случайное int в диапазоне [a, b] включительно."""
        if self._fallback_rng and self._config.crypto_safe:
            return self._fallback_rng.randint(a, b)
        return self._rng.randint(a, b)
    
    def uniform(self, a: float, b: float) -> float:
        """Вернуть случайное float в диапазоне [a, b]."""
        if self._fallback_rng and self._config.crypto_safe:
            return self._fallback_rng.uniform(a, b)
        return self._rng.uniform(a, b)
    
    def gauss(self, mu: float, sigma: float) -> float:
        """Вернуть случайное float из нормального распределения."""
        if self._fallback_rng and self._config.crypto_safe:
            return self._fallback_rng.gauss(mu, sigma)
        return self._rng.gauss(mu, sigma)
    
    def choice(self, seq: Sequence[T]) -> T:
        """Вернуть случайный элемент из последовательности."""
        if not seq:
            raise ValueError("Cannot choose from empty sequence")
        if self._fallback_rng and self._config.crypto_safe:
            return self._fallback_rng.choice(seq)
        return self._rng.choice(seq)
    
    def choices(self, population: Sequence[T], weights: Sequence[float] | None = None, k: int = 1) -> list[T]:
        """Вернуть k случайных элементов с весами."""
        if self._fallback_rng and self._config.crypto_safe:
            return self._fallback_rng.choices(population, weights=weights, k=k)
        return self._rng.choices(population, weights=weights, k=k)
    
    def sample(self, population: Sequence[T], k: int) -> list[T]:
        """Вернуть k уникальных случайных элементов."""
        if self._fallback_rng and self._config.crypto_safe:
            return self._fallback_rng.sample(population, k=k)
        return self._rng.sample(population, k=k)
    
    def shuffle(self, x: list[T]) -> None:
        """Перемешать список на месте."""
        if self._fallback_rng and self._config.crypto_safe:
            self._fallback_rng.shuffle(x)
        else:
            self._rng.shuffle(x)
    
    def randbool(self, chance: float = 0.5) -> bool:
        """Вернуть True с вероятностью chance (0.0-1.0)."""
        return self.random() < chance
    
    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        """Вернуть случайное число из диапазона с шагом."""
        if self._fallback_rng and self._config.crypto_safe:
            if stop is None:
                return self._fallback_rng.randrange(start, step=step)
            return self._fallback_rng.randrange(start, stop, step=step)
        if stop is None:
            return self._rng.randrange(start, step=step)
        return self._rng.randrange(start, stop, step=step)
    
    @property
    def state(self) -> tuple:
        """Получить текущее состояние RNG для сохранения/восстановления."""
        return self._rng.getstate()
    
    @state.setter
    def state(self, value: tuple) -> None:
        """Восстановить состояние RNG."""
        self._rng.setstate(value)
    
    def clone(self) -> RNGManager:
        """Создать копию менеджера с тем же состоянием."""
        clone = RNGManager(self._config)
        clone._rng = random.Random()
        clone._rng.setstate(self._rng.getstate())
        return clone


# Глобальный экземпляр по умолчанию (ленивая инициализация)
_default_rng: RNGManager | None = None


def get_default_rng() -> RNGManager:
    """Получить глобальный RNG менеджер (singleton)."""
    global _default_rng
    if _default_rng is None:
        _default_rng = RNGManager(RNGConfig(seed=42))  # Детерминированный по умолчанию
    return _default_rng


def set_default_rng(rng: RNGManager) -> None:
    """Установить глобальный RNG менеджер."""
    global _default_rng
    _default_rng = rng


def reset_default_rng(seed: int | None = 42) -> None:
    """Сбросить глобальный RNG с новым seed."""
    global _default_rng
    _default_rng = RNGManager(RNGConfig(seed=seed))
