"""
Damage Component
Реализует IDamageDealer интерфейс.
Отвечает только за расчет и нанесение урона.
"""
from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.interfaces import IDamageDealer, IHealthComponent


class DamageComponent(BaseComponent, IDamageDealer):
    """
    Компонент нанесения урона.
    Принцип единственной ответственности (SRP).
    """
    
    def __init__(self, name: str = "Damage", base_damage: float = 10.0):
        super().__init__(
            component_id=f"damage_{name}",
            component_type=ComponentType.COMPONENT,
            priority=Priority.NORMAL
        )
        self._base_damage = base_damage
        self._damage_multiplier = 1.0
        self._crit_chance = 0.0
        self._crit_multiplier = 2.0
    
    def _on_update(self, delta_time: float) -> None:
        """Обновление компонента (пустая реализация)."""
    
    @property
    def base_damage(self) -> float:
        """Базовый урон."""
        return self._base_damage
    
    @base_damage.setter
    def base_damage(self, value: float) -> None:
        if value < 0:
            raise ValueError("Damage cannot be negative")
        self._base_damage = value
    
    @property
    def damage_multiplier(self) -> float:
        """Множитель урона."""
        return self._damage_multiplier
    
    @damage_multiplier.setter
    def damage_multiplier(self, value: float) -> None:
        self._damage_multiplier = max(0.0, value)
    
    @property
    def crit_chance(self) -> float:
        """Шанс критического удара (0.0 - 1.0)."""
        return self._crit_chance
    
    @crit_chance.setter
    def crit_chance(self, value: float) -> None:
        self._crit_chance = max(0.0, min(1.0, value))
    
    @property
    def crit_multiplier(self) -> float:
        """Множитель критического удара."""
        return self._crit_multiplier
    
    @crit_multiplier.setter
    def crit_multiplier(self, value: float) -> None:
        self._crit_multiplier = max(1.0, value)
    
    def calculate_damage(self, target: IHealthComponent) -> float:
        """
        Расчет урона по цели с учетом защиты.
        Возвращает итоговый урон до применения.
        """
        import random
        
        # Базовый урон с множителем
        damage = self._base_damage * self._damage_multiplier
        
        # Критический удар
        is_crit = random.random() < self._crit_chance
        if is_crit:
            damage *= self._crit_multiplier
            if hasattr(self, 'logger') and self.logger:
                self.logger.debug(f"Critical hit! Damage: {damage}")
        
        # Учет защиты цели (если есть)
        if hasattr(target, 'defense'):
            defense = getattr(target, 'defense', 0)
            damage = max(1.0, damage - defense)
        
        return max(0.0, damage)
    
    def attack(self, target: IHealthComponent) -> float:
        """
        Атака цели.
        Вычисляет урон и применяет его к цели.
        Возвращает фактический нанесенный урон.
        """
        if not target.is_alive:
            if hasattr(self, 'logger') and self.logger:
                self.logger.warning(f"Target {target} is already dead")
            return 0.0
        
        damage = self.calculate_damage(target)
        actual_damage = target.take_damage(damage)
        
        if hasattr(self, 'logger') and self.logger:
            self.logger.debug(f"Attack dealt {actual_damage} damage to {target}")
        
        return actual_damage
    
    def set_base_damage(self, value: float) -> None:
        """Установка базового урона."""
        self.base_damage = value
    
    def add_damage_buff(self, percent: float) -> None:
        """Добавить временный бафф к урону (в процентах)."""
        self._damage_multiplier += percent / 100.0
    
    def remove_damage_buff(self, percent: float) -> None:
        """Удалить бафф урона."""
        self._damage_multiplier -= percent / 100.0
        self._damage_multiplier = max(0.0, self._damage_multiplier)
    
    def get_metrics(self) -> dict:
        """Метрики компонента."""
        base_metrics = super().get_metrics()
        base_metrics.update({
            "base_damage": self._base_damage,
            "current_multiplier": self._damage_multiplier,
            "crit_chance": self._crit_chance,
            "crit_multiplier": self._crit_multiplier,
            "effective_damage": self._base_damage * self._damage_multiplier
        })
        return base_metrics
