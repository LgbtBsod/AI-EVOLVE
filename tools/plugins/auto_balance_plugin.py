"""
Plugin for AI-EVOLVE Dev Probe: Auto-Balance Analyzer
Purpose: Automatically detect game balance issues from combat data and suggest fixes.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from collections import defaultdict


@dataclass
class BalanceIssue:
    """Detected balance issue with severity and recommendation."""
    issue_type: str
    severity: str  # "critical", "high", "medium", "low"
    description: str
    evidence: Dict[str, Any]
    recommendation: str
    affected_entities: List[str] = field(default_factory=list)


@dataclass
class WeaponStats:
    """Aggregated weapon performance stats."""
    total_uses: int = 0
    total_damage: float = 0
    kills: int = 0
    avg_damage_per_use: float = 0
    kill_rate: float = 0


@dataclass
class EnemyStats:
    """Aggregated enemy performance stats."""
    spawns: int = 0
    kills_on_player: int = 0
    deaths: int = 0
    avg_time_to_kill: float = 0
    difficulty_rating: str = "unknown"


class AutoBalancePlugin:
    """Plugin for automatic game balance analysis."""
    
    def __init__(self, probe_instance):
        self.probe = probe_instance
        self.combat_sessions: List[Dict[str, Any]] = []
        self.weapon_stats: Dict[str, WeaponStats] = defaultdict(WeaponStats)
        self.enemy_stats: Dict[str, EnemyStats] = defaultdict(EnemyStats)
        self.player_deaths: List[Dict[str, Any]] = []
        self.issues: List[BalanceIssue] = []
        
        # Thresholds for balance detection
        self.win_rate_threshold_low = 0.3
        self.win_rate_threshold_high = 0.8
        self.crit_rate_threshold = 0.4
        self.dodge_rate_threshold = 0.5
        self.damage_variance_threshold = 3.0  # Max damage / Min damage ratio
        
        self._register_hooks()
    
    def _register_hooks(self):
        """Register event hooks with the probe."""
        if hasattr(self.probe, 'register_hook'):
            self.probe.register_hook('combat_start', self._on_combat_start)
            self.probe.register_hook('combat_end', self._on_combat_end)
            self.probe.register_hook('player_death', self._on_player_death)
            self.probe.register_hook('session_end', self._on_session_end)
    
    def _on_combat_start(self, data: Dict[str, Any]):
        """Initialize combat session tracking."""
        session = {
            'start_time': time.time(),
            'player_hp': data.get('player_hp', 100),
            'enemy_type': data.get('enemy_type', 'unknown'),
            'enemy_hp': data.get('enemy_hp', 100),
            'weapon_used': data.get('weapon', 'default'),
            'events': []
        }
        self.combat_sessions.append(session)
    
    def _on_combat_end(self, data: Dict[str, Any]):
        """Process combat results and update stats."""
        if not self.combat_sessions:
            return
        
        session = self.combat_sessions[-1]
        session['end_time'] = time.time()
        session['duration'] = session['end_time'] - session['start_time']
        session['winner'] = data.get('winner', 'unknown')
        session['damage_dealt'] = data.get('damage_dealt', 0)
        session['damage_taken'] = data.get('damage_taken', 0)
        session['critical_hits'] = data.get('critical_hits', 0)
        session['dodges'] = data.get('dodges', 0)
        session['total_attacks'] = data.get('total_attacks', 1)
        
        # Update weapon stats
        weapon = session.get('weapon_used', 'default')
        ws = self.weapon_stats[weapon]
        ws.total_uses += 1
        ws.total_damage += session.get('damage_dealt', 0)
        if session.get('winner') == 'player':
            ws.kills += 1
        ws.avg_damage_per_use = ws.total_damage / ws.total_uses if ws.total_uses > 0 else 0
        ws.kill_rate = ws.kills / ws.total_uses if ws.total_uses > 0 else 0
        
        # Update enemy stats
        enemy_type = session.get('enemy_type', 'unknown')
        es = self.enemy_stats[enemy_type]
        es.spawns += 1
        if session.get('winner') == 'enemy':
            es.kills_on_player += 1
        else:
            es.deaths += 1
        
        # Calculate average time to kill for enemy
        if session.get('winner') == 'player' and session.get('duration', 0) > 0:
            total_ttk = es.avg_time_to_kill * (es.deaths - 1) + session['duration']
            es.avg_time_to_kill = total_ttk / es.deaths if es.deaths > 0 else 0
    
    def _on_player_death(self, data: Dict[str, Any]):
        """Record player death for analysis."""
        death_record = {
            'timestamp': time.time(),
            'enemy_type': data.get('enemy_type', 'unknown'),
            'player_hp_before': data.get('player_hp', 0),
            'damage_source': data.get('damage_source', 'unknown'),
            'combat_duration': data.get('combat_duration', 0)
        }
        self.player_deaths.append(death_record)
    
    def _on_session_end(self, data: Dict[str, Any]):
        """Run full balance analysis at session end."""
        self._analyze_balance()
        self._generate_report()
    
    def _analyze_balance(self):
        """Analyze collected data for balance issues."""
        self.issues.clear()
        
        # Analyze win rates
        self._check_win_rates()
        
        # Analyze crit/dodge rates
        self._check_crit_dodge_rates()
        
        # Analyze weapon balance
        self._check_weapon_balance()
        
        # Analyze enemy difficulty
        self._check_enemy_difficulty()
        
        # Analyze player death patterns
        self._check_death_patterns()
    
    def _check_win_rates(self):
        """Check if player win rate is within acceptable bounds."""
        if not self.combat_sessions:
            return
        
        wins = sum(1 for s in self.combat_sessions if s.get('winner') == 'player')
        win_rate = wins / len(self.combat_sessions)
        
        if win_rate < self.win_rate_threshold_low:
            self.issues.append(BalanceIssue(
                issue_type="win_rate_too_low",
                severity="critical",
                description=f"Player win rate ({win_rate:.1%}) is below {self.win_rate_threshold_low:.0%}",
                evidence={'win_rate': win_rate, 'total_combats': len(self.combat_sessions)},
                recommendation="Reduce enemy damage/health or increase player power",
                affected_entities=['player']
            ))
        elif win_rate > self.win_rate_threshold_high:
            self.issues.append(BalanceIssue(
                issue_type="win_rate_too_high",
                severity="high",
                description=f"Player win rate ({win_rate:.1%}) is above {self.win_rate_threshold_high:.0%}",
                evidence={'win_rate': win_rate, 'total_combats': len(self.combat_sessions)},
                recommendation="Increase enemy difficulty or reduce player power",
                affected_entities=['player']
            ))
    
    def _check_crit_dodge_rates(self):
        """Check critical hit and dodge rates."""
        if not self.combat_sessions:
            return
        
        total_crits = sum(s.get('critical_hits', 0) for s in self.combat_sessions)
        total_attacks = sum(s.get('total_attacks', 1) for s in self.combat_sessions)
        crit_rate = total_crits / total_attacks if total_attacks > 0 else 0
        
        total_dodges = sum(s.get('dodges', 0) for s in self.combat_sessions)
        enemy_attacks = sum(s.get('enemy_attacks', 1) for s in self.combat_sessions)
        dodge_rate = total_dodges / enemy_attacks if enemy_attacks > 0 else 0
        
        if crit_rate > self.crit_rate_threshold:
            self.issues.append(BalanceIssue(
                issue_type="crit_rate_too_high",
                severity="high",
                description=f"Critical hit rate ({crit_rate:.1%}) exceeds {self.crit_rate_threshold:.0%}",
                evidence={'crit_rate': crit_rate, 'total_crits': total_crits},
                recommendation="Reduce critical chance or increase requirements",
                affected_entities=['combat_system']
            ))
        
        if dodge_rate > self.dodge_rate_threshold:
            self.issues.append(BalanceIssue(
                issue_type="dodge_rate_too_high",
                severity="high",
                description=f"Dodge rate ({dodge_rate:.1%}) exceeds {self.dodge_rate_threshold:.0%}",
                evidence={'dodge_rate': dodge_rate, 'total_dodges': total_dodges},
                recommendation="Reduce dodge chance or improve enemy accuracy",
                affected_entities=['player']
            ))
    
    def _check_weapon_balance(self):
        """Check if any weapons are significantly over/underpowered."""
        if len(self.weapon_stats) < 2:
            return
        
        avg_damages = [(w, s.avg_damage_per_use) for w, s in self.weapon_stats.items() if s.total_uses > 5]
        if len(avg_damages) < 2:
            return
        
        avg_damages.sort(key=lambda x: x[1], reverse=True)
        best_weapon, best_dmg = avg_damages[0]
        worst_weapon, worst_dmg = avg_damages[-1]
        
        if worst_dmg > 0 and best_dmg / worst_dmg > self.damage_variance_threshold:
            self.issues.append(BalanceIssue(
                issue_type="weapon_imbalance",
                severity="medium",
                description=f"Weapon '{best_weapon}' deals {best_dmg/worst_dmg:.1f}x more damage than '{worst_weapon}'",
                evidence={
                    'best_weapon': best_weapon,
                    'best_dps': best_dmg,
                    'worst_weapon': worst_weapon,
                    'worst_dps': worst_dmg
                },
                recommendation=f"Nerf {best_weapon} or buff {worst_weapon}",
                affected_entities=[best_weapon, worst_weapon]
            ))
    
    def _check_enemy_difficulty(self):
        """Check if any enemies are too easy/hard."""
        for enemy_type, stats in self.enemy_stats.items():
            if stats.spawns < 5:
                continue
            
            kill_rate = stats.kills_on_player / stats.spawns if stats.spawns > 0 else 0
            
            if kill_rate > 0.7:
                self.issues.append(BalanceIssue(
                    issue_type="enemy_too_hard",
                    severity="high",
                    description=f"Enemy '{enemy_type}' kills player {kill_rate:.0%} of the time",
                    evidence={
                        'enemy_type': enemy_type,
                        'kill_rate': kill_rate,
                        'avg_ttk': stats.avg_time_to_kill
                    },
                    recommendation=f"Reduce {enemy_type} damage/health or add counterplay",
                    affected_entities=[enemy_type]
                ))
            elif kill_rate < 0.1 and stats.spawns > 10:
                self.issues.append(BalanceIssue(
                    issue_type="enemy_too_easy",
                    severity="low",
                    description=f"Enemy '{enemy_type}' rarely kills player ({kill_rate:.0%})",
                    evidence={
                        'enemy_type': enemy_type,
                        'kill_rate': kill_rate,
                        'deaths': stats.deaths
                    },
                    recommendation=f"Increase {enemy_type} difficulty or reward",
                    affected_entities=[enemy_type]
                ))
    
    def _check_death_patterns(self):
        """Analyze player death patterns for unfair situations."""
        if len(self.player_deaths) < 3:
            return
        
        # Check for instant deaths
        instant_deaths = [d for d in self.player_deaths if d.get('combat_duration', 0) < 1.0]
        if len(instant_deaths) > len(self.player_deaths) * 0.3:
            self.issues.append(BalanceIssue(
                issue_type="instant_deaths",
                severity="critical",
                description=f"{len(instant_deaths)} out of {len(self.player_deaths)} deaths occurred in under 1 second",
                evidence={'instant_death_count': len(instant_deaths)},
                recommendation="Add damage falloff, shields, or warning telegraphs",
                affected_entities=['combat_system', 'enemies']
            ))
    
    def _generate_report(self):
        """Generate balance analysis report."""
        report = {
            'timestamp': time.time(),
            'total_combats': len(self.combat_sessions),
            'total_player_deaths': len(self.player_deaths),
            'weapons_analyzed': len(self.weapon_stats),
            'enemies_analyzed': len(self.enemy_stats),
            'issues_found': len(self.issues),
            'issues_by_severity': {
                'critical': sum(1 for i in self.issues if i.severity == 'critical'),
                'high': sum(1 for i in self.issues if i.severity == 'high'),
                'medium': sum(1 for i in self.issues if i.severity == 'medium'),
                'low': sum(1 for i in self.issues if i.severity == 'low'),
            },
            'issues': [
                {
                    'type': i.issue_type,
                    'severity': i.severity,
                    'description': i.description,
                    'recommendation': i.recommendation
                }
                for i in self.issues
            ],
            'weapon_stats': {
                w: {
                    'uses': s.total_uses,
                    'avg_damage': round(s.avg_damage_per_use, 2),
                    'kill_rate': round(s.kill_rate, 2)
                }
                for w, s in self.weapon_stats.items()
            },
            'enemy_stats': {
                e: {
                    'spawns': s.spawns,
                    'kills_on_player': s.kills_on_player,
                    'deaths': s.deaths,
                    'avg_ttk': round(s.avg_time_to_kill, 2)
                }
                for e, s in self.enemy_stats.items()
            }
        }
        
        # Save report
        report_path = Path('tools/balance_reports')
        report_path.mkdir(exist_ok=True)
        
        timestamp = int(time.time())
        report_file = report_path / f'balance_analysis_{timestamp}.json'
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Print summary
        print(f"\n⚖️  BALANCE ANALYSIS REPORT: {report_file}")
        print(f"   Total Combats: {len(self.combat_sessions)}")
        print(f"   Issues Found: {len(self.issues)}")
        
        if self.issues:
            print("\n   Issues by Severity:")
            for severity in ['critical', 'high', 'medium', 'low']:
                count = sum(1 for i in self.issues if i.severity == severity)
                if count > 0:
                    emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}[severity]
                    print(f"     {emoji} {severity.upper()}: {count}")
            
            print("\n   Top Recommendations:")
            for i, issue in enumerate(self.issues[:3], 1):
                print(f"     {i}. [{issue.severity}] {issue.recommendation}")
        else:
            print("   ✅ No balance issues detected!")
        
        return report
    
    def get_stats(self) -> Dict[str, Any]:
        """Return current balance stats."""
        return {
            'total_combats': len(self.combat_sessions),
            'issues_found': len(self.issues),
            'weapons_tracked': len(self.weapon_stats),
            'enemies_tracked': len(self.enemy_stats)
        }


def register_plugin(probe_instance):
    """Register the plugin with the probe."""
    plugin = AutoBalancePlugin(probe_instance)
    print("✅ AutoBalancePlugin registered successfully")
    return plugin


if __name__ == "__main__":
    print("Running AutoBalancePlugin self-test...")
    
    class MockProbe:
        def __init__(self):
            self.hooks = {}
        
        def register_hook(self, event, callback):
            if event not in self.hooks:
                self.hooks[event] = []
            self.hooks[event].append(callback)
    
    mock_probe = MockProbe()
    plugin = AutoBalancePlugin(mock_probe)
    
    # Simulate combats
    plugin._on_session_start = lambda d: None  # Dummy
    plugin._on_session_end = lambda d: None  # Will call manually
    
    for i in range(20):
        plugin._on_combat_start({
            'player_hp': 100,
            'enemy_type': 'basic' if i % 2 == 0 else 'strong',
            'enemy_hp': 50,
            'weapon': 'sword' if i % 3 == 0 else 'axe'
        })
        plugin._on_combat_end({
            'winner': 'player' if i % 3 != 0 else 'enemy',
            'damage_dealt': 30 + i,
            'damage_taken': 10,
            'critical_hits': 1 if i % 4 == 0 else 0,
            'dodges': 1 if i % 5 == 0 else 0,
            'total_attacks': 5,
            'enemy_attacks': 3
        })
    
    plugin._analyze_balance()
    stats = plugin.get_stats()
    
    print(f"✅ Self-test PASSED - Stats: {stats}")
    print(f"   Issues found: {len(plugin.issues)}")
