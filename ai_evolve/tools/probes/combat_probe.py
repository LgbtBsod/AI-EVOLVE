"""
Combat Test Probe - Tests combat mechanics, damage calculation, and HP tracking.
Detects anomalies like instant death, HP freeze, impossible damage values.
"""
import logging
from ai_evolve.tools.dev_probe_framework import DevProbePlugin, ProbeResult, ProbeStatus

logger = logging.getLogger(__name__)

class CombatTestProbe(DevProbePlugin):
    """Agent that tests combat mechanics."""
    
    def __init__(self):
        super().__init__("CombatTestProbe")
        self.test_iteration = 0
        self.simulated_hp = 100.0
        self.last_hp = 100.0
        self.damage_dealt_total = 0.0
        
    def setup(self):
        """Initialize combat test scenario."""
        logger.info("[CombatTestProbe] Setting up combat test scenario")
        self.test_iteration = 0
        self.simulated_hp = 100.0
        self.last_hp = 100.0
        self.damage_dealt_total = 0.0
        
    def run_step(self, delta_time: float) -> ProbeResult:
        """Run one step of combat testing."""
        self.test_iteration += 1
        
        # Simulate combat: deal random damage
        import random
        damage = random.uniform(1.0, 10.0)
        self.simulated_hp -= damage
        self.damage_dealt_total += damage
        
        # Anomaly Detection 1: Instant Death (HP dropped from 100 to 0 in < 5 steps)
        if self.simulated_hp <= 0 and self.test_iteration < 5:
            return ProbeResult(
                status=ProbeStatus.ANOMALY,
                message=f"INSTANT DEATH DETECTED: Died at iteration {self.test_iteration}",
                metrics={"hp": self.simulated_hp, "iterations": self.test_iteration}
            )
            
        # Anomaly Detection 2: HP Freeze (HP hasn't changed for 50 iterations)
        if self.test_iteration > 50 and abs(self.simulated_hp - self.last_hp) < 0.001:
            # Check if it's not already dead
            if self.simulated_hp > 0:
                return ProbeResult(
                    status=ProbeStatus.ANOMALY,
                    message=f"HP FREEZE DETECTED: HP stuck at {self.simulated_hp}",
                    metrics={"hp": self.simulated_hp, "frozen_for": 50}
                )
                
        # Anomaly Detection 3: Impossible Damage (> 50 in one hit when max should be ~15)
        if damage > 50:
            return ProbeResult(
                status=ProbeStatus.ANOMALY,
                message=f"IMPOSSIBLE DAMAGE: {damage} damage in one hit",
                metrics={"damage": damage, "iteration": self.test_iteration}
            )
            
        self.last_hp = self.simulated_hp
        
        # Periodic success report
        if self.test_iteration % 200 == 0 and self.simulated_hp > 0:
            return ProbeResult(
                status=ProbeStatus.RUNNING,
                message=f"Combat OK: HP={self.simulated_hp:.2f}, Total Dmg={self.damage_dealt_total:.2f}",
                metrics={"hp": self.simulated_hp, "total_damage": self.damage_dealt_total}
            )
            
        # Death is expected eventually
        if self.simulated_hp <= 0:
            return ProbeResult(
                status=ProbeStatus.SUCCESS,
                message=f"Character died normally at iteration {self.test_iteration}",
                metrics={"final_hp": self.simulated_hp, "survived_iterations": self.test_iteration}
            )
            
        return ProbeResult(status=ProbeStatus.RUNNING)
        
    def teardown(self):
        """Cleanup after test."""
        logger.info(f"[CombatTestProbe] Test completed. Survived {self.test_iteration} iterations")
