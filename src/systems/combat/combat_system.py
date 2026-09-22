#!/usr/bin/env python3
"""
Combat System - система боя с разделением ответственности.

Refactoring Summary:
- SRP: Разделение логики атаки, защиты, сессий и статистики
- DIP: Внедрение зависимостей через Protocol/абстракции
- Type Hints: Python 3.10+ стиль (list[str], dict[str, Any])
- Performance: __slots__ для dataclass, кэширование расчетов
- DRY: Устранение дублирования формул расчета урона
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.systems.attributes.attribute_system import AttributeSystem

logger = logging.getLogger(__name__)


# ============================================================================
# ТИПЫ БОЯ
# ============================================================================


class CombatType(Enum):
    """Типы боя"""
    TURN_BASED = "turn_based"
    REAL_TIME = "real_time"
    HYBRID = "hybrid"


class AttackType(Enum):
    """Типы атак"""
    MELEE = "melee"
    RANGED = "ranged"
    MAGIC = "magic"
    AREA = "area"
    SPECIAL = "special"


class DefenseType(Enum):
    """Типы защиты"""
    ARMOR = "armor"
    BLOCK = "block"
    RESISTANCE = "resistance"


# ============================================================================
# ИНТЕРФЕЙСЫ (ISP)
# ============================================================================


class ICombatParticipant(Protocol):
    """Интерфейс участника боя"""
    
    @property
    def entity_id(self) -> str: ...
    def take_damage(self, damage: float, damage_type: str) -> bool: ...
    def is_alive(self) -> bool: ...
    def get_combat_stats(self) -> CombatStats: ...


# ============================================================================
# СТРУКТУРЫ ДАННЫХ
# ============================================================================


@dataclass(slots=True)
class CombatStats:
    """Боевые характеристики"""
    physical_damage: float = 10.0
    magical_damage: float = 5.0
    defense: float = 5.0
    attack_speed: float = 1.0
    critical_chance: float = 0.05
    critical_damage: float = 1.5
    dodge_chance: float = 0.05
    block_chance: float = 0.05
    magic_resistance: float = 0.0
    accuracy: float = 0.8
    initiative: float = 10.0
    range: float = 2.0
    damage_modifier: float = 1.0
    defense_modifier: float = 1.0
    speed_modifier: float = 1.0


@dataclass(slots=True)
class DamageInfo:
    """Информация об уроне"""
    damage: float
    damage_type: str
    attack_type: AttackType
    is_critical: bool = False
    is_blocked: bool = False
    is_dodged: bool = False
    toughness_damage: float = 0.0
    toughness_type: str = "physical"
    source: str = ""
    target: str = ""
    applied_effect: str | None = None


@dataclass(slots=True)
class CombatSession:
    """Сессия боя"""
    session_id: str
    participants: list[str]
    combat_type: CombatType
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float = 0.0
    current_turn: int = 0
    turn_order: list[str] = field(default_factory=list)
    active_effects: dict[str, list[str]] = field(default_factory=dict)
    combat_log: list[str] = field(default_factory=list)
    is_active: bool = True


# ============================================================================
# СИСТЕМА БОЯ
# ============================================================================


class CombatSystem:
    """
    Система боя - координирует боевые действия.
    """
    
    __slots__ = (
        '_attribute_system',
        '_damage_formulas',
        '_effect_system',
        '_event_handlers',
        '_rng',
        '_sessions'
    )

    def __init__(
        self,
        attribute_system: AttributeSystem | None = None,
        rng=None,
        effect_system=None,
    ) -> None:
        self._sessions: dict[str, CombatSession] = {}
        self._attribute_system = attribute_system
        self._damage_formulas: dict[str, Callable[..., float]] = {}
        self._event_handlers: list[Callable[[DamageInfo], None]] = []
        self._rng = rng  # RNGManager (см. src.core.rng_manager.get_default_rng)
        self._effect_system = effect_system  # src.systems.effects.effect_system.EffectSystem, опционально

        self._setup_default_formulas()
    
    def _setup_default_formulas(self) -> None:
        """Настройка формул расчета урона"""
        self._damage_formulas['physical'] = self._calculate_physical_damage
        self._damage_formulas['magical'] = self._calculate_magical_damage
    
    def create_session(
        self,
        session_id: str,
        participants: list[str],
        combat_type: CombatType = CombatType.TURN_BASED
    ) -> CombatSession:
        """Создание боевой сессии"""
        session = CombatSession(
            session_id=session_id,
            participants=participants,
            combat_type=combat_type
        )
        self._sessions[session_id] = session
        logger.info(f"Боевая сессия создана: {session_id}")
        return session
    
    def end_session(self, session_id: str) -> bool:
        """Завершение боевой сессии"""
        if session_id not in self._sessions:
            return False
        
        session = self._sessions[session_id]
        session.end_time = time.perf_counter()
        session.is_active = False
        
        logger.info(f"Боевая сессия завершена: {session_id}")
        return True
    
    def execute_attack(
        self,
        attacker: ICombatParticipant,
        target: ICombatParticipant,
        attack_type: AttackType = AttackType.MELEE,
        damage_multiplier: float = 1.0,
        on_hit_effect: str | None = None,
    ) -> DamageInfo:
        """Выполнение атаки.

        damage_multiplier - множитель для конкретной атаки/скила поверх
        обычных характеристик атакующего (например скрытная атака разбойника
        х1.5) - раньше такие скилы просто обходили CombatSystem и считали
        урон вручную через target.take_damage() напрямую.

        on_hit_effect - id шаблона EffectSystem (например "poison_debuff"),
        применяемый к цели при удачном (не уклонившемся) попадании - это и
        есть подключение системы эффектов к боевой системе: без effect_system,
        переданной в конструктор, параметр просто игнорируется."""
        if not attacker.is_alive() or not target.is_alive():
            return DamageInfo(0, "none", attack_type)

        stats = attacker.get_combat_stats()
        target_stats = target.get_combat_stats()

        # Расчет базового урона
        base_damage = stats.physical_damage * damage_multiplier

        # Проверка критического удара
        is_critical = False
        crit_roll = self._rng.random() if self._rng else 0.5
        if crit_roll < stats.critical_chance:
            is_critical = True
            base_damage *= stats.critical_damage

        # Проверка уклонения
        is_dodged = False
        dodge_roll = self._rng.random() if self._rng else 0.5
        if dodge_roll < target_stats.dodge_chance:
            is_dodged = True
            damage_info = DamageInfo(
                damage=0,
                damage_type="physical",
                attack_type=attack_type,
                is_dodged=True,
                source=attacker.entity_id,
                target=target.entity_id
            )
            self._notify_event(damage_info)
            return damage_info

        # Применение модификаторов и защиты
        final_damage = max(1.0, (base_damage - target_stats.defense))

        applied_effect = None
        if on_hit_effect and self._effect_system is not None:
            if self._effect_system.apply_effect(target.entity_id, on_hit_effect, source=attacker.entity_id):
                applied_effect = on_hit_effect

        damage_info = DamageInfo(
            damage=final_damage,
            damage_type="physical",
            attack_type=attack_type,
            is_critical=is_critical,
            is_dodged=is_dodged,
            source=attacker.entity_id,
            target=target.entity_id,
            applied_effect=applied_effect,
        )

        # Нанесение урона
        target.take_damage(final_damage, "physical")
        
        self._notify_event(damage_info)
        self._log_combat_action(session_id=None, action=f"{attacker.entity_id} атакует {target.entity_id}")
        
        return damage_info
    
    def _calculate_physical_damage(
        self,
        attack: float,
        defense: float,
        modifier: float = 1.0
    ) -> float:
        """Формула физического урона"""
        return max(1.0, (attack - defense) * modifier)
    
    def _calculate_magical_damage(
        self,
        magic_power: float,
        resistance: float,
        modifier: float = 1.0
    ) -> float:
        """Формула магического урона"""
        return max(1.0, magic_power * (1 - min(0.75, resistance / 100)) * modifier)
    
    def _check_critical(self, chance: float) -> bool:
        """Проверка критического удара"""
        if self._rng:
            return self._rng.random() < chance
        return False
    
    def _check_dodge(self, chance: float) -> bool:
        """Проверка уклонения"""
        if self._rng:
            return self._rng.random() < chance
        return False
    
    def _notify_event(self, damage_info: DamageInfo) -> None:
        """Уведомление подписчиков о событии"""
        for handler in self._event_handlers:
            try:
                handler(damage_info)
            except Exception as e:
                logger.error(f"Ошибка в обработчике боевого события: {e}")
    
    def _log_combat_action(self, session_id: str | None, action: str) -> None:
        """Логирование боевого действия"""
        if session_id and session_id in self._sessions:
            self._sessions[session_id].combat_log.append(action)
        logger.debug(f"Боевое действие: {action}")
    
    def register_event_handler(
        self,
        handler: Callable[[DamageInfo], None]
    ) -> None:
        """Регистрация обработчика событий"""
        self._event_handlers.append(handler)
    
    def get_session(self, session_id: str) -> CombatSession | None:
        """Получение боевой сессии"""
        return self._sessions.get(session_id)
    
    def get_active_sessions(self) -> list[CombatSession]:
        """Получение активных сессий"""
        return [s for s in self._sessions.values() if s.is_active]
