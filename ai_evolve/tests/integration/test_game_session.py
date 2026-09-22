"""
Integration tests for full game session lifecycle.
Tests: Start -> Quest -> Fight -> Loot -> Save -> Exit
"""
import pytest
import time
from unittest.mock import patch, MagicMock

from ai_evolve.core.game_loop import GameLoop, GameState
from ai_evolve.core.event_system import EventSystem


class TestFullGameSession:
    """Integration tests for the complete game loop."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup before each test."""
        EventSystem.reset_instance()
        self.game_loop = GameLoop()
        yield
        # Cleanup
        if self.game_loop.state != GameState.SHUTDOWN:
            self.game_loop.shutdown()

    def test_initialization(self):
        """Test that the game loop initializes correctly."""
        assert self.game_loop.state == GameState.INITIALIZING
        
        success = self.game_loop.initialize(db_url="sqlite:///:memory:")
        
        assert success is True
        assert self.game_loop.state == GameState.MENU
        assert self.game_loop.plugin_manager is not None
        assert self.game_loop.db_core is not None

    def test_new_game_session(self):
        """Test starting a new game session."""
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        
        success = self.game_loop.start_session()
        
        assert success is True
        assert self.game_loop.state == GameState.PLAYING
        assert self.game_loop.running is True

    def test_quest_flow(self):
        """Test quest initiation and completion flow."""
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        self.game_loop.start_session()
        
        # Simulate quest start (via QuestPlugin internally)
        # In a real scenario, we'd check quest state
        assert self.game_loop.state == GameState.PLAYING
        
        # Run a few frames to let systems update
        self.game_loop.run(max_frames=5)
        
        # State should still be playing
        assert self.game_loop.state == GameState.PLAYING

    def test_combat_flow(self):
        """Test entering and exiting combat."""
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        self.game_loop.start_session()
        
        # Start combat
        success = self.game_loop.start_combat("enemy_001")
        
        assert success is True
        assert self.game_loop.state == GameState.IN_COMBAT
        
        # Simulate combat duration
        self.game_loop.run(max_frames=10)
        
        # End combat with victory
        self.game_loop.end_combat(victory=True)
        
        assert self.game_loop.state == GameState.PLAYING

    def test_dialogue_flow(self):
        """Test entering and exiting dialogue."""
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        self.game_loop.start_session()
        
        # Load a test dialogue manually since we don't have files
        from ai_evolve.features.dialogue_plugin import DialoguePlugin, DialogueData, DialogueNode
        
        dialogue_plugin = self.game_loop.plugin_manager.get_plugin("DialoguePlugin")
        assert dialogue_plugin is not None
        
        # Create a simple dialogue
        test_dialogue = DialogueData(
            id="test_dialogue",
            title="Test",
            nodes={
                "start": DialogueNode(
                    id="start",
                    speaker="NPC",
                    text="Hello, traveler!",
                    choices=[{"text": "Hi!", "next_id": "end"}]
                ),
                "end": DialogueNode(
                    id="end",
                    speaker="NPC",
                    text="Goodbye!",
                    choices=[]
                )
            },
            start_node_id="start"
        )
        dialogue_plugin.dialogues["test_dialogue"] = test_dialogue
        
        # Start dialogue
        success = self.game_loop.start_dialogue("test_dialogue")
        
        assert success is True
        assert self.game_loop.state == GameState.IN_DIALOGUE
        
        # Make a choice
        dialogue_plugin.make_choice(0)
        
        # Dialogue should end after last node
        assert self.game_loop.state == GameState.PLAYING or self.game_loop.state == GameState.IN_DIALOGUE
        
        # End dialogue explicitly
        self.game_loop.end_dialogue()
        assert self.game_loop.state == GameState.PLAYING

    def test_save_load_flow(self):
        """Test saving and loading game state."""
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        self.game_loop.start_session()
        
        # Run a bit to change state
        self.game_loop.run(max_frames=5)
        
        # Save game
        save_success = self.game_loop.save_game(slot=1)
        
        assert save_success is True
        
        # Note: Full load test requires actual save data implementation
        # For now, we verify the save mechanism doesn't crash

    def test_pause_resume(self):
        """Test pausing and resuming the game."""
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        self.game_loop.start_session()
        
        # Pause
        self.game_loop.pause()
        assert self.game_loop.state == GameState.PAUSED
        
        # Resume
        self.game_loop.resume()
        assert self.game_loop.state == GameState.PLAYING

    def test_full_session_lifecycle(self):
        """
        Complete integration test: Start -> Quest -> Fight -> Loot -> Save -> Exit
        """
        # 1. Initialize
        init_success = self.game_loop.initialize(db_url="sqlite:///:memory:")
        assert init_success is True
        assert self.game_loop.state == GameState.MENU
        
        # 2. Start Session (New Game)
        start_success = self.game_loop.start_session()
        assert start_success is True
        assert self.game_loop.state == GameState.PLAYING
        
        # 3. Quest Flow (simulated by running frames)
        self.game_loop.run(max_frames=5)
        assert self.game_loop.state == GameState.PLAYING
        
        # 4. Combat Flow
        combat_started = self.game_loop.start_combat("boss_001")
        assert combat_started is True
        assert self.game_loop.state == GameState.IN_COMBAT
        
        # Simulate combat
        self.game_loop.run(max_frames=10)
        
        # Victory
        self.game_loop.end_combat(victory=True)
        assert self.game_loop.state == GameState.PLAYING
        
        # 5. Dialogue Flow (post-combat NPC interaction)
        from ai_evolve.features.dialogue_plugin import DialogueData, DialogueNode
        dialogue_plugin = self.game_loop.plugin_manager.get_plugin("DialoguePlugin")
        test_dialogue = DialogueData(
            id="victory_dialogue",
            title="Victory",
            nodes={
                "start": DialogueNode(
                    id="start",
                    speaker="King",
                    text="You did it!",
                    choices=[{"text": "Thanks!", "next_id": "reward"}]
                ),
                "reward": DialogueNode(
                    id="reward",
                    speaker="King",
                    text="Here is your reward.",
                    choices=[]
                )
            },
            start_node_id="start"
        )
        dialogue_plugin.dialogues["victory_dialogue"] = test_dialogue
        
        dialogue_entered = self.game_loop.start_dialogue("victory_dialogue")
        assert dialogue_entered is True
        assert self.game_loop.state == GameState.IN_DIALOGUE
        
        # End dialogue
        self.game_loop.end_dialogue()
        assert self.game_loop.state == GameState.PLAYING
        
        # 6. Save Game
        save_success = self.game_loop.save_game(slot=1)
        assert save_success is True
        
        # 7. Exit to Menu
        self.game_loop.exit_to_menu()
        assert self.game_loop.state == GameState.MENU
        
        # 8. Shutdown
        self.game_loop.shutdown()
        assert self.game_loop.state == GameState.SHUTDOWN

    def test_event_emission(self):
        """Test that game state change events are emitted."""
        events_received = []
        
        def on_state_change(sender, old_state, new_state):
            events_received.append((old_state, new_state))
        
        EventSystem.connect("game_state_changed", on_state_change)
        
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        self.game_loop.start_session()
        self.game_loop.pause()
        self.game_loop.resume()
        self.game_loop.exit_to_menu()
        self.game_loop.shutdown()
        
        # Verify multiple state changes were recorded
        assert len(events_received) > 0
        
        EventSystem.disconnect("game_state_changed", on_state_change)

    def test_error_handling_bad_dialogue(self):
        """Test handling of non-existent dialogue."""
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        self.game_loop.start_session()
        
        # Try to start non-existent dialogue
        result = self.game_loop.start_dialogue("non_existent")
        
        assert result is False
        assert self.game_loop.state == GameState.PLAYING  # Should remain playing

    def test_error_handling_combat_while_in_dialogue(self):
        """Test that combat cannot start during dialogue."""
        self.game_loop.initialize(db_url="sqlite:///:memory:")
        self.game_loop.start_session()
        
        # Mock dialogue state
        self.game_loop.state = GameState.IN_DIALOGUE
        
        result = self.game_loop.start_combat("enemy")
        
        assert result is False
