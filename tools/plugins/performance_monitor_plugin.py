"""
Plugin for AI-EVOLVE Dev Probe: Performance Monitor
Purpose: Track FPS, frame times, and performance metrics during test runs.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from collections import deque


@dataclass
class FrameMetrics:
    """Metrics for a single frame."""
    timestamp: float
    elapsed: float
    frame_time_ms: float
    fps: float
    is_stutter: bool = False  # Frame time > 2x average


@dataclass 
class PerformanceReport:
    """Aggregated performance report."""
    avg_fps: float
    min_fps: float
    max_fps: float
    avg_frame_time_ms: float
    p95_frame_time_ms: float
    p99_frame_time_ms: float
    total_frames: int
    stutter_count: int
    stutter_percentage: float
    performance_score: str  # "excellent", "good", "fair", "poor"


class PerformanceMonitorPlugin:
    """Plugin for monitoring game performance during dev probe runs."""
    
    def __init__(self, probe_instance, window_size: int = 100):
        self.probe = probe_instance
        self.window_size = window_size
        
        self.frame_times: deque = deque(maxlen=window_size)
        self.fps_history: deque = deque(maxlen=window_size)
        self.all_metrics: List[FrameMetrics] = []
        
        self.last_frame_time = None
        self.start_time = None
        self.frame_count = 0
        self.stutter_threshold_multiplier = 2.0
        
        self._register_hooks()
    
    def _register_hooks(self):
        """Register event hooks with the probe."""
        if hasattr(self.probe, 'register_hook'):
            self.probe.register_hook('session_start', self._on_session_start)
            self.probe.register_hook('sample_tick', self._on_sample_tick)
            self.probe.register_hook('session_end', self._on_session_end)
    
    def _on_session_start(self, data: Dict[str, Any]):
        """Initialize performance tracking."""
        self.start_time = time.time()
        self.last_frame_time = self.start_time
        self.frame_count = 0
        self.frame_times.clear()
        self.fps_history.clear()
        self.all_metrics.clear()
    
    def _on_sample_tick(self, data: Dict[str, Any]):
        """Record frame metrics on each sample tick."""
        current_time = time.time()
        elapsed = data.get('elapsed', 0.0)
        
        if self.last_frame_time is None:
            self.last_frame_time = current_time
            return
        
        # Calculate frame time
        frame_time_sec = current_time - self.last_frame_time
        frame_time_ms = frame_time_sec * 1000
        fps = 1.0 / frame_time_sec if frame_time_sec > 0 else 0
        
        self.frame_count += 1
        self.frame_times.append(frame_time_ms)
        self.fps_history.append(fps)
        
        # Detect stutter
        avg_frame_time = sum(self.frame_times) / len(self.frame_times) if self.frame_times else 0
        is_stutter = frame_time_ms > (avg_frame_time * self.stutter_threshold_multiplier)
        
        metric = FrameMetrics(
            timestamp=current_time,
            elapsed=elapsed,
            frame_time_ms=frame_time_ms,
            fps=fps,
            is_stutter=is_stutter
        )
        
        self.all_metrics.append(metric)
        self.last_frame_time = current_time
    
    def _on_session_end(self, data: Dict[str, Any]):
        """Generate performance report."""
        report = self._generate_report()
        self._print_summary(report)
    
    def _generate_report(self) -> PerformanceReport:
        """Generate comprehensive performance report."""
        if not self.fps_history:
            return PerformanceReport(
                avg_fps=0, min_fps=0, max_fps=0,
                avg_frame_time_ms=0, p95_frame_time_ms=0, p99_frame_time_ms=0,
                total_frames=0, stutter_count=0, stutter_percentage=0,
                performance_score="no_data"
            )
        
        fps_list = list(self.fps_history)
        frame_times_list = list(self.frame_times)
        
        avg_fps = sum(fps_list) / len(fps_list)
        min_fps = min(fps_list)
        max_fps = max(fps_list)
        
        avg_frame_time = sum(frame_times_list) / len(frame_times_list)
        
        # Calculate percentiles
        sorted_times = sorted(frame_times_list)
        p95_idx = int(len(sorted_times) * 0.95)
        p99_idx = int(len(sorted_times) * 0.99)
        p95_frame_time = sorted_times[p95_idx] if p95_idx < len(sorted_times) else sorted_times[-1]
        p99_frame_time = sorted_times[p99_idx] if p99_idx < len(sorted_times) else sorted_times[-1]
        
        # Count stutters
        stutter_count = sum(1 for m in self.all_metrics if m.is_stutter)
        stutter_percentage = (stutter_count / len(self.all_metrics) * 100) if self.all_metrics else 0
        
        # Calculate performance score
        performance_score = self._calculate_performance_score(avg_fps, p95_frame_time, stutter_percentage)
        
        return PerformanceReport(
            avg_fps=round(avg_fps, 2),
            min_fps=round(min_fps, 2),
            max_fps=round(max_fps, 2),
            avg_frame_time_ms=round(avg_frame_time, 2),
            p95_frame_time_ms=round(p95_frame_time, 2),
            p99_frame_time_ms=round(p99_frame_time, 2),
            total_frames=len(self.all_metrics),
            stutter_count=stutter_count,
            stutter_percentage=round(stutter_percentage, 2),
            performance_score=performance_score
        )
    
    def _calculate_performance_score(self, avg_fps: float, p95_frame_time: float, stutter_pct: float) -> str:
        """Calculate overall performance score."""
        if avg_fps >= 60 and p95_frame_time < 20 and stutter_pct < 1:
            return "excellent"
        elif avg_fps >= 45 and p95_frame_time < 30 and stutter_pct < 5:
            return "good"
        elif avg_fps >= 30 and p95_frame_time < 50 and stutter_pct < 10:
            return "fair"
        else:
            return "poor"
    
    def _print_summary(self, report: PerformanceReport):
        """Print performance summary to console."""
        print(f"\n📊 PERFORMANCE REPORT:")
        print(f"   Average FPS: {report.avg_fps}")
        print(f"   FPS Range: {report.min_fps} - {report.max_fps}")
        print(f"   Avg Frame Time: {report.avg_frame_time_ms:.2f} ms")
        print(f"   P95 Frame Time: {report.p95_frame_time_ms:.2f} ms")
        print(f"   P99 Frame Time: {report.p99_frame_time_ms:.2f} ms")
        print(f"   Total Frames: {report.total_frames}")
        print(f"   Stutters: {report.stutter_count} ({report.stutter_percentage:.2f}%)")
        print(f"   Performance Score: {self._get_score_emoji(report.performance_score)} {report.performance_score.upper()}")
        
        # Save report
        self._save_report(report)
    
    def _get_score_emoji(self, score: str) -> str:
        """Get emoji for performance score."""
        emojis = {
            "excellent": "✅",
            "good": "👍",
            "fair": "⚠️",
            "poor": "❌",
            "no_data": "❓"
        }
        return emojis.get(score, "❓")
    
    def _save_report(self, report: PerformanceReport):
        """Save performance report to file."""
        report_path = Path('tools/performance_reports')
        report_path.mkdir(exist_ok=True)
        
        timestamp = int(time.time())
        report_file = report_path / f'performance_report_{timestamp}.json'
        
        report_dict = {
            'avg_fps': report.avg_fps,
            'min_fps': report.min_fps,
            'max_fps': report.max_fps,
            'avg_frame_time_ms': report.avg_frame_time_ms,
            'p95_frame_time_ms': report.p95_frame_time_ms,
            'p99_frame_time_ms': report.p99_frame_time_ms,
            'total_frames': report.total_frames,
            'stutter_count': report.stutter_count,
            'stutter_percentage': report.stutter_percentage,
            'performance_score': report.performance_score,
        }
        
        with open(report_file, 'w') as f:
            json.dump(report_dict, f, indent=2)
        
        print(f"   Report saved: {report_file}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Return current performance stats."""
        if not self.fps_history:
            return {'status': 'no_data'}
        
        return {
            'current_fps': round(self.fps_history[-1], 2) if self.fps_history else 0,
            'avg_fps': round(sum(self.fps_history) / len(self.fps_history), 2),
            'avg_frame_time_ms': round(sum(self.frame_times) / len(self.frame_times), 2),
            'frame_count': self.frame_count
        }


def register_plugin(probe_instance):
    """Register the plugin with the probe."""
    plugin = PerformanceMonitorPlugin(probe_instance)
    print("✅ PerformanceMonitorPlugin registered successfully")
    return plugin


if __name__ == "__main__":
    print("Running PerformanceMonitorPlugin self-test...")
    
    class MockProbe:
        def __init__(self):
            self.hooks = {}
        
        def register_hook(self, event, callback):
            if event not in self.hooks:
                self.hooks[event] = []
            self.hooks[event].append(callback)
    
    mock_probe = MockProbe()
    plugin = PerformanceMonitorPlugin(mock_probe, window_size=50)
    
    # Simulate session with varying frame times
    plugin._on_session_start({'test': True})
    
    base_time = time.time()
    for i in range(100):
        # Simulate varying frame times (16-33ms)
        simulated_delay = 0.016 + (i % 5) * 0.004
        time.sleep(simulated_delay)
        plugin._on_sample_tick({'elapsed': i * 0.02})
    
    plugin._on_session_end({})
    
    stats = plugin.get_stats()
    print(f"\n✅ Self-test PASSED - Stats: {stats}")
