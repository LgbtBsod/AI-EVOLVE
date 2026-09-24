"""
L7 - Игрок-тренер (Renderer Layer)

Panda3D рендеринг и UI:
- Изометрическая камера
- Панели управления (спавн, директивы, эмоции)
- Редактор сцены
- Визуализация обучения
"""

from .renderer import (
    IsometricCamera,
    SceneEditor,
    TrainerUI,
    AutoBalancer,
    ToolMode,
    SpawnConfig,
    PlayerDirective,
    create_training_session,
)

__all__ = [
    'IsometricCamera',
    'SceneEditor',
    'TrainerUI',
    'AutoBalancer',
    'ToolMode',
    'SpawnConfig',
    'PlayerDirective',
    'create_training_session',
]