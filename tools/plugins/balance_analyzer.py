"""
Plugin for AI-EVOLVE Dev Probe: Balance Analyzer & Token Optimizer

This plugin provides:
1. Automatic balance analysis from combat logs
2. Token usage optimization through state caching
3. Smart test scenario generation
4. Performance metrics collection
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

@dataclass
class CombatMetrics:
    """Metrics collected from combat sessions"""
    total_combats: int = 0
    avg_combat_duration: float = 0.0
    player_win_rate: float = 0.0
    avg_damage_taken: float = 0.0
    avg_damage_dealt: float = 0.0
    critical_hit_rate: float = 0.0
    dodge_rate: float = 0.0
    death_locations: List[Tuple[float, float, float]] = field(default_factory=list)
    enemy_type_distribution: Dict[str, int] = field(default_factory=dict)
    
@dataclass
class TokenUsageStats:
    """Statistics about token usage during testing"""
    total_tokens_used: int = 0
    tokens_per_test: float = 0.0
    cache_hit_rate: float = 0.0
    redundant_queries: int = 0
    optimized_queries: int = 0

class BalanceAnalyzerPlugin:
    """Plugin for analyzing game balance and optimizing token usage"""
    
    def __init__(self, probe_instance):
        self.probe = probe_instance
        self.combat_logs: List[Dict[str, Any]] = []
        self.metrics = CombatMetrics()
        self.token_stats = TokenUsageStats()
        self.state_cache: Dict[str, Any] = {}
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Register with probe
        self._register_hooks()
        
    def _register_hooks(self):
        """Register event hooks with the probe"""
        if hasattr(self.probe, 'register_hook'):
            self.probe.register_hook('combat_start', self._on_combat_start)
            self.probe.register_hook('combat_end', self._on_combat_end)
            self.probe.register_hook('action_taken', self._on_action_taken)
            self.probe.register_hook('session_end', self._on_session_end)
    
    def _on_combat_start(self, data: Dict[str, Any]):
        """Called when combat starts"""
        pass  # Initialize combat-specific tracking
    
    def _on_combat_end(self, data: Dict[str, Any]):
        """Called when combat end - collect metrics"""
        self.combat_logs.append(data)
        self._update_combat_metrics(data)
        
    def _on_action_taken(self, data: Dict[str, Any]):
        """Called when an action is taken by AI"""
        # Check if this action could be cached
        state_key = self._generate_state_key(data)
        if state_key in self.state_cache:
            self.cache_hits += 1
            # Return cached suggestion instead of querying LLM
            return self.state_cache[state_key]
        else:
            self.cache_misses += 1
            # Store result after LLM query
            # This will be set by the main logic
            pass
    
    def _on_session_end(self, data: Dict[str, Any]):
        """Called when testing session ends"""
        self._generate_balance_report()
        self._optimize_token_usage()
    
    def _generate_state_key(self, action_data: Dict[str, Any]) -> str:
        """Generate a unique key for caching AI decisions"""
        # Create a hashable representation of the game state
        relevant_fields = [
            str(action_data.get('player_hp', 0)),
            str(action_data.get('enemy_hp', 0)),
            str(action_data.get('enemy_type', 'unknown')),
            str(action_data.get('distance', 0)),
            str(action_data.get('active_effects', []))
        ]
        return '|'.join(relevant_fields)
    
    def cache_ai_decision(self, state_key: str, decision: Dict[str, Any]):
        """Cache an AI decision for future reuse"""
        self.state_cache[state_key] = decision
        # Limit cache size to prevent memory issues
        if len(self.state_cache) > 1000:
            # Remove oldest entries
            keys_to_remove = list(self.state_cache.keys())[:200]
            for key in keys_to_remove:
                del self.state_cache[key]
    
    def _update_combat_metrics(self, combat_data: Dict[str, Any]):
        """Update aggregate combat metrics"""
        self.metrics.total_combats += 1
        
        # Update win rate
        if 'winner' in combat_data:
            wins = sum(1 for log in self.combat_logs if log.get('winner') == 'player')
            self.metrics.player_win_rate = wins / self.metrics.total_combats
        
        # Update damage stats
        if 'damage_dealt' in combat_data:
            total_dealt = sum(log.get('damage_dealt', 0) for log in self.combat_logs)
            self.metrics.avg_damage_dealt = total_dealt / self.metrics.total_combats
            
        if 'damage_taken' in combat_data:
            total_taken = sum(log.get('damage_taken', 0) for log in self.combat_logs)
            self.metrics.avg_damage_taken = total_taken / self.metrics.total_combats
        
        # Update crit and dodge rates
        if 'critical_hits' in combat_data:
            total_crits = sum(log.get('critical_hits', 0) for log in self.combat_logs)
            total_attacks = sum(log.get('total_attacks', 1) for log in self.combat_logs)
            self.metrics.critical_hit_rate = total_crits / max(total_attacks, 1)
            
        if 'dodges' in combat_data:
            total_dodges = sum(log.get('dodges', 0) for log in self.combat_logs)
            total_enemy_attacks = sum(log.get('enemy_attacks', 1) for log in self.combat_logs)
            self.metrics.dodge_rate = total_dodges / max(total_enemy_attacks, 1)
        
        # Track enemy types
        enemy_type = combat_data.get('enemy_type', 'unknown')
        self.metrics.enemy_type_distribution[enemy_type] = \
            self.metrics.enemy_type_distribution.get(enemy_type, 0) + 1
    
    def _generate_balance_report(self) -> Dict[str, Any]:
        """Generate a comprehensive balance report"""
        report = {
            'timestamp': time.time(),
            'total_combats': self.metrics.total_combats,
            'player_win_rate': self.metrics.player_win_rate,
            'avg_damage_dealt': self.metrics.avg_damage_dealt,
            'avg_damage_taken': self.metrics.avg_damage_taken,
            'critical_hit_rate': self.metrics.critical_hit_rate,
            'dodge_rate': self.metrics.dodge_rate,
            'enemy_distribution': self.metrics.enemy_type_distribution,
            'balance_issues': [],
            'recommendations': []
        }
        
        # Detect balance issues
        if self.metrics.player_win_rate < 0.3:
            report['balance_issues'].append("Player win rate too low (<30%)")
            report['recommendations'].append("Reduce enemy damage or increase player health")
        elif self.metrics.player_win_rate > 0.8:
            report['balance_issues'].append("Player win rate too high (>80%)")
            report['recommendations'].append("Increase enemy difficulty or reduce player power")
        
        if self.metrics.critical_hit_rate > 0.4:
            report['balance_issues'].append("Critical hit rate too high (>40%)")
            report['recommendations'].append("Reduce critical chance or increase requirements")
        
        if self.metrics.dodge_rate > 0.5:
            report['balance_issues'].append("Dodge rate too high (>50%)")
            report['recommendations'].append("Reduce dodge chance or improve enemy accuracy")
        
        # Save report to file
        report_path = Path('tools/balance_reports')
        report_path.mkdir(exist_ok=True)
        
        timestamp = int(time.time())
        report_file = report_path / f'balance_report_{timestamp}.json'
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📊 BALANCE REPORT GENERATED: {report_file}")
        print(f"   Total Combats: {self.metrics.total_combats}")
        print(f"   Win Rate: {self.metrics.player_win_rate:.2%}")
        print(f"   Issues Found: {len(report['balance_issues'])}")
        
        return report
    
    def _optimize_token_usage(self):
        """Analyze and optimize token usage"""
        total_queries = self.cache_hits + self.cache_misses
        if total_queries > 0:
            self.token_stats.cache_hit_rate = self.cache_hits / total_queries
        
        optimization_report = {
            'cache_hit_rate': self.token_stats.cache_hit_rate,
            'cache_size': len(self.state_cache),
            'estimated_token_savings': self.cache_hits * 150,  # Approximate tokens per query
            'recommendations': []
        }
        
        if self.token_stats.cache_hit_rate < 0.3:
            optimization_report['recommendations'].append(
                "Consider implementing more aggressive caching strategies"
            )
        
        if len(self.state_cache) > 800:
            optimization_report['recommendations'].append(
                "Cache size is large, consider implementing TTL or LRU eviction"
            )
        
        print(f"\n💰 TOKEN OPTIMIZATION REPORT:")
        print(f"   Cache Hit Rate: {self.token_stats.cache_hit_rate:.2%}")
        print(f"   Estimated Tokens Saved: {optimization_report['estimated_token_savings']}")
        
        return optimization_report
    
    def get_optimized_action(self, state_data: Dict[str, Any], llm_query_func) -> Dict[str, Any]:
        """Get AI action with caching optimization"""
        state_key = self._generate_state_key(state_data)
        
        if state_key in self.state_cache:
            self.cache_hits += 1
            return self.state_cache[state_key]
        
        self.cache_misses += 1
        # Call LLM for new state
        decision = llm_query_func(state_data)
        # Cache the result
        self.cache_ai_decision(state_key, decision)
        
        return decision


def register_plugin(probe_instance):
    """Register the plugin with the probe"""
    plugin = BalanceAnalyzerPlugin(probe_instance)
    print("✅ BalanceAnalyzerPlugin registered successfully")
    return plugin
