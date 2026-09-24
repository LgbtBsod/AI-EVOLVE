"""
AI-EVOLVE Core Module
Exports core components: EventSystem, DatabaseCore
"""
from ai_evolve.core.event_system import EventSystem, event_system
from ai_evolve.db.database_core import DatabaseCore, db_core, Base, GameEntity

__all__ = [
    'EventSystem',
    'event_system',
    'DatabaseCore',
    'db_core',
    'Base',
    'GameEntity'
]
