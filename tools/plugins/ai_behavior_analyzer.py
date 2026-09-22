"""
Dev Probe Plugin: AI Behavior Analyzer
Monitors and analyzes AI agent behavior patterns
Detects anomalies, loops, and inefficiencies in decision making
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import logging
import statistics
from collections import deque, defaultdict
import time

logger = logging.getLogger(__name__)


@dataclass
class BehaviorMetrics:
    """Metrics for AI behavior analysis"""
    action_counts: Dict[str, int] = field(default_factory=dict)
    action_durations: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))
    state_transitions: List[tuple] = field(default_factory=list)
    decision_times: List[float] = field(default_factory=list)
    recent_actions: List[str] = field(default_factory=list)  # Track actual sequence
    loop_detected: bool = False
    anomaly_score: float = 0.0
    
    def add_action(self, action: str, duration: float = 0.0) -> None:
        self.action_counts[action] = self.action_counts.get(action, 0) + 1
        self.recent_actions.append(action)  # Track sequence
        if duration > 0:
            self.action_durations[action].append(duration)
    
    def add_transition(self, from_state: str, to_state: str) -> None:
        self.state_transitions.append((from_state, to_state))
    
    def add_decision_time(self, time_ms: float) -> None:
        self.decision_times.append(time_ms)
    
    def get_most_common_action(self) -> Optional[str]:
        if not self.action_counts:
            return None
        return max(self.action_counts.items(), key=lambda x: x[1])[0]
    
    def get_avg_decision_time(self) -> float:
        if not self.decision_times:
            return 0.0
        return statistics.mean(self.decision_times)
    
    def get_action_distribution(self) -> Dict[str, float]:
        total = sum(self.action_counts.values())
        if total == 0:
            return {}
        return {k: v / total * 100 for k, v in self.action_counts.items()}


@dataclass
class AgentProfile:
    """Behavioral profile of an AI agent"""
    agent_id: str
    agent_type: str
    metrics: BehaviorMetrics = field(default_factory=BehaviorMetrics)
    session_start: float = field(default_factory=time.time)
    total_ticks: int = 0
    stuck_count: int = 0
    efficiency_score: float = 100.0


class AIBehaviorAnalyzerPlugin:
    """
    Dev Probe Plugin for analyzing AI agent behavior
    
    Features:
    - Track action frequencies and patterns
    - Detect behavioral loops (stuck agents)
    - Identify anomalies in decision making
    - Calculate efficiency scores
    - Generate behavior reports
    """
    
    def __init__(self, probe_instance=None):
        self.probe = probe_instance
        self.agent_profiles: Dict[str, AgentProfile] = {}
        self.global_metrics = BehaviorMetrics()
        self.config = {
            "loop_threshold": 5,  # Consecutive same actions to detect loop
            "anomaly_std_dev": 2.0,  # Standard deviations for anomaly detection
            "max_history": 1000,
            "report_interval_seconds": 60
        }
        self.enabled = True
        self.reports_generated = 0
        
        logger.info("AIBehaviorAnalyzerPlugin initialized")
    
    def register_agent(self, agent_id: str, agent_type: str) -> AgentProfile:
        """Register a new agent for monitoring"""
        if agent_id not in self.agent_profiles:
            profile = AgentProfile(agent_id=agent_id, agent_type=agent_type)
            self.agent_profiles[agent_id] = profile
            logger.info(f"Registered agent {agent_id} ({agent_type})")
        return self.agent_profiles[agent_id]
    
    def record_tick(self, agent_id: str, action: str, 
                   prev_state: str, curr_state: str, 
                   decision_time_ms: float) -> None:
        """Record a single tick of an agent's behavior"""
        if not self.enabled or agent_id not in self.agent_profiles:
            return
        
        profile = self.agent_profiles[agent_id]
        profile.total_ticks += 1
        
        # Record action
        profile.metrics.add_action(action)
        self.global_metrics.add_action(action)
        
        # Record state transition
        profile.metrics.add_transition(prev_state, curr_state)
        
        # Record decision time
        profile.metrics.add_decision_time(decision_time_ms)
        self.global_metrics.add_decision_time(decision_time_ms)
        
        # Detect loops
        self._detect_loops(profile, action)
        
        # Calculate efficiency
        self._update_efficiency(profile)
    
    def _detect_loops(self, profile: AgentProfile, current_action: str) -> None:
        """Detect if agent is stuck in a loop"""
        # Use the recent_actions list to detect loops
        recent = profile.metrics.recent_actions
        
        # Check if we have enough history
        if len(recent) >= self.config["loop_threshold"]:
            # Get the last N actions
            last_n_actions = recent[-self.config["loop_threshold"]:]
            
            # If all last N actions are the same, it's a loop
            if len(set(last_n_actions)) == 1:
                profile.metrics.loop_detected = True
                profile.stuck_count += 1
                logger.warning(f"Agent {profile.agent_id} detected in loop: {current_action}")
    
    def _update_efficiency(self, profile: AgentProfile) -> None:
        """Calculate agent efficiency score"""
        if profile.total_ticks < 10:
            return
        
        # Factors affecting efficiency:
        # 1. Action diversity (too few actions = bad)
        action_diversity = len(profile.metrics.action_counts)
        diversity_penalty = max(0, (5 - action_diversity) * 5)
        
        # 2. Loop detection
        loop_penalty = profile.stuck_count * 10
        
        # 3. Decision time (too slow = bad)
        avg_decision_time = profile.metrics.get_avg_decision_time()
        time_penalty = max(0, (avg_decision_time - 100) / 10)  # Penalty if >100ms
        
        profile.efficiency_score = max(0, 100 - diversity_penalty - loop_penalty - time_penalty)
    
    def detect_anomalies(self, agent_id: str) -> List[Dict[str, Any]]:
        """Detect behavioral anomalies for an agent"""
        if agent_id not in self.agent_profiles:
            return []
        
        profile = self.agent_profiles[agent_id]
        anomalies = []
        
        # Check for unusual action distribution
        dist = profile.metrics.get_action_distribution()
        for action, percentage in dist.items():
            if percentage > 80:  # Single action dominates
                anomalies.append({
                    "type": "action_domination",
                    "action": action,
                    "percentage": percentage,
                    "severity": "high" if percentage > 95 else "medium"
                })
        
        # Check for excessive decision time
        avg_time = profile.metrics.get_avg_decision_time()
        if avg_time > 500:  # >500ms average
            anomalies.append({
                "type": "slow_decisions",
                "avg_time_ms": avg_time,
                "severity": "high" if avg_time > 1000 else "medium"
            })
        
        # Check for loops
        if profile.metrics.loop_detected:
            anomalies.append({
                "type": "behavioral_loop",
                "stuck_count": profile.stuck_count,
                "severity": "high" if profile.stuck_count > 5 else "medium"
            })
        
        # Update anomaly score
        profile.metrics.anomaly_score = len(anomalies) * 0.2
        
        return anomalies
    
    def generate_report(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate behavior analysis report"""
        if agent_id:
            if agent_id not in self.agent_profiles:
                return {"error": "Agent not found"}
            
            profile = self.agent_profiles[agent_id]
            anomalies = self.detect_anomalies(agent_id)
            
            report = {
                "agent_id": agent_id,
                "agent_type": profile.agent_type,
                "session_duration_s": time.time() - profile.session_start,
                "total_ticks": profile.total_ticks,
                "efficiency_score": profile.efficiency_score,
                "most_common_action": profile.metrics.get_most_common_action(),
                "action_distribution": profile.metrics.get_action_distribution(),
                "avg_decision_time_ms": profile.metrics.get_avg_decision_time(),
                "loops_detected": profile.stuck_count,
                "anomalies": anomalies,
                "anomaly_score": profile.metrics.anomaly_score
            }
        else:
            # Global report
            report = {
                "total_agents": len(self.agent_profiles),
                "avg_efficiency": statistics.mean([p.efficiency_score for p in self.agent_profiles.values()]) if self.agent_profiles else 0,
                "total_ticks": sum(p.total_ticks for p in self.agent_profiles.values()),
                "global_action_distribution": self.global_metrics.get_action_distribution(),
                "agents_with_loops": sum(1 for p in self.agent_profiles.values() if p.stuck_count > 0),
                "reports_generated": self.reports_generated + 1
            }
            self.reports_generated += 1
        
        return report
    
    def get_recommendations(self, agent_id: str) -> List[str]:
        """Get recommendations for improving agent behavior"""
        if agent_id not in self.agent_profiles:
            return []
        
        profile = self.agent_profiles[agent_id]
        recommendations = []
        
        if profile.efficiency_score < 50:
            recommendations.append("Critical: Agent efficiency is very low. Review behavior tree.")
        
        if profile.stuck_count > 3:
            recommendations.append(f"Warning: Agent stuck {profile.stuck_count} times. Add escape conditions.")
        
        action_dist = profile.metrics.get_action_distribution()
        if action_dist:
            dominant = max(action_dist.items(), key=lambda x: x[1])
            if dominant[1] > 70:
                recommendations.append(f"Suggestion: Reduce dominance of '{dominant[0]}' action ({dominant[1]:.1f}%).")
        
        avg_time = profile.metrics.get_avg_decision_time()
        if avg_time > 200:
            recommendations.append(f"Performance: Average decision time {avg_time:.1f}ms is high. Optimize conditions.")
        
        if len(action_dist) < 3:
            recommendations.append("Diversity: Agent uses too few actions. Add more behaviors.")
        
        return recommendations
    
    def reset(self) -> None:
        """Reset all metrics"""
        self.agent_profiles.clear()
        self.global_metrics = BehaviorMetrics()
        logger.info("AIBehaviorAnalyzerPlugin reset")
    
    def get_plugin_status(self) -> Dict[str, Any]:
        """Get plugin status for Dev Probe"""
        return {
            "enabled": self.enabled,
            "monitored_agents": len(self.agent_profiles),
            "total_ticks_recorded": sum(p.total_ticks for p in self.agent_profiles.values()),
            "reports_generated": self.reports_generated,
            "config": self.config
        }


if __name__ == "__main__":
    # Test the plugin
    logging.basicConfig(level=logging.INFO)
    
    print("=== AIBehaviorAnalyzerPlugin Test ===\n")
    
    plugin = AIBehaviorAnalyzerPlugin()
    
    # Simulate agents
    import random
    
    # Register agents
    plugin.register_agent("warrior_001", "warrior")
    plugin.register_agent("mage_001", "mage")
    
    # Simulate ticks
    actions = ["idle", "move", "attack", "defend", "collect_loot", "flee"]
    
    print("Simulating 100 ticks...")
    for tick in range(100):
        for agent_id in ["warrior_001", "mage_001"]:
            # Normal behavior
            action = random.choice(actions[:4])
            
            # Simulate loop for warrior
            if agent_id == "warrior_001" and tick > 50 and tick % 3 == 0:
                action = "idle"  # Stuck in idle
            
            # Simulate slow decisions for mage
            decision_time = random.uniform(10, 50)
            if agent_id == "mage_001" and tick > 30:
                decision_time = random.uniform(200, 600)  # Slow
            
            plugin.record_tick(
                agent_id=agent_id,
                action=action,
                prev_state="prev",
                curr_state="curr",
                decision_time_ms=decision_time
            )
    
    # Generate reports
    print("\n--- Warrior Report ---")
    warrior_report = plugin.generate_report("warrior_001")
    print(f"Efficiency: {warrior_report['efficiency_score']:.1f}")
    print(f"Loops: {warrior_report['loops_detected']}")
    print(f"Anomalies: {len(warrior_report['anomalies'])}")
    
    print("\nRecommendations:")
    for rec in plugin.get_recommendations("warrior_001"):
        print(f"  - {rec}")
    
    print("\n--- Mage Report ---")
    mage_report = plugin.generate_report("mage_001")
    print(f"Efficiency: {mage_report['efficiency_score']:.1f}")
    print(f"Avg Decision Time: {mage_report['avg_decision_time_ms']:.1f}ms")
    
    print("\nRecommendations:")
    for rec in plugin.get_recommendations("mage_001"):
        print(f"  - {rec}")
    
    print("\n--- Global Report ---")
    global_report = plugin.generate_report()
    print(f"Total Agents: {global_report['total_agents']}")
    print(f"Avg Efficiency: {global_report['avg_efficiency']:.1f}")
    
    print("\n=== Test Complete ===")
