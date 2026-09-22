"""
Plugin: SessionStateCache
Purpose: Reduce token usage by caching entity states and providing diffs instead of full dumps.
Author: Core Lead Game Designer (AI Agent)
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import hashlib
import json
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

@dataclass
class CachedEntityState:
    """Snapshot of an entity's critical state."""
    entity_id: int
    hash_signature: str
    data_snapshot: Dict[str, Any]
    timestamp: float = 0.0

class SessionStateCache:
    """
    Caches entity states to minimize data sent to LLM agents.
    Only returns changed fields (diffs) to save tokens.
    """
    
    def __init__(self, ttl_seconds: float = 5.0):
        self.cache: Dict[int, CachedEntityState] = {}
        self.ttl = ttl_seconds
        self.hit_count = 0
        self.miss_count = 0
        self.tokens_saved_estimate = 0
        
    def _compute_hash(self, data: Dict[str, Any]) -> str:
        """Create a quick hash of significant state fields."""
        # Only hash gameplay-critical fields, ignore visual/rendering noise
        significant_data = {
            k: v for k, v in data.items() 
            if k in ['health', 'mana', 'status_effects', 'position', 'state', 'target_id']
        }
        serialized = json.dumps(significant_data, sort_keys=True, default=str)
        return hashlib.md5(serialized.encode()).hexdigest()
        
    def get_state_diff(self, entity_id: int, current_data: Dict[str, Any], current_time: float) -> Optional[Dict[str, Any]]:
        """
        Compare current state with cached state.
        Returns None if no significant change (agent can skip processing).
        Returns diff dict if changes detected.
        """
        current_hash = self._compute_hash(current_data)
        
        if entity_id in self.cache:
            cached = self.cache[entity_id]
            if cached.hash_signature == current_hash:
                self.hit_count += 1
                return None  # No change, save tokens
            
            # Change detected
            self.miss_count += 1
            diff = self._calculate_diff(cached.data_snapshot, current_data)
            self.tokens_saved_estimate += len(json.dumps(cached.data_snapshot)) // 4 # Approx char to token ratio
            
            # Update cache
            self.cache[entity_id] = CachedEntityState(
                entity_id=entity_id,
                hash_signature=current_hash,
                data_snapshot=current_data.copy(),
                timestamp=current_time
            )
            return diff
        
        # New entity or cache miss
        self.miss_count += 1
        self.cache[entity_id] = CachedEntityState(
            entity_id=entity_id,
            hash_signature=current_hash,
            data_snapshot=current_data.copy(),
            timestamp=current_time
        )
        return current_data  # Return full state for new entities
        
    def _calculate_diff(self, old_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a minimal diff object."""
        diff = {}
        all_keys = set(old_data.keys()) | set(new_data.keys())
        
        for key in all_keys:
            old_val = old_data.get(key)
            new_val = new_data.get(key)
            
            if old_val != new_val:
                diff[key] = new_val
                
        return diff
        
    def get_stats(self) -> Dict[str, Any]:
        """Return cache performance metrics."""
        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total * 100) if total > 0 else 0
        return {
            "cache_hits": self.hit_count,
            "cache_misses": self.miss_count,
            "hit_rate_percent": round(hit_rate, 2),
            "estimated_tokens_saved": self.tokens_saved_estimate,
            "cached_entities_count": len(self.cache)
        }
        
    def clear(self):
        """Clear cache for new session."""
        self.cache.clear()
        self.hit_count = 0
        self.miss_count = 0
        self.tokens_saved_estimate = 0

# Self-test block
if __name__ == "__main__":
    print("Running SessionStateCache self-test...")
    cache = SessionStateCache()
    
    entity_1 = {"health": 100, "mana": 50, "position": (0,0,0), "state": "IDLE", "render_info": "noise"}
    
    # First call (Miss)
    diff1 = cache.get_state_diff(1, entity_1, 0.0)
    assert diff1 is not None, "First call should return full state"
    assert diff1 == entity_1, "First call should return exact data"
    
    # Second call with same data (Hit)
    diff2 = cache.get_state_diff(1, entity_1, 0.1)
    assert diff2 is None, "Unchanged state should return None"
    
    # Third call with changed health (Miss + Diff)
    entity_1_changed = entity_1.copy()
    entity_1_changed["health"] = 90
    diff3 = cache.get_state_diff(1, entity_1_changed, 0.2)
    assert diff3 is not None, "Changed state should return diff"
    assert "health" in diff3, "Diff should contain health"
    assert diff3["health"] == 90, "Diff value should be correct"
    assert "render_info" not in diff3, "Diff should not contain unchanged fields"
    
    stats = cache.get_stats()
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 2
    
    print("✅ SessionStateCache self-test PASSED")
    print(f"Stats: {stats}")
