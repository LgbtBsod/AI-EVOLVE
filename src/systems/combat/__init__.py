"""
Combat System Package

Unified combat system using component-based architecture.
All combat logic flows through RefactoredCombatSystem with components.
"""

from src.systems.combat.components import (
    CombatStatsComponent,
    DamageComponent,
    HealthComponent,
)
from src.systems.combat.refactored_combat_system import CombatEntity, RefactoredCombatSystem

__all__ = [
    # Systems
    "RefactoredCombatSystem",
    "CombatEntity",
    # Components
    "HealthComponent",
    "DamageComponent",
    "CombatStatsComponent",
]
