"""
Dev Probe Plugin Framework for AI-EVOLVE

This module transforms dev_probe into a plugin-based testing framework.
Plugins can hook into the testing lifecycle to:
- Add custom state collectors
- Define custom event detectors
- Provide specialized analysis
- Generate custom reports

Usage:
    # Create a plugin
    class MyTestPlugin(DevProbePlugin):
        def on_sample(self, game, entities, elapsed):
            # Custom sampling logic
            pass
        
        def on_event(self, event_type, data):
            # Handle detected events
            pass
    
    # Register plugin
    from ai_evolve.tools.dev_probe_framework import DevProbeFramework
    framework = DevProbeFramework()
    framework.register_plugin(MyTestPlugin())
    framework.run(duration=30)
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
import time
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ProbeEvent:
    """Represents a detected event during probing."""
    event_type: str
    timestamp: float
    data: Dict[str, Any] = field(default_factory=dict)
    entity_id: Optional[str] = None
    kind: Optional[str] = None  # For grouping similar events


@dataclass
class EntityState:
    """Snapshot of an entity's state."""
    entity_id: str
    entity_type: str
    is_player: bool
    health: float
    max_health: float
    position: tuple
    is_alive: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProbeFrame:
    """A single frame of probe data."""
    timestamp: float
    entities: List[EntityState]
    events: List[ProbeEvent]
    screenshot_path: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


class DevProbePlugin(ABC):
    """
    Base class for Dev Probe plugins.
    
    Plugins can hook into various stages of the probing process:
    - on_init: Called when framework initializes
    - on_pre_run: Called before the probe starts
    - on_sample: Called every sample interval
    - on_event: Called when an event is detected
    - on_screenshot: Called when a screenshot is taken
    - on_post_run: Called after the probe finishes
    - on_shutdown: Called when framework shuts down
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this plugin."""
        pass
    
    def on_init(self, framework):
        """Called when plugin is registered with framework."""
        pass
    
    def on_pre_run(self, game, config: Dict[str, Any]):
        """Called before probing starts."""
        pass
    
    def on_sample(self, game, entities: List[EntityState], elapsed: float) -> Optional[Dict[str, Any]]:
        """
        Called every sample interval.
        
        Args:
            game: The game instance
            entities: Current state of all entities
            elapsed: Time since probe started
            
        Returns:
            Optional dict of custom metrics to add to frame
        """
        pass
    
    def on_event(self, event: ProbeEvent):
        """Called when an event is detected."""
        pass
    
    def on_screenshot(self, path: str, reason: str, frame_number: int):
        """Called when a screenshot is taken."""
        pass
    
    def on_post_run(self, summary: Dict[str, Any]):
        """Called after probing completes with final summary."""
        pass
    
    def on_shutdown(self):
        """Called when framework is shutting down."""
        pass


class DevProbeFramework:
    """
    Main framework for running instrumented game probes with plugins.
    
    This wraps the core dev_probe functionality and adds:
    - Plugin lifecycle management
    - Event detection and routing
    - State collection and aggregation
    - Extensible analysis pipeline
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir) if output_dir else None
        self.plugins: Dict[str, DevProbePlugin] = {}
        self._plugin_order: List[str] = []
        self._events: List[ProbeEvent] = []
        self._frames: List[ProbeFrame] = []
        self._entity_detectors: Dict[str, Callable] = {}
        self._event_detectors: Dict[str, Callable] = {}
        self._game_instance = None
        self._is_running = False
        self._start_time = 0.0
        
        # Default adapters (project-specific)
        self.get_entities_func = None
        self.get_combat_system_func = None
        
        logger.info("[DevProbeFramework] Initialized")
    
    def register_plugin(self, plugin: DevProbePlugin):
        """Register a plugin with the framework."""
        if plugin.name in self.plugins:
            raise ValueError(f"Plugin '{plugin.name}' already registered")
        
        self.plugins[plugin.name] = plugin
        self._plugin_order.append(plugin.name)
        plugin.on_init(self)
        logger.info(f"[DevProbeFramework] Registered plugin: {plugin.name}")
    
    def unregister_plugin(self, name: str):
        """Unregister a plugin."""
        if name in self.plugins:
            self.plugins[name].on_shutdown()
            del self.plugins[name]
            self._plugin_order.remove(name)
            logger.info(f"[DevProbeFramework] Unregistered plugin: {name}")
    
    def set_entity_adapter(self, func: Callable):
        """
        Set the function to get entities from game.
        
        Function signature: func(game) -> List[(entity, is_player)]
        """
        self.get_entities_func = func
    
    def set_combat_adapter(self, func: Callable):
        """
        Set the function to get combat system from game.
        
        Function signature: func(game) -> object with register_event_handler()
        """
        self.get_combat_system_func = func
    
    def register_event_detector(self, event_type: str, detector: Callable):
        """
        Register a custom event detector.
        
        Args:
            event_type: Type of event this detector finds
            detector: Function(prev_state, curr_state) -> List[ProbeEvent]
        """
        self._event_detectors[event_type] = detector
        logger.debug(f"[DevProbeFramework] Registered event detector: {event_type}")
    
    def _detect_events(self, prev_entities: List[EntityState], 
                       curr_entities: List[EntityState], 
                       elapsed: float) -> List[ProbeEvent]:
        """Run all event detectors and return detected events."""
        events = []
        
        # Build lookup maps
        prev_map = {e.entity_id: e for e in prev_entities}
        curr_map = {e.entity_id: e for e in curr_entities}
        
        # Run built-in detectors
        # Death detection
        for entity_id, prev_entity in prev_map.items():
            if prev_entity.is_alive and not curr_map.get(entity_id, prev_entity).is_alive:
                event = ProbeEvent(
                    event_type="entity_death",
                    timestamp=elapsed,
                    entity_id=entity_id,
                    data={"entity_type": prev_entity.entity_type},
                    kind="death"
                )
                events.append(event)
        
        # Spawn detection
        for entity_id, curr_entity in curr_map.items():
            if entity_id not in prev_map and curr_entity.is_alive:
                event = ProbeEvent(
                    event_type="entity_spawn",
                    timestamp=elapsed,
                    entity_id=entity_id,
                    data={"entity_type": curr_entity.entity_type},
                    kind="spawn"
                )
                events.append(event)
        
        # Low HP detection
        LOW_HP_THRESHOLD = 0.25
        for curr_entity in curr_entities:
            if curr_entity.is_alive and curr_entity.health < curr_entity.max_health * LOW_HP_THRESHOLD:
                prev_entity = prev_map.get(curr_entity.entity_id)
                if not prev_entity or prev_entity.health >= prev_entity.max_health * LOW_HP_THRESHOLD:
                    event = ProbeEvent(
                        event_type="low_hp",
                        timestamp=elapsed,
                        entity_id=curr_entity.entity_id,
                        data={
                            "health": curr_entity.health,
                            "max_health": curr_entity.max_health,
                            "percent": curr_entity.health / curr_entity.max_health
                        },
                        kind="low_hp"
                    )
                    events.append(event)
        
        # Run custom detectors
        for event_type, detector in self._event_detectors.items():
            try:
                detected = detector(prev_entities, curr_entities)
                events.extend(detected)
            except Exception as e:
                logger.error(f"[DevProbeFramework] Event detector {event_type} failed: {e}")
        
        return events
    
    def _notify_plugins_event(self, event: ProbeEvent):
        """Notify all plugins of an event."""
        self._events.append(event)
        for name in self._plugin_order:
            try:
                self.plugins[name].on_event(event)
            except Exception as e:
                logger.error(f"[DevProbeFramework] Plugin {name} on_event failed: {e}")
    
    def _notify_plugins_screenshot(self, path: str, reason: str, frame_number: int):
        """Notify all plugins of a screenshot."""
        for name in self._plugin_order:
            try:
                self.plugins[name].on_screenshot(path, reason, frame_number)
            except Exception as e:
                logger.error(f"[DevProbeFramework] Plugin {name} on_screenshot failed: {e}")
    
    def run(self, game, duration: float, sample_interval: float = 1.0):
        """
        Run the probe framework.
        
        Args:
            game: The game instance to probe
            duration: How long to run in seconds
            sample_interval: Time between samples in seconds
        """
        if self._is_running:
            raise RuntimeError("Framework is already running")
        
        self._is_running = True
        self._start_time = time.perf_counter()
        self._game_instance = game
        self._events.clear()
        self._frames.clear()
        
        # Notify plugins
        config = {
            "duration": duration,
            "sample_interval": sample_interval,
            "output_dir": str(self.output_dir) if self.output_dir else None
        }
        for name in self._plugin_order:
            try:
                self.plugins[name].on_pre_run(game, config)
            except Exception as e:
                logger.error(f"[DevProbeFramework] Plugin {name} on_pre_run failed: {e}")
        
        # Setup combat event handler if available
        combat_system = None
        if self.get_combat_system_func:
            combat_system = self.get_combat_system_func(game)
            if combat_system and hasattr(combat_system, 'register_event_handler'):
                combat_system.register_event_handler(self._handle_combat_event)
        
        prev_entities = []
        frame_number = 0
        
        try:
            while True:
                elapsed = time.perf_counter() - self._start_time
                
                if elapsed >= duration:
                    break
                
                # Sample entities
                current_entities = []
                if self.get_entities_func:
                    raw_entities = self.get_entities_func(game)
                    for entity, is_player in raw_entities:
                        state = EntityState(
                            entity_id=getattr(entity, 'entity_id', f"obj_{id(entity)}"),
                            entity_type="hero" if is_player else getattr(entity, 'enemy_type', entity.__class__.__name__),
                            is_player=is_player,
                            health=getattr(entity, 'health', 0),
                            max_health=getattr(entity, 'max_health', 100),
                            position=(getattr(entity, 'x', 0), getattr(entity, 'y', 0)),
                            is_alive=getattr(entity, 'is_alive', lambda: True)() if callable(getattr(entity, 'is_alive', None)) else getattr(entity, 'is_alive', True),
                        )
                        current_entities.append(state)
                
                # Detect events
                if prev_entities:
                    events = self._detect_events(prev_entities, current_entities, elapsed)
                    for event in events:
                        self._notify_plugins_event(event)
                
                # Collect metrics from plugins
                metrics = {}
                for name in self._plugin_order:
                    try:
                        plugin_metrics = self.plugins[name].on_sample(game, current_entities, elapsed)
                        if plugin_metrics:
                            metrics.update(plugin_metrics)
                    except Exception as e:
                        logger.error(f"[DevProbeFramework] Plugin {name} on_sample failed: {e}")
                
                # Create frame
                frame = ProbeFrame(
                    timestamp=elapsed,
                    entities=current_entities.copy(),
                    events=[e for e in self._events if abs(e.timestamp - elapsed) < sample_interval],
                    metrics=metrics
                )
                self._frames.append(frame)
                frame_number += 1
                
                prev_entities = current_entities
                
                # Wait until next sample
                next_sample_time = frame_number * sample_interval
                sleep_time = next_sample_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        
        finally:
            # Build summary
            summary = {
                "status": "completed",
                "duration": time.perf_counter() - self._start_time,
                "total_frames": len(self._frames),
                "total_events": len(self._events),
                "events_by_type": {},
                "plugins_used": list(self._plugin_order),
            }
            
            # Count events by type
            for event in self._events:
                key = event.event_type
                summary["events_by_type"][key] = summary["events_by_type"].get(key, 0) + 1
            
            # Notify plugins
            for name in self._plugin_order:
                try:
                    self.plugins[name].on_post_run(summary)
                except Exception as e:
                    logger.error(f"[DevProbeFramework] Plugin {name} on_post_run failed: {e}")
            
            self._is_running = False
            logger.info(f"[DevProbeFramework] Probe completed: {summary['total_frames']} frames, {summary['total_events']} events")
    
    def _handle_combat_event(self, event_type: str, data: Dict[str, Any]):
        """Handle combat system events."""
        elapsed = time.perf_counter() - self._start_time
        event = ProbeEvent(
            event_type=f"combat_{event_type}",
            timestamp=elapsed,
            data=data,
            entity_id=data.get('attacker_id') or data.get('target_id'),
            kind=event_type
        )
        self._notify_plugins_event(event)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of the last probe run."""
        return {
            "total_frames": len(self._frames),
            "total_events": len(self._events),
            "events": [
                {
                    "type": e.event_type,
                    "timestamp": e.timestamp,
                    "entity_id": e.entity_id,
                    "kind": e.kind,
                }
                for e in self._events
            ],
            "frames": [
                {
                    "timestamp": f.timestamp,
                    "entity_count": len(f.entities),
                    "event_count": len(f.events),
                    "metrics": f.metrics,
                }
                for f in self._frames
            ]
        }


# Built-in plugins

class StatsCollectorPlugin(DevProbePlugin):
    """Collects basic statistics about entities."""
    
    @property
    def name(self) -> str:
        return "stats_collector"
    
    def __init__(self):
        self.stats = {
            "total_damage_taken": 0,
            "total_healing_received": 0,
            "deaths": 0,
            "kills": 0,
        }
        self._entity_stats: Dict[str, Dict[str, Any]] = {}
    
    def on_event(self, event: ProbeEvent):
        if event.event_type == "entity_death":
            self.stats["deaths"] += 1
        elif event.event_type == "combat_damage_dealt":
            damage = event.data.get("damage", 0)
            self.stats["total_damage_taken"] += damage


class ScreenshotManagerPlugin(DevProbePlugin):
    """Manages screenshot capture based on events."""
    
    @property
    def name(self) -> str:
        return "screenshot_manager"
    
    def __init__(self, output_dir: str, trigger_events: List[str] = None):
        self.output_dir = Path(output_dir)
        self.trigger_events = trigger_events or ["entity_death", "low_hp"]
        self.screenshots_taken = 0
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def on_event(self, event: ProbeEvent):
        if event.event_type in self.trigger_events:
            # In real implementation, this would trigger actual screenshot
            path = self.output_dir / f"screenshot_{self.screenshots_taken:04d}.png"
            self.screenshots_taken += 1
            logger.info(f"[ScreenshotManager] Would capture: {path} (event: {event.event_type})")


class AnomalyDetectorPlugin(DevProbePlugin):
    """Detects anomalous behavior during probing."""
    
    @property
    def name(self) -> str:
        return "anomaly_detector"
    
    def __init__(self):
        self.anomalies = []
        self._hp_history: Dict[str, List[float]] = {}
    
    def on_sample(self, game, entities: List[EntityState], elapsed: float) -> Dict[str, Any]:
        anomalies_found = []
        
        for entity in entities:
            if entity.entity_id not in self._hp_history:
                self._hp_history[entity.entity_id] = []
            
            history = self._hp_history[entity.entity_id]
            history.append(entity.health)
            
            # Keep only last 10 samples
            if len(history) > 10:
                history.pop(0)
            
            # Detect HP freeze (no change for 5+ samples)
            if len(history) >= 5 and entity.is_alive:
                if len(set(history[-5:])) == 1:
                    anomaly = {
                        "type": "hp_freeze",
                        "entity_id": entity.entity_id,
                        "timestamp": elapsed,
                        "hp": entity.health,
                    }
                    anomalies_found.append(anomaly)
                    self.anomalies.append(anomaly)
            
            # Detect instant death (HP drop > 80% in one sample)
            if len(history) >= 2:
                hp_drop = history[-2] - history[-1]
                if hp_drop > history[-2] * 0.8 and history[-2] > 0:
                    anomaly = {
                        "type": "instant_death",
                        "entity_id": entity.entity_id,
                        "timestamp": elapsed,
                        "hp_before": history[-2],
                        "hp_after": history[-1],
                    }
                    anomalies_found.append(anomaly)
                    self.anomalies.append(anomaly)
        
        return {"anomalies_detected": len(anomalies_found)}
    
    def on_post_run(self, summary: Dict[str, Any]):
        summary["anomalies"] = self.anomalies
        summary["anomaly_count"] = len(self.anomalies)
        logger.info(f"[AnomalyDetector] Found {len(self.anomalies)} anomalies")
