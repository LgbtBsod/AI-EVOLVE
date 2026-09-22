# Dev Probe: Complete Documentation

## Overview
**Dev Probe** is a lightweight, multi-threaded instrumentation framework designed to reduce AI agent token costs, increase execution speed, and provide real-time game analytics without interfering with the main game loop.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Dev Probe Core                      │
│  (Async Multi-Threaded Supervisor)                   │
├──────────────────────────────────────────────────────┤
│  Plugin Manager                                      │
│  ├── Memory Profiler                                 │
│  ├── Performance Monitor                             │
│  ├── Auto Balance                                    │
│  ├── ML Vision                                       │
│  ├── Agent Command (AI Control)                      │
│  ├── Network Remote (HTTP API)                       │
│  ├── GM Control (Dungeon Master)                     │
│  └── Hot Reload (Live Updates)                       │
└──────────────────────────────────────────────────────┘
```

---

## Active Plugins (8 Total)

### 1. MemoryProfilerPlugin
- **File:** `tools/plugins/memory_profiler_plugin.py`
- **Purpose:** Tracks memory leaks, heap growth, and object allocation.
- **Features:**
  - Baseline snapshots
  - Delta analysis
  - Leak detection (>5% growth threshold)
- **Usage:**
  ```python
  plugin = MemoryProfilerPlugin(probe)
  plugin.take_snapshot("start")
  # ... game logic ...
  report = plugin.analyze()
  ```

### 2. PerformanceMonitorPlugin
- **File:** `tools/plugins/performance_monitor_plugin.py`
- **Purpose:** Monitors FPS, frame time, and stutter events.
- **Features:**
  - Sliding window metrics (deque)
  - Stutter detection (>100ms frame)
  - Real-time FPS tracking
- **Usage:**
  ```python
  plugin = PerformanceMonitorPlugin(probe)
  plugin.record_frame(0.016)  # 60 FPS
  stats = plugin.get_stats()
  ```

### 3. AutoBalancePlugin
- **File:** `tools/plugins/auto_balance_plugin.py`
- **Purpose:** Analyzes win rates, damage taken, and suggests balance tweaks.
- **Features:**
  - Win/Loss tracking
  - Damage distribution analysis
  - Automatic difficulty adjustment suggestions
- **Usage:**
  ```python
  plugin = AutoBalancePlugin(probe)
  plugin.record_combat_result(win=True, damage_taken=50)
  suggestions = plugin.get_balance_report()
  ```

### 4. MLVisionPlugin
- **File:** `tools/plugins/ml_vision_plugin.py`
- **Purpose:** Computer Vision for UI anomaly detection and screen analysis.
- **Features:**
  - Screenshot diffing
  - UI element detection (OpenCV)
  - Anomaly flagging
- **Usage:**
  ```python
  plugin = MLVisionPlugin(probe)
  anomaly = plugin.detect_anomaly(screenshot_array)
  ```

### 5. AgentCommandPlugin
- **File:** `tools/plugins/agent_command_plugin.py`
- **Purpose:** Allows AI agents to send commands to the game (spawn, teleport, etc.).
- **Features:**
  - 17 command types (SPAWN_ENTITY, MODIFY_STATS, etc.)
  - Priority queue
  - Callback support
- **Constraint:** Can control Hero directly (unlike GM plugin).
- **Usage:**
  ```python
  plugin = AgentCommandPlugin(probe)
  cmd_id = plugin.send_command(CommandType.SPAWN_ENTITY, {'type': 'enemy'})
  ```

### 6. NetworkRemotePlugin
- **File:** `tools/plugins/network_remote_plugin.py`
- **Purpose:** Exposes HTTP API for remote control and monitoring.
- **Features:**
  - RESTful endpoints (/status, /command, /batch)
  - Session management
  - Thread-per-request server
- **Usage:**
  ```bash
  curl http://localhost:8765/command -d '{"type": "pause_game"}'
  ```

### 7. GMControlPlugin (NEW)
- **File:** `tools/plugins/gm_control_plugin.py`
- **Purpose:** Enables AI to act as a "Dungeon Master" influencing the WORLD, not the Hero.
- **SRP Constraint:** CANNOT directly control Hero movement or actions.
- **Allowed Actions:**
  - Spawn Enemies
  - Place Traps
  - Spawn Loot/Chests
  - Change Weather
  - Trigger World Events
- **Usage:**
  ```python
  plugin = GMControlPlugin(probe)
  plugin.set_gm_interface(game_master_instance)
  plugin.execute_world_action('SPAWN_ENEMY', {'pos': (10, 20), 'level': 5})
  ```

### 8. HotReloadPlugin (NEW)
- **File:** `tools/plugins/hot_reload_plugin.py`
- **Purpose:** Live code updates without restarting the session.
- **Features:**
  - Safe module whitelist
  - Syntax validation
  - Rollback history
- **Usage:**
  ```python
  plugin = HotReloadPlugin()
  success = plugin.reload_module('src.features.combat_plugin')
  ```

---

## Async & Multi-Threading Model

Dev Probe uses a **7-Thread Architecture**:

| Thread | Purpose | Frequency |
|--------|---------|-----------|
| Main Loop | Game State Updates | 60 Hz |
| HUD/UI | Rendering | 30 Hz |
| Combat | Damage Calculations | 120 Hz (4 workers) |
| ML Training | Model Updates | 10 Hz (8 workers) |
| AI Thinking | Decision Making | 30 Hz (4 workers) |
| I/O Ops | Disk/Network | 10 Hz (2 workers) |
| Analytics | Metrics Aggregation | 1 Hz (4 workers) |

---

## Best Practices Applied

1. **SRP (Single Responsibility Principle):** Each plugin has one clear job.
2. **DRY (Don't Repeat Yourself):** Shared utilities in `tools/utils.py`.
3. **SOLID:** Dependency injection used in GM plugin.
4. **SSOT (Single Source of Truth):** GameMaster is SSOT for world state.
5. **Pythonic:**
   - `dataclasses` for config
   - `collections.deque` for lock-free queues
   - `functools.lru_cache` for caching
   - `concurrent.futures` for thread pools
   - `typing` for type hints

---

## Integration Example

```python
from tools.dev_probe_async import DevProbeAsync
from src.core.game_master import GameMaster
from tools.plugins.gm_control_plugin import GMControlPlugin

# Initialize Probe
probe = DevProbeAsync()

# Initialize Game Master
gm = GameMaster(entity_manager)

# Connect GM Plugin
gm_plugin = GMControlPlugin(probe)
gm_plugin.set_gm_interface(gm)
probe.register_plugin(gm_plugin)

# Run Session
probe.start()
# AI can now spawn enemies via GM plugin
```

---

## Changelog

- **v1.0:** Initial release (Memory, Performance, Balance plugins)
- **v1.1:** Added Async/Multi-threading core
- **v1.2:** Added Agent Command & Network Remote plugins
- **v1.3:** Added GM Control (World-only influence) & Hot Reload
- **v1.4:** Fixed SRP violations, standardized on stdlib (deque, lru_cache)
