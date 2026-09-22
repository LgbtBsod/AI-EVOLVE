# Dev Probe Summary — 2026-09-22 17:52:33

Status: OK

Config: duration=5.0s dev_map=True seed=None actions=[]

## Timeline
[   1.0s] SCREENSHOT frame_001.jpg — run start
[   5.2s] SCREENSHOT frame_002.jpg — run end

## Combat totals
attacks: 0 (0 hit, 0 dodged, 0 critical)
damage dealt by player: 0.0
damage taken by player: 0.0
enemies killed: 0

## Player HP
start: 120/120  min: 120.0 (at t=1.0s)  end: 120.0/120

## Issues detected
- 6 WARNING/ERROR log line(s) captured (see below).

## Warnings / errors
17:52:25 WARNING src.core.architecture: Недопустимый переход состояния: UNINITIALIZED -> READY
17:52:25 WARNING src.core.architecture: Недопустимый переход состояния: UNINITIALIZED -> READY
17:52:25 WARNING src.core.architecture: Недопустимый переход состояния: UNINITIALIZED -> READY
17:52:25 ERROR src.core.game_core: GameCore не готов к запуску
17:52:25 ERROR main: Failed to start GameCore, falling back to legacy mode
17:52:25 WARNING main: Using fallback initialization without GameCore

## Screenshots (each has a matching frame_NNN.json with per-entity screen_xy pixels)
- frame_001.jpg — run start
- frame_002.jpg — run end

Contact sheet (open this first for a whole-run visual check): contact_sheet.jpg
Timelapse GIF (human scrubbing convenience, not a whole-run overview image): timelapse.gif

Raw per-tick state: state.jsonl (5 samples)
Full game log: game.log
Panda3D's own engine output: panda3d.log
Machine-readable numbers (for tools/dev_probe_diff.py or your own scripting): summary.json