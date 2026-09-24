#!/usr/bin/env python3
"""Headless boot test: the real main.Game in an offscreen buffer, no window.

Checks what combat_smoke_test.py cannot (it never builds a ShowBase): the
GameCore -> SceneManager -> plugins boot chain, that the game world actually
loads with a hero and enemies, that combat/effect systems are wired, and that
the director's "1" key spawns an enemy. Needs an OpenGL context for the
offscreen buffer (a GPU driver, or Mesa under xvfb-run on Linux CI).

    python tools/boot_smoke_test.py            # prints one RESULT line, exit 0/1
"""

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BOOT_SECONDS = 3.0


class _ErrorCounter(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


def run_frames(game, seconds):
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        game.taskMgr.step()


def main() -> int:
    errors = _ErrorCounter()
    logging.getLogger().addHandler(errors)

    import main as game_main

    game = game_main.Game(dev_mode=True, headless=True, skip_menu=True, db_url="sqlite:///:memory:")
    failures = []

    if game.combat_system is None:
        failures.append("combat_system is None")
    if game.effect_system is None:
        failures.append("effect_system is None")
    if game.scene_manager.active_scene != "game_world":
        failures.append(f"active scene is {game.scene_manager.active_scene!r}, expected 'game_world'")

    run_frames(game, BOOT_SECONDS)
    scene = game.scene
    if scene is None or scene.player is None:
        failures.append("no game world / hero after boot")
        enemies_before = 0
    else:
        enemies_before = len(scene.enemies)
        if enemies_before == 0:
            failures.append("no enemies spawned in the world")

        # Director action: "1" spawns an enemy next to the hero (edge-triggered). Count what
        # the player created, not who is alive: a slime next to the hero dies to one sword swing.
        created_before = scene.player_spawns
        game._keys["1"] = True
        run_frames(game, 0.3)
        game._keys["1"] = False
        run_frames(game, 0.3)
        if scene.player_spawns <= created_before:
            failures.append(f"key '1' did not spawn an enemy ({enemies_before} -> {len(scene.enemies)})")

    if errors.lines:
        failures.append(f"{len(errors.lines)} ERROR log line(s): {errors.lines[0]}")

    enemies_after = len(scene.enemies) if scene is not None else 0
    status = "FAIL" if failures else "OK"
    print(f"RESULT status={status} scene={game.scene_manager.active_scene} "
          f"enemies={enemies_before}->{enemies_after} errors={len(errors.lines)}")
    for failure in failures:
        print(f"  - {failure}")

    game.destroy()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
