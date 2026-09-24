"""
Toughness Plugin - analyzes toughness mechanics.
Tracks breaks, recovery patterns, scaling, and HP-based bonus caps.
Updated to support 5% cumulative HP-based scaling up to 20% cap.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .base import DevProbePlugin, PluginReport


@dataclass
class BreakEvent:
    """Represents a toughness break event."""
    entity_id: str
    timestamp: float
    frame: int
    max_toughness_before: float
    max_toughness_after: float
    scaling_applied: float
    hp_bonus_added: float = 0.0
    cap_reached: bool = False


@dataclass
class ToughnessMetrics:
    """Aggregated metrics for toughness analysis."""
    total_breaks: int = 0
    total_scaling: float = 0.0
    avg_scaling: float = 0.0
    max_hp_bonus_observed: float = 0.0
    cap_violations: int = 0
    entities_at_cap: List[str] = field(default_factory=list)


class ToughnessPlugin(DevProbePlugin):
    """Analyzes toughness system performance with enhanced tracking."""
    
    def __init__(self):
        self.break_events: List[BreakEvent] = []
        self.total_toughness_damage = 0.0
        self.entities_tracked: Dict[str, Dict[str, Any]] = {}
        self.anomalies: List[Dict[str, Any]] = []
        self.metrics = ToughnessMetrics()
        self.hp_bonus_history: Dict[str, List[float]] = {}
    
    @property
    def name(self) -> str:
        return "ToughnessPlugin"
    
    def on_snapshot(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze toughness state from snapshot with enhanced tracking."""
        state = snapshot.get("state", {})
        entities = state.get("entities", [])
        
        for entity in entities:
            entity_id = entity.get("id", "unknown")
            toughness = entity.get("toughness")
            
            if not toughness:
                continue
            
            # Track entity
            if entity_id not in self.entities_tracked:
                self.entities_tracked[entity_id] = {
                    "first_seen_frame": snapshot.get("frame", 0),
                    "break_count": 0,
                    "max_toughness_observed": toughness.get("max", 0),
                    "base_max_toughness": toughness.get("max", 0),
                    "hp_bonus": 0.0,
                    "cap_reached": False,
                }
                self.hp_bonus_history[entity_id] = []
            
            current_state = toughness.get("state", "NORMAL")
            current_tough = toughness.get("current", 0)
            max_tough = toughness.get("max", 0)
            entity_data = self.entities_tracked[entity_id]
            
            # Calculate HP bonus (max - base)
            base_max = entity_data.get("base_max_toughness", max_tough)
            current_hp_bonus = max_tough - base_max
            entity_data["hp_bonus"] = current_hp_bonus
            self.hp_bonus_history[entity_id].append(current_hp_bonus)
            
            # Detect break
            if current_state == "BROKEN":
                # Check if this is a new break (not already counted this frame)
                if entity_data.get("last_break_frame") != snapshot.get("frame"):
                    entity_data["break_count"] += 1
                    entity_data["last_break_frame"] = snapshot.get("frame")
                    self.metrics.total_breaks += 1
                    
                    # Calculate scaling
                    prev_max = entity_data.get("max_toughness_observed", max_tough)
                    scaling = max_tough - prev_max
                    
                    # Check if cap reached (20% of max HP)
                    max_health = entity.get("max_health", 0)
                    cap_value = max_health * 0.2 if max_health > 0 else float('inf')
                    cap_reached = current_hp_bonus >= cap_value * 0.99  # 1% tolerance
                    
                    if scaling > 0 or cap_reached:
                        self.break_events.append(BreakEvent(
                            entity_id=entity_id,
                            timestamp=snapshot.get("timestamp", 0),
                            frame=snapshot.get("frame", 0),
                            max_toughness_before=prev_max,
                            max_toughness_after=max_tough,
                            scaling_applied=scaling,
                            hp_bonus_added=current_hp_bonus,
                            cap_reached=cap_reached,
                        ))
                        
                        if cap_reached and entity_id not in self.metrics.entities_at_cap:
                            self.metrics.entities_at_cap.append(entity_id)
                    
                    entity_data["max_toughness_observed"] = max_tough
                    entity_data["cap_reached"] = cap_reached
            
            # Update max observed
            if max_tough > entity_data["max_toughness_observed"]:
                entity_data["max_toughness_observed"] = max_tough
            
            # Track max HP bonus
            if current_hp_bonus > self.metrics.max_hp_bonus_observed:
                self.metrics.max_hp_bonus_observed = current_hp_bonus
        
        broken_count = sum(1 for e in entities if e.get("toughness", {}).get("state") == "BROKEN")
        
        return {
            "total_entities_with_toughness": len([e for e in entities if e.get("toughness")]),
            "broken_count": broken_count,
            "total_breaks_so_far": self.metrics.total_breaks,
            "entities_at_cap": len(self.metrics.entities_at_cap),
        }
    
    def on_event(self, event: Any) -> None:
        """Track toughness-related events."""
        from ..core.event_tracker import EventType
        
        if hasattr(event, 'event_type'):
            if event.event_type == EventType.TOUGHNESS_DAMAGE:
                self.total_toughness_damage += event.data.get("toughness_damage", 0)
            elif event.event_type == EventType.TOUGHNESS_BREAK:
                # Event-based break tracking (backup to snapshot analysis)
                pass
    
    def _detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in toughness behavior."""
        anomalies = []
        
        for entity_id, data in self.entities_tracked.items():
            # Excessive breaks
            if data["break_count"] > 10:
                anomalies.append({
                    "type": "excessive_breaks",
                    "entity_id": entity_id,
                    "break_count": data["break_count"],
                    "severity": "medium",
                })
            
            # HP bonus decreased (should only increase)
            hp_history = self.hp_bonus_history.get(entity_id, [])
            if len(hp_history) > 1:
                for i in range(1, len(hp_history)):
                    if hp_history[i] < hp_history[i-1] * 0.99:  # 1% tolerance
                        anomalies.append({
                            "type": "hp_bonus_decreased",
                            "entity_id": entity_id,
                            "previous_bonus": hp_history[i-1],
                            "current_bonus": hp_history[i],
                            "severity": "high",
                        })
                        break
        
        return anomalies
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []
        
        if self.metrics.total_breaks == 0:
            recommendations.append(
                "No toughness breaks detected. Consider reducing enemy toughness "
                "or increasing player toughness damage."
            )
        
        if self.metrics.avg_scaling > 500:
            recommendations.append(
                f"Average toughness scaling ({self.metrics.avg_scaling:.1f}) seems high. "
                "May need to cap scaling."
            )
        
        if len(self.metrics.entities_at_cap) > 0:
            recommendations.append(
                f"{len(self.metrics.entities_at_cap)} entities reached toughness cap (20% HP). "
                "This is expected behavior for long fights."
            )
        
        # Check for cap violations
        if self.metrics.cap_violations > 0:
            recommendations.append(
                f"WARNING: {self.metrics.cap_violations} potential cap violations detected. "
                "Toughness may exceed 20% HP limit."
            )
        
        return recommendations
    
    def on_finish(self) -> PluginReport:
        """Generate final toughness analysis report."""
        # Calculate average scaling
        if len(self.break_events) > 0:
            self.metrics.total_scaling = sum(e.scaling_applied for e in self.break_events)
            self.metrics.avg_scaling = self.metrics.total_scaling / len(self.break_events)
        
        # Detect anomalies
        anomalies = self._detect_anomalies()
        
        # Generate recommendations
        recommendations = self._generate_recommendations()
        
        return PluginReport(
            plugin_name=self.name,
            summary={
                "total_breaks": self.metrics.total_breaks,
                "total_toughness_damage": self.total_toughness_damage,
                "entities_analyzed": len(self.entities_tracked),
                "total_scaling_applied": self.metrics.total_scaling,
                "average_scaling_per_break": self.metrics.avg_scaling,
                "max_hp_bonus_observed": self.metrics.max_hp_bonus_observed,
                "entities_at_cap": len(self.metrics.entities_at_cap),
                "cap_violations": self.metrics.cap_violations,
                "break_events": [
                    {
                        "entity_id": e.entity_id,
                        "frame": e.frame,
                        "scaling": e.scaling_applied,
                        "hp_bonus": e.hp_bonus_added,
                        "cap_reached": e.cap_reached,
                    }
                    for e in self.break_events[-10:]  # Last 10 breaks
                ],
            },
            anomalies=anomalies,
            recommendations=recommendations,
        )
