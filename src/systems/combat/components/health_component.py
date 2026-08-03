"""
Health Component
Реализует IHealthComponent интерфейс.
Отвечает только за здоровье, урон и лечение.
"""
from typing import Optional
from src.core.interfaces import IHealthComponent
from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.validation import CombatStats


class HealthComponent(BaseComponent, IHealthComponent):
    """
    Компонент здоровья сущности.
    Принцип единственной ответственности (SRP).
    """
    
    def __init__(self, name: str = "Health", max_health: float = 100.0):
        super().__init__(
            component_id=f"health_{name}",
            component_type=ComponentType.COMPONENT,
            priority=Priority.NORMAL
        )
        self._max_health = max_health
        self._current_health = max_health
        self._is_dead = False
    
    def _on_update(self, delta_time: float) -> None:
        """Обновление компонента (пустая реализация)."""
        pass
    
    @property
    def current_health(self) -> float:
        """Текущее здоровье."""
        return self._current_health
    
    @property
    def max_health(self) -> float:
        """Максимальное здоровье."""
        return self._max_health
    
    @property
    def health_percent(self) -> float:
        """Процент здоровья."""
        return (self._current_health / self._max_health) * 100.0
    
    @property
    def is_alive(self) -> bool:
        """Жив ли объект."""
        return self._current_health > 0 and not self._is_dead
    
    @property
    def is_dead(self) -> bool:
        """Мертв ли объект."""
        return self._is_dead
    
    def take_damage(self, amount: float) -> float:
        """
        Получение урона.
        Возвращает фактический нанесенный урон.
        """
        if amount <= 0:
            return 0.0
        
        if not self.is_alive:
            return 0.0
        
        old_health = self._current_health
        self._current_health = max(0.0, self._current_health - amount)
        
        actual_damage = old_health - self._current_health
        
        if self._current_health <= 0:
            self._on_death()
        
        return actual_damage
    
    def heal(self, amount: float) -> float:
        """
        Лечение.
        Возвращает фактическое восстановленное здоровье.
        """
        if amount <= 0:
            return 0.0
        
        if not self.is_alive:
            return 0.0
        
        old_health = self._current_health
        self._current_health = min(self._max_health, self._current_health + amount)
        
        actual_heal = self._current_health - old_health
        return actual_heal
    
    def set_max_health(self, value: float) -> None:
        """Установка максимального здоровья с корректировкой текущего."""
        if value <= 0:
            raise ValueError("Max health must be positive")
        
        ratio = value / self._max_health
        self._max_health = value
        self._current_health = min(self._current_health * ratio, value)
    
    def reset(self) -> None:
        """Полное восстановление здоровья."""
        self._current_health = self._max_health
        self._is_dead = False
    
    def _on_death(self) -> None:
        """Вызывается при смерти."""
        self._is_dead = True
        if hasattr(self, 'logger') and self.logger:
            self.logger.info(f"{self.name} died")
        # Здесь можно отправить событие о смерти
        # self.event_system.emit("entity_died", {"entity_id": self.component_id})
    
    def get_metrics(self) -> dict:
        """Метрики компонента."""
        base_metrics = super().get_metrics()
        base_metrics.update({
            "current_health": self._current_health,
            "max_health": self._max_health,
            "health_percent": self.health_percent,
            "is_alive": self.is_alive
        })
        return base_metrics
