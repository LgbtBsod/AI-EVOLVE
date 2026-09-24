#!/usr/bin/env python3
"""Точка входа в игру.

Архитектура на основе ядра игры (GameCore) с плагинной системой:
- GameCore: центральное ядро, управляющее жизненным циклом
- DatabaseCore: ядро БД (SQLAlchemy) для всех операций с данными
- EventSystem: система событий для слабой связности компонентов
- StateManager: управление состояниями игры
- SceneManager: сцены (main_menu -> game_world), подключается к ядру
- Plugins: фичи как плагины (effects -> combat)

Игровой дизайн: персонажем управляет ИИ (движение/бой/лут выполняются
автоматически), а игрок выступает "дирижёром" уровня — спавнит врагов,
ловушки и сундуки рядом с героем клавишами 1/2/3.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Корень приложения: рядом с exe в собранной игре (build_apps ставит
# sys.frozen), иначе каталог этого файла.
if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parent
    sys.path.insert(0, str(APP_ROOT))

from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import loadPrcFileData  # noqa: E402

from src.core.game_core import GameCore  # noqa: E402
from src.database.db_core import DatabaseCore  # noqa: E402
from src.core.event_system import EventSystem  # noqa: E402
from src.core.state_manager import StateManager  # noqa: E402
from src.scenes.scene_manager import SceneManager  # noqa: E402
from src.features.combat_plugin import CombatPlugin  # noqa: E402
from src.features.effects_plugin import EffectsPlugin  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

loadPrcFileData("", "window-title AI-EVOLVE (dev build)")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "show-frame-rate-meter 0")


class Game(ShowBase):
    """Основной класс игры с архитектурой на основе ядра.

    GameCore координирует все системы:
    - DatabaseCore: операции с БД (чтение/запись/транзакции)
    - EventSystem: события между компонентами
    - StateManager: состояния игры
    - SceneManager: сцены (подключается к ядру)
    - Plugins: фичи как плагины; их системы доступны как
      game.effect_system / game.combat_system (их ищут сущности)
    """

    def __init__(self, dev_mode: bool = False, headless: bool = False, skip_menu: bool = False,
                 db_url: str = "sqlite:///saves/game_database.db"):
        # Игра читает config/*.json и пишет saves/ по относительным путям, а
        # собранную игру (например, двойным кликом на macOS) запускают с любым
        # текущим каталогом - поэтому явно работаем из корня приложения.
        # saves/ не хранится в git, SQLite сам каталог не создаёт.
        os.chdir(APP_ROOT)
        (APP_ROOT / "saves").mkdir(exist_ok=True)

        if headless:
            # Offscreen-буфер без окна и звука - для тестов и CI
            loadPrcFileData("", "window-type offscreen")
            loadPrcFileData("", "audio-library-name null")
            loadPrcFileData("", "sync-video 0")

        super().__init__()
        self.showbase = self
        self.disableMouse()

        self.dev_mode = dev_mode
        self.scene = None  # игровой мир; выставляет GameScene при загрузке game_world
        self._keys = {
            "1": False, "2": False, "3": False,
            "e": False, "space": False, "mouse1": False,
        }

        # === ЯДРО ИГРЫ ===
        logger.info("=== Инициализация ядра игры ===")
        self.game_core = GameCore()
        self.database_core = DatabaseCore(db_url=db_url)
        self.event_system = EventSystem()
        self.state_manager = StateManager()
        self.game_core.set_dependencies(
            database_core=self.database_core,
            event_system=self.event_system,
            state_manager=self.state_manager,
        )
        if not self.game_core.initialize():
            raise RuntimeError("GameCore не инициализировался - причина в логе выше")

        # === СЦЕНЫ ===
        self.scene_manager = SceneManager()
        self.scene_manager.set_architecture_components(self.state_manager)
        self.scene_manager.game = self  # сцены достают отсюда render/cam/taskMgr
        if not self.scene_manager.initialize():
            raise RuntimeError("SceneManager не инициализировался - причина в логе выше")
        self.game_core.set_scene_manager(self.scene_manager)

        # === ПЛАГИНЫ (порядок важен: combat получает effect_system) ===
        self.effects_plugin = EffectsPlugin(entity_lookup=self._find_entity_by_id)
        self.combat_plugin = CombatPlugin(effects_plugin=self.effects_plugin)
        for plugin_id, plugin, deps in (
            ("effects", self.effects_plugin, None),
            ("combat", self.combat_plugin, ["effects"]),
        ):
            plugin.set_core_references(
                game_core=self.game_core,
                database_core=self.database_core,
                event_system=self.event_system,
                state_manager=self.state_manager,
            )
            if not self.game_core.register_plugin(plugin_id, plugin, dependencies=deps):
                raise RuntimeError(f"Плагин {plugin_id} не зарегистрировался - причина в логе выше")

        self.effect_system = self.effects_plugin.effect_system
        self.combat_system = self.combat_plugin.combat_system

        # Запуск ядра запускает плагины и SceneManager (он открывает main_menu)
        if not self.game_core.start():
            raise RuntimeError("GameCore не запустился - причина в логе выше")
        if skip_menu:
            self.scene_manager.load_scene("game_world")

        self._bind_input()
        self.taskMgr.add(self._game_loop, "main_game_loop")
        self.accept("escape", sys.exit)

        logger.info(
            "Game started (dev_mode=%s, scene=%s). Plugins: %s. "
            "1/2/3 = spawn enemy/trap/chest, space/mouse1 = force attack, Esc = quit.",
            dev_mode, self.scene_manager.active_scene, list(self.game_core.plugins.keys()),
        )

    def _bind_input(self):
        for key in self._keys:
            self.accept(key, self._set_key, [key, True])
            self.accept(f"{key}-up", self._set_key, [key, False])

    def _set_key(self, key, pressed):
        self._keys[key] = pressed

    def _find_entity_by_id(self, entity_id):
        """Ищет сущность по entity_id среди игрока/врагов игрового мира."""
        scene = self.scene
        if scene is None:
            return None
        if scene.player is not None and scene.player.entity_id == entity_id:
            return scene.player
        for enemy in scene.enemies:
            if enemy.entity_id == entity_id:
                return enemy
        return None

    def _game_loop(self, task):
        dt = globalClock.getDt()  # noqa: F821 (injected by ShowBase)
        # Ядро обновляет плагины (эффекты) и SceneManager (активную сцену)
        self.game_core.update(dt)
        return task.cont


def parse_args():
    parser = argparse.ArgumentParser(description="AI-EVOLVE launcher")
    parser.add_argument(
        "--dev", action="store_true",
        help="Use a small dev-sized map (fast to traverse) instead of the full-size world",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Standalone build only: use the full-size world (the build defaults to the dev map, like run_game.bat)",
    )
    parser.add_argument(
        "--skip-menu", action="store_true",
        help="Start directly in the game world instead of the main menu",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    # Собранную игру запускают двойным кликом, без аргументов - она ведёт
    # себя как run_game.bat: маленькая карта, пока не попросили --full
    dev_mode = (not args.full) if getattr(sys, "frozen", False) else args.dev
    game = Game(dev_mode=dev_mode, skip_menu=args.skip_menu)
    game.run()


if __name__ == "__main__":
    main()
