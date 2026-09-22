"""
Scene Manager Plugin for AI-EVOLVE
Handles scene transitions and management.
"""
from ai_evolve.core.plugin_base import GamePlugin
from ai_evolve.core.event_system import event_system
from typing import Dict, Any, Optional

class BaseScene:
    """Base class for all scenes."""
    
    def __init__(self, name: str):
        self.name = name
        self.is_active = False
    
    def on_enter(self):
        """Called when scene becomes active."""
        pass
    
    def on_exit(self):
        """Called when scene becomes inactive."""
        pass
    
    def on_update(self, delta_time: float):
        """Called every frame while scene is active."""
        pass

class SceneManagerPlugin(GamePlugin):
    """
    Scene management plugin.
    Handles scene transitions and lifecycle.
    """
    
    def __init__(self):
        super().__init__("scene_manager")
        self.scenes: Dict[str, BaseScene] = {}
        self.current_scene: Optional[BaseScene] = None
        self.next_scene: Optional[str] = None
    
    def on_init(self):
        """Initialize scene manager."""
        print("[SceneManager] Initialized")
    
    def on_update(self, delta_time: float):
        """Update current scene."""
        if self.current_scene:
            self.current_scene.on_update(delta_time)
        
        # Handle scene transition
        if self.next_scene and self.next_scene in self.scenes:
            self._perform_transition()
    
    def on_shutdown(self):
        """Shutdown scene manager."""
        if self.current_scene:
            self.current_scene.on_exit()
        print("[SceneManager] Shutdown")
    
    def register_events(self, event_system):
        """Register scene manager event handlers."""
        event_system.subscribe("change_scene", self.request_scene_change)
    
    def add_scene(self, scene: BaseScene):
        """Add a scene to the manager."""
        self.scenes[scene.name] = scene
    
    def request_scene_change(self, sender, **data):
        """Request a scene change."""
        scene_name = data.get("scene_name")
        if scene_name in self.scenes:
            self.next_scene = scene_name
        else:
            print(f"[SceneManager] Scene '{scene_name}' not found")
    
    def _perform_transition(self):
        """Perform the actual scene transition."""
        if self.current_scene:
            self.current_scene.on_exit()
        
        self.current_scene = self.scenes[self.next_scene]
        self.next_scene = None
        
        if self.current_scene:
            self.current_scene.on_enter()
            print(f"[SceneManager] Entered scene: {self.current_scene.name}")
    
    def get_config(self) -> Dict[str, Any]:
        return {"current_scene": self.current_scene.name if self.current_scene else None}
