#!/usr/bin/env python3
"""Game Scene - Main Gameplay"""

import logging
from src.scenes.scene_manager import Scene

logger = logging.getLogger(__name__)


class GameScene(Scene):
    """Игровой мир: тонкая обёртка SceneManager над EnhancedGameScene.

    Весь геймплей (герой под управлением ИИ, враги, ловушки, сундуки, HUD)
    живёт в EnhancedGameScene (src/scenes/main_game_scene.py). Эта сцена
    только встраивает её в жизненный цикл SceneManager:
    start -> создать мир и enter(), update -> handle_input + update,
    cleanup -> exit(). Созданный мир доступен как self.world и как
    game.scene - по game.scene его ищут сущности, эффекты и dev_probe.
    """

    def __init__(self):
        super().__init__("game_world")
        self.world = None

    def start(self) -> bool:
        if not super().start():
            return False

        game = getattr(self.scene_manager, "game", None)
        if game is None:
            logger.error("GameScene: у SceneManager нет ссылки на game - мир не создан")
            return False

        # Локальный импорт: main_game_scene тянет Panda3D-сущности, которые
        # не нужны при простом импорте менеджера сцен
        from src.scenes.main_game_scene import EnhancedGameScene

        self.world = EnhancedGameScene(game, dev_mode=getattr(game, "dev_mode", False))
        game.scene = self.world
        self.world.enter()
        logger.info("GameScene: игровой мир создан")
        return True

    def update(self, delta_time: float) -> None:
        if self.world is None:
            return
        game = self.scene_manager.game
        self.world.handle_input(getattr(game, "_keys", {}))
        self.world.update(delta_time)

    def cleanup(self) -> None:
        if self.world is not None:
            self.world.exit()
            game = getattr(self.scene_manager, "game", None)
            if game is not None and getattr(game, "scene", None) is self.world:
                game.scene = None
            self.world = None
        super().cleanup()
