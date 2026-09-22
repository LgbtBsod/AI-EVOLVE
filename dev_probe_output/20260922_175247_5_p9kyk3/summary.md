# Dev Probe Summary — 2026-09-22 17:52:56

Status: OK

Config: duration=5.0s dev_map=True seed=None actions=[]

## Timeline
[   1.0s] SCREENSHOT frame_001.jpg — run start
[   5.6s] SCREENSHOT frame_002.jpg — run end

## Combat totals
attacks: 0 (0 hit, 0 dodged, 0 critical)
damage dealt by player: 0.0
damage taken by player: 0.0
enemies killed: 0

## Player HP
start: 120/120  min: 120.0 (at t=1.0s)  end: 120.0/120

## Issues detected
- 5 WARNING/ERROR log line(s) captured (see below).

## Warnings / errors
17:52:47 WARNING src.core.architecture: Недопустимый переход состояния: UNINITIALIZED -> READY
17:52:47 ERROR src.database.db_core: Ошибка инициализации DatabaseCore: name 'new_state' is not defined
Traceback (most recent call last):
  File "/workspace/src/database/db_core.py", line 109, in initialize
    self.system_state = LifecycleState.READY
    ^^^^^^^^^^^^^^^^^
  File "/workspace/src/core/architecture.py", line 224, in system_state
    logger.debug(f"Форсированный переход состояния (legacy): {old_state.name} -> {new_state.name}")
                                                                                  ^^^^^^^^^
NameError: name 'new_state' is not defined. Did you mean: 'old_state'?
17:52:47 ERROR src.core.game_core: Не удалось инициализировать DatabaseCore
17:52:47 ERROR main: Failed to initialize GameCore, falling back to legacy mode
17:52:47 WARNING main: Using fallback initialization without GameCore

## Screenshots (each has a matching frame_NNN.json with per-entity screen_xy pixels)
- frame_001.jpg — run start
- frame_002.jpg — run end

Contact sheet (open this first for a whole-run visual check): contact_sheet.jpg
Timelapse GIF (human scrubbing convenience, not a whole-run overview image): timelapse.gif

Raw per-tick state: state.jsonl (5 samples)
Full game log: game.log
Panda3D's own engine output: panda3d.log
Machine-readable numbers (for tools/dev_probe_diff.py or your own scripting): summary.json