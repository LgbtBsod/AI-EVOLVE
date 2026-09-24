"""
Модуль адаптивных ML-агентов для обучения персонажей и врагов.
"""

from .adaptive_agent import (
    ActionType,
    AdaptiveNeuralNetwork,
    AdaptiveRLAgent,
    BattleContext,
    EntityState,
    SkillDiscoveryState,
    SkillInfo,
    WeaponInfo,
)

__all__ = [
    'ActionType',
    'AdaptiveNeuralNetwork',
    'AdaptiveRLAgent',
    'BattleContext',
    'EntityState',
    'SkillDiscoveryState',
    'SkillInfo',
    'WeaponInfo'
]
