"""
Toughness Plugin - analyzes toughness mechanics.
Tracks breaks, recovery patterns, and scaling.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

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


class ToughnessPlugin(DevProbePlugin):
    """Analyzes toughness system performance."""
    
    def __init__(self):
        self.break_events: List[BreakEvent] = []
        self.total_toughness_damage = 0.0
        self.entities_tracked: Dict[str, Dict[str, Any]] = {}
        self.anomalies: List[Dict[str, Any]] = []
    
    @property
    def name(self) -> str:
        return "ToughnessPlugin"
    
    def on_snapshot(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze toughness state from snapshot."""
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
                }
            
            current_state = toughness.get("state", "NORMAL")
            current_tough = toughness.get("current", 0)
            max_tough = toughness.get("max", 0)
            
            # Detect break
            if current_state == "BROKEN":
                entity_data = self.entities_tracked[entity_id]
                
                # Check if this is a new break (not already counted this frame)
                if entity_data.get("last_break_frame") != snapshot.get("frame"):
                    entity_data["break_count"] += 1
                    entity_data["last_break_frame"] = snapshot.get("frame")
                    
                    # Calculate scaling
                    prev_max = entity_data.get("max_toughness_observed", max_tough)
                    scaling = max_tough - prev_max
                    
                    if scaling > 0:
                        self.break_events.append(BreakEvent(
                            entity_id=entity_id,
                            timestamp=snapshot.get("timestamp", 0),
                            frame=snapshot.get("frame", 0),
                            max_toughness_before=prev_max,
                            max_toughness_after=max_tough,
                            scaling_applied=scaling,
                        ))
                    
                    entity_data["max_toughness_observed"] = max_tough
            
            # Update max observed
            if max_tough > self.entities_tracked[entity_id]["max_toughness_observed"]:
                self.entities_tracked[entity_id]["max_toughness_observed"] = max_tough
        
        return {
            "total_entities_with_toughness": len([e for e in entities if e.get("toughness")]),
            "broken_count": sum(1 for e in entities if e.get("toughness", {}).get("state") == "BROKEN"),
            "total_breaks_so_far": len(self.break_events),
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
    
    def on_finish(self) -> PluginReport:
        """Generate final toughness analysis report."""
        total_breaks = len(self.break_events)
        total_scaling = sum(e.scaling_applied for e in self.break_events)
        avg_scaling = total_scaling / total_breaks if total_breaks > 0 else 0
        
        # Detect anomalies
        anomalies = []
        for entity_id, data in self.entities_tracked.items():
            if data["break_count"] > 10:
                anomalies.append({
                    "type": "excessive_breaks",
                    "entity_id": entity_id,
                    "break_count": data["break_count"],
                    "severity": "medium",
                })
        
        recommendations = []
        if total_breaks == 0:
            recommendations.append("No toughness breaks detected. Consider reducing enemy toughness or increasing player toughness damage.")
        if avg_scaling > 500:
            recommendations.append(f"Average toughness scaling ({avg_scaling:.1f}) seems high. May need to cap scaling.")
        
        return PluginReport(
            plugin_name=self.name,
            summary={
                "total_breaks": total_breaks,
                "total_toughness_damage": self.total_toughness_damage,
                "entities_analyzed": len(self.entities_tracked),
                "total_scaling_applied": total_scaling,
                "average_scaling_per_break": avg_scaling,
                "break_events": [
                    {
                        "entity_id": e.entity_id,
                        "frame": e.frame,
                        "scaling": e.scaling_applied,
                    }
                    for e in self.break_events[-10:]  # Last 10 breaks
                ],
            },
            anomalies=anomalies,
            recommendations=recommendations,
        )
