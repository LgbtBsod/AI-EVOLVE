"""
Combat Plugin - analyzes combat mechanics.
Tracks damage, crits, kills, and combat flow.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .base import DevProbePlugin, PluginReport


@dataclass
class DamageEvent:
    """Represents a damage event."""
    source_id: str
    target_id: str
    damage: float
    is_critical: bool
    timestamp: float
    frame: int
    damage_type: str = "physical"


@dataclass 
class KillEvent:
    """Represents a kill event."""
    killer_id: str
    victim_id: str
    timestamp: float
    frame: int
    total_damage_dealt: float


class CombatPlugin(DevProbePlugin):
    """Analyzes combat system performance."""
    
    def __init__(self):
        self.damage_events: List[DamageEvent] = []
        self.kill_events: List[KillEvent] = []
        self.total_damage_by_source: Dict[str, float] = {}
        self.crit_count_by_source: Dict[str, int] = {}
        self.entities_damaged: Dict[str, Dict[str, Any]] = {}
        self.anomalies: List[Dict[str, Any]] = []
    
    @property
    def name(self) -> str:
        return "CombatPlugin"
    
    def on_snapshot(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze combat state from snapshot (passive tracking)."""
        # Snapshots are mainly used for state verification
        # Real-time tracking happens in on_event
        state = snapshot.get("state", {})
        entities = state.get("entities", [])
        
        alive_count = sum(1 for e in entities if e.get("is_alive", False))
        dead_count = len(entities) - alive_count
        
        return {
            "entities_alive": alive_count,
            "entities_dead": dead_count,
            "total_damage_tracked": sum(self.total_damage_by_source.values()),
        }
    
    def on_event(self, event: Any) -> None:
        """Track combat events in real-time."""
        from ..core.event_tracker import EventType
        
        if not hasattr(event, 'event_type'):
            return
        
        event_type = event.event_type
        
        if event_type == EventType.DAMAGE_DEALT:
            damage = event.data.get("damage", 0)
            source_id = event.source_entity_id or "unknown"
            target_id = event.target_entity_id or "unknown"
            is_crit = event.data.get("is_critical", False)
            
            self.damage_events.append(DamageEvent(
                source_id=source_id,
                target_id=target_id,
                damage=damage,
                is_critical=is_crit,
                timestamp=event.timestamp,
                frame=event.frame,
                damage_type=event.data.get("damage_type", "physical"),
            ))
            
            # Track by source
            self.total_damage_by_source[source_id] = self.total_damage_by_source.get(source_id, 0.0) + damage
            if is_crit:
                self.crit_count_by_source[source_id] = self.crit_count_by_source.get(source_id, 0) + 1
            
            # Track entity damage taken
            if target_id not in self.entities_damaged:
                self.entities_damaged[target_id] = {
                    "total_damage_taken": 0.0,
                    "hit_count": 0,
                    "crit_count": 0,
                }
            
            self.entities_damaged[target_id]["total_damage_taken"] += damage
            self.entities_damaged[target_id]["hit_count"] += 1
            if is_crit:
                self.entities_damaged[target_id]["crit_count"] += 1
        
        elif event_type == EventType.ENTITY_DIED:
            self.kill_events.append(KillEvent(
                killer_id=event.source_entity_id or "unknown",
                victim_id=event.target_entity_id or "unknown",
                timestamp=event.timestamp,
                frame=event.frame,
                total_damage_dealt=self.total_damage_by_source.get(event.source_entity_id or "unknown", 0),
            ))
    
    def on_finish(self) -> PluginReport:
        """Generate final combat analysis report."""
        total_damage = sum(self.total_damage_by_source.values())
        total_hits = len(self.damage_events)
        total_crits = sum(self.crit_count_by_source.values())
        crit_rate = total_crits / total_hits if total_hits > 0 else 0
        avg_damage = total_damage / total_hits if total_hits > 0 else 0
        
        # Calculate DPS (if we have time data)
        dps = 0.0
        if self.damage_events:
            first_hit_time = self.damage_events[0].timestamp
            last_hit_time = self.damage_events[-1].timestamp
            duration = last_hit_time - first_hit_time
            if duration > 0:
                dps = total_damage / duration
        
        # Detect anomalies
        anomalies = []
        
        # Check for zero damage issues
        zero_damage_count = sum(1 for e in self.damage_events if e.damage == 0)
        if zero_damage_count > total_hits * 0.3 and total_hits > 10:
            anomalies.append({
                "type": "excessive_zero_damage",
                "count": zero_damage_count,
                "percentage": zero_damage_count / total_hits * 100,
                "severity": "high",
            })
        
        # Check for one-shot kills
        for kill in self.kill_events:
            if kill.total_damage_dealt > 10000:  # Threshold for one-shot
                anomalies.append({
                    "type": "potential_one_shot",
                    "killer": kill.killer_id,
                    "victim": kill.victim_id,
                    "damage": kill.total_damage_dealt,
                    "severity": "medium",
                })
        
        # Check for unbalanced damage distribution
        if len(self.total_damage_by_source) > 1:
            max_damage = max(self.total_damage_by_source.values())
            min_damage = min(self.total_damage_by_source.values())
            if max_damage > min_damage * 10 and max_damage > 1000:
                anomalies.append({
                    "type": "unbalanced_damage_distribution",
                    "max_source_damage": max_damage,
                    "min_source_damage": min_damage,
                    "ratio": max_damage / min_damage if min_damage > 0 else float('inf'),
                    "severity": "medium",
                })
        
        recommendations = []
        if total_hits == 0:
            recommendations.append("No damage events detected. Check if combat skills are working.")
        if crit_rate < 0.05 and total_hits > 20:
            recommendations.append(f"Crit rate ({crit_rate:.1%}) is very low. Consider increasing crit chance.")
        if crit_rate > 0.8 and total_hits > 20:
            recommendations.append(f"Crit rate ({crit_rate:.1%}) is extremely high. May feel unrewarding.")
        if avg_damage < 10 and total_hits > 20:
            recommendations.append(f"Average damage ({avg_damage:.1f}) seems low. Check damage formulas.")
        
        # Top damage dealers
        top_dealers = sorted(
            self.total_damage_by_source.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return PluginReport(
            plugin_name=self.name,
            summary={
                "total_damage": total_damage,
                "total_hits": total_hits,
                "total_kills": len(self.kill_events),
                "total_crits": total_crits,
                "crit_rate": crit_rate,
                "average_damage": avg_damage,
                "dps": dps,
                "top_damage_dealers": [
                    {"source": src, "damage": dmg}
                    for src, dmg in top_dealers
                ],
                "recent_damage_events": [
                    {
                        "source": e.source_id,
                        "target": e.target_id,
                        "damage": e.damage,
                        "crit": e.is_critical,
                        "frame": e.frame,
                    }
                    for e in self.damage_events[-10:]
                ],
            },
            anomalies=anomalies,
            recommendations=recommendations,
        )
