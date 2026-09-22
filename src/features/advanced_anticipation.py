"""
Advanced Adaptive Anticipation System
Predicts player actions based on pattern recognition, state weighting, and historical data.
"""

import time
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

class PlayerAction(Enum):
    ATTACK_LIGHT = "attack_light"
    ATTACK_HEAVY = "attack_heavy"
    DODGE = "dodge"
    BLOCK = "block"
    HEAL = "heal"
    SKILL_USE = "skill_use"
    RETREAT = "retreat"

@dataclass
class ActionPattern:
    """Represents a detected pattern in player behavior."""
    sequence: List[PlayerAction]
    frequency: int = 0
    last_seen: float = 0.0
    success_rate: float = 0.5  # How often this pattern leads to player success

@dataclass
class PredictionResult:
    predicted_action: Optional[PlayerAction]
    confidence: float  # 0.0 to 1.0
    recommended_counter: str
    reasoning: str

class AdvancedAdaptiveAnticipation:
    """
    Advanced AI module that predicts player moves using:
    1. Short-term sequence matching (N-grams)
    2. State-based probability weighting
    3. Long-term habit tracking
    """
    
    def __init__(self, history_size: int = 20, pattern_depth: int = 3):
        self.history: deque[PlayerAction] = deque(maxlen=history_size)
        self.pattern_depth = pattern_depth
        self.known_patterns: Dict[str, ActionPattern] = {}
        
        # State weights: how likely an action is given current context
        self.state_weights: Dict[str, Dict[PlayerAction, float]] = defaultdict(
            lambda: {action: 1.0 for action in PlayerAction}
        )
        
        # Counters for frequency analysis
        self.action_counts: Dict[PlayerAction, int] = defaultdict(int)
        self.total_actions = 0
        
        # Decay factor for old patterns (0.9 = 10% decay per update)
        self.decay_factor = 0.95

    def record_action(self, action: PlayerAction, context: str = "neutral"):
        """Record a player action with optional context (e.g., 'low_health', 'distance_close')."""
        self.history.append(action)
        self.action_counts[action] += 1
        self.total_actions += 1
        
        # Update state weights based on outcome (simplified: assume action happened)
        # In full implementation, this would be updated post-engagement based on success/fail
        self._update_patterns()
        self._decay_old_data()

    def _get_pattern_key(self, sequence: List[PlayerAction]) -> str:
        return "->".join([a.value for a in sequence])

    def _update_patterns(self):
        """Analyze history to detect recurring sequences."""
        if len(self.history) < self.pattern_depth:
            return
            
        # Extract current N-gram
        current_seq = list(self.history)[-self.pattern_depth:]
        key = self._get_pattern_key(current_seq)
        
        if key in self.known_patterns:
            pattern = self.known_patterns[key]
            pattern.frequency += 1
            pattern.last_seen = time.time()
        else:
            self.known_patterns[key] = ActionPattern(sequence=current_seq, frequency=1, last_seen=time.time())
            
        # Limit pattern storage to prevent memory bloat
        if len(self.known_patterns) > 100:
            # Remove least frequent patterns
            sorted_patterns = sorted(self.known_patterns.items(), key=lambda x: x[1].frequency)
            for i in range(10): # Remove bottom 10
                if len(self.known_patterns) > 50:
                    self.known_patterns.pop(sorted_patterns[i][0], None)

    def _decay_old_data(self):
        """Apply decay to pattern relevance over time."""
        current_time = time.time()
        keys_to_remove = []
        
        for key, pattern in self.known_patterns.items():
            time_diff = current_time - pattern.last_seen
            # Decay based on time since last seen (arbitrary threshold: 60s for significant decay)
            decay = max(0.1, (1.0 - (time_diff / 120.0))) 
            pattern.frequency = int(pattern.frequency * self.decay_factor)
            
            if pattern.frequency == 0:
                keys_to_remove.append(key)
                
        for key in keys_to_remove:
            del self.known_patterns[key]

    def predict_next_action(self, context: str = "neutral") -> PredictionResult:
        """
        Predict the next player action based on history and context.
        Returns PredictionResult with confidence score and counter strategy.
        """
        if len(self.history) < 2:
            return PredictionResult(
                predicted_action=None,
                confidence=0.0,
                recommended_counter="observe",
                reasoning="Insufficient data"
            )
        
        scores: Dict[PlayerAction, float] = defaultdict(float)
        
        # 1. Pattern Matching Score (High weight if pattern found)
        recent_seq = list(self.history)[-self.pattern_depth + 1:] # Look for what comes NEXT
        best_match = None
        best_match_count = 0
        
        for key, pattern in self.known_patterns.items():
            # Check if pattern starts with our recent sequence
            pattern_seq_str = self._get_pattern_key(pattern.sequence[:-1])
            current_seq_str = self._get_pattern_key(recent_seq)
            
            if pattern_seq_str == current_seq_str:
                # Found a match! The next action in pattern is the prediction
                predicted_act = pattern.sequence[-1]
                confidence_boost = min(1.0, pattern.frequency * 0.15) # Cap at 1.0
                scores[predicted_act] += confidence_boost * 2.0 # High weight for patterns
                
                if pattern.frequency > best_match_count:
                    best_match = predicted_act
                    best_match_count = pattern.frequency

        # 2. Frequency Bias (Players tend to repeat favorite actions)
        if self.total_actions > 0:
            for action, count in self.action_counts.items():
                freq_bias = count / self.total_actions
                scores[action] += freq_bias * 0.5 # Lower weight for general frequency

        # 3. Contextual Weights (e.g., if low health, heal is more likely)
        context_multipliers = self._get_context_multipliers(context)
        for action, mult in context_multipliers.items():
            scores[action] *= mult

        # Determine winner
        if not scores:
            return PredictionResult(
                predicted_action=None,
                confidence=0.0,
                recommended_counter="standard_stance",
                reasoning="No predictive signals"
            )
            
        best_action = max(scores, key=scores.get)
        total_score = sum(scores.values())
        confidence = min(0.95, scores[best_action] / total_score) if total_score > 0 else 0.0
        
        counter = self._get_counter_strategy(best_action)
        reasoning = f"Pattern match: {best_match_count}x, Freq bias: {self.action_counts[best_action]}"
        
        return PredictionResult(
            predicted_action=best_action,
            confidence=confidence,
            recommended_counter=counter,
            reasoning=reasoning
        )

    def _get_context_multipliers(self, context: str) -> Dict[PlayerAction, float]:
        """Return multipliers for actions based on game context."""
        multipliers = {a: 1.0 for a in PlayerAction}
        
        if context == "low_health":
            multipliers[PlayerAction.HEAL] = 2.5
            multipliers[PlayerAction.RETREAT] = 2.0
            multipliers[PlayerAction.ATTACK_HEAVY] = 0.5
        elif context == "player_stunned":
            multipliers[PlayerAction.ATTACK_HEAVY] = 1.5
            multipliers[PlayerAction.SKILL_USE] = 1.2
        elif context == "distance_far":
            multipliers[PlayerAction.RETREAT] = 0.2
            multipliers[PlayerAction.SKILL_USE] = 1.3
            
        return multipliers

    def _get_counter_strategy(self, predicted_action: PlayerAction) -> str:
        """Map predicted player action to AI counter-strategy."""
        counters = {
            PlayerAction.ATTACK_LIGHT: "parry_ready",
            PlayerAction.ATTACK_HEAVY: "dodge_back",
            PlayerAction.DODGE: "delayed_attack",
            PlayerAction.BLOCK: "guard_break",
            PlayerAction.HEAL: "aggressive_rush",
            PlayerAction.SKILL_USE: "interrupt_attempt",
            PlayerAction.RETREAT: "gap_closer"
        }
        return counters.get(predicted_action, "standard_stance")

    def get_statistics(self) -> Dict[str, Any]:
        """Return stats for debugging/analysis."""
        return {
            "total_actions": self.total_actions,
            "unique_patterns": len(self.known_patterns),
            "most_frequent_action": max(self.action_counts, key=self.action_counts.get) if self.action_counts else None,
            "history_length": len(self.history)
        }
