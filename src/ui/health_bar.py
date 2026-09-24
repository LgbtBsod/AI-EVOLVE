#!/usr/bin/env python3
"""Полоска HP над юнитом, отрисованная прямо в 3D-мире (billboard к камере).

main_game_scene.py раньше не давал никакого визуального фидбека по бою —
кубы просто исчезали при смерти. Без этого невозможно читать бой между
ИИ-персонажем и врагами со стороны.

REFACTORING: Теперь использует Renderer Abstraction Layer для:
- Headless тестирования без GUI
- Изоляции зависимости от Panda3D
- Поддержки future engine migration
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.renderer import IRenderer

logger = logging.getLogger(__name__)


class HealthBar:
    """Billboard-полоска HP, прикрепляемая к NodePath сущности.
    
    REFACTORED: Использует IRenderer интерфейс вместо прямых импортов panda3d.core
    """

    def __init__(self, width: float = 1.0, height: float = 0.12, renderer: Any | None = None):
        self.width = width
        self.height = height
        self.renderer = renderer
        self.root = None
        self.fill = None
        self.border = None
        self._fraction = 1.0
        self._is_headless = False
        
        # Определяем режим работы
        if renderer is not None:
            from src.core.renderer import HeadlessRenderer
            self._is_headless = renderer.is_headless
            logger.debug(f"HealthBar initialized with {renderer.__class__.__name__}")

    def create(self, parent: Any, z_offset: float = 2.5):
        """Создать health bar.
        
        Args:
            parent: Родительский узел (NodePath или mock)
            z_offset: Смещение по Z относительно родителя
        """
        if self._is_headless:
            # Headless mode - создаём mock объекты
            logger.debug(f"[Headless] Creating health bar at z={z_offset}")
            self.root = type('MockNode', (), {
                'setPos': lambda x, y, z: None,
                'attachNewNode': lambda name: type('MockChild', (), {'removeNode': lambda: None})(),
                'removeNode': lambda: None,
                'setName': lambda name: None
            })()
            self.fill = type('MockFill', (), {'setSx': lambda x: None, 'setColor': lambda *args: None})()
            return
        
        # Production mode - используем Panda3D напрямую (legacy support)
        # В будущем полностью перейдём на renderer.create_health_bar()
        try:
            from panda3d.core import CardMaker, TransparencyAttrib
            
            self.root = parent.attachNewNode("health_bar")
            self.root.setPos(0, 0, z_offset)
            self.root.setBillboardPointEye()
            self.root.setTransparency(TransparencyAttrib.MAlpha)
            self.root.setLightOff(1)
            self.root.setDepthWrite(False)
            self.root.setBin("fixed", 100)

            bg_cm = CardMaker("health_bar_bg")
            bg_cm.setFrame(-self.width / 2, self.width / 2, -self.height / 2, self.height / 2)
            bg = self.root.attachNewNode(bg_cm.generate())
            bg.setColor(0.15, 0.15, 0.15, 0.85)

            # Полоса заполнения "растёт" от левого края - пивот в 0, карта в [0, width].
            fill_cm = CardMaker("health_bar_fill")
            fill_cm.setFrame(0, self.width, -self.height / 2, self.height / 2)
            self.fill = self.root.attachNewNode(fill_cm.generate())
            self.fill.setPos(-self.width / 2, 0.01, 0)
            self.fill.setColor(0.2, 0.9, 0.2, 1)
            
            logger.debug("HealthBar created with Panda3D")
            
        except ImportError:
            logger.warning("Panda3D not available, using headless fallback")
            self._is_headless = True
            self.create(parent, z_offset)  # Рекурсивный вызов в headless режим

    def update(self, fraction: float):
        """Обновить отображение здоровья.
        
        Args:
            fraction: Доля здоровья от 0.0 до 1.0
        """
        if not self.fill:
            return
        fraction = max(0.0, min(1.0, fraction))
        if fraction == self._fraction:
            return
        self._fraction = fraction
        
        if self._is_headless:
            logger.debug(f"[Headless] HealthBar updated to {fraction:.1%}")
            return
        
        self.fill.setSx(max(0.001, fraction))
        if fraction > 0.5:
            self.fill.setColor(0.2, 0.9, 0.2, 1)
        elif fraction > 0.25:
            self.fill.setColor(0.95, 0.8, 0.1, 1)
        else:
            self.fill.setColor(0.9, 0.15, 0.15, 1)

    def destroy(self):
        """Удалить health bar из сцены."""
        if self._is_headless:
            logger.debug("[Headless] HealthBar destroyed")
            return
        
        if self.root:
            self.root.removeNode()
        self.root = None
        self.fill = None
        self.border = None
        self.fill = None
