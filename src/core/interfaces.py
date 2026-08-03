"""
ISP (Interface Segregation Principle) Interfaces
Разделение больших интерфейсов на меньшие, специфичные для клиента.
Позволяет классам реализовывать только те методы, которые им действительно нужны.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable, List
from enum import Enum


# === Lifecycle Interfaces ===

class IInitializable(ABC):
    """Интерфейс для инициализируемых компонентов."""
    @abstractmethod
    def on_init(self) -> None:
        """Инициализация компонента."""
        pass


class IStartable(ABC):
    """Интерфейс для запускаемых компонентов."""
    @abstractmethod
    def on_start(self) -> None:
        """Запуск компонента."""
        pass


class IPausable(ABC):
    """Интерфейс для приостанавливаемых компонентов."""
    @abstractmethod
    def on_pause(self) -> None:
        """Пауза."""
        pass
    
    @abstractmethod
    def on_resume(self) -> None:
        """Возобновление."""
        pass


class IStoppable(ABC):
    """Интерфейс для останавливаемых компонентов."""
    @abstractmethod
    def on_stop(self) -> None:
        """Остановка."""
        pass


class IDestroyable(ABC):
    """Интерфейс для уничтожаемых компонентов."""
    @abstractmethod
    def on_destroy(self) -> None:
        """Очистка ресурсов."""
        pass


# === Event Interfaces ===

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
    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Подписка на событие."""
        pass
    
    @abstractmethod
    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Отписка от события."""
        pass


# === State Interfaces ===

class IStateGetter(ABC):
    """Интерфейс только для чтения состояний."""
    @abstractmethod
    def get_state(self, key: str) -> Optional[Any]:
        """Получение состояния."""
        pass
    
    @abstractmethod
    def has_state(self, key: str) -> bool:
        """Проверка наличия состояния."""
        pass


class IStateSetter(ABC):
    """Интерфейс только для записи состояний."""
    @abstractmethod
    def set_state(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
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


# === Component Interfaces ===

class IComponentInfo(ABC):
    """Интерфейс для получения информации о компоненте."""
    @property
    @abstractmethod
    def name(self) -> str:
        """Имя компонента."""
        pass
    
    @property
    @abstractmethod
    def component_id(self) -> str:
        """Уникальный ID."""
        pass
    
    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Флаг активности."""
        pass


class IComponentMetrics(ABC):
    """Интерфейс для получения метрик компонента."""
    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик производительности."""
        pass
    
    @abstractmethod
    def reset_metrics(self) -> None:
        """Сброс метрик."""
        pass


# === Combat Interfaces (для рефакторинга CombatSystem) ===

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


# === Cache Interfaces ===

class ICacheable(ABC):
    """Интерфейс для кэшируемых данных."""
    @abstractmethod
    def get_cache_key(self) -> str:
        """Ключ для кэширования."""
        pass
    
    @abstractmethod
    def get_ttl(self) -> Optional[float]:
        """Время жизни в кэше."""
        pass


# === Asset/Load Interfaces ===

class ILoadable(ABC):
    """Интерфейс для загружаемых ресурсов."""
    @abstractmethod
    def save_state(self) -> Dict[str, Any]:
        """Сохранение состояния."""
        pass
    
    @abstractmethod
    def load_state(self, state: Dict[str, Any]) -> None:
        """Загрузка состояния."""
        pass


# === Composite Interfaces (удобные комбинации) ===

class IFullLifecycle(IInitializable, IStartable, IPausable, IStoppable, IDestroyable):
    """Полный жизненный цикл компонента."""
    pass


class IReadWriteState(IStateGetter, IStateSetter):
    """Полный доступ к состоянию (чтение + запись)."""
    pass


class IGameComponent(IComponentInfo, IFullLifecycle, IComponentMetrics):
    """Полноценный игровой компонент."""
    pass


class ICombatEntity(IHealthComponent, ICombatStats):
    """Боевая сущность с здоровьем и статами."""
    pass
