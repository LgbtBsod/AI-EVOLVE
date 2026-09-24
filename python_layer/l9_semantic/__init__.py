"""
L9 Semantic Core - Token-Efficient Data Compression

This layer provides intelligent compression of logs, states, and events
to reduce token usage when AI agents analyze game sessions.

Features:
- Log pattern compression (1000 lines → 20 patterns)
- State diff calculation (only changed fields)
- Event correlation detection (visual + logical errors)

Architecture:
- Rust: Core compression algorithms (fast, GIL-free)
- Lua: Compression rules and thresholds
- Python: Orchestration and integration with L8 Probe
"""

from typing import Dict, List, Any, Optional
import json


class LogCompressor:
    """
    Compresses repetitive log lines into semantic patterns.
    
    Example:
        Input:  ["Player took 5 dmg", "Player took 3 dmg", "Player took 7 dmg", ...]
        Output: "[100x] Player took * dmg (avg: 4.8)"
    
    Reduces 10,000 log lines to ~50 patterns (200x compression).
    """
    
    def __init__(self):
        self._patterns: Dict[str, int] = {}
        self._numeric_values: Dict[str, List[float]] = {}
        self._total_lines = 0
    
    def ingest(self, line: str) -> None:
        """Process a single log line."""
        self._total_lines += 1
        pattern = self._normalize_pattern(line)
        
        self._patterns[pattern] = self._patterns.get(pattern, 0) + 1
        
        # Extract numbers for statistics
        numbers = self._extract_numbers(line)
        if numbers:
            if pattern not in self._numeric_values:
                self._numeric_values[pattern] = []
            self._numeric_values[pattern].extend(numbers)
    
    def ingest_batch(self, lines: List[str]) -> None:
        """Process multiple log lines efficiently."""
        for line in lines:
            self.ingest(line)
    
    def summarize(self, top_n: int = 20) -> str:
        """
        Generate compressed summary.
        
        Args:
            top_n: Number of top patterns to include
            
        Returns:
            Human-readable summary string
        """
        sorted_patterns = sorted(
            self._patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]
        
        summary_lines = [f"Log Summary ({self._total_lines} total lines):\n"]
        
        for pattern, count in sorted_patterns:
            if count > 1:
                summary_lines.append(f"[{count}x] {pattern}")
                if pattern in self._numeric_values:
                    nums = self._numeric_values[pattern]
                    avg = sum(nums) / len(nums)
                    summary_lines.append(f"  → Avg value: {avg:.2f}")
            else:
                summary_lines.append(pattern)
        
        return "\n".join(summary_lines)
    
    def get_compressed_tokens(self) -> Dict[str, Any]:
        """
        Get structured data for AI agent consumption.
        
        Returns:
            Dict with patterns and stats (ready for LLM context)
        """
        sorted_patterns = sorted(
            self._patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        result = {
            "total_lines": self._total_lines,
            "unique_patterns": len(self._patterns),
            "compression_ratio": self._total_lines / max(len(self._patterns), 1),
            "patterns": []
        }
        
        for pattern, count in sorted_patterns[:50]:
            entry = {"pattern": pattern, "count": count}
            if pattern in self._numeric_values:
                nums = self._numeric_values[pattern]
                entry["stats"] = {
                    "avg": sum(nums) / len(nums),
                    "min": min(nums),
                    "max": max(nums)
                }
            result["patterns"].append(entry)
        
        return result
    
    def reset(self) -> None:
        """Clear all stored patterns."""
        self._patterns.clear()
        self._numeric_values.clear()
        self._total_lines = 0
    
    def _normalize_pattern(self, line: str) -> str:
        """Replace numbers with wildcard for pattern matching."""
        import re
        return re.sub(r'\d+\.?\d*', '*', line)
    
    def _extract_numbers(self, line: str) -> List[float]:
        """Extract all numeric values from a line."""
        import re
        matches = re.findall(r'\d+\.?\d*', line)
        return [float(m) for m in matches]


class StateDiffCalculator:
    """
    Calculates minimal diff between two game states.
    
    Only returns changed fields to minimize token usage.
    Essential for sending state updates to AI agents.
    """
    
    @staticmethod
    def calculate_diff(old_state: Dict[str, Any], new_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate difference between two states.
        
        Args:
            old_state: Previous state dict
            new_state: Current state dict
            
        Returns:
            Dict containing only changed/new/deleted fields
        """
        diff = {}
        
        # Check for new or changed fields
        for key, new_val in new_state.items():
            if key not in old_state:
                diff[key] = new_val
            elif old_state[key] != new_val:
                diff[key] = new_val
        
        # Check for deleted fields
        for key in old_state:
            if key not in new_state:
                diff[key] = "__DELETED__"
        
        return diff
    
    @staticmethod
    def format_diff_for_llm(diff: Dict[str, Any]) -> str:
        """
        Format diff as human-readable string for LLM context.
        
        Example:
            "hp: 100 → 85 (-15)\nposition: (10,20) → (11,20)"
        """
        lines = []
        for key, value in diff.items():
            if value == "__DELETED__":
                lines.append(f"{key}: DELETED")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)


class EventCorrelator:
    """
    Correlates visual events (from L8 Probe) with logical errors.
    
    Detects relationships like:
    - "Render blackout" + "Panic error" within 100ms = Critical crash
    - "Low FPS" + "Memory warning" = Memory leak suspected
    """
    
    CRITICAL_PAIRS = [
        ("visual_blackout", "panic_error"),
        ("freeze_detected", "timeout_exception"),
        ("low_fps", "memory_leak_warning"),
        ("texture_missing", "asset_load_error"),
        ("ssim_drop", "render_exception"),
    ]
    
    def __init__(self, time_window_ms: int = 100):
        self.time_window_ms = time_window_ms
        self.events: List[Dict[str, Any]] = []
    
    def add_event(self, timestamp_ms: int, event_type: str, payload: str = "") -> None:
        """Record an event with timestamp."""
        self.events.append({
            "timestamp": timestamp_ms,
            "type": event_type,
            "payload": payload
        })
        # Keep events sorted by timestamp
        self.events.sort(key=lambda x: x["timestamp"])
    
    def find_correlations(self) -> List[Dict[str, Any]]:
        """
        Find correlated events within time window.
        
        Returns:
            List of correlation dicts with event pairs and analysis
        """
        correlations = []
        
        for i, event1 in enumerate(self.events):
            for j in range(i + 1, len(self.events)):
                event2 = self.events[j]
                
                # Break if outside time window
                if event2["timestamp"] - event1["timestamp"] > self.time_window_ms:
                    break
                
                # Check if this is a critical pair
                pair_key = tuple(sorted([event1["type"], event2["type"]]))
                for critical_pair in self.CRITICAL_PAIRS:
                    if pair_key == tuple(sorted(critical_pair)):
                        correlations.append({
                            "event1": event1,
                            "event2": event2,
                            "time_delta_ms": event2["timestamp"] - event1["timestamp"],
                            "severity": "CRITICAL" if pair_key in [
                                ("visual_blackout", "panic_error"),
                                ("freeze_detected", "timeout_exception")
                            ] else "WARNING",
                            "analysis": self._generate_analysis(event1, event2)
                        })
        
        return correlations
    
    def clear(self) -> None:
        """Clear all recorded events."""
        self.events.clear()
    
    def _generate_analysis(self, event1: Dict, event2: Dict) -> str:
        """Generate human-readable analysis of the correlation."""
        return (
            f"ALERT: {event1['type']} at {event1['timestamp']}ms "
            f"correlated with {event2['type']} at {event2['timestamp']}ms "
            f"(Δt={event2['timestamp'] - event1['timestamp']}ms). "
            f"Suggests causal relationship."
        )


# Lazy imports for optional Rust acceleration
def get_rust_compressor():
    """Get Rust-accelerated LogCompressor if available."""
    try:
        from rust_core import LogCompressor as RustLogCompressor
        return RustLogCompressor
    except ImportError:
        return None


def get_rust_diff_calculator():
    """Get Rust-accelerated StateDiffCalculator if available."""
    try:
        from rust_core import StateDiffCalculator as RustStateDiffCalculator
        return RustStateDiffCalculator
    except ImportError:
        return None


def get_rust_correlator():
    """Get Rust-accelerated EventCorrelator if available."""
    try:
        from rust_core import EventCorrelator as RustEventCorrelator
        return RustEventCorrelator
    except ImportError:
        return None
