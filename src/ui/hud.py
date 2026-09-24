#!/usr/bin/env python3
"""HUD игрового мира.

    слева вверху   - полосы HP / маны / стамины, уровень, опыт, очки характеристик
    под ними       - эмоция героя, подсказка игрока и что герой сейчас «думает»
    справа вверху  - лента событий (scene.messages: уровень, боссы, трюки, зелья)
    внизу по центру - полоса HP босса (если он на уровне) и клавиши управления

Шрифт - DejaVu Sans из assets/fonts (встроенный шрифт Panda3D не знает кириллицу).
Без шрифта HUD работает со встроенным и латиницей.
"""

import logging

from direct.gui.DirectGui import DirectWaitBar
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

from src.ui.fonts import load_ui_font

logger = logging.getLogger(__name__)

FEED_LINES = 6
KEYS_HELP = ("F1-F6 эмоция · стрелки - сторона · C сундук · X выход · N NPC · Z снять подсказку · "
             "1/2/3/4 враг/ловушка/сундук/босс")
BARS = (("health", "max_health", (0.85, 0.15, 0.15, 1)),
        ("mana", "max_mana", (0.2, 0.35, 0.95, 1)),
        ("stamina", "max_stamina", (0.95, 0.75, 0.15, 1)))


def _font(game):
    loader = getattr(game, "loader", None) or getattr(getattr(game, "showbase", None), "loader", None)
    return load_ui_font(loader)


class EnhancedHUD:
    """HUD поверх игровой сцены: состояние героя, его настроение, события, босс."""

    def __init__(self, game):
        self.game = game
        self.font = None
        self.status_text = None
        self.mood_text = None
        self.feed_text = None
        self.boss_text = None
        self.hint_text = None
        self.bars = []
        self.bar_labels = []
        self.boss_bar = None

    def _text(self, pos, scale, fg=(1, 1, 1, 1), align=TextNode.ALeft, text=""):
        kw = {"font": self.font} if self.font is not None else {}
        return OnscreenText(text=text, pos=pos, scale=scale, fg=fg, shadow=(0, 0, 0, 1), align=align,
                            mayChange=True, **kw)

    def create_hud(self):
        self.font = _font(self.game)
        y = 0.93
        for _cur, _cap, color in BARS:
            bar = DirectWaitBar(range=100, value=100, pos=(-1.05, 0, y), scale=(0.28, 1, 0.3),
                                barColor=color, frameColor=(0.1, 0.1, 0.1, 0.8))
            self.bars.append(bar)
            self.bar_labels.append(self._text((-0.74, y - 0.012), 0.034))
            y -= 0.045
        self.status_text = self._text((-1.32, 0.78), 0.038)
        self.mood_text = self._text((-1.32, 0.73), 0.042, fg=(1, 0.9, 0.6, 1))
        self.feed_text = self._text((1.3, 0.92), 0.036, fg=(0.85, 0.95, 1, 1), align=TextNode.ARight)
        self.boss_text = self._text((0, -0.78), 0.045, fg=(1, 0.6, 0.5, 1), align=TextNode.ACenter)
        self.boss_bar = DirectWaitBar(range=100, value=100, pos=(0, 0, -0.84), scale=(0.6, 1, 0.5),
                                      barColor=(0.75, 0.1, 0.1, 1), frameColor=(0.1, 0.1, 0.1, 0.8))
        self.boss_bar.hide()
        help_text = KEYS_HELP if self.font is not None else "F1-F6 mood, arrows/C/X/N/Z hints, 1-4 spawn"
        self.hint_text = self._text((0, -0.95), 0.036, fg=(1, 1, 0.6, 1), align=TextNode.ACenter, text=help_text)
        logger.info("HUD created (font: %s)", "DejaVu" if self.font is not None else "built-in")

    # ---------------------------------------------------------------- update
    def update_hud(self, player):
        if not self.status_text or not player:
            return
        for bar, label, (cur, cap, _c), tag in zip(self.bars, self.bar_labels, BARS, ("HP", "MP", "ST")):
            top = float(getattr(player, cap, 0) or 0)
            now = float(getattr(player, cur, 0) or 0)
            bar["value"] = 100.0 * now / top if top > 0 else 0
            label.setText(f"{tag} {now:.0f}/{top:.0f}")
        pts = int(getattr(player, "attribute_points", 0) or 0)
        latin = self.font is None
        self.status_text.setText(
            "{} {}   {} {}/{}{}".format(
                "Lvl" if latin else "Уровень", player.level, "XP" if latin else "Опыт",
                int(player.experience), int(getattr(player, "experience_to_next_level", 0) or 0),
                "" if not pts else (f"   +{pts} pts" if latin else f"   +{pts} очков")))
        self._update_mood(player, latin)
        scene = getattr(self.game, "scene", None)
        self._update_feed(scene, latin)
        self._update_boss(scene)

    def _update_mood(self, player, latin):
        drive = getattr(player, "drive", None)
        if drive is None or latin:
            self.mood_text.setText("")
            return
        line = drive.thought(getattr(player, "ai_state", None) if getattr(player, "ai_state", "") == "retreating"
                             else None)
        mind = getattr(player, "mind", None)
        if mind is not None and mind.stance == "press":
            line += " · давлю до конца"
        self.mood_text.setText(line)

    def _update_feed(self, scene, latin):
        messages = list(getattr(scene, "messages", []) or [])[-FEED_LINES:] if scene is not None else []
        if latin:
            messages = []
        self.feed_text.setText("\n".join(text for _t, text in messages))

    def _update_boss(self, scene):
        bosses = [b for b in (getattr(scene, "active_bosses", None) or []) if b.is_alive()] if scene else []
        if not bosses:
            self.boss_bar.hide()
            self.boss_text.setText("")
            return
        b = bosses[0]
        self.boss_bar.show()
        self.boss_bar["value"] = 100.0 * b.health / max(1.0, b.max_health)
        name = getattr(b, "display_name", b.enemy_type) if self.font is not None else b.enemy_type
        self.boss_text.setText(f"{name}   {b.health:.0f}/{b.max_health:.0f}")

    def destroy(self):
        for w in [self.status_text, self.mood_text, self.feed_text, self.boss_text, self.hint_text,
                  self.boss_bar, *self.bars, *self.bar_labels]:
            if w is not None:
                w.destroy()
        self.bars, self.bar_labels = [], []
        self.status_text = self.mood_text = self.feed_text = self.boss_text = self.hint_text = None
        self.boss_bar = None
