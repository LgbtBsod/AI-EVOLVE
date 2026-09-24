#!/usr/bin/env python3
"""Main Menu Scene"""

import logging
import os
import sys

from src.scenes.scene_manager import Scene

logger = logging.getLogger(__name__)

# Встроенный шрифт Panda3D не содержит кириллицы - русские подписи без
# системного TTF рендерятся пустыми. Берём первый найденный шрифт Windows,
# иначе меню падает обратно на английские подписи.
_CYRILLIC_FONT_CANDIDATES = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
    for name in ("segoeui.ttf", "arial.ttf", "tahoma.ttf")
]


def _load_cyrillic_font(game):
    from panda3d.core import Filename

    for path in _CYRILLIC_FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        # WINDIR даёт "C:\WINDOWS", а Panda3D сверяет регистр с реальной
        # папкой "C:\Windows" и иначе "не находит" файл - makeTrueCase чинит.
        # FontPool при этом принимает только str, не Filename.
        filename = Filename.fromOsSpecific(path)
        filename.makeTrueCase()
        try:
            font = game.loader.loadFont(filename.getFullpath())
        except OSError:
            continue
        if font is not None and font.isValid():
            return font
    return None


class MenuScene(Scene):
    """Главное меню игры: «Начать игру» (Enter) и «Выход» (Esc)."""

    def __init__(self):
        super().__init__("main_menu")
        self.menu_items = []
        self._widgets = []
        self._previous_background = None

    def initialize(self) -> bool:
        logger.info("Инициализация MenuScene")
        if not super().initialize():
            return False

        self.menu_items = [
            {"id": "start", "text": "Начать игру", "fallback": "Start game", "action": self._start_game},
            {"id": "exit", "text": "Выход", "fallback": "Quit", "action": self._exit_game},
        ]

        logger.info("MenuScene инициализирована")
        return True

    def start(self) -> bool:
        logger.info("Запуск MenuScene")
        if not super().start():
            return False

        self._render_menu()
        return True

    def update(self, delta_time: float) -> None:
        """Меню статично - вся логика в обработчиках кнопок"""

    def cleanup(self) -> None:
        game = self._game()
        for widget in self._widgets:
            widget.destroy()
        self._widgets.clear()
        if game is not None:
            game.ignore("enter")
            if self._previous_background is not None:
                game.setBackgroundColor(self._previous_background)
                self._previous_background = None
        super().cleanup()

    def _game(self):
        return getattr(self.scene_manager, "game", None) if self.scene_manager else None

    def _render_menu(self):
        """Отрисовка меню"""
        game = self._game()
        if game is None:
            logger.warning("MenuScene: нет ссылки на game - меню не отрисовано")
            return

        from direct.gui.DirectGui import DirectButton, DirectFrame
        from direct.gui.OnscreenText import OnscreenText

        self._previous_background = game.getBackgroundColor()
        game.setBackgroundColor(0.03, 0.035, 0.05, 1)

        font = _load_cyrillic_font(game)
        label_key = "text" if font is not None else "fallback"
        font_kwargs = {"text_font": font} if font is not None else {}

        frame = DirectFrame(frameColor=(0.05, 0.06, 0.09, 0.92), frameSize=(-0.6, 0.6, -0.5, 0.55), pos=(0, 0, 0))
        self._widgets.append(frame)

        title = OnscreenText(
            text="AI-EVOLVE", pos=(0, 0.35), scale=0.12, fg=(0.9, 0.95, 1.0, 1),
            parent=frame, mayChange=False,
        )
        self._widgets.append(title)

        for index, item in enumerate(self.menu_items):
            button = DirectButton(
                text=item[label_key], scale=0.075, pos=(0, 0, 0.08 - index * 0.2),
                frameSize=(-4.2, 4.2, -0.9, 1.3), frameColor=(0.18, 0.22, 0.32, 1),
                text_fg=(1, 1, 1, 1), relief=1, command=item["action"], parent=frame,
                **font_kwargs,
            )
            self._widgets.append(button)

        hint = OnscreenText(
            text="Enter - start, Esc - quit", pos=(0, -0.42), scale=0.045,
            fg=(0.6, 0.65, 0.75, 1), parent=frame, mayChange=False,
        )
        self._widgets.append(hint)

        game.accept("enter", self._start_game)
        logger.debug("Рендеринг меню")

    def _start_game(self):
        """Начать новую игру"""
        logger.info("Запуск новой игры")
        if self.scene_manager:
            self.scene_manager.load_scene("game_world")

    def _exit_game(self):
        """Выход из игры"""
        logger.info("Выход из игры")
        sys.exit()
