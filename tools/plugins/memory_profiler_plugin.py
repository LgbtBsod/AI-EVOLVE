"""
Plugin for AI-EVOLVE Dev Probe: Memory Profiler
Purpose: Track memory usage during test runs to detect leaks and optimize resource usage.
"""

import gc
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path
import json

try:
    import tracemalloc
    TRACEMALLOC_AVAILABLE = True
except ImportError:
    TRACEMALLOC_AVAILABLE = False


@dataclass
class MemorySnapshot:
    """Snapshot of memory usage at a point in time."""
    timestamp: float
    elapsed: float
    current_mb: float
    peak_mb: float
    object_counts: Dict[str, int] = field(default_factory=dict)
    top_allocations: List[Dict[str, Any]] = field(default_factory=list)


class MemoryProfilerPlugin:
    """Plugin for profiling memory usage during dev probe runs."""
    
    def __init__(self, probe_instance, track_objects: bool = True):
        self.probe = probe_instance
        self.track_objects = track_objects
        self.snapshots: List[MemorySnapshot] = []
        self.start_time = None
        self.baseline_memory = 0
        self.leak_detected = False
        self.leak_threshold_mb = 50  # MB growth considered a leak
        
        if TRACEMALLOC_AVAILABLE:
            tracemalloc.start(25)  # Store 25 frames
        
        self._register_hooks()
        
    def _register_hooks(self):
        """Register event hooks with the probe."""
        if hasattr(self.probe, 'register_hook'):
            self.probe.register_hook('session_start', self._on_session_start)
            self.probe.register_hook('sample_tick', self._on_sample_tick)
            self.probe.register_hook('session_end', self._on_session_end)
    
    def _on_session_start(self, data: Dict[str, Any]):
        """Initialize memory tracking at session start."""
        self.start_time = time.time()
        self.snapshots.clear()
        gc.collect()
        
        if TRACEMALLOC_AVAILABLE:
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')[:10]
            self.baseline_memory = sum(stat.size for stat in top_stats) / 1024 / 1024
    
    def _on_sample_tick(self, data: Dict[str, Any]):
        """Capture memory snapshot on each sample tick."""
        elapsed = data.get('elapsed', 0.0)
        
        gc.collect()
        current_mb = self._get_current_memory_mb()
        peak_mb = self._get_peak_memory_mb()
        
        object_counts = {}
        if self.track_objects:
            object_counts = self._count_objects_by_type()
        
        top_allocations = []
        if TRACEMALLOC_AVAILABLE:
            top_allocations = self._get_top_allocations(5)
        
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            elapsed=elapsed,
            current_mb=current_mb,
            peak_mb=peak_mb,
            object_counts=object_counts,
            top_allocations=top_allocations
        )
        
        self.snapshots.append(snapshot)
        
        # Check for memory leak
        if len(self.snapshots) > 10:
            recent_growth = snapshot.current_mb - self.snapshots[-10].current_mb
            if recent_growth > self.leak_threshold_mb:
                self.leak_detected = True
                print(f"⚠️  MEMORY LEAK DETECTED: {recent_growth:.2f} MB growth in last 10 samples")
    
    def _on_session_end(self, data: Dict[str, Any]):
        """Generate memory profile report at session end."""
        self._generate_report()
        
        if TRACEMALLOC_AVAILABLE:
            tracemalloc.stop()
    
    def _get_current_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        if TRACEMALLOC_AVAILABLE:
            current, peak = tracemalloc.get_traced_memory()
            return current / 1024 / 1024
        
        # Fallback: try to use psutil if available
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0
    
    def _get_peak_memory_mb(self) -> float:
        """Get peak memory usage in MB."""
        if TRACEMALLOC_AVAILABLE:
            current, peak = tracemalloc.get_traced_memory()
            return peak / 1024 / 1024
        return 0.0
    
    def _count_objects_by_type(self) -> Dict[str, int]:
        """Count objects by type in garbage collector."""
        counts = {}
        for obj in gc.get_objects():
            type_name = type(obj).__name__
            counts[type_name] = counts.get(type_name, 0) + 1
        
        # Return top 20 most common types
        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:20]
        return dict(sorted_counts)
    
    def _get_top_allocations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top memory allocations by size."""
        if not TRACEMALLOC_AVAILABLE:
            return []
        
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')[:limit]
        
        return [
            {
                'file': str(stat.traceback),
                'size_kb': round(stat.size / 1024, 2),
                'count': stat.count
            }
            for stat in top_stats
        ]
    
    def _generate_report(self):
        """Generate memory profiling report."""
        if not self.snapshots:
            print("📊 MEMORY PROFILER: No data collected")
            return
        
        final_snapshot = self.snapshots[-1]
        total_growth = final_snapshot.current_mb - self.baseline_memory
        
        report = {
            'baseline_memory_mb': round(self.baseline_memory, 2),
            'final_memory_mb': round(final_snapshot.current_mb, 2),
            'peak_memory_mb': round(final_snapshot.peak_mb, 2),
            'total_growth_mb': round(total_growth, 2),
            'leak_detected': self.leak_detected,
            'samples_count': len(self.snapshots),
            'top_object_types': final_snapshot.object_counts,
            'top_allocations': final_snapshot.top_allocations,
        }
        
        # Save report
        report_path = Path('tools/memory_reports')
        report_path.mkdir(exist_ok=True)
        
        timestamp = int(time.time())
        report_file = report_path / f'memory_profile_{timestamp}.json'
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📊 MEMORY PROFILE REPORT: {report_file}")
        print(f"   Baseline: {self.baseline_memory:.2f} MB")
        print(f"   Final: {final_snapshot.current_mb:.2f} MB")
        print(f"   Peak: {final_snapshot.peak_mb:.2f} MB")
        print(f"   Growth: {total_growth:.2f} MB")
        print(f"   Leak Detected: {'⚠️ YES' if self.leak_detected else '✅ NO'}")
        
        return report
    
    def get_stats(self) -> Dict[str, Any]:
        """Return current memory stats."""
        if not self.snapshots:
            return {'status': 'no_data'}
        
        latest = self.snapshots[-1]
        return {
            'current_mb': round(latest.current_mb, 2),
            'peak_mb': round(latest.peak_mb, 2),
            'growth_mb': round(latest.current_mb - self.baseline_memory, 2),
            'leak_detected': self.leak_detected,
            'samples': len(self.snapshots)
        }


def register_plugin(probe_instance):
    """Register the plugin with the probe."""
    plugin = MemoryProfilerPlugin(probe_instance)
    print("✅ MemoryProfilerPlugin registered successfully")
    return plugin


if __name__ == "__main__":
    print("Running MemoryProfilerPlugin self-test...")
    
    class MockProbe:
        def __init__(self):
            self.hooks = {}
        
        def register_hook(self, event, callback):
            if event not in self.hooks:
                self.hooks[event] = []
            self.hooks[event].append(callback)
    
    mock_probe = MockProbe()
    plugin = MemoryProfilerPlugin(mock_probe, track_objects=False)
    
    # Simulate session
    plugin._on_session_start({'test': True})
    time.sleep(0.1)
    plugin._on_sample_tick({'elapsed': 1.0})
    time.sleep(0.1)
    plugin._on_sample_tick({'elapsed': 2.0})
    plugin._on_session_end({})
    
    stats = plugin.get_stats()
    print(f"✅ Self-test PASSED - Stats: {stats}")
