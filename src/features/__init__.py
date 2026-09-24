"""
AI-EVOLVE Features Module
Advanced gameplay mechanics for AI evolution and dynamic combat.
"""

from src.features.adaptive_anticipation import (
    AdaptiveAnticipationSystem,
    AnticipationStats,
    AttackPattern,
    PatternRecord,
)
from src.features.dynamic_weather import (
    DynamicWeatherSystem,
    WeatherEffect,
    WeatherType,
)
from src.features.genetic_memory import GeneticMemorySystem, MemoryFragment
from src.features.morale_system import MoraleState, MoraleStats, MoraleSystem
from src.features.neuro_resonance import (
    NeuroResonanceSystem,
    ResonanceLink,
    ResonanceState,
    ResonanceStats,
)
from src.features.terraforming import (
    TerraformingSystem,
    TerrainModification,
    TerrainModificationType,
)

__all__ = [
    # Genetic Memory
    "GeneticMemorySystem",
    "MemoryFragment",
    
    # Dynamic Weather
    "DynamicWeatherSystem",
    "WeatherType",
    "WeatherEffect",
    
    # Morale System
    "MoraleSystem",
    "MoraleState",
    "MoraleStats",
    
    # Neuro Resonance
    "NeuroResonanceSystem",
    "ResonanceState",
    "ResonanceLink",
    "ResonanceStats",
    
    # Terraforming
    "TerraformingSystem",
    "TerrainModificationType",
    "TerrainModification",
    
    # Adaptive Anticipation
    "AdaptiveAnticipationSystem",
    "AttackPattern",
    "PatternRecord",
    "AnticipationStats"
]