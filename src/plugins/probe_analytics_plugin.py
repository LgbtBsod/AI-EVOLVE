"""
Plugin: CombatAnalytics
Purpose: Real-time combat balance analysis and anomaly detection.
Author: Core Lead Game Designer (AI Agent)
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import statistics
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

@dataclass
class CombatEvent:
    timestamp: float
    attacker_id: int
    defender_id: int
    damage_dealt: float
    damage_expected: float
    is_critical: bool
    is_dodge: bool
    attacker_level: int
    defender_level: int
    defender_type: str

@dataclass
class BalanceMetrics:
    avg_damage_ratio: float = 0.0  # actual / expected
    crit_rate: float = 0.0
    dodge_rate: float = 0.0
    kill_time_avg: float = 0.0
    damage_variance: float = 0.0
    anomaly_count: int = 0

class CombatAnalytics:
    """
    Analyzes combat logs in real-time to detect balance issues.
    Provides actionable insights for designers.
    """
    
    def __init__(self):
        self.events: List[CombatEvent] = []
        self.entity_stats: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
            "damage_dealt": 0,
            "damage_taken": 0,
            "kills": 0,
            "deaths": 0,
            "crits_landed": 0,
            "dodges_received": 0
        })
        self.combat_sessions: Dict[str, List[CombatEvent]] = defaultdict(list)
        
    def log_event(self, event: CombatEvent):
        """Record a combat event for analysis."""
        self.events.append(event)
        
        # Update entity stats
        self.entity_stats[event.attacker_id]["damage_dealt"] += event.damage_dealt
        self.entity_stats[event.attacker_id]["crits_landed"] += 1 if event.is_critical else 0
        
        self.entity_stats[event.defender_id]["damage_taken"] += event.damage_dealt
        self.entity_stats[event.defender_id]["dodges_received"] += 1 if event.is_dodge else 0
        
        # Session tracking (simple 60s windows)
        session_key = f"{event.attacker_id}_vs_{event.defender_id}"
        self.combat_sessions[session_key].append(event)
        
    def detect_anomalies(self, threshold: float = 2.0) -> List[Dict[str, Any]]:
        """
        Detect balance anomalies using statistical methods.
        Returns list of issues with severity ratings.
        """
        anomalies = []
        
        if len(self.events) < 10:
            return anomalies  # Not enough data
            
        # Check damage ratio distribution
        damage_ratios = [e.damage_dealt / max(e.damage_expected, 1) for e in self.events]
        mean_ratio = statistics.mean(damage_ratios)
        stdev_ratio = statistics.stdev(damage_ratios) if len(damage_ratios) > 1 else 0
        
        # Flag outliers
        for i, event in enumerate(self.events):
            ratio = event.damage_dealt / max(event.damage_expected, 1)
            if stdev_ratio > 0 and abs(ratio - mean_ratio) > threshold * stdev_ratio:
                anomalies.append({
                    "type": "damage_outlier",
                    "severity": "HIGH" if abs(ratio - mean_ratio) > 3 * stdev_ratio else "MEDIUM",
                    "event_index": i,
                    "details": f"Damage {event.damage_dealt:.1f} vs expected {event.damage_expected:.1f} (ratio: {ratio:.2f})"
                })
        
        # Check crit rate consistency
        crit_events = [e for e in self.events if e.is_critical]
        actual_crit_rate = len(crit_events) / len(self.events)
        
        # Assume base crit chance ~5% from config
        expected_crit_rate = 0.05
        if actual_crit_rate > expected_crit_rate * 2:
            anomalies.append({
                "type": "crit_rate_too_high",
                "severity": "MEDIUM",
                "details": f"Actual crit rate {actual_crit_rate*100:.1f}% vs expected {expected_crit_rate*100:.1f}%"
            })
            
        # Check dodge rate
        dodge_events = [e for e in self.events if e.is_dodge]
        actual_dodge_rate = len(dodge_events) / len(self.events)
        
        # Assume base dodge ~10%
        if actual_dodge_rate > 0.25:
            anomalies.append({
                "type": "dodge_rate_too_high",
                "severity": "MEDIUM",
                "details": f"Actual dodge rate {actual_dodge_rate*100:.1f}% vs expected ~10%"
            })
            
        return anomalies
        
    def get_balance_report(self) -> Dict[str, Any]:
        """Generate comprehensive balance report."""
        if not self.events:
            return {"status": "no_data"}
            
        damage_ratios = [e.damage_dealt / max(e.damage_expected, 1) for e in self.events]
        crit_events = [e for e in self.events if e.is_critical]
        dodge_events = [e for e in self.events if e.is_dodge]
        
        anomalies = self.detect_anomalies()
        
        return {
            "total_events": len(self.events),
            "metrics": {
                "avg_damage_ratio": round(statistics.mean(damage_ratios), 3),
                "damage_ratio_stdev": round(statistics.stdev(damage_ratios), 3) if len(damage_ratios) > 1 else 0,
                "crit_rate_percent": round(len(crit_events) / len(self.events) * 100, 2),
                "dodge_rate_percent": round(len(dodge_events) / len(self.events) * 100, 2),
            },
            "entity_performance": {
                eid: {
                    "dps": stats["damage_dealt"] / max(len([e for e in self.events if e.attacker_id == eid]), 1),
                    "survivability": stats["damage_dealt"] / max(stats["damage_taken"], 1)
                }
                for eid, stats in self.entity_stats.items()
            },
            "anomalies": anomalies,
            "health_status": "BALANCED" if len(anomalies) == 0 else "NEEDS_ATTENTION"
        }
        
    def reset(self):
        """Clear all data for new session."""
        self.events.clear()
        self.entity_stats.clear()
        self.combat_sessions.clear()

# Self-test
if __name__ == "__main__":
    print("Running CombatAnalytics self-test...")
    analytics = CombatAnalytics()
    
    # Log some test events
    for i in range(20):
        event = CombatEvent(
            timestamp=i * 0.5,
            attacker_id=1,
            defender_id=2,
            damage_dealt=10.0 if i != 15 else 50.0,  # One outlier
            damage_expected=10.0,
            is_critical=(i % 20 == 0),  # 5% crit rate
            is_dodge=False,
            attacker_level=5,
            defender_level=3,
            defender_type="slime"
        )
        analytics.log_event(event)
    
    report = analytics.get_balance_report()
    assert report["total_events"] == 20
    assert report["metrics"]["crit_rate_percent"] == 5.0  # 1/20
    assert len(report["anomalies"]) >= 1  # Should detect the outlier
    
    print("✅ CombatAnalytics self-test PASSED")
    print(f"Report summary: {report['metrics']}")
    print(f"Anomalies found: {len(report['anomalies'])}")
