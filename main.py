#!/usr/bin/env python3
"""Точка входа в игру.

SceneManager (src/scenes/scene_manager.py) сейчас нерабочий: он импортирует
шесть модулей сцен (menu_scene, game_scene, load_scene, pause_scene,
creator_scene, settings_scene), которых нет в репозитории, поэтому его
инициализация всегда падает и молча проглатывается. Пока это не починено,
main.py поднимает Panda3D напрямую и запускает EnhancedGameScene из
src/scenes/main_game_scene.py в обход SceneManager — это первый шаг к тому,
чтобы вообще увидеть игру на экране.

Игровой дизайн: персонажем управляет ИИ (движение/бой/лут выполняются
автоматически), а игрок выступает "дирижёром" уровня — спавнит врагов,
ловушки и сундуки рядом с героем клавишами 1/2/3.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import loadPrcFileData  # noqa: E402

from src.core.rng_manager import get_default_rng  # noqa: E402
from src.systems.combat.combat_system import CombatSystem  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

loadPrcFileData("", "window-title AI-EVOLVE (dev build)")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "sync-video 1")


class Game(ShowBase):
    """Тонкая обёртка над ShowBase, которую ожидают игровые системы.

    main_game_scene.py и сущности (Character/EnhancedEnemy) обращаются к
    game.render, game.cam и game.showbase.taskMgr — поэтому self.showbase
    указывает сам на себя.
    """

    def __init__(self, dev_mode: bool = False):
        super().__init__()
        self.showbase = self
        self.disableMouse()

        # Единая боевая система: Character/EnhancedEnemy.attack() дергают
        # game.combat_system.execute_attack(...) вместо дублирования формул
        # крита/уворота у каждой сущности по отдельности.
        self.combat_system = CombatSystem(rng=get_default_rng())

        self._keys = {
            "1": False, "2": False, "3": False,
            "e": False, "space": False, "mouse1": False,
        }
        self._bind_input()

        from src.scenes.main_game_scene import EnhancedGameScene

        self.scene = EnhancedGameScene(self, dev_mode=dev_mode)
        self.scene.enter()

        self.taskMgr.add(self._game_loop, "main_game_loop")
        self.accept("escape", sys.exit)

        logger.info(
            "Game started (dev_mode=%s, world_size=%s). 1/2/3 = spawn enemy/trap/chest, "
            "space/mouse1 = force attack, Esc = quit.",
            dev_mode, self.scene.world_size,
        )

    def _bind_input(self):
        for key in self._keys:
            self.accept(key, self._set_key, [key, True])
            self.accept(f"{key}-up", self._set_key, [key, False])

    def _set_key(self, key, pressed):
        self._keys[key] = pressed

    def _game_loop(self, task):
        dt = globalClock.getDt()  # noqa: F821 (injected by ShowBase)
        self.scene.handle_input(self._keys)
        self.scene.update(dt)
        return task.cont


def parse_args():
    parser = argparse.ArgumentParser(description="AI-EVOLVE launcher")
    parser.add_argument(
        "--dev", action="store_true",
        help="Use a small dev-sized map (fast to traverse) instead of the full-size world",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    game = Game(dev_mode=args.dev)
    game.run()


if __name__ == "__main__":
    main()
