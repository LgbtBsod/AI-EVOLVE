"""
AI-EVOLVE Features Module
Advanced gameplay mechanics for AI evolution and dynamic combat.
"""

from src.features.genetic_memory import GeneticMemorySystem, MemoryFragment
from src.features.dynamic_weather import DynamicWeatherSystem, WeatherType, WeatherEffect
from src.features.morale_system import MoraleSystem, MoraleState, MoraleStats
from src.features.neuro_resonance import NeuroResonanceSystem, ResonanceState, ResonanceLink, ResonanceStats
from src.features.terraforming import TerraformingSystem, TerrainModificationType, TerrainModification
from src.features.adaptive_anticipation import AdaptiveAnticipationSystem, AttackPattern, PatternRecord, AnticipationStats

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