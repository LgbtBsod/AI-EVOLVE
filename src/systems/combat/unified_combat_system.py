#!/usr/bin/env python3
"""
Unified Combat System

Purpose:
- Single source of truth for all combat logic
- Combines best features from old systems
- Implements ICombatSystem interface
- Uses component-based architecture
- Data-driven balance via JSON configs

Migration Guide:
- Old: CombatPlugin.calculate_damage() → New: UnifiedCombatSystem.attack()
- Old: CombatSystem.execute_attack() → New: UnifiedCombatSystem.attack()
- Old: RefactoredCombatSystem.attack() → New: UnifiedCombatSystem.attack()
"""

from __future__ import annotations

import logging
import random
from typing import Any

from src.core.contracts.i_combat_system import (
    BaseCombatSystem,
    CombatStats,
    DamageInfo,
    ICombatEntity,
)
from src.systems.combat.components import (
    CombatStatsComponent,
    DamageComponent,
    HealthComponent,
)

logger = logging.getLogger(__name__)


class UnifiedCombatSystem(BaseCombatSystem):
    """
    Единая система боя для проекта.
    
    Features:
    - Component-based architecture
    - Data-driven balance (JSON configs)
    - Critical hits, dodges, blocks
    - Damage types: physical, magical, true
    - Combat sessions with logging
    - ML-agent ready (via contracts)
    """
    
    def __init__(self) -> None:
        super().__init__()
        
        # Combat configuration (can be loaded from JSON)
        self._config = {
            "crit_chance_base": 0.05,
            "crit_damage_multiplier": 2.0,
            "dodge_chance_base": 0.1,
            "block_chance_base": 0.15,
            "damage_variance": 0.2,  # ±20%
            "armor_reduction": 0.5,  # Armor reduces damage by 50%
        }
        
        # Combat sessions
        self._sessions: dict[str, dict[str, Any]] = {}
        
        logger.info("UnifiedCombatSystem initialized")
    
    def attack(
        self,
        attacker_id: str,
        target_id: str,
        attack_type: str = "melee",
        skill_id: str | None = None,
    ) -> DamageInfo:
        """
        Выполнить атаку.
        
        Args:
            attacker_id: ID атакующего
            target_id: ID цели
            attack_type: Тип атаки ("melee", "ranged", "magic", "skill")
            skill_id: ID скилла (опционально)
        
        Returns:
            DamageInfo с результатами атаки
        """
        attacker = self.get_entity(attacker_id)
        target = self.get_entity(target_id)
        
        if not attacker or not target:
            logger.error(f"Entity not found: {attacker_id} or {target_id}")
            return DamageInfo(
                damage=0.0,
                damage_type="none",
                source_id=attacker_id,
                target_id=target_id,
            )
        
        if not attacker.is_alive:
            logger.warning(f"Attacker {attacker_id} is dead")
            return DamageInfo(
                damage=0.0,
                damage_type="none",
                source_id=attacker_id,
                target_id=target_id,
            )
        
        if not target.is_alive:
            logger.warning(f"Target {target_id} is already dead")
            return DamageInfo(
                damage=0.0,
                damage_type="none",
                source_id=attacker_id,
                target_id=target_id,
            )
        
        # Get attacker stats
        attacker_stats = attacker.get_combat_stats()
        
        # Determine base damage
        if attack_type in ("melee", "ranged"):
            base_damage = attacker_stats.physical_damage
            damage_type = "physical"
        else:
            base_damage = attacker_stats.magical_damage
            damage_type = "magical"
        
        # Calculate final damage
        final_damage, damage_info = self.calculate_damage(
            attacker, target, base_damage, damage_type
        )
        
        # Apply damage
        actual_damage = target.take_damage(final_damage, damage_type)
        
        # Update stats
        self._stats["total_attacks"] += 1
        self._stats["total_damage_dealt"] += actual_damage
        
        if not target.is_alive:
            self._stats["total_kills"] += 1
            logger.info(f"{attacker_id} killed {target_id}")
        
        logger.debug(
            f"Attack: {attacker_id} -> {target_id}, "
            f"damage={actual_damage:.1f}, crit={damage_info.is_critical}"
        )
        
        return damage_info
    
    def calculate_damage(
        self,
        attacker: ICombatEntity,
        defender: ICombatEntity,
        base_damage: float,
        damage_type: str,
    ) -> tuple[float, DamageInfo]:
        """
        Рассчитать урон без нанесения.
        
        Args:
            attacker: Атакующий
            defender: Защищающийся
            base_damage: Базовый урон
            damage_type: Тип урона
        
        Returns:
            (final_damage, damage_info)
        """
        atk_stats = attacker.get_combat_stats()
        def_stats = defender.get_combat_stats()
        
        damage_info = DamageInfo(
            damage=base_damage,
            damage_type=damage_type,
            source_id=attacker.entity_id,
            target_id=defender.entity_id,
        )
        
        # Check dodge
        if random.random() < def_stats.dodge_chance:
            damage_info.is_dodged = True
            return 0.0, damage_info
        
        # Check block
        if random.random() < def_stats.block_chance:
            damage_info.is_blocked = True
            base_damage *= (1.0 - self._config["armor_reduction"])
        
        # Check critical
        if random.random() < atk_stats.critical_chance:
            damage_info.is_critical = True
            base_damage *= atk_stats.critical_damage
        
        # Apply variance
        variance = random.uniform(
            -self._config["damage_variance"],
            self._config["damage_variance"]
        )
        base_damage *= (1.0 + variance)
        
        # Apply defense
        if damage_type == "physical":
            defense = def_stats.defense
            final_damage = max(1.0, base_damage - defense)
        else:
            resistance = def_stats.magic_resistance
            final_damage = base_damage * (1.0 - min(0.75, resistance / 100))
        
        damage_info.damage = final_damage
        return final_damage, damage_info
    
    def heal(self, entity_id: str, amount: float) -> float:
        """
        Полечить сущность.
        
        Args:
            entity_id: ID сущности
            amount: Количество лечения
        
        Returns:
            Фактически применённое лечение
        """
        entity = self.get_entity(entity_id)
        if not entity:
            logger.error(f"Entity not found: {entity_id}")
            return 0.0
        
        if not entity.is_alive:
            logger.warning(f"Cannot heal dead entity: {entity_id}")
            return 0.0
        
        # Simple heal - actual implementation may vary
        health_comp = getattr(entity, '_health', None)
        if health_comp and isinstance(health_comp, HealthComponent):
            return health_comp.heal(amount)
        
        # Fallback for entities without HealthComponent
        current = entity.current_health
        max_h = entity.max_health
        new_health = min(max_h, current + amount)
        return new_health - current
    
    def get_combat_stats(self, entity_id: str) -> dict[str, Any] | None:
        """
        Получить статистику сущности.
        
        Args:
            entity_id: ID сущности
        
        Returns:
            Dict со статистикой или None
        """
        entity = self.get_entity(entity_id)
        if not entity:
            return None
        
        stats = entity.get_combat_stats()
        return {
            "entity_id": entity_id,
            "is_alive": entity.is_alive,
            "current_health": entity.current_health,
            "max_health": entity.max_health,
            "health_percent": (entity.current_health / entity.max_health * 100)
            if entity.max_health > 0 else 0,
            "combat_stats": {
                "physical_damage": stats.physical_damage,
                "magical_damage": stats.magical_damage,
                "defense": stats.defense,
                "critical_chance": stats.critical_chance,
                "dodge_chance": stats.dodge_chance,
            },
        }
    
    def reset(self) -> None:
        """Сбросить состояние системы."""
        self._entities.clear()
        self._active_combats.clear()
        self._sessions.clear()
        self._stats = {
            "total_attacks": 0,
            "total_damage_dealt": 0.0,
            "total_kills": 0,
            "combats_started": 0,
        }
        logger.info("UnifiedCombatSystem reset")
    
    def create_session(self, session_id: str, participants: list[str]) -> bool:
        """
        Создать боевую сессию.
        
        Args:
            session_id: Уникальный ID сессии
            participants: Список ID участников
        
        Returns:
            True если сессия создана
        """
        if session_id in self._sessions:
            return False
        
        self._sessions[session_id] = {
            "participants": participants,
            "start_time": 0,
            "log": [],
        }
        logger.info(f"Combat session created: {session_id}")
        return True
    
    def log_action(self, session_id: str, action: str) -> None:
        """
        Записать действие в лог сессии.
        
        Args:
            session_id: ID сессии
            action: Описание действия
        """
        if session_id in self._sessions:
            self._sessions[session_id]["log"].append(action)
    
    def set_config(self, key: str, value: Any) -> None:
        """
        Изменить конфигурацию (для балансировки).
        
        Args:
            key: Ключ настройки
            value: Новое значение
        """
        if key in self._config:
            self._config[key] = value
            logger.info(f"Combat config updated: {key} = {value}")
        else:
            logger.warning(f"Unknown config key: {key}")
    
    def get_config(self) -> dict[str, Any]:
        """Получить текущую конфигурацию."""
        return self._config.copy()


# ============================================================================
# ADAPTER FOR LEGACY CODE
# ============================================================================


class LegacyCombatAdapter:
    """
    Адаптер для совместимости со старым кодом.
    
    Позволяет использовать старый интерфейс через новую систему.
    Should be removed after full migration.
    """
    
    def __init__(self, combat_system: UnifiedCombatSystem) -> None:
        self._system = combat_system
    
    def calculate_damage(
        self,
        attacker_stats: dict[str, Any],
        defender_stats: dict[str, Any],
        base_damage: float,
    ) -> dict[str, Any]:
        """Legacy interface compatibility."""
        # Create mock entities for calculation
        class MockEntity:
            def __init__(self, entity_id: str, stats: dict[str, Any]) -> None:
                self._id = entity_id
                self._stats = stats
            
            @property
            def entity_id(self) -> str:
                return self._id
            
            @property
            def current_health(self) -> float:
                return self._stats.get("health", 100)
            
            @property
            def max_health(self) -> float:
                return self._stats.get("max_health", 100)
            
            @property
            def is_alive(self) -> bool:
                return self.current_health > 0
            
            def take_damage(self, damage: float, damage_type: str) -> float:
                return damage
            
            def get_combat_stats(self) -> CombatStats:
                return CombatStats(
                    physical_damage=self._stats.get("physical_damage", 10),
                    magical_damage=self._stats.get("magical_damage", 5),
                    defense=self._stats.get("defense", 0),
                    critical_chance=self._stats.get(
                        "crit_chance", 0.05
                    ),
                    critical_damage=self._stats.get(
                        "crit_multiplier", 2.0
                    ),
                    dodge_chance=self._stats.get("dodge_chance", 0.1),
                    block_chance=self._stats.get("block_chance", 0.15),
                    magic_resistance=self._stats.get("magic_resist", 0),
                )
        
        attacker = MockEntity("attacker", attacker_stats)
        defender = MockEntity("defender", defender_stats)
        
        final_damage, info = self._system.calculate_damage(
            attacker, defender, base_damage, "physical"
        )
        
        return {
            "base_damage": base_damage,
            "final_damage": final_damage,
            "is_crit": info.is_critical,
            "is_dodged": info.is_dodged,
            "is_blocked": info.is_blocked,
        }


__all__ = ["UnifiedCombatSystem", "LegacyCombatAdapter"]
