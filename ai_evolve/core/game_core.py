"""
AI-EVOLVE Game Core Application
Main entry point that initializes core systems and plugins.
"""
import sys
from ai_evolve.core.event_system import event_system, EventSystem
from ai_evolve.db.database_core import db_core, DatabaseCore
from ai_evolve.core.plugin_manager import PluginManager
from ai_evolve.features.combat.combat_plugin import CombatPlugin
from ai_evolve.features.toughness.toughness_plugin import ToughnessPlugin
from ai_evolve.features.effects.effects_plugin import EffectsPlugin
from ai_evolve.features.scenes.scene_manager_plugin import SceneManagerPlugin

class GameCore:
    """
    Main Game Core Application.
    Initializes and manages all core systems and plugins.
    """
    
    def __init__(self):
        self.event_system = event_system
        self.db_core = db_core
        self.plugin_manager = None
        self.is_running = False
    
    def initialize(self, db_url: str = None):
        """Initialize the game core."""
        print("[GameCore] Initializing...")
        
        # Initialize database
        if db_url:
            self.db_core = DatabaseCore(db_url)
        self.db_core.init_db()
        print("[GameCore] Database initialized")
        
        # Create plugin manager
        self.plugin_manager = PluginManager(self.event_system)
        
        # Register core plugins
        self._register_plugins()
        
        # Initialize all plugins
        self.plugin_manager.initialize_all()
        print("[GameCore] All plugins initialized")
        
        self.is_running = True
    
    def _register_plugins(self):
        """Register all game plugins."""
        # Combat system
        combat_plugin = CombatPlugin()
        self.plugin_manager.register_plugin(combat_plugin)
        
        # Toughness system
        toughness_plugin = ToughnessPlugin()
        self.plugin_manager.register_plugin(toughness_plugin)
        
        # Effects system (DoT, combos, CC)
        effects_plugin = EffectsPlugin()
        self.plugin_manager.register_plugin(effects_plugin)
        
        # Scene manager
        scene_manager = SceneManagerPlugin()
        self.plugin_manager.register_plugin(scene_manager)
        
        print(f"[GameCore] Registered {len(self.plugin_manager.plugins)} plugins")
    
    def run(self, delta_time: float = 0.016):
        """Run one frame/update cycle."""
        if not self.is_running:
            return
        
        self.plugin_manager.update_all(delta_time)
    
    def shutdown(self):
        """Shutdown the game core."""
        print("[GameCore] Shutting down...")
        
        if self.plugin_manager:
            self.plugin_manager.shutdown_all()
        
        self.is_running = False
        print("[GameCore] Shutdown complete")
    
    def get_plugin(self, name: str):
        """Get a plugin by name."""
        if self.plugin_manager:
            return self.plugin_manager.get_plugin(name)
        return None


def main():
    """Main entry point."""
    game = GameCore()
    
    try:
        # Initialize with in-memory database
        game.initialize(db_url="sqlite:///:memory:")
        
        # Run a few frames
        for i in range(10):
            game.run(delta_time=0.016)
        
        print("[GameCore] Demo run complete")
        
    except Exception as e:
        print(f"[GameCore] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        game.shutdown()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
