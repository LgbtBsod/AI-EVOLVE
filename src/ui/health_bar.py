#!/usr/bin/env python3
"""Полоска HP над юнитом, отрисованная прямо в 3D-мире (billboard к камере).

main_game_scene.py раньше не давал никакого визуального фидбека по бою —
кубы просто исчезали при смерти. Без этого невозможно читать бой между
ИИ-персонажем и врагами со стороны."""

from panda3d.core import CardMaker, TransparencyAttrib


class HealthBar:
    """Billboard-полоска HP, прикрепляемая к NodePath сущности."""

    def __init__(self, width: float = 1.0, height: float = 0.12):
        self.width = width
        self.height = height
        self.root = None
        self.fill = None
        self._fraction = 1.0

    def create(self, parent, z_offset: float):
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

    def update(self, fraction: float):
        if not self.fill:
            return
        fraction = max(0.0, min(1.0, fraction))
        if fraction == self._fraction:
            return
        self._fraction = fraction
        self.fill.setSx(max(0.001, fraction))
        if fraction > 0.5:
            self.fill.setColor(0.2, 0.9, 0.2, 1)
        elif fraction > 0.25:
            self.fill.setColor(0.95, 0.8, 0.1, 1)
        else:
            self.fill.setColor(0.9, 0.15, 0.15, 1)

    def destroy(self):
        if self.root:
            self.root.removeNode()
        self.root = None
        self.fill = None
