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
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from architecture import IComponent


# ============================================================================
# EVENT INTERFACES
# ============================================================================


class IEventListener(ABC):
    """Интерфейс для слушателя событий."""
    
    @abstractmethod
    def handle_event(self, event_type: str, data: Any) -> None:
        """Обработка события."""
        pass


class IEventEmitter(ABC):
    """Интерфейс для эмиттера событий."""
    
    @abstractmethod
    def emit(self, event_type: str, data: Any) -> None:
        """Отправка события."""
        pass
    
    @abstractmethod
    def subscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        """Подписка на событие."""
        pass
    
    @abstractmethod
    def unsubscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        """Отписка от события."""
        pass


# ============================================================================
# STATE INTERFACES
# ============================================================================


class IStateGetter(ABC):
    """Интерфейс только для чтения состояний."""
    
    @abstractmethod
    def get_state(self, key: str) -> Any | None:
        """Получение состояния."""
        pass
    
    @abstractmethod
    def has_state(self, key: str) -> bool:
        """Проверка наличия состояния."""
        pass


class IStateSetter(ABC):
    """Интерфейс только для записи состояний."""
    
    @abstractmethod
    def set_state(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Установка состояния."""
        pass
    
    @abstractmethod
    def delete_state(self, key: str) -> bool:
        """Удаление состояния."""
        pass


class IStateObserver(ABC):
    """Интерфейс для наблюдателя за изменениями состояний."""
    
    @abstractmethod
    def on_state_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """Вызывается при изменении состояния."""
        pass


# ============================================================================
# COMBAT INTERFACES
# ============================================================================


class IHealthComponent(ABC):
    """Интерфейс компонента здоровья."""
    
    @abstractmethod
    def take_damage(self, amount: float) -> float:
        """Получение урона. Возвращает фактический урон."""
        pass
    
    @abstractmethod
    def heal(self, amount: float) -> float:
        """Лечение. Возвращает фактическое лечение."""
        pass
    
    @property
    @abstractmethod
    def current_health(self) -> float:
        """Текущее здоровье."""
        pass
    
    @property
    @abstractmethod
    def max_health(self) -> float:
        """Максимальное здоровье."""
        pass
    
    @property
    @abstractmethod
    def is_alive(self) -> bool:
        """Жив ли объект."""
        pass


class IDamageDealer(ABC):
    """Интерфейс для наносящего урон."""
    
    @abstractmethod
    def calculate_damage(self, target: IHealthComponent) -> float:
        """Расчет урона по цели."""
        pass
    
    @abstractmethod
    def attack(self, target: IHealthComponent) -> float:
        """Атака цели. Возвращает нанесенный урон."""
        pass


class ICombatStats(ABC):
    """Интерфейс боевых характеристик."""
    
    @property
    @abstractmethod
    def damage(self) -> float:
        """Базовый урон."""
        pass
    
    @property
    @abstractmethod
    def defense(self) -> float:
        """Защита."""
        pass
    
    @property
    @abstractmethod
    def speed(self) -> float:
        """Скорость/инициатива."""
        pass


# ============================================================================
# CACHE INTERFACES
# ============================================================================


class ICacheable(ABC):
    """Интерфейс для кэшируемых данных."""
    
    @abstractmethod
    def get_cache_key(self) -> str:
        """Ключ для кэширования."""
        pass
    
    @abstractmethod
    def get_ttl(self) -> float | None:
        """Время жизни в кэше."""
        pass


# ============================================================================
# ASSET/LOAD INTERFACES
# ============================================================================


class ILoadable(ABC):
    """Интерфейс для загружаемых ресурсов."""
    
    @abstractmethod
    def save_state(self) -> dict[str, Any]:
        """Сохранение состояния."""
        pass
    
    @abstractmethod
    def load_state(self, state: dict[str, Any]) -> None:
        """Загрузка состояния."""
        pass


# ============================================================================
# COMPOSITE INTERFACES (удобные комбинации)
# ============================================================================


class IReadWriteState(IStateGetter, IStateSetter):
    """Полный доступ к состоянию (чтение + запись)."""
    pass


class ICombatEntity(IHealthComponent, ICombatStats):
    """Боевая сущность с здоровьем и статами."""
    pass
