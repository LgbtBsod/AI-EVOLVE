"""
Comprehensive Test Suite for AI Systems and Plugins
Tests behavior trees, agent analytics, and integration
"""
import unittest
import sys
import time
from typing import List, Dict, Any

# Add workspace to path
sys.path.insert(0, '/workspace')

from src.ai.behavior_tree import (
    AIAgent, create_agent, Blackboard, BTNode, 
    Action, Condition, Selector, Sequence, Repeater,
    NodeStatus, AgentState
)
from tools.plugins.ai_behavior_analyzer import (
    AIBehaviorAnalyzerPlugin, BehaviorMetrics, AgentProfile
)


class TestBehaviorTree(unittest.TestCase):
    """Test Behavior Tree components"""
    
    def test_blackboard_operations(self):
        """Test blackboard get/set/has operations"""
        bb = Blackboard()
        
        # Set and get
        bb.set("health", 100)
        self.assertEqual(bb.get("health"), 100)
        
        # Default value
        self.assertEqual(bb.get("missing", "default"), "default")
        
        # Has check
        self.assertTrue(bb.has("health"))
        self.assertFalse(bb.has("missing"))
        
        # Clear
        bb.clear()
        self.assertFalse(bb.has("health"))
    
    def test_condition_success(self):
        """Test condition node that succeeds"""
        condition = Condition("TestCondition", lambda bb: True)
        bb = Blackboard()
        
        result = condition.execute(bb)
        self.assertEqual(result, NodeStatus.SUCCESS)
    
    def test_condition_failure(self):
        """Test condition node that fails"""
        condition = Condition("TestCondition", lambda bb: False)
        bb = Blackboard()
        
        result = condition.execute(bb)
        self.assertEqual(result, NodeStatus.FAILURE)
    
    def test_action_success(self):
        """Test action node that succeeds"""
        action = Action("TestAction", lambda bb: True)
        bb = Blackboard()
        
        result = action.execute(bb)
        self.assertEqual(result, NodeStatus.SUCCESS)
    
    def test_action_failure(self):
        """Test action node that fails"""
        action = Action("TestAction", lambda bb: False)
        bb = Blackboard()
        
        result = action.execute(bb)
        self.assertEqual(result, NodeStatus.FAILURE)
    
    def test_selector_with_success(self):
        """Test selector with at least one successful child"""
        selector = Selector("TestSelector")
        selector.add_child(Condition("Fail", lambda bb: False))
        selector.add_child(Condition("Success", lambda bb: True))
        selector.add_child(Condition("NeverReached", lambda bb: True))
        
        bb = Blackboard()
        result = selector.execute(bb)
        
        self.assertEqual(result, NodeStatus.SUCCESS)
    
    def test_selector_all_fail(self):
        """Test selector where all children fail"""
        selector = Selector("TestSelector")
        selector.add_child(Condition("Fail1", lambda bb: False))
        selector.add_child(Condition("Fail2", lambda bb: False))
        
        bb = Blackboard()
        result = selector.execute(bb)
        
        self.assertEqual(result, NodeStatus.FAILURE)
    
    def test_sequence_all_success(self):
        """Test sequence where all children succeed"""
        sequence = Sequence("TestSequence")
        sequence.add_child(Action("Success1", lambda bb: True))
        sequence.add_child(Action("Success2", lambda bb: True))
        
        bb = Blackboard()
        result = sequence.execute(bb)
        
        self.assertEqual(result, NodeStatus.SUCCESS)
    
    def test_sequence_with_failure(self):
        """Test sequence with a failing child"""
        sequence = Sequence("TestSequence")
        sequence.add_child(Action("Success", lambda bb: True))
        sequence.add_child(Action("Fail", lambda bb: False))
        sequence.add_child(Action("NeverReached", lambda bb: True))
        
        bb = Blackboard()
        result = sequence.execute(bb)
        
        self.assertEqual(result, NodeStatus.FAILURE)
    
    def test_repeater_success(self):
        """Test repeater executes N times"""
        counter = {"count": 0}
        
        def increment(bb):
            counter["count"] += 1
            return True
        
        repeater = Repeater("TestRepeater", max_iterations=3)
        repeater.add_child(Action("Increment", increment))
        
        bb = Blackboard()
        result = repeater.execute(bb)
        
        self.assertEqual(result, NodeStatus.SUCCESS)
        self.assertEqual(counter["count"], 3)
    
    def test_create_agent_factory(self):
        """Test agent factory creates different types"""
        warrior = create_agent("warrior")
        mage = create_agent("mage")
        rogue = create_agent("rogue")
        
        self.assertEqual(warrior.agent_type, "warrior")
        self.assertEqual(warrior.state.health, 150.0)
        
        self.assertEqual(mage.agent_type, "mage")
        self.assertEqual(mage.state.mana, 150.0)
        
        self.assertEqual(rogue.agent_type, "rogue")
        self.assertEqual(rogue.state.stamina, 120.0)


class TestAIAgent(unittest.TestCase):
    """Test AI Agent functionality"""
    
    def test_agent_initialization(self):
        """Test agent initializes correctly"""
        agent = AIAgent("test_001", "warrior")
        
        self.assertEqual(agent.agent_id, "test_001")
        self.assertEqual(agent.agent_type, "warrior")
        self.assertIsNotNone(agent.root)
        self.assertEqual(agent.current_action, "idle")
    
    def test_agent_tick(self):
        """Test agent tick execution"""
        agent = create_agent("warrior")
        
        result = agent.tick()
        
        self.assertIsInstance(result, str)
        self.assertIn("(", result)  # Should contain status
    
    def test_agent_state_summary(self):
        """Test agent state summary"""
        agent = create_agent("rogue")
        agent.tick()
        
        summary = agent.get_state_summary()
        
        self.assertIn("agent_id", summary)
        self.assertIn("type", summary)
        self.assertIn("current_action", summary)
        self.assertIn("health", summary)
        self.assertIn("position", summary)
    
    def test_agent_action_history(self):
        """Test agent records action history"""
        agent = create_agent("warrior")
        
        # Run multiple ticks
        for _ in range(5):
            agent.tick()
        
        self.assertGreater(len(agent.action_history), 0)
    
    def test_agent_flee_behavior(self):
        """Test agent flees when health is low"""
        agent = create_agent("warrior")
        agent.state.health = 20.0  # Low health
        agent.state.enemies_nearby = True
        
        result = agent.tick()
        
        self.assertIn("fleeing", result.lower())
    
    def test_agent_combat_behavior(self):
        """Test agent engages in combat"""
        agent = create_agent("warrior")
        agent.state.health = 100.0
        agent.state.enemies_nearby = True
        
        result = agent.tick()
        
        # Should be attacking or defending
        self.assertTrue(
            "attacking" in result.lower() or 
            "defending" in result.lower() or
            "combat" in result.lower()
        )


class TestAIBehaviorAnalyzerPlugin(unittest.TestCase):
    """Test AI Behavior Analyzer Plugin"""
    
    def setUp(self):
        """Setup test fixtures"""
        self.plugin = AIBehaviorAnalyzerPlugin()
    
    def test_plugin_initialization(self):
        """Test plugin initializes correctly"""
        self.assertTrue(self.plugin.enabled)
        self.assertEqual(len(self.plugin.agent_profiles), 0)
        self.assertIn("loop_threshold", self.plugin.config)
    
    def test_register_agent(self):
        """Test agent registration"""
        profile = self.plugin.register_agent("test_001", "warrior")
        
        self.assertEqual(profile.agent_id, "test_001")
        self.assertEqual(profile.agent_type, "warrior")
        self.assertEqual(len(self.plugin.agent_profiles), 1)
    
    def test_record_tick(self):
        """Test tick recording"""
        self.plugin.register_agent("test_001", "warrior")
        
        self.plugin.record_tick(
            agent_id="test_001",
            action="attack",
            prev_state="idle",
            curr_state="combat",
            decision_time_ms=50.0
        )
        
        profile = self.plugin.agent_profiles["test_001"]
        self.assertEqual(profile.total_ticks, 1)
        self.assertEqual(profile.metrics.action_counts.get("attack"), 1)
    
    def test_detect_loop(self):
        """Test loop detection"""
        self.plugin.register_agent("test_001", "warrior")
        
        # Record same action multiple times
        for i in range(10):
            self.plugin.record_tick(
                agent_id="test_001",
                action="idle",
                prev_state="idle",
                curr_state="idle",
                decision_time_ms=10.0
            )
        
        profile = self.plugin.agent_profiles["test_001"]
        self.assertTrue(profile.metrics.loop_detected)
        self.assertGreater(profile.stuck_count, 0)
    
    def test_efficiency_calculation(self):
        """Test efficiency score calculation"""
        self.plugin.register_agent("test_001", "warrior")
        
        # Record diverse actions
        actions = ["move", "attack", "defend", "collect", "idle"]
        for i in range(20):
            self.plugin.record_tick(
                agent_id="test_001",
                action=actions[i % len(actions)],
                prev_state="prev",
                curr_state="curr",
                decision_time_ms=20.0
            )
        
        profile = self.plugin.agent_profiles["test_001"]
        self.assertGreater(profile.efficiency_score, 70)  # Should be high
    
    def test_anomaly_detection(self):
        """Test anomaly detection"""
        self.plugin.register_agent("test_001", "mage")
        
        # Record slow decisions
        for i in range(20):
            self.plugin.record_tick(
                agent_id="test_001",
                action="cast_spell",
                prev_state="casting",
                curr_state="casting",
                decision_time_ms=600.0  # Very slow
            )
        
        anomalies = self.plugin.detect_anomalies("test_001")
        
        self.assertGreater(len(anomalies), 0)
        anomaly_types = [a["type"] for a in anomalies]
        self.assertIn("slow_decisions", anomaly_types)
    
    def test_generate_report(self):
        """Test report generation"""
        self.plugin.register_agent("test_001", "warrior")
        
        for i in range(10):
            self.plugin.record_tick(
                agent_id="test_001",
                action="attack",
                prev_state="combat",
                curr_state="combat",
                decision_time_ms=30.0
            )
        
        report = self.plugin.generate_report("test_001")
        
        self.assertIn("agent_id", report)
        self.assertIn("efficiency_score", report)
        self.assertIn("total_ticks", report)
        self.assertEqual(report["total_ticks"], 10)
    
    def test_global_report(self):
        """Test global report generation"""
        self.plugin.register_agent("test_001", "warrior")
        self.plugin.register_agent("test_002", "mage")
        
        for i in range(5):
            self.plugin.record_tick("test_001", "attack", "", "", 20.0)
            self.plugin.record_tick("test_002", "cast", "", "", 30.0)
        
        report = self.plugin.generate_report()
        
        self.assertEqual(report["total_agents"], 2)
        self.assertGreater(report["total_ticks"], 0)
    
    def test_get_recommendations(self):
        """Test recommendations generation"""
        self.plugin.register_agent("test_001", "warrior")
        
        # Create inefficient agent
        for i in range(30):
            self.plugin.record_tick(
                agent_id="test_001",
                action="idle",  # Only one action
                prev_state="idle",
                curr_state="idle",
                decision_time_ms=300.0  # Slow
            )
        
        recommendations = self.plugin.get_recommendations("test_001")
        
        self.assertGreater(len(recommendations), 0)
    
    def test_reset(self):
        """Test plugin reset"""
        self.plugin.register_agent("test_001", "warrior")
        self.plugin.record_tick("test_001", "attack", "", "", 20.0)
        
        self.plugin.reset()
        
        self.assertEqual(len(self.plugin.agent_profiles), 0)
    
    def test_plugin_status(self):
        """Test plugin status reporting"""
        self.plugin.register_agent("test_001", "warrior")
        self.plugin.record_tick("test_001", "attack", "", "", 20.0)
        
        status = self.plugin.get_plugin_status()
        
        self.assertTrue(status["enabled"])
        self.assertEqual(status["monitored_agents"], 1)
        self.assertEqual(status["total_ticks_recorded"], 1)


class TestIntegration(unittest.TestCase):
    """Integration tests for AI systems"""
    
    def test_agent_with_analyzer(self):
        """Test agent behavior tracked by analyzer"""
        # Create agent
        agent = create_agent("warrior")
        
        # Create analyzer
        analyzer = AIBehaviorAnalyzerPlugin()
        analyzer.register_agent(agent.agent_id, agent.agent_type)
        
        # Simulate gameplay
        for tick in range(20):
            # Random events
            if tick % 5 == 0:
                agent.state.enemies_nearby = True
            if tick % 7 == 0:
                agent.state.loot_available = True
            
            # Execute tick
            start_time = time.time()
            result = agent.tick()
            decision_time = (time.time() - start_time) * 1000
            
            # Record in analyzer
            analyzer.record_tick(
                agent_id=agent.agent_id,
                action=agent.current_action,
                prev_state="prev",
                curr_state=result,
                decision_time_ms=decision_time
            )
        
        # Generate report
        report = analyzer.generate_report(agent.agent_id)
        
        self.assertGreater(report["total_ticks"], 0)
        self.assertIn("efficiency_score", report)
    
    def test_multiple_agents_simulation(self):
        """Test simulation with multiple agents"""
        agents = [
            create_agent("warrior"),
            create_agent("mage"),
            create_agent("rogue")
        ]
        
        analyzer = AIBehaviorAnalyzerPlugin()
        
        for agent in agents:
            analyzer.register_agent(agent.agent_id, agent.agent_type)
        
        # Run simulation
        for tick in range(50):
            for agent in agents:
                # Random events
                if tick % 10 == 0:
                    agent.state.enemies_nearby = True
                
                start_time = time.time()
                agent.tick()
                decision_time = (time.time() - start_time) * 1000
                
                analyzer.record_tick(
                    agent_id=agent.agent_id,
                    action=agent.current_action,
                    prev_state="prev",
                    curr_state="curr",
                    decision_time_ms=decision_time
                )
        
        # Check global report
        global_report = analyzer.generate_report()
        
        self.assertEqual(global_report["total_agents"], 3)
        self.assertGreater(global_report["total_ticks"], 0)
        self.assertIn("avg_efficiency", global_report)


def run_tests():
    """Run all tests and return results"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestBehaviorTree))
    suite.addTests(loader.loadTestsFromTestCase(TestAIAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestAIBehaviorAnalyzerPlugin))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("AI SYSTEMS COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    
    result = run_tests()
    
    print("\n" + "=" * 60)
    print(f"Tests Run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success: {result.wasSuccessful()}")
    print("=" * 60)
    
    sys.exit(0 if result.wasSuccessful() else 1)
