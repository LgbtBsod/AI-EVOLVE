#!/usr/bin/env python3
"""Dev-инструмент для наблюдения за игрой без ручного запуска и клика.

До этого единственным способом понять "как оно там на самом деле" были
логи и разовый скриншот, снятый ad hoc отдельным скриптом. Этот прогоняет
игру заданное время, каждые --interval секунд сохраняет скриншот и
JSON-строку состояния (HP/позиция игрока, список врагов с HP/позицией,
уровень) в один прогон — так по изменению можно "посмотреть" сжатую
партию постфактум, без открытого окна и без ручного тестирования.

Опционально можно проиграть простую последовательность действий
(--action-at SEC:KEY, повторяемо), чтобы детерминированно проверить
конкретный сценарий (например, заспавнить врага рядом с героем сразу
после старта), а не ждать, пока ИИ сам до него дойдёт.

Использование:
    .venv/Scripts/python.exe tools/dev_probe.py --duration 30 --interval 3
    .venv/Scripts/python.exe tools/dev_probe.py --action-at 1:1 --action-at 1:2

Результат в dev_probe_output/<timestamp>/: frame_XXXX.jpg + state.jsonl
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from panda3d.core import Filename  # noqa: E402

import main as game_main  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Headless-ish playtest probe: periodic screenshots + state log")
    parser.add_argument("--duration", type=float, default=30.0, help="total seconds to run")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between snapshots")
    parser.add_argument("--full", action="store_true", help="use the full-size map instead of the dev map")
    parser.add_argument("--out", type=str, default=None,
                         help="output directory (default: dev_probe_output/<timestamp>/)")
    parser.add_argument(
        "--action-at", action="append", default=[], metavar="SEC:KEY",
        help="simulate pressing KEY at time SEC (e.g. 1:1 to spawn near hero at t=1s). Repeatable.",
    )
    return parser.parse_args()


def _entity_state(entity, is_player=False):
    if entity is None:
        return None
    state = {
        "hp": round(entity.health, 1),
        "max_hp": entity.max_health,
        "pos": [round(entity.x, 1), round(entity.y, 1)],
    }
    if is_player:
        state["level"] = entity.level
        state["xp"] = entity.experience
    else:
        state["type"] = entity.enemy_type
    return state


def main():
    args = parse_args()

    out_dir = Path(args.out) if args.out else ROOT / "dev_probe_output" / time.strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    scheduled_actions = sorted(
        (float(sec_str), key) for sec_str, key in (spec.split(":", 1) for spec in args.action_at)
    )
    fired_actions = set()

    game = game_main.Game(dev_mode=not args.full)
    state_log = (out_dir / "state.jsonl").open("w", encoding="utf-8")
    start_time = time.perf_counter()
    frame_count = 0

    def _release_key(key, task):
        game._set_key(key, False)
        return task.done

    def snapshot(task):
        nonlocal frame_count
        elapsed = time.perf_counter() - start_time

        for idx, (sec, key) in enumerate(scheduled_actions):
            if idx not in fired_actions and elapsed >= sec:
                fired_actions.add(idx)
                game._set_key(key, True)
                game.taskMgr.doMethodLater(0.15, _release_key, f"release_{key}_{idx}", extraArgs=[key], appendTask=True)

        frame_count += 1
        shot_path = out_dir / f"frame_{frame_count:04d}.jpg"
        game.screenshot(namePrefix=Filename.from_os_specific(str(shot_path)), defaultFilename=False)

        scene = game.scene
        state = {
            "t": round(elapsed, 2),
            "frame": frame_count,
            "player": _entity_state(scene.player, is_player=True),
            "enemies": [_entity_state(e) for e in scene.enemies],
            "current_level": scene.current_level,
        }
        state_log.write(json.dumps(state, ensure_ascii=False) + "\n")
        state_log.flush()

        hp = state["player"]["hp"] if state["player"] else "-"
        print(f"[{elapsed:5.1f}s] frame {frame_count} player_hp={hp} enemies={len(state['enemies'])}")

        if elapsed >= args.duration:
            state_log.close()
            print(f"Done. Output in {out_dir}")
            sys.exit(0)
        return task.again

    game.taskMgr.doMethodLater(args.interval, snapshot, "dev_probe_snapshot")
    game.run()


if __name__ == "__main__":
    main()
