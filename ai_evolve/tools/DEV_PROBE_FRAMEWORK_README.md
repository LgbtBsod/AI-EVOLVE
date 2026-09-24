# Dev Probe Framework - Plugin-Based Testing for AI-EVOLVE

## Overview

The **Dev Probe Framework** is a plugin-based testing framework that transforms the original `dev_probe.py` tool into a modular, extensible system for automated game testing and analysis.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DevProbeFramework                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Plugin    │  │    Event     │  │   State          │   │
│  │  Lifecycle  │  │  Detection   │  │  Collection      │   │
│  │  Manager    │  │  Engine      │  │  System          │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ StatsCollector│  │  Screenshot   │  │   Anomaly     │
│    Plugin     │  │   Manager     │  │   Detector    │
│               │  │    Plugin     │  │    Plugin     │
└───────────────┘  └───────────────┘  └───────────────┘
```

## Core Components

### DevProbeFramework
Main orchestrator that manages:
- Plugin registration and lifecycle
- Event detection and routing
- State sampling and aggregation
- Summary generation

### DevProbePlugin (Abstract Base Class)
Base class for all plugins with hooks:
- `on_init(framework)` - Called when plugin is registered
- `on_pre_run(game, config)` - Before probing starts
- `on_sample(game, entities, elapsed)` - Every sample interval
- `on_event(event)` - When an event is detected
- `on_screenshot(path, reason, frame)` - When screenshot taken
- `on_post_run(summary)` - After probe completes
- `on_shutdown()` - When framework shuts down

### Built-in Plugins

#### StatsCollectorPlugin
Collects combat statistics:
- Total damage taken
- Deaths count
- Kills count

#### ScreenshotManagerPlugin
Captures screenshots on trigger events:
- Entity death
- Low HP threshold
- Custom event types

#### AnomalyDetectorPlugin
Detects problematic behavior:
- HP freeze (no change for 5+ samples)
- Instant death (>80% HP drop in one sample)
- Custom anomaly patterns

## Usage

### Basic Example

```python
from ai_evolve.tools.dev_probe_framework import (
    DevProbeFramework,
    StatsCollectorPlugin,
    AnomalyDetectorPlugin,
)

# Create framework
framework = DevProbeFramework(output_dir="./probe_output")

# Register plugins
framework.register_plugin(StatsCollectorPlugin())
framework.register_plugin(AnomalyDetectorPlugin())

# Set adapters for your game
def get_entities(game):
    return [
        (game.scene.player, True),
        *[(enemy, False) for enemy in game.scene.enemies],
    ]

def get_combat_system(game):
    return game.combat_system

framework.set_entity_adapter(get_entities)
framework.set_combat_adapter(get_combat_system)

# Run probe
framework.run(game_instance, duration=30.0, sample_interval=1.0)

# Get results
summary = framework.get_summary()
print(f"Events: {summary['total_events']}")
print(f"Frames: {summary['total_frames']}")
```

### Creating Custom Plugins

```python
from ai_evolve.tools.dev_probe_framework import DevProbePlugin, ProbeEvent, EntityState
from typing import Dict, Any, List, Optional

class ToughnessMonitorPlugin(DevProbePlugin):
    """Monitor toughness break events."""
    
    @property
    def name(self) -> str:
        return "toughness_monitor"
    
    def __init__(self):
        self.break_events = []
        self.toughness_history: Dict[str, List[float]] = {}
    
    def on_event(self, event: ProbeEvent):
        if event.event_type == "toughness_broken":
            self.break_events.append({
                "entity_id": event.entity_id,
                "timestamp": event.timestamp,
                "break_count": event.data.get("break_count", 0),
            })
    
    def on_sample(self, game, entities: List[EntityState], elapsed: float) -> Optional[Dict[str, Any]]:
        # Track toughness over time
        for entity in entities:
            if hasattr(entity, 'current_toughness'):
                if entity.entity_id not in self.toughness_history:
                    self.toughness_history[entity.entity_id] = []
                self.toughness_history[entity.entity_id].append(entity.current_toughness)
        
        return {"tracked_entities": len(self.toughness_history)}
    
    def on_post_run(self, summary: Dict[str, Any]):
        summary["toughness_breaks"] = self.break_events
        summary["total_breaks"] = len(self.break_events)
```

### Custom Event Detectors

```python
def detect_combo_events(prev_entities, curr_entities):
    """Detect elemental combo reactions."""
    events = []
    
    for curr in curr_entities:
        prev = next((e for e in prev_entities if e.entity_id == curr.entity_id), None)
        if not prev:
            continue
        
        # Detect new status effects
        curr_effects = getattr(curr, 'active_effects', [])
        prev_effects = getattr(prev, 'active_effects', [])
        
        if len(curr_effects) > len(prev_effects):
            new_effects = set(curr_effects) - set(prev_effects)
            if 'fire' in new_effects and 'ice' in prev_effects:
                events.append(ProbeEvent(
                    event_type="combo_melt",
                    timestamp=0.0,  # Will be set by framework
                    entity_id=curr.entity_id,
                    kind="combo"
                ))
    
    return events

framework.register_event_detector("combo_reaction", detect_combo_events)
```

## Integration with Existing dev_probe.py

The framework is designed to work alongside the original `tools/dev_probe.py`:

- Use `dev_probe.py` for visual/rendering tests with screenshots
- Use the framework for logic-only automated testing
- Both can share the same entity/combat adapters

## Running Tests

```bash
# Run framework tests
PYTHONPATH=/workspace:$PYTHONPATH python -m pytest ai_evolve/tests/tools/test_dev_probe_framework.py -v

# Run all tests
PYTHONPATH=/workspace:$PYTHONPATH python -m pytest ai_evolve/tests/ -v
```

## Benefits

1. **Modularity**: Add/remove features via plugins without touching core code
2. **Testability**: Each plugin can be tested independently
3. **Extensibility**: Easy to add custom detectors and analyzers
4. **Reusability**: Plugins can be shared across projects
5. **Agent-Friendly**: Structured output optimized for AI analysis

## Future Enhancements

- [ ] Performance profiler plugin
- [ ] AI behavior validator plugin
- [ ] Balance analyzer (damage curves, time-to-kill)
- [ ] Automated bug report generator
- [ ] Comparison mode (before/after fixes)
- [ ] Export to common formats (JSON, CSV, JUnit XML)
