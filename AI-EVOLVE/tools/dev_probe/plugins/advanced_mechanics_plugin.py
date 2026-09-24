"""
Advanced Mechanics Plugin - analyzes advanced game mechanics.
Tracks combo systems, dodge/parry mechanics, and resource management.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .base import DevProbePlugin, PluginReport


@dataclass
class ComboEvent:
    """Represents a combo chain event."""
    entity_id: str
    combo_count: int
    max_combo: int
    timestamp: float
    frame: int
    combo_reset: bool = False


@dataclass
class DodgeEvent:
    """Represents a dodge/parry event."""
    entity_id: str
    success: bool
    dodge_type: str  # "dodge", "parry", "block"
    timestamp: float
    frame: int
    stamina_cost: float = 0.0


@dataclass
class ResourceEvent:
    """Represents a resource change event."""
    entity_id: str
    resource_type: str  # "mana", "energy", "rage", "stamina"
    current_value: float
    max_value: float
    change: float
    timestamp: float
    frame: int


class AdvancedMechanicsPlugin(DevProbePlugin):
    """Analyzes advanced gameplay mechanics performance."""
    
    def __init__(self):
        self.combo_events: List[ComboEvent] = []
        self.dodge_events: List[DodgeEvent] = []
        self.resource_events: List[ResourceEvent] = []
        self.entities_tracked: Dict[str, Dict[str, Any]] = {}
        self.current_combos: Dict[str, int] = {}
        self.max_combos: Dict[str, int] = {}
        self.resource_states: Dict[str, Dict[str, float]] = {}
        self.anomalies: List[Dict[str, Any]] = []
    
    @property
    def name(self) -> str:
        return "AdvancedMechanicsPlugin"
    
    def on_snapshot(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze advanced mechanics state from snapshot."""
        state = snapshot.get("state", {})
        entities = state.get("entities", [])
        
        total_combos_active = 0
        total_dodges_available = 0
        resources_low = 0
        
        for entity in entities:
            entity_id = entity.get("id", "unknown")
            
            # Track entity initialization
            if entity_id not in self.entities_tracked:
                self.entities_tracked[entity_id] = {
                    "first_seen_frame": snapshot.get("frame", 0),
                    "total_combos_achieved": 0,
                    "total_dodges": 0,
                    "total_parries": 0,
                }
            
            # Analyze combo system
            combo_data = entity.get("combo")
            if combo_data:
                current_combo = combo_data.get("count", 0)
                max_combo = combo_data.get("max", 0)
                
                if current_combo > 0:
                    total_combos_active += 1
                
                # Track combo changes
                prev_combo = self.current_combos.get(entity_id, 0)
                if current_combo != prev_combo:
                    combo_reset = current_combo < prev_combo
                    
                    if combo_reset and prev_combo > 0:
                        # Record completed combo chain
                        self.combo_events.append(ComboEvent(
                            entity_id=entity_id,
                            combo_count=prev_combo,
                            max_combo=max(max_combo, self.max_combos.get(entity_id, 0)),
                            timestamp=snapshot.get("timestamp", 0),
                            frame=snapshot.get("frame", 0),
                            combo_reset=True,
                        ))
                    
                    if current_combo > prev_combo:
                        # Update max combo
                        if entity_id not in self.max_combos or current_combo > self.max_combos[entity_id]:
                            self.max_combos[entity_id] = current_combo
                            self.entities_tracked[entity_id]["total_combos_achieved"] += 1
                    
                    self.current_combos[entity_id] = current_combo
            
            # Analyze dodge/parry system
            combat_stats = entity.get("combat_stats", {})
            dodges = combat_stats.get("dodges", {})
            if dodges:
                available = dodges.get("available", 0)
                total_dodges_available += available
            
            # Analyze resource system
            resources = entity.get("resources", {})
            for res_type, res_data in resources.items():
                current = res_data.get("current", 0)
                maximum = res_data.get("max", 100)
                
                if entity_id not in self.resource_states:
                    self.resource_states[entity_id] = {}
                
                prev_value = self.resource_states[entity_id].get(res_type, current)
                change = current - prev_value
                
                if change != 0:
                    self.resource_events.append(ResourceEvent(
                        entity_id=entity_id,
                        resource_type=res_type,
                        current_value=current,
                        max_value=maximum,
                        change=change,
                        timestamp=snapshot.get("timestamp", 0),
                        frame=snapshot.get("frame", 0),
                    ))
                
                self.resource_states[entity_id][res_type] = current
                
                # Check for low resources
                if maximum > 0 and current / maximum < 0.2:
                    resources_low += 1
        
        return {
            "active_combos": total_combos_active,
            "available_dodges": total_dodges_available,
            "entities_with_low_resources": resources_low,
            "total_resource_events": len(self.resource_events),
        }
    
    def on_event(self, event: Any) -> None:
        """Track advanced mechanic events."""
        from ..core.event_tracker import EventType
        
        if not hasattr(event, 'event_type'):
            return
        
        event_type = event.event_type
        
        if event_type == EventType.DODGE_PERFORMED:
            success = event.data.get("success", False)
            dodge_type = event.data.get("dodge_type", "dodge")
            stamina_cost = event.data.get("stamina_cost", 0.0)
            
            entity_id = getattr(event, 'source_entity_id', None) or event.source_id or "unknown"
            
            self.dodge_events.append(DodgeEvent(
                entity_id=entity_id,
                success=success,
                dodge_type=dodge_type,
                timestamp=event.timestamp,
                frame=event.frame,
                stamina_cost=stamina_cost,
            ))
            
            if entity_id not in self.entities_tracked:
                self.entities_tracked[entity_id] = {
                    "first_seen_frame": event.frame,
                    "total_combos_achieved": 0,
                    "total_dodges": 0,
                    "total_parries": 0,
                }
            
            if success:
                if dodge_type == "dodge":
                    self.entities_tracked[entity_id]["total_dodges"] += 1
                elif dodge_type == "parry":
                    self.entities_tracked[entity_id]["total_parries"] += 1
        
        elif event_type == EventType.COMBO_STARTED:
            combo_count = event.data.get("combo_count", 1)
            entity_id = getattr(event, 'source_entity_id', None) or event.source_id or "unknown"
            self.current_combos[entity_id] = combo_count
    
    def on_finish(self) -> PluginReport:
        """Generate final advanced mechanics analysis report."""
        total_combos = len(self.combo_events)
        max_combo_achieved = max(self.max_combos.values()) if self.max_combos else 0
        avg_combo = sum(self.max_combos.values()) / len(self.max_combos) if self.max_combos else 0
        
        total_dodges = len(self.dodge_events)
        successful_dodges = sum(1 for d in self.dodge_events if d.success)
        dodge_success_rate = successful_dodges / total_dodges if total_dodges > 0 else 0
        
        # Analyze resource patterns
        resource_depletion_events = sum(1 for r in self.resource_events if r.change < 0 and r.current_value == 0)
        
        # Detect anomalies
        anomalies = []
        
        # Check for impossible combos
        for entity_id, max_combo in self.max_combos.items():
            if max_combo > 100:
                anomalies.append({
                    "type": "impossible_combo",
                    "entity_id": entity_id,
                    "combo_count": max_combo,
                    "severity": "high",
                })
        
        # Check for dodge spam
        for entity_id, data in self.entities_tracked.items():
            if data.get("total_dodges", 0) > 50:
                anomalies.append({
                    "type": "excessive_dodging",
                    "entity_id": entity_id,
                    "dodge_count": data["total_dodges"],
                    "severity": "medium",
                })
        
        # Check for resource starvation
        if resource_depletion_events > 10:
            anomalies.append({
                "type": "frequent_resource_depletion",
                "count": resource_depletion_events,
                "severity": "medium",
            })
        
        recommendations = []
        if total_combos == 0 and max_combo_achieved == 0:
            recommendations.append("No combo systems detected. Consider implementing combo mechanics.")
        if dodge_success_rate > 0.9 and total_dodges > 20:
            recommendations.append(f"Dodge success rate ({dodge_success_rate:.1%}) is too high. May reduce challenge.")
        if dodge_success_rate < 0.3 and total_dodges > 20:
            recommendations.append(f"Dodge success rate ({dodge_success_rate:.1%}) is too low. May feel unfair.")
        if resource_depletion_events > 5:
            recommendations.append("Frequent resource depletion detected. Consider balancing resource regeneration.")
        
        # Resource statistics by type
        resource_stats: Dict[str, Dict[str, Any]] = {}
        for res_event in self.resource_events:
            res_type = res_event.resource_type
            if res_type not in resource_stats:
                resource_stats[res_type] = {
                    "total_changes": 0,
                    "gains": 0,
                    "losses": 0,
                    "avg_change": 0.0,
                }
            
            resource_stats[res_type]["total_changes"] += 1
            if res_event.change > 0:
                resource_stats[res_type]["gains"] += 1
            else:
                resource_stats[res_type]["losses"] += 1
        
        # Calculate averages
        for res_type in resource_stats:
            total = resource_stats[res_type]["total_changes"]
            if total > 0:
                type_events = [r for r in self.resource_events if r.resource_type == res_type]
                avg_change = sum(r.change for r in type_events) / total
                resource_stats[res_type]["avg_change"] = avg_change
        
        return PluginReport(
            plugin_name=self.name,
            summary={
                "total_combo_resets": total_combos,
                "max_combo_achieved": max_combo_achieved,
                "average_max_combo": avg_combo,
                "total_dodge_events": total_dodges,
                "dodge_success_rate": dodge_success_rate,
                "resource_depletion_events": resource_depletion_events,
                "entities_tracked": len(self.entities_tracked),
                "resource_statistics": resource_stats,
                "top_combos": [
                    {"entity_id": eid, "max_combo": combo}
                    for eid, combo in sorted(self.max_combos.items(), key=lambda x: x[1], reverse=True)[:5]
                ],
            },
            anomalies=anomalies,
            recommendations=recommendations,
        )
