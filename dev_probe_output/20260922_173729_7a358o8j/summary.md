# Dev Probe Summary — 2026-09-22 17:37:49

Status: OK

Config: duration=20.0s dev_map=True seed=42 actions=[]

## Timeline
[   0.5s] ANOMALY: frame_001.jpg looks blank/solid-color (pixel stddev=0.0) - rendering may be broken even though game state looks fine
[   0.5s] SCREENSHOT frame_001.jpg — run start
[  20.0s] ANOMALY: frame_002.jpg looks blank/solid-color (pixel stddev=0.0) - rendering may be broken even though game state looks fine
[  20.0s] SCREENSHOT frame_002.jpg — run end

## Combat totals
attacks: 0 (0 hit, 0 dodged, 0 critical)
damage dealt by player: 0.0
damage taken by player: 0.0
enemies killed: 0

## Issues detected
- 3 WARNING/ERROR log line(s) captured (see below).
- 2 screenshot(s) looked blank/solid-color - rendering may be broken despite game state looking healthy (needs Pillow to detect; see per-frame pixel_stddev in frame_NNN.json).

## Warnings / errors
17:37:29 ERROR src.scenes.scene_manager: Ошибка запуска SceneManager: 'SceneManager' object has no attribute 'system_state'
17:37:29 WARNING src.core.game_core: Не удалось запустить SceneManager
17:37:29 WARNING src.scenes.scene_manager: Сцена с ID game_world не найдена

## Screenshots (each has a matching frame_NNN.json with per-entity screen_xy pixels)
- frame_001.jpg — run start
- frame_002.jpg — run end

Contact sheet (open this first for a whole-run visual check): contact_sheet.jpg
Timelapse GIF (human scrubbing convenience, not a whole-run overview image): timelapse.gif

Raw per-tick state: state.jsonl (40 samples)
Full game log: game.log
Panda3D's own engine output: panda3d.log
Machine-readable numbers (for tools/dev_probe_diff.py or your own scripting): summary.json