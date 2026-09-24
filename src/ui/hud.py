#!/usr/bin/env python3
"""Минимальный HUD для первого играбельного билда.

main_game_scene.py импортирует EnhancedHUD из этого модуля, но модуль
раньше не существовал вовсе (src/ui/ не было в репозитории), поэтому игра
падала на первом же enter(). Это временная, но полностью рабочая реализация:
текстовый оверлей с HP/MP/уровнем игрока и текущим режимом создания объектов.
"""

import logging

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

logger = logging.getLogger(__name__)


class EnhancedHUD:
    """Простой текстовый HUD поверх игровой сцены."""

    def __init__(self, game):
        self.game = game
        self.status_text = None
        self.hint_text = None

    def create_hud(self):
        self.status_text = OnscreenText(
            text="",
            pos=(-1.3, 0.9),
            scale=0.06,
            fg=(1, 1, 1, 1),
            shadow=(0, 0, 0, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.hint_text = OnscreenText(
            # ASCII only: default Panda3D built-in font has no Cyrillic glyphs
            # and spams "No definition... for character" warnings otherwise.
            text="1/2/3: spawn enemy/trap/chest near hero",
            pos=(0, -0.95),
            scale=0.05,
            fg=(1, 1, 0.6, 1),
            shadow=(0, 0, 0, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )
        logger.info("HUD created")

    def update_hud(self, player):
        if not self.status_text or not player:
            return
        self.status_text.setText(
            "HP: {:.0f}/{:.0f}\n"
            "MP: {:.0f}/{:.0f}\n"
            "Stamina: {:.0f}/{:.0f}\n"
            "Level: {}  XP: {}".format(
                player.health, player.max_health,
                player.mana, player.max_mana,
                player.stamina, player.max_stamina,
                player.level, player.experience,
            )
        )

    def destroy(self):
        if self.status_text:
            self.status_text.destroy()
            self.status_text = None
        if self.hint_text:
            self.hint_text.destroy()
            self.hint_text = None
