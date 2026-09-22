"""
Game Loop - Central orchestration of the game lifecycle.
Unifies all plugins into a coherent session: Start -> Quest -> Fight -> Loot -> Save -> Exit.
"""
import time
import logging
from typing import Dict, List, Optional, Any
from enum import Enum, auto

from ai_evolve.core.event_system import EventSystem
from ai_evolve.core.plugin_manager import PluginManager
from ai_evolve.db.database_core import DatabaseCore, Base


class GameState(Enum):
    """Possible states of the game session."""
    INITIALIZING = auto()
    MENU = auto()
    LOADING = auto()
    PLAYING = auto()
    PAUSED = auto()
    IN_DIALOGUE = auto()
    IN_COMBAT = auto()
    SAVING = auto()
    EXITING = auto()
    SHUTDOWN = auto()


class GameLoop:
    """
    Main game loop orchestrator.
    Manages state transitions and plugin updates.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.state = GameState.INITIALIZING
        self.plugin_manager: Optional[PluginManager] = None
        self.db_core: Optional[DatabaseCore] = None
        self.running = False
        self.last_update_time = 0.0
        self._event_system = EventSystem()

    @property
    def on_state_changed(self):
        """Lazy property for state change event signal."""
        return self._event_system.get_signal("game_state_changed")
    
    @property
    def on_session_started(self):
        """Lazy property for session started event signal."""
        return self._event_system.get_signal("session_started")
    
    @property
    def on_session_ended(self):
        """Lazy property for session ended event signal."""
        return self._event_system.get_signal("session_ended")

    def initialize(self, plugin_configs: Optional[Dict[str, Dict]] = None, db_url: str = "sqlite:///:memory:") -> bool:
        """Initialize core systems and plugins."""
        try:
            self.logger.info("Initializing Game Loop...")
            
            # Initialize Database
            self.db_core = DatabaseCore(db_url)
            self.db_core.init_db()
            self.logger.info("Database initialized.")
            
            # Initialize Plugin Manager
            self.plugin_manager = PluginManager(self._event_system)
            
            # Register Core Plugins
            # Note: In a real app, these would be discovered dynamically
            from ai_evolve.features.combat.combat_plugin import CombatPlugin
            from ai_evolve.features.toughness.toughness_plugin import ToughnessPlugin
            from ai_evolve.features.effects.effects_plugin import EffectsPlugin
            from ai_evolve.features.scenes.scene_manager_plugin import SceneManagerPlugin
            from ai_evolve.features.inventory.inventory_plugin import InventoryPlugin
            from ai_evolve.features.quest.quest_plugin import QuestPlugin
            from ai_evolve.features.dialogue.dialogue_plugin import DialoguePlugin
            
            plugins = [
                CombatPlugin(),
                ToughnessPlugin(),
                EffectsPlugin(),
                SceneManagerPlugin(),
                InventoryPlugin(),
                QuestPlugin(),
                DialoguePlugin()
            ]
            
            for plugin in plugins:
                self.plugin_manager.register_plugin(plugin)
            
            # Initialize all plugins through PluginManager
            if not self.plugin_manager.initialize_all():
                self.logger.error("Failed to initialize one or more plugins.")
                return False
            
            self.state = GameState.MENU
            self.on_state_changed.send(self, old_state=None, new_state=self.state)
            self.logger.info(f"Game Loop initialized. State: {self.state.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Critical error during initialization: {e}", exc_info=True)
            return False

    def start_session(self, save_slot: Optional[int] = None) -> bool:
        """Start a new game session or load a save."""
        if self.state != GameState.MENU:
            self.logger.warning(f"Cannot start session from state {self.state.name}")
            return False
        
        self.state = GameState.LOADING
        self.on_state_changed.send(self, old_state=GameState.MENU, new_state=self.state)
        
        try:
            if save_slot is not None:
                self._load_game(save_slot)
            else:
                self._new_game()
            
            self.state = GameState.PLAYING
            self.on_state_changed.send(self, old_state=GameState.LOADING, new_state=self.state)
            self.on_session_started.send(self)
            self.running = True
            self.last_update_time = time.time()
            self.logger.info("Session started.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to start session: {e}")
            self.state = GameState.MENU
            return False

    def _new_game(self) -> None:
        """Initialize a new game state."""
        self.logger.info("Starting new game...")
        # Trigger quest plugin to start intro quest
        if self.plugin_manager:
            quest_plugin = self.plugin_manager.get_plugin("QuestPlugin")
            if quest_plugin:
                # Player entity ID 1 is assumed for the first player
                quest_plugin.start_quest(entity_id=1, quest_id="intro_quest")

    def _load_game(self, slot: int) -> None:
        """Load game from a save slot."""
        self.logger.info(f"Loading game from slot {slot}...")
        # Implementation depends on SavePlugin/Database structure
        pass

    def run(self, max_frames: Optional[int] = None) -> None:
        """
        Run the main game loop.
        If max_frames is provided, runs only for that many frames (for testing).
        """
        if not self.running:
            self.logger.warning("Game loop is not running. Call start_session first.")
            return
        
        frame_count = 0
        while self.running and self.state == GameState.PLAYING:
            current_time = time.time()
            dt = current_time - self.last_update_time
            self.last_update_time = current_time
            
            self._update(dt)
            
            frame_count += 1
            if max_frames and frame_count >= max_frames:
                break
        
        self.logger.info(f"Game loop finished after {frame_count} frames.")

    def _update(self, dt: float) -> None:
        """Update all active systems."""
        if self.plugin_manager:
            self.plugin_manager.update_all(dt)
        
        # Check for game over conditions, etc.
        # This is where high-level game logic resides

    def pause(self) -> None:
        """Pause the game."""
        if self.state == GameState.PLAYING:
            old_state = self.state
            self.state = GameState.PAUSED
            self.on_state_changed.send(self, old_state=old_state, new_state=self.state)
            self.logger.info("Game paused.")

    def resume(self) -> None:
        """Resume the game."""
        if self.state == GameState.PAUSED:
            old_state = self.state
            self.state = GameState.PLAYING
            self.on_state_changed.send(self, old_state=old_state, new_state=self.state)
            self.last_update_time = time.time()
            self.logger.info("Game resumed.")

    def start_dialogue(self, dialogue_id: str, speaker_id: int = 1) -> bool:
        """Enter dialogue state."""
        if self.state != GameState.PLAYING:
            return False
            
        if self.plugin_manager:
            dialogue_plugin = self.plugin_manager.get_plugin("DialoguePlugin")
            if dialogue_plugin:
                if dialogue_plugin.start_dialogue(entity_id=speaker_id, dialogue_id=dialogue_id):
                    old_state = self.state
                    self.state = GameState.IN_DIALOGUE
                    self.on_state_changed.send(self, old_state=old_state, new_state=self.state)
                    return True
        return False

    def end_dialogue(self) -> None:
        """Exit dialogue state."""
        if self.state == GameState.IN_DIALOGUE:
            old_state = self.state
            self.state = GameState.PLAYING
            self.on_state_changed.send(self, old_state=old_state, new_state=self.state)
            self.logger.info("Dialogue ended.")

    def start_combat(self, enemy_id: str) -> bool:
        """Enter combat state."""
        if self.state != GameState.PLAYING:
            return False
            
        if self.plugin_manager:
            # Try both naming conventions
            combat_plugin = self.plugin_manager.get_plugin("CombatPlugin") or \
                           self.plugin_manager.get_plugin("combat")
            if combat_plugin:
                # Simplified combat start
                old_state = self.state
                self.state = GameState.IN_COMBAT
                self.on_state_changed.send(self, old_state=old_state, new_state=self.state)
                self.logger.info(f"Combat started with {enemy_id}.")
                return True
        return False

    def end_combat(self, victory: bool) -> None:
        """Exit combat state."""
        if self.state == GameState.IN_COMBAT:
            old_state = self.state
            self.state = GameState.PLAYING
            self.on_state_changed.send(self, old_state=old_state, new_state=self.state)
            
            if victory:
                self._handle_victory()
            
            self.logger.info("Combat ended.")

    def _handle_victory(self) -> None:
        """Handle post-combat victory logic (loot, XP, quests)."""
        self.logger.info("Victory! Processing rewards...")
        # Trigger loot, XP, quest updates via events/plugins

    def save_game(self, slot: int) -> bool:
        """Save the current game state."""
        if self.state not in [GameState.PLAYING, GameState.PAUSED]:
            return False
        
        old_state = self.state
        self.state = GameState.SAVING
        self.on_state_changed.send(self, old_state=old_state, new_state=self.state)
        
        try:
            # Collect state from all plugins
            game_state = {}
            if self.plugin_manager:
                game_state = self.plugin_manager.get_state()
            
            # Save to DB via DatabaseCore
            if self.db_core:
                with self.db_core.session_scope() as session:
                    # Placeholder for actual save logic
                    # save_record = SaveData(slot=slot, data=json.dumps(game_state))
                    # session.add(save_record)
                    pass
            
            self.state = GameState.PLAYING if old_state == GameState.PLAYING else GameState.PAUSED
            self.on_state_changed.send(self, old_state=GameState.SAVING, new_state=self.state)
            self.logger.info(f"Game saved to slot {slot}.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save game: {e}")
            self.state = old_state
            return False

    def exit_to_menu(self) -> None:
        """Exit current session to menu."""
        self.logger.info("Exiting to menu...")
        self.end_session()
        self.state = GameState.MENU
        self.on_state_changed.send(self, old_state=GameState.EXITING, new_state=self.state)

    def end_session(self) -> None:
        """End the current game session."""
        if not self.running:
            return
        
        self.running = False
        self.on_session_ended.send(self)
        self.logger.info("Session ended.")

    def shutdown(self) -> None:
        """Shutdown all systems."""
        self.logger.info("Shutting down Game Loop...")
        
        self.end_session()
        
        if self.plugin_manager:
            self.plugin_manager.shutdown_all()
        
        if self.db_core:
            # DatabaseCore doesn't have dispose, just clear for testing
            pass
        
        self.state = GameState.SHUTDOWN
        self.logger.info("Game Loop shut down.")
