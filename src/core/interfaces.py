#!/usr/bin/env python3
"""
ISP (Interface Segregation Principle) Interfaces

REFactoring Summary:
- DRY: Удалено дублирование с architecture.py (теперь используются Protocol из architecture)
- Type Hints: Обновлены на Python 3.10+ стиль (dict, list, T | None)
- ISP: Интерфейсы разбиты по областям ответственности
- SSOT: Базовые интерфейсы компонентов импортируются из architecture.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

# ============================================================================
# EVENT INTERFACES
# ============================================================================


class IEventListener(ABC):
    """Интерфейс для слушателя событий."""
    
    @abstractmethod
    def handle_event(self, event_type: str, data: Any) -> None:
        """Обработка события."""


class IEventEmitter(ABC):
    """Интерфейс для эмиттера событий."""
    
    @abstractmethod
    def emit(self, event_type: str, data: Any) -> None:
        """Отправка события."""
    
    @abstractmethod
    def subscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        """Подписка на событие."""
    
    @abstractmethod
    def unsubscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        """Отписка от события."""


# ============================================================================
# STATE INTERFACES
# ============================================================================


class IStateGetter(ABC):
    """Интерфейс только для чтения состояний."""
    
    @abstractmethod
    def get_state(self, key: str) -> Any | None:
        """Получение состояния."""
    
    @abstractmethod
    def has_state(self, key: str) -> bool:
        """Проверка наличия состояния."""


class IStateSetter(ABC):
    """Интерфейс только для записи состояний."""
    
    @abstractmethod
    def set_state(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Установка состояния."""
    
    @abstractmethod
    def delete_state(self, key: str) -> bool:
        """Удаление состояния."""


class IStateObserver(ABC):
    """Интерфейс для наблюдателя за изменениями состояний."""
    
    @abstractmethod
    def on_state_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """Вызывается при изменении состояния."""


# ============================================================================
# COMBAT INTERFACES
# ============================================================================


class IHealthComponent(ABC):
    """Интерфейс компонента здоровья."""
    
    @abstractmethod
    def take_damage(self, amount: float) -> float:
        """Получение урона. Возвращает фактический урон."""
    
    @abstractmethod
    def heal(self, amount: float) -> float:
        """Лечение. Возвращает фактическое лечение."""
    
    @property
    @abstractmethod
    def current_health(self) -> float:
        """Текущее здоровье."""
    
    @property
    @abstractmethod
    def max_health(self) -> float:
        """Максимальное здоровье."""
    
    @property
    @abstractmethod
    def is_alive(self) -> bool:
        """Жив ли объект."""


class IDamageDealer(ABC):
    """Интерфейс для наносящего урон."""
    
    @abstractmethod
    def calculate_damage(self, target: IHealthComponent) -> float:
        """Расчет урона по цели."""
    
    @abstractmethod
    def attack(self, target: IHealthComponent) -> float:
        """Атака цели. Возвращает нанесенный урон."""


class ICombatStats(ABC):
    """Интерфейс боевых характеристик."""
    
    @property
    @abstractmethod
    def damage(self) -> float:
        """Базовый урон."""
    
    @property
    @abstractmethod
    def defense(self) -> float:
        """Защита."""
    
    @property
    @abstractmethod
    def speed(self) -> float:
        """Скорость/инициатива."""


# ============================================================================
# CACHE INTERFACES
# ============================================================================


class ICacheable(ABC):
    """Интерфейс для кэшируемых данных."""
    
    @abstractmethod
    def get_cache_key(self) -> str:
        """Ключ для кэширования."""
    
    @abstractmethod
    def get_ttl(self) -> float | None:
        """Время жизни в кэше."""


# ============================================================================
# ASSET/LOAD INTERFACES
# ============================================================================


class ILoadable(ABC):
    """Интерфейс для загружаемых ресурсов."""
    
    @abstractmethod
    def save_state(self) -> dict[str, Any]:
        """Сохранение состояния."""
    
    @abstractmethod
    def load_state(self, state: dict[str, Any]) -> None:
        """Загрузка состояния."""


# ============================================================================
# COMPOSITE INTERFACES (удобные комбинации)
# ============================================================================


class IReadWriteState(IStateGetter, IStateSetter):
    """Полный доступ к состоянию (чтение + запись)."""


class ICombatEntity(IHealthComponent, ICombatStats):
    """Боевая сущность с здоровьем и статами."""
