"""Шрифт интерфейса с кириллицей: DejaVu Sans, лежит в assets/fonts.

Встроенный шрифт Panda3D кириллицу не знает, а системные шрифты на разных ОС
разные - поэтому HUD и меню берут один и тот же шрифт из репозитория.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def app_root() -> Path:
    """Корень приложения: рядом с exe в собранной игре, иначе корень репозитория."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def font_path(bold: bool = False) -> Path:
    return app_root() / "assets" / "fonts" / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")


def load_ui_font(loader, bold: bool = False):
    """Шрифт интерфейса или None (тогда вызывающий падает обратно на латиницу).

    Путь Windows Panda3D принимает только в своём формате (/c/Users/...) и с
    точным регистром каталогов - иначе "Unable to find font file".
    """
    if loader is None:
        return None
    path = font_path(bold)
    if not path.exists():
        logger.warning("UI font not found: %s", path)
        return None
    try:
        from panda3d.core import Filename

        filename = Filename.fromOsSpecific(str(path))
        filename.makeTrueCase()
        font = loader.loadFont(filename.getFullpath())  # FontPool берёт только str
        # Шрифт общий (FontPool кеширует по пути): меню уже могло нарисовать текст, а
        # setPixelsPerUnit разрешён только пока нет страниц глифов ("get_num_pages() == 0")
        if font.getNumPages() == 0:
            font.setPixelsPerUnit(60)
        return font
    except Exception as exc:  # шрифт - украшение, не причина падать
        logger.warning("UI font not loaded: %s", exc)
        return None
