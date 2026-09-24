"""
Effects Plugin - analyzes buff/debuff system.
Tracks effect applications, synergies, and negative effect counts.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .base import DevProbePlugin, PluginReport


@dataclass
class EffectApplication:
    """Represents an effect application event."""
    entity_id: str
    effect_id: str
    tags: List[str]
    timestamp: float
    frame: int
    duration: float


class EffectsPlugin(DevProbePlugin):
    """Analyzes effects system performance."""
    
    def __init__(self):
        self.effect_applications: List[EffectApplication] = []
        self.negative_effect_counts: Dict[str, int] = {}
        self.cc_durations: Dict[str, float] = {}
        self.entities_with_effects: Dict[str, Dict[str, Any]] = {}
        self.anomalies: List[Dict[str, Any]] = []
    
    @property
    def name(self) -> str:
        return "EffectsPlugin"
    
    def on_snapshot(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze effects state from snapshot."""
        state = snapshot.get("state", {})
        entities = state.get("entities", [])
        
        total_effects = 0
        total_negative = 0
        total_cc_duration = 0.0
        
        for entity in entities:
            entity_id = entity.get("id", "unknown")
            effects = entity.get("effects", [])
            
            if not effects:
                continue
            
            # Track entity
            if entity_id not in self.entities_with_effects:
                self.entities_with_effects[entity_id] = {
                    "first_seen_frame": snapshot.get("frame", 0),
                    "max_effects_simultaneous": 0,
                    "total_negative_received": 0,
                }
            
            entity_negative_count = 0
            entity_cc_duration = 0.0
            
            for effect in effects:
                total_effects += 1
                tags = effect.get("tags", [])
                
                # Count negative effects
                if "negative" in tags or "EffectTag.NEGATIVE" in tags:
                    total_negative += 1
                    entity_negative_count += 1
                
                # Sum CC durations
                remaining = effect.get("remaining", 0)
                cc_tags = ["stun", "knockdown", "slow", "root", "silence", "daze", "fear", "charm"]
                if any(tag in cc_tags or f"EffectTag.{tag.upper()}" in tags for tag in cc_tags):
                    if remaining != float('inf'):
                        entity_cc_duration += remaining
                
                # Track effect application (first time seen)
                effect_key = f"{entity_id}:{effect.get('id')}"
                if effect_key not in [f"{a.entity_id}:{a.effect_id}" for a in self.effect_applications]:
                    self.effect_applications.append(EffectApplication(
                        entity_id=entity_id,
                        effect_id=effect.get("id", "unknown"),
                        tags=tags,
                        timestamp=snapshot.get("timestamp", 0),
                        frame=snapshot.get("frame", 0),
                        duration=effect.get("duration", 0),
                    ))
            
            # Update entity stats
            entity_data = self.entities_with_effects[entity_id]
            effect_count = len(effects)
            if effect_count > entity_data["max_effects_simultaneous"]:
                entity_data["max_effects_simultaneous"] = effect_count
            
            entity_data["total_negative_received"] += entity_negative_count
            
            # Track for anomaly detection
            if entity_negative_count > 0:
                self.negative_effect_counts[entity_id] = self.negative_effect_counts.get(entity_id, 0) + entity_negative_count
            
            if entity_cc_duration > 0:
                self.cc_durations[entity_id] = self.cc_durations.get(entity_id, 0.0) + entity_cc_duration
        
        return {
            "total_active_effects": total_effects,
            "total_negative_effects": total_negative,
            "entities_with_effects": len([e for e in entities if e.get("effects")]),
            "total_cc_duration": total_cc_duration,
        }
    
    def on_event(self, event: Any) -> None:
        """Track effect-related events."""
        from ..core.event_tracker import EventType
        
        if hasattr(event, 'event_type'):
            if event.event_type == EventType.EFFECT_APPLIED:
                # Event-based tracking (backup to snapshot analysis)
                pass
            elif event.event_type == EventType.EFFECT_EXPIRED:
                # Track expiration patterns
                pass
    
    def on_finish(self) -> PluginReport:
        """Generate final effects analysis report."""
        total_apps = len(self.effect_applications)
        avg_negative_per_entity = sum(self.negative_effect_counts.values()) / len(self.negative_effect_counts) if self.negative_effect_counts else 0
        avg_cc_duration = sum(self.cc_durations.values()) / len(self.cc_durations) if self.cc_durations else 0
        
        # Detect anomalies
        anomalies = []
        for entity_id, data in self.entities_with_effects.items():
            if data["max_effects_simultaneous"] > 20:
                anomalies.append({
                    "type": "excessive_effects",
                    "entity_id": entity_id,
                    "effect_count": data["max_effects_simultaneous"],
                    "severity": "high",
                })
            
            neg_count = self.negative_effect_counts.get(entity_id, 0)
            if neg_count > 50:
                anomalies.append({
                    "type": "excessive_negative_effects",
                    "entity_id": entity_id,
                    "negative_count": neg_count,
                    "severity": "medium",
                })
        
        # Check for CC chains
        for entity_id, cc_dur in self.cc_durations.items():
            if cc_dur > 30.0:  # More than 30 seconds of CC
                anomalies.append({
                    "type": "cc_chain_detected",
                    "entity_id": entity_id,
                    "total_cc_duration": cc_dur,
                    "severity": "critical",
                })
        
        recommendations = []
        if total_apps == 0:
            recommendations.append("No effects detected. Check if skills/items are applying effects correctly.")
        if avg_negative_per_entity < 1:
            recommendations.append("Very few negative effects applied. Consider adding more debuff mechanics.")
        if avg_cc_duration > 10.0:
            recommendations.append(f"Average CC duration ({avg_cc_duration:.1f}s) is high. May feel unfair to players.")
        
        # Categorize effects by tags
        effects_by_tag: Dict[str, int] = {}
        for app in self.effect_applications:
            for tag in app.tags:
                effects_by_tag[tag] = effects_by_tag.get(tag, 0) + 1
        
        return PluginReport(
            plugin_name=self.name,
            summary={
                "total_effect_applications": total_apps,
                "unique_entities_affected": len(self.entities_with_effects),
                "average_negative_per_entity": avg_negative_per_entity,
                "average_cc_duration": avg_cc_duration,
                "effects_by_tag": dict(sorted(effects_by_tag.items(), key=lambda x: x[1], reverse=True)[:10]),
                "recent_applications": [
                    {
                        "entity_id": a.entity_id,
                        "effect_id": a.effect_id,
                        "tags": a.tags,
                        "frame": a.frame,
                    }
                    for a in self.effect_applications[-10:]
                ],
            },
            anomalies=anomalies,
            recommendations=recommendations,
        )
