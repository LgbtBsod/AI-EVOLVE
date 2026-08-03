"""
Adaptive Anticipation System - Predictive AI Defense
AI learns player attack patterns and adapts defensive behavior.
Implements machine learning-based prediction for dodging, blocking, and countering.
"""
import logging
import time
import random
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.event_system import EventSystem, Event


class AttackPattern(Enum):
    MELEE_RUSH = "melee_rush"
    RANGED_SNIPER = "ranged_sniper"
    AREA_BOMBARDMENT = "area_bombardment"
    STEALTH_FLANK = "stealth_flank"
    COMBO_ASSAULT = "combo_assault"


@dataclass
class PatternRecord:
    pattern_type: AttackPattern
    timestamp: float
    success: bool  # Did the attack succeed?
    player_position: Tuple[float, float]
    ai_response: str
    outcome_rating: float  # -1.0 (bad for AI) to 1.0 (good for AI)


@dataclass
class AnticipationStats:
    recognized_patterns: Dict[AttackPattern, int]
    prediction_accuracy: float
    average_reaction_time: float
    counter_effectiveness: float
    adaptation_level: float  # 0.0 to 1.0


class AdaptiveAnticipationSystem(BaseComponent):
    """
    Advanced AI system that learns and predicts player attack patterns.
    
    Features:
    - Pattern recognition from combat history
    - Predictive positioning for dodging
    - Adaptive counter-strategies
    - Improves over time as more data is collected
    """
    
    def __init__(self, history_size: int = 100, learning_rate: float = 0.1):
        super().__init__(ComponentType.SYSTEM, Priority.HIGH)
        self.history_size = history_size
        self.learning_rate = learning_rate
        
        self.pattern_history: deque[PatternRecord] = deque(maxlen=history_size)
        self.pattern_weights: Dict[AttackPattern, float] = {
            p: 0.5 for p in AttackPattern
        }
        self.player_behavior_profile: Dict[str, Any] = {}
        self.reaction_times: deque[float] = deque(maxlen=50)
        
        self.stats = AnticipationStats(
            recognized_patterns={p: 0 for p in AttackPattern},
            prediction_accuracy=0.5,
            average_reaction_time=0.5,
            counter_effectiveness=0.5,
            adaptation_level=0.0
        )
        
    def on_start(self):
        logging.info("Adaptive Anticipation System initialized. Learning player patterns...")
        
    def record_encounter(
        self,
        pattern: AttackPattern,
        player_position: Tuple[float, float],
        ai_response: str,
        attack_successful: bool,
        reaction_time: float
    ):
        """Record a combat encounter for pattern analysis."""
        outcome_rating = -1.0 if attack_successful else 1.0
        
        record = PatternRecord(
            pattern_type=pattern,
            timestamp=time.time(),
            success=not attack_successful,  # Success for AI = attack blocked
            player_position=player_position,
            ai_response=ai_response,
            outcome_rating=outcome_rating
        )
        
        self.pattern_history.append(record)
        self.reaction_times.append(reaction_time)
        
        # Update pattern recognition count
        self.stats.recognized_patterns[pattern] += 1
        
        # Update pattern weight based on outcome
        old_weight = self.pattern_weights[pattern]
        new_weight = old_weight + (self.learning_rate * outcome_rating)
        self.pattern_weights[pattern] = max(0.0, min(1.0, new_weight))
        
        # Update stats
        self._recalculate_stats()
        
        logging.debug(
            f"Encounter recorded: {pattern.value}, outcome: {'blocked' if not attack_successful else 'hit'}, "
            f"reaction: {reaction_time:.3f}s"
        )
        
    def _recalculate_stats(self):
        """Recalculate anticipation statistics."""
        if len(self.pattern_history) == 0:
            return
            
        # Prediction accuracy
        successful_predictions = sum(1 for r in self.pattern_history if r.outcome_rating > 0)
        self.stats.prediction_accuracy = successful_predictions / len(self.pattern_history)
        
        # Average reaction time
        if len(self.reaction_times) > 0:
            self.stats.average_reaction_time = sum(self.reaction_times) / len(self.reaction_times)
            
        # Counter effectiveness
        effective_counters = sum(r.outcome_rating for r in self.pattern_history) / len(self.pattern_history)
        self.stats.counter_effectiveness = (effective_counters + 1) / 2  # Normalize to 0-1
        
        # Adaptation level (based on history size and accuracy)
        history_factor = min(1.0, len(self.pattern_history) / self.history_size)
        self.stats.adaptation_level = history_factor * self.stats.prediction_accuracy
        
    def predict_next_attack(self) -> Optional[AttackPattern]:
        """Predict the player's next attack pattern based on history."""
        if len(self.pattern_history) < 5:
            return None
            
        # Analyze recent patterns
        recent_patterns = list(self.pattern_history)[-10:]
        
        # Count pattern frequency in recent history
        pattern_counts = {}
        for record in recent_patterns:
            pattern = record.pattern_type
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
            
        if not pattern_counts:
            return None
            
        # Get most frequent pattern
        predicted_pattern = max(pattern_counts, key=pattern_counts.get)
        
        # Adjust by pattern weight (AI's confidence in countering this pattern)
        weight = self.pattern_weights[predicted_pattern]
        if weight < 0.3:
            # AI struggles with this pattern, might mispredict
            if random.random() < 0.3:
                # Return a different pattern
                other_patterns = [p for p in AttackPattern if p != predicted_pattern]
                predicted_pattern = random.choice(other_patterns)
                
        logging.debug(f"Predicted next attack: {predicted_pattern.value} (confidence: {weight:.2f})")
        return predicted_pattern
        
    def get_optimal_counter(self, predicted_pattern: AttackPattern) -> str:
        """Get the optimal counter-strategy for a predicted pattern."""
        counters = {
            AttackPattern.MELEE_RUSH: "backpedal_and_aoe",
            AttackPattern.RANGED_SNIPER: "take_cover_and_flank",
            AttackPattern.AREA_BOMBARDMENT: "scatter_and_close_distance",
            AttackPattern.STEALTH_FLANK: "area_scan_and_defensive_stance",
            AttackPattern.COMBO_ASSAULT: "interrupt_and_retreat"
        }
        
        base_counter = counters.get(predicted_pattern, "defensive_stance")
        
        # Adjust counter based on past success
        best_response = self._find_best_response(predicted_pattern)
        if best_response:
            return best_response
            
        return base_counter
        
    def _find_best_response(self, pattern: AttackPattern) -> Optional[str]:
        """Find the most successful historical response to a pattern."""
        successful_responses = [
            r.ai_response for r in self.pattern_history
            if r.pattern_type == pattern and r.outcome_rating > 0.5
        ]
        
        if not successful_responses:
            return None
            
        # Return most common successful response
        from collections import Counter
        counter = Counter(successful_responses)
        return counter.most_common(1)[0][0]
        
    def get_dodge_direction(self, attacker_position: Tuple[float, float], ai_position: Tuple[float, float]) -> Tuple[float, float]:
        """Calculate optimal dodge direction based on predicted attack."""
        predicted = self.predict_next_attack()
        
        if predicted is None:
            # Default: dodge perpendicular to attack vector
            dx = attacker_position[0] - ai_position[0]
            dy = attacker_position[1] - ai_position[1]
            # Perpendicular vector
            return (-dy, dx)
            
        # Pattern-specific dodge logic
        if predicted == AttackPattern.MELEE_RUSH:
            # Dodge backward and to the side
            dx = ai_position[0] - attacker_position[0]
            dy = ai_position[1] - attacker_position[1]
            return (dx * 0.7, dy * 0.7)  # Backward
            
        elif predicted == AttackPattern.AREA_BOMBARDMENT:
            # Dodge randomly but away from center
            angle = random.uniform(0, 2 * 3.14159)
            return (random.uniform(5, 10) * random.choice([-1, 1]), 
                    random.uniform(5, 10) * random.choice([-1, 1]))
                    
        elif predicted == AttackPattern.RANGED_SNIPER:
            # Dodge toward cover (simplified: just zigzag)
            return (random.uniform(-5, 5), random.uniform(-3, 3))
            
        # Default perpendicular dodge
        dx = attacker_position[0] - ai_position[0]
        dy = attacker_position[1] - ai_position[1]
        return (-dy, dx)
        
    def get_player_profile(self) -> Dict[str, Any]:
        """Get analyzed player behavior profile."""
        if len(self.pattern_history) == 0:
            return {"analysis": "insufficient_data"}
            
        # Analyze favorite patterns
        pattern_freq = self.stats.recognized_patterns
        favorite_pattern = max(pattern_freq, key=pattern_freq.get) if any(pattern_freq.values()) else None
        
        # Analyze timing preferences
        avg_reaction = self.stats.average_reaction_time
        timing_preference = "fast" if avg_reaction < 0.3 else "moderate" if avg_reaction < 0.6 else "slow"
        
        self.player_behavior_profile = {
            "favorite_pattern": favorite_pattern.value if favorite_pattern else None,
            "timing_preference": timing_preference,
            "predictability": self.stats.prediction_accuracy,
            "encounters_analyzed": len(self.pattern_history),
            "ai_adaptation_level": self.stats.adaptation_level
        }
        
        return self.player_behavior_profile
        
    def on_update(self, dt: float):
        """Periodic update for time-based analysis."""
        # Could implement decay of old patterns here
        pass
        
    def _on_update(self, delta_time: float) -> None:
        """Implementation of abstract method."""
        self.on_update(delta_time)
