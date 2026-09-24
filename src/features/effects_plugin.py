#!/usr/bin/env python3
"""
Effects Plugin - подключает EffectSystem (баффы/дебаффы/DoT/HoT) к ядру.

EffectSystem сама считает длительности и тики; плагин только встраивает её
в жизненный цикл GameCore (update каждый кадр) и применяет тики к живым
сущностям через apply_tick_to_entity - тот же путь take_damage/death-latch,
что и у обычного урона.
"""

import logging
from collections.abc import Callable
from typing import Any

from src.core.architecture import LifecycleState
from src.core.base_plugin import BasePlugin
from src.systems.effects.effect_system import EffectSystem, apply_tick_to_entity

logger = logging.getLogger(__name__)


class EffectsPlugin(BasePlugin):
    """Плагин системы эффектов. Регистрируется в GameCore раньше CombatPlugin."""

    def __init__(self, entity_lookup: Callable[[str], Any] | None = None):
        """
        Args:
            entity_lookup: entity_id -> сущность (или None); нужен, чтобы
                применять тики эффектов к объектам сцены
        """
        super().__init__(
            plugin_id="effects_plugin",
            plugin_name="Effect System",
            version="1.0.0",
            dependencies=[],
        )
        self.effect_system: EffectSystem | None = None
        self._entity_lookup = entity_lookup

    def initialize(self) -> bool:
        try:
            self.effect_system = EffectSystem()
            if not self.effect_system.initialize():
                logger.error("EffectSystem не инициализировалась")
                return False
            self.effect_system.on_effect_tick = self._on_effect_tick
            self.system_state = LifecycleState.READY
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации EffectsPlugin: {e}", exc_info=True)
            return False

    def start(self) -> bool:
        # EffectSystem.update() - no-op, пока компонент не в RUNNING:
        # initialize() доводит только до READY, нужен явный start()
        if self.effect_system is None or not self.effect_system.start():
            logger.error("EffectSystem не запустилась")
            return False
        self.system_state = LifecycleState.RUNNING
        return True

    def update_logic(self, delta_time: float) -> None:
        self.effect_system.update(delta_time)

    def _on_effect_tick(self, entity_id: str, active_effect: Any) -> None:
        entity = self._entity_lookup(entity_id) if self._entity_lookup else None
        if entity is not None:
            apply_tick_to_entity(entity, active_effect)


__all__ = ['EffectsPlugin']
