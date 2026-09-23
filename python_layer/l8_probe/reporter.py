"""L8 Probe Reporter - Issue detection and summary generation

Detects issues from frame metrics and game state.
Generates agent-friendly summary.md reports.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DetectedIssue:
    """A detected issue during the probe session"""
    issue_type: str
    description: str
    first_occurrence: float
    last_occurrence: float
    frame_ids: List[int]
    severity: str = 'medium'  # low/medium/high/critical
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'issue_type': self.issue_type,
            'description': self.description,
            'first_frame': self.frame_ids[0] if self.frame_ids else None,
            'last_frame': self.frame_ids[-1] if self.frame_ids else None,
            'duration_seconds': self.last_occurrence - self.first_occurrence,
            'occurrence_count': len(self.frame_ids),
            'severity': self.severity,
            'context': self.context,
        }


class IssueDetector:
    """Detect issues from frame metrics and game state"""
    
    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None):
        """
        Initialize issue detector.
        
        Args:
            rules: List of issue detection rules from Lua config
                  Each rule has: name, description, condition
        """
        self.rules = rules or self._get_default_rules()
        self._issues: List[DetectedIssue] = []
        self._pending_frames: Dict[str, List[Tuple[int, float, Dict]]] = {}
    
    def _get_default_rules(self) -> List[Dict[str, Any]]:
        """Default issue detection rules"""
        return [
            {
                'name': 'render_blackout',
                'description': 'Black screen while entities are alive',
                'check_fn': self._check_render_blackout,
                'severity': 'critical',
            },
            {
                'name': 'frozen_game',
                'description': 'No motion detected for extended period',
                'check_fn': self._check_frozen_game,
                'severity': 'high',
            },
            {
                'name': 'flash_bang',
                'description': 'Sudden brightness change (flash/fade effect)',
                'check_fn': self._check_flash_bang,
                'severity': 'medium',
            },
            {
                'name': 'low_complexity',
                'description': 'Unusually low visual complexity (possible rendering issue)',
                'check_fn': self._check_low_complexity,
                'severity': 'low',
            },
        ]
    
    def analyze_frame(
        self,
        frame_id: int,
        timestamp: float,
        metrics: Dict[str, Any],
        game_state: Optional[Dict[str, Any]] = None
    ):
        """
        Analyze a single frame for issues.
        
        Args:
            frame_id: Sequential frame number
            timestamp: Unix timestamp
            metrics: FrameMetrics as dict from Rust analyzer
            game_state: Optional game state (entities, combat events, etc.)
        """
        for rule in self.rules:
            try:
                issue = rule['check_fn'](frame_id, timestamp, metrics, game_state)
                if issue:
                    self._add_issue(issue)
            except Exception as e:
                logger.debug(f"Rule {rule.get('name', 'unknown')} failed: {e}")
    
    def _check_render_blackout(
        self,
        frame_id: int,
        timestamp: float,
        metrics: Dict[str, Any],
        game_state: Optional[Dict[str, Any]]
    ) -> Optional[DetectedIssue]:
        """Check for black screen while game is active"""
        if metrics.get('is_blank', False):
            entities_alive = 0
            if game_state:
                entities_alive = game_state.get('entities_alive', 0)
            
            if entities_alive > 0:
                return DetectedIssue(
                    issue_type='render_blackout',
                    description=f'Black screen detected but {entities_alive} entities are alive',
                    first_occurrence=timestamp,
                    last_occurrence=timestamp,
                    frame_ids=[frame_id],
                    severity='critical',
                    context={'entities_alive': entities_alive},
                )
        return None
    
    def _check_frozen_game(
        self,
        frame_id: int,
        timestamp: float,
        metrics: Dict[str, Any],
        game_state: Optional[Dict[str, Any]]
    ) -> Optional[DetectedIssue]:
        """Check for frozen game (no motion)"""
        motion_ratio = metrics.get('motion_ratio', 0.0)
        
        if motion_ratio < 0.01:
            # Track consecutive low-motion frames
            key = 'frozen_game'
            if key not in self._pending_frames:
                self._pending_frames[key] = []
            
            self._pending_frames[key].append((frame_id, timestamp, metrics))
            
            # Check if we have 10+ consecutive frozen frames
            recent = self._pending_frames[key][-10:]
            if len(recent) >= 10:
                first_ts = recent[0][1]
                last_ts = recent[-1][1]
                
                if last_ts - first_ts >= 0.5:  # ~10 frames at 20 FPS
                    return DetectedIssue(
                        issue_type='frozen_game',
                        description=f'No motion detected for {len(recent)} frames',
                        first_occurrence=first_ts,
                        last_occurrence=last_ts,
                        frame_ids=[f[0] for f in recent],
                        severity='high',
                        context={'motion_ratio': motion_ratio, 'frame_count': len(recent)},
                    )
        else:
            # Reset pending frames when motion returns
            self._pending_frames.pop('frozen_game', None)
        
        return None
    
    def _check_flash_bang(
        self,
        frame_id: int,
        timestamp: float,
        metrics: Dict[str, Any],
        game_state: Optional[Dict[str, Any]]
    ) -> Optional[DetectedIssue]:
        """Check for sudden brightness changes"""
        brightness = metrics.get('brightness_mean', 0.0)
        
        if brightness > 50.0 or brightness < 10.0:
            return DetectedIssue(
                issue_type='flash_bang',
                description=f'Extreme brightness detected: {brightness:.1f}',
                first_occurrence=timestamp,
                last_occurrence=timestamp,
                frame_ids=[frame_id],
                severity='medium',
                context={'brightness': brightness},
            )
        return None
    
    def _check_low_complexity(
        self,
        frame_id: int,
        timestamp: float,
        metrics: Dict[str, Any],
        game_state: Optional[Dict[str, Any]]
    ) -> Optional[DetectedIssue]:
        """Check for unusually low visual complexity"""
        complexity = metrics.get('complexity_score', 1.0)
        edge_density = metrics.get('edge_density', 0.0)
        
        if complexity < 0.1 and edge_density < 0.05:
            return DetectedIssue(
                issue_type='low_complexity',
                description=f'Very low visual complexity: {complexity:.3f}',
                first_occurrence=timestamp,
                last_occurrence=timestamp,
                frame_ids=[frame_id],
                severity='low',
                context={'complexity': complexity, 'edge_density': edge_density},
            )
        return None
    
    def _add_issue(self, issue: DetectedIssue):
        """Add or merge an issue"""
        # Try to merge with existing issue of same type
        for existing in self._issues:
            if existing.issue_type == issue.issue_type:
                if issue.first_occurrence - existing.last_occurrence < 1.0:
                    # Merge into existing issue
                    existing.last_occurrence = issue.last_occurrence
                    existing.frame_ids.extend(issue.frame_ids)
                    existing.context.update(issue.context)
                    return
        
        # Add as new issue
        self._issues.append(issue)
    
    def get_issues(self) -> List[DetectedIssue]:
        """Get all detected issues"""
        return self._issues.copy()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get issue detection summary"""
        by_type = {}
        for issue in self._issues:
            if issue.issue_type not in by_type:
                by_type[issue.issue_type] = []
            by_type[issue.issue_type].append(issue)
        
        critical_count = sum(1 for i in self._issues if i.severity == 'critical')
        high_count = sum(1 for i in self._issues if i.severity == 'high')
        
        return {
            'total_issues': len(self._issues),
            'critical_issues': critical_count,
            'high_issues': high_count,
            'issues_by_type': {k: len(v) for k, v in by_type.items()},
            'unique_issue_types': list(by_type.keys()),
        }
    
    def reset(self):
        """Reset all detection state"""
        self._issues = []
        self._pending_frames = {}


class SummaryGenerator:
    """Generate agent-friendly summary.md reports"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize summary generator.
        
        Args:
            output_dir: Directory to write summary.md
                       If None, uses current working directory
        """
        self.output_dir = output_dir or Path.cwd()
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(
        self,
        session_summary: Dict[str, Any],
        clustering_summary: Dict[str, Any],
        issues: List[DetectedIssue],
        representative_frames: List[Tuple[int, float]],
        screenshots: Optional[Dict[int, str]] = None,
    ) -> Path:
        """
        Generate summary.md report.
        
        Args:
            session_summary: From AnalysisSession.get_summary()
            clustering_summary: From FrameClusterer.get_summary()
            issues: List of DetectedIssue
            representative_frames: List of (frame_id, timestamp) tuples
            screenshots: Optional mapping of frame_id -> screenshot path
            
        Returns:
            Path to generated summary.md
        """
        lines = []
        
        # Header
        lines.append("# Dev Probe Session Summary")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Status line (critical for agents)
        status = "OK"
        if any(i.severity == 'critical' for i in issues):
            status = "CRITICAL_ISSUES_FOUND"
        elif any(i.severity == 'high' for i in issues):
            status = "HIGH_ISSUES_FOUND"
        
        lines.append(f"**Status:** {status}")
        lines.append("")
        
        # Quick stats
        lines.append("## Quick Stats")
        lines.append("")
        lines.append(f"- **Total Frames:** {session_summary.get('total_frames', 0)}")
        lines.append(f"- **Duration:** {session_summary.get('duration_seconds', 0):.1f}s")
        lines.append(f"- **Unique Visual States:** {clustering_summary.get('total_clusters', 0)}")
        lines.append(f"- **Compression Ratio:** {clustering_summary.get('compression_ratio', 0):.1f}x")
        lines.append(f"- **Blank Frames:** {session_summary.get('blank_frames', 0)} ({session_summary.get('blank_percentage', 0):.1f}%)")
        lines.append("")
        
        # Issues section
        lines.append("## Detected Issues")
        lines.append("")
        
        if not issues:
            lines.append("✅ No issues detected")
        else:
            critical = [i for i in issues if i.severity == 'critical']
            high = [i for i in issues if i.severity == 'high']
            medium = [i for i in issues if i.severity == 'medium']
            low = [i for i in issues if i.severity == 'low']
            
            if critical:
                lines.append(f"### 🚨 Critical ({len(critical)})")
                for issue in critical[:5]:  # Limit to 5 per severity
                    lines.append(f"- **{issue.issue_type}**: {issue.description}")
                    lines.append(f"  - Frames: {issue.frame_ids[0]} to {issue.frame_ids[-1]}")
                    lines.append(f"  - Duration: {issue.last_occurrence - issue.first_occurrence:.2f}s")
                if len(critical) > 5:
                    lines.append(f"- ... and {len(critical) - 5} more critical issues")
                lines.append("")
            
            if high:
                lines.append(f"### ⚠️ High ({len(high)})")
                for issue in high[:5]:
                    lines.append(f"- **{issue.issue_type}**: {issue.description}")
                lines.append("")
            
            if medium:
                lines.append(f"### 🔶 Medium ({len(medium)})")
                for issue in medium[:5]:
                    lines.append(f"- **{issue.issue_type}**: {issue.description}")
                lines.append("")
            
            if low:
                lines.append(f"### 🔹 Low ({len(low)})")
                for issue in low[:5]:
                    lines.append(f"- **{issue.issue_type}**: {issue.description}")
                lines.append("")
        
        # Representative frames
        lines.append("## Representative Frames")
        lines.append("")
        lines.append("Visually unique frames selected for agent review:")
        lines.append("")
        
        for i, (frame_id, timestamp) in enumerate(representative_frames[:20], 1):
            screenshot_path = screenshots.get(frame_id) if screenshots else None
            if screenshot_path:
                lines.append(f"{i}. Frame #{frame_id} @ {timestamp:.2f}s - `![screenshot]({screenshot_path})`")
            else:
                lines.append(f"{i}. Frame #{frame_id} @ {timestamp:.2f}s")
        
        if len(representative_frames) > 20:
            lines.append(f"... and {len(representative_frames) - 20} more frames")
        
        lines.append("")
        
        # Clustering details
        lines.append("## Clustering Details")
        lines.append("")
        lines.append(f"- Total clusters: {clustering_summary.get('total_clusters', 0)}")
        lines.append(f"- Average cluster size: {clustering_summary.get('avg_cluster_size', 0):.1f} frames")
        lines.append(f"- Largest cluster: {clustering_summary.get('max_cluster_size', 0)} frames")
        lines.append("")
        
        # Recommendations
        lines.append("## Recommendations")
        lines.append("")
        
        if status == "OK":
            lines.append("✅ Session completed successfully. No action required.")
        elif status == "CRITICAL_ISSUES_FOUND":
            lines.append("🚨 **Immediate action required:**")
            lines.append("1. Review critical issues above")
            lines.append("2. Check render pipeline for blackout causes")
            lines.append("3. Verify entity rendering logic")
        elif status == "HIGH_ISSUES_FOUND":
            lines.append("⚠️ **Investigation recommended:**")
            lines.append("1. Review high-severity issues")
            lines.append("2. Check for game logic freezes")
            lines.append("3. Profile performance if motion issues persist")
        
        lines.append("")
        
        # Write file
        content = "\n".join(lines)
        output_path = self.output_dir / "summary.md"
        output_path.write_text(content, encoding='utf-8')
        
        logger.info(f"Generated summary.md at {output_path}")
        return output_path
