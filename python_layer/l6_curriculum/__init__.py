"""
L6 - Curriculum Learning Layer

Управление сложностью обучения:
- Оценка текущего уровня агента
- Подбор подходящей сложности окружения
- Подсказки игроку-тренеру
- Прогрессия через curriculum stages
"""

from .curriculum_manager import (
    CurriculumManager,
    PlayerCoachInterface,
    AgentMetrics,
    WeaknessAnalysis,
    CurriculumStage,
    DifficultyLevel,
)

__all__ = [
    'CurriculumManager',
    'PlayerCoachInterface',
    'AgentMetrics',
    'WeaknessAnalysis',
    'CurriculumStage',
    'DifficultyLevel',
]