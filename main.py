#!/usr/bin/env python3
"""Точка входа в игру.

Архитектура на основе ядра игры (GameCore) с плагинной системой:
- GameCore: центральное ядро, управляющее жизненным циклом
- DatabaseCore: ядро БД (SQLAlchemy) для всех операций с данными
- EventSystem: система событий для слабой связности компонентов
- StateManager: управление состояниями игры
- SceneManager: управление сценами (подключается как модуль)
- Plugins: фичи подключаются как плагины (combat, effects, и т.д.)

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

from src.core.game_core import GameCore  # noqa: E402
from src.database.db_core import DatabaseCore  # noqa: E402
from src.core.event_system import EventSystem  # noqa: E402
from src.core.state_manager import StateManager  # noqa: E402
from src.scenes.scene_manager import SceneManager  # noqa: E402
from src.features.combat_plugin import CombatPlugin  # noqa: E402

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
    """Основной класс игры с архитектурой на основе ядра.

    GameCore координирует все системы:
    - DatabaseCore: операции с БД (чтение/запись/транзакции)
    - EventSystem: события между компонентами
    - StateManager: состояния игры
    - SceneManager: сцены (подключается к ядру)
    - Plugins: фичи как плагины
    """

    def __init__(self, dev_mode: bool = False):
        super().__init__()
        self.showbase = self
        self.disableMouse()

        # === ИНИЦИАЛИЗАЦИЯ ЯДРА ИГРЫ ===
        logger.info("=== Инициализация ядра игры ===")
        
        # Создаем ядро игры
        self.game_core = GameCore()
        
        # Создаем ядро БД
        db_path = "sqlite:///saves/game_database.db"
        self.database_core = DatabaseCore(db_url=db_path)
        
        # Создаем систему событий
        self.event_system = EventSystem()
        
        # Создаем менеджер состояний
        self.state_manager = StateManager()
        
        # Устанавливаем зависимости ядра
        self.game_core.set_dependencies(
            database_core=self.database_core,
            event_system=self.event_system,
            state_manager=self.state_manager,
        )
        
        # Инициализируем ядро
        if not self.game_core.initialize():
            logger.error("Failed to initialize GameCore, falling back to legacy mode")
            self._fallback_init(dev_mode)
            return
        
        # === ПОДКЛЮЧЕНИЕ МОДУЛЕЙ ===
        logger.info("=== Подключение модулей ===")
        
        # Создаем и подключаем SceneManager
        self.scene_manager = SceneManager()
        self.scene_manager.set_architecture_components(self.state_manager)
        self.game_core.set_scene_manager(self.scene_manager)
        
        # === РЕГИСТРАЦИЯ ПЛАГИНОВ (ФИЧЕЙ) ===
        logger.info("=== Регистрация плагинов ===")
        
        # Combat Plugin - боевая система
        self.combat_plugin = CombatPlugin()
        self.combat_plugin.set_core_references(
            game_core=self.game_core,
            database_core=self.database_core,
            event_system=self.event_system,
            state_manager=self.state_manager,
        )
        self.game_core.register_plugin("combat", self.combat_plugin)
        
        # Запускаем ядро (оно запустит все системы и плагины)
        if not self.game_core.start():
            logger.error("Failed to start GameCore, falling back to legacy mode")
            self._fallback_init(dev_mode)
            return
        
        # Загружаем игровую сцену для dev-режима
        if dev_mode:
            logger.info("Dev mode: loading game_world directly")
            self.scene_manager.load_scene("game_world")
        
        # Получаем доступ к combat системе из плагина
        self.combat_system = getattr(self.combat_plugin, 'combat_system', None)
        
        self._keys = {
            "1": False, "2": False, "3": False,
            "e": False, "space": False, "mouse1": False,
        }
        self._bind_input()

        self.taskMgr.add(self._game_loop, "main_game_loop")
        self.accept("escape", sys.exit)

        logger.info(
            "Game started with GameCore architecture (dev_mode=%s). "
            "Plugins loaded: %s. 1/2/3 = spawn enemy/trap/chest, "
            "space/mouse1 = force attack, Esc = quit.",
            dev_mode,
            list(self.game_core.plugins.keys()),
        )

    def _fallback_init(self, dev_mode: bool = False):
        """Резервная инициализация без GameCore (для отладки)"""
        logger.warning("Using fallback initialization without GameCore")

        from src.scenes.main_game_scene import EnhancedGameScene

        self.scene_manager = None
        self.scene = EnhancedGameScene(self, dev_mode=dev_mode)
        self.scene.enter()

        self._keys = {
            "1": False, "2": False, "3": False,
            "e": False, "space": False, "mouse1": False,
        }
        self._bind_input()

        logger.info("Fallback initialization complete")

    def _bind_input(self):
        for key in self._keys:
            self.accept(key, self._set_key, [key, True])
            self.accept(f"{key}-up", self._set_key, [key, False])

    def _set_key(self, key, pressed):
        self._keys[key] = pressed

    def _find_entity_by_id(self, entity_id):
        """Ищет сущность по entity_id среди игрока/врагов сцены."""
        # Сначала пытаемся найти через активную сцену менеджера сцен
        if hasattr(self, 'scene_manager') and self.scene_manager:
            active_scene_data = self.scene_manager.get_scene(self.scene_manager.active_scene)
            if active_scene_data and active_scene_data.instance:
                scene_instance = active_scene_data.instance
                if hasattr(scene_instance, 'player') and scene_instance.player:
                    if scene_instance.player.entity_id == entity_id:
                        return scene_instance.player
                if hasattr(scene_instance, 'enemies'):
                    for enemy in scene_instance.enemies:
                        if enemy.entity_id == entity_id:
                            return enemy

        # Fallback: ищем в атрибуте scene (для fallback режима)
        scene = getattr(self, "scene", None)
        if not scene:
            return None
        if scene.player is not None and scene.player.entity_id == entity_id:
            return scene.player
        for enemy in scene.enemies:
            if enemy.entity_id == entity_id:
                return enemy
        return None

    def _game_loop(self, task):
        dt = globalClock.getDt()  # noqa: F821 (injected by ShowBase)
        
        # Обновляем ядро игры (оно обновит все системы и плагины)
        if hasattr(self, 'game_core') and self.game_core:
            self.game_core.update(dt)
        else:
            # Fallback режим
            scene = getattr(self, "scene", None)
            if scene:
                scene.handle_input(self._keys)
                scene.update(dt)

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
