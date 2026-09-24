"""
Refactored Combat System
Использует компонентный подход (HealthComponent, DamageComponent, CombatStatsComponent).
Соблюдает SRP, ISP, DIP.
"""
import logging
from collections.abc import Callable
from typing import Any

from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.circuit_breaker import CircuitBreaker, circuit_breaker
from src.systems.combat.components import (
    CombatStatsComponent,
    DamageComponent,
    HealthComponent,
)

logger = logging.getLogger(__name__)


class CombatEntity:
    """
    Боевая сущность, агрегирующая компоненты.
    Композиция вместо наследования.
    """
    
    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self._health: HealthComponent | None = None
        self._damage: DamageComponent | None = None
        self._stats: CombatStatsComponent | None = None
    
    @property
    def health(self) -> HealthComponent | None:
        return self._health
    
    @property
    def damage(self) -> DamageComponent | None:
        return self._damage
    
    @property
    def stats(self) -> CombatStatsComponent | None:
        return self._stats
    
    def add_health_component(self, max_health: float = 100.0) -> HealthComponent:
        """Добавить компонент здоровья."""
        self._health = HealthComponent(max_health=max_health)
        return self._health
    
    def add_damage_component(self, base_damage: float = 10.0) -> DamageComponent:
        """Добавить компонент урона."""
        self._damage = DamageComponent(base_damage=base_damage)
        return self._damage
    
    def add_stats_component(
        self, 
        base_damage: float = 10.0,
        base_defense: float = 0.0,
        base_speed: float = 1.0
    ) -> CombatStatsComponent:
        """Добавить компонент статов."""
        self._stats = CombatStatsComponent(
            base_damage=base_damage,
            base_defense=base_defense,
            base_speed=base_speed
        )
        return self._stats
    
    @property
    def is_alive(self) -> bool:
        """Жива ли сущность."""
        return self._health is not None and self._health.is_alive
    
    @property
    def is_dead(self) -> bool:
        """Мертва ли сущность."""
        return self._health is None or self._health.is_dead


class RefactoredCombatSystem(BaseComponent):
    """
    Рефакторенная система боя.
    - Использует маленькие компоненты (SRP)
    - Защищена Circuit Breaker'ом
    - Следует ISP через интерфейсы
    """
    
    def __init__(self):
        super().__init__(
            component_id="refactored_combat_system",
            component_type=ComponentType.SYSTEM,
            priority=Priority.HIGH
        )
        
        # Хранилище сущностей
        self._entities: dict[str, CombatEntity] = {}
        
        # Активные бои
        self._active_combats: dict[str, list[str]] = {}
        
        # Circuit Breaker для внешних вызовов
        self._external_call_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30.0
        )
        
        # Статистика
        self._stats = {
            "total_combats": 0,
            "total_damage_dealt": 0.0,
            "entities_created": 0,
            "entities_killed": 0
        }
        
        # Callbacks
        self.on_entity_died: Callable[[str], None] | None = None
        self.on_combat_started: Callable[[str], None] | None = None
        self.on_combat_ended: Callable[[str], None] | None = None
        
        logger.info("Refactored Combat System initialized")
    
    def _on_update(self, delta_time: float) -> None:
        """Обновление системы боя."""
    
    def create_entity(self, entity_id: str) -> CombatEntity:
        """Создать боевую сущность."""
        if entity_id in self._entities:
            raise ValueError(f"Entity {entity_id} already exists")
        
        entity = CombatEntity(entity_id)
        self._entities[entity_id] = entity
        self._stats["entities_created"] += 1
        
        logger.debug(f"Created combat entity: {entity_id}")
        return entity
    
    def remove_entity(self, entity_id: str) -> None:
        """Удалить сущность."""
        if entity_id in self._entities:
            del self._entities[entity_id]
            logger.debug(f"Removed combat entity: {entity_id}")
    
    def get_entity(self, entity_id: str) -> CombatEntity | None:
        """Получить сущность."""
        return self._entities.get(entity_id)
    
    @circuit_breaker(failure_threshold=3, recovery_timeout=10.0)
    def attack(
        self, 
        attacker_id: str, 
        target_id: str,
        use_skills: bool = False
    ) -> tuple[float, bool]:
        """
        Атака цели атакующим.
        Возвращает (нанесенный_урон, был_крит).
        Защищено Circuit Breaker'ом.
        """
        attacker = self.get_entity(attacker_id)
        target = self.get_entity(target_id)
        
        if not attacker or not target:
            raise ValueError(f"Entity not found: {attacker_id} or {target_id}")
        
        if not attacker.damage:
            raise ValueError(f"Attacker {attacker_id} has no damage component")
        
        if not target.health:
            raise ValueError(f"Target {target_id} has no health component")
        
        if not target.is_alive:
            logger.warning(f"Target {target_id} is already dead")
            return 0.0, False
        
        # Расчет и нанесение урона
        damage_dealt = attacker.damage.attack(target.health)
        
        # Проверка на крит (если есть стат компонент)
        is_crit = False
        if attacker.stats:
            # Упрощенная проверка крита
            import random
            crit_chance = getattr(attacker.damage, 'crit_chance', 0.0)
            is_crit = random.random() < crit_chance
        
        self._stats["total_damage_dealt"] += damage_dealt
        
        logger.debug(f"{attacker_id} attacked {target_id} for {damage_dealt} damage")
        
        # Проверка смерти
        if not target.is_alive:
            self._stats["entities_killed"] += 1
            if self.on_entity_died:
                self.on_entity_died(target_id)
        
        return damage_dealt, is_crit
    
    def start_combat(self, combat_id: str, participants: list[str]) -> bool:
        """Начать бой между участниками."""
        if combat_id in self._active_combats:
            logger.warning(f"Combat {combat_id} already active")
            return False
        
        # Проверка существования всех участников
        for p_id in participants:
            if p_id not in self._entities:
                raise ValueError(f"Participant {p_id} not found")
        
        self._active_combats[combat_id] = participants
        self._stats["total_combats"] += 1
        
        logger.info(f"Started combat {combat_id} with {len(participants)} participants")
        
        if self.on_combat_started:
            self.on_combat_started(combat_id)
        
        return True
    
    def end_combat(self, combat_id: str) -> bool:
        """Завершить бой."""
        if combat_id not in self._active_combats:
            return False
        
        del self._active_combats[combat_id]
        logger.info(f"Ended combat {combat_id}")
        
        if self.on_combat_ended:
            self.on_combat_ended(combat_id)
        
        return True
    
    def heal(self, entity_id: str, amount: float) -> float:
        """Лечить сущность."""
        entity = self.get_entity(entity_id)
        if not entity or not entity.health:
            raise ValueError(f"Entity {entity_id} not found or has no health component")
        
        return entity.health.heal(amount)
    
    def get_combat_stats(self, entity_id: str) -> dict[str, Any]:
        """Получить статистику по сущности."""
        entity = self.get_entity(entity_id)
        if not entity:
            return {}
        
        stats = {
            "entity_id": entity_id,
            "is_alive": entity.is_alive
        }
        
        if entity.health:
            stats["health"] = {
                "current": entity.health.current_health,
                "max": entity.health.max_health,
                "percent": entity.health.health_percent
            }
        
        if entity.damage:
            stats["damage"] = entity.damage.get_metrics()
        
        if entity.stats:
            stats["combat_stats"] = entity.stats.get_metrics()
        
        return stats
    
    def get_system_metrics(self) -> dict[str, Any]:
        """Метрики системы."""
        base_metrics = super().get_metrics()
        base_metrics.update({
            **self._stats,
            "active_combats": len(self._active_combats),
            "total_entities": len(self._entities)
        })
        return base_metrics
    
    def reset(self) -> None:
        """Сброс системы."""
        self._entities.clear()
        self._active_combats.clear()
        self._external_call_breaker.reset()
        logger.info("Combat system reset")
