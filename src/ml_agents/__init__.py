"""
Модуль адаптивных ML-агентов для обучения персонажей и врагов.
"""

from .adaptive_agent import (
    AdaptiveRLAgent,
    AdaptiveNeuralNetwork,
    ActionType,
    SkillDiscoveryState,
    SkillInfo,
    WeaponInfo,
    EntityState,
    BattleContext
)

__all__ = [
    'AdaptiveRLAgent',
    'AdaptiveNeuralNetwork',
    'ActionType',
    'SkillDiscoveryState',
    'SkillInfo',
    'WeaponInfo',
    'EntityState',
    'BattleContext'
]
