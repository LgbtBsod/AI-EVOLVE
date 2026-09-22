"""
Audio Core Plugin
Provides audio engine integration with FMOD/Wwise stubs
Supports 2D/3D sound, music, voice, and audio events
"""

from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from enum import Enum
import logging

from ai_evolve.core.plugin_base import GamePlugin
from ai_evolve.core.event_system import EventSystem


class AudioType(Enum):
    SFX_2D = "sfx_2d"
    SFX_3D = "sfx_3d"
    MUSIC = "music"
    VOICE = "voice"
    AMBIENCE = "ambience"


@dataclass
class AudioEvent:
    """Represents an audio event to be played"""
    event_name: str
    audio_type: AudioType
    volume: float = 1.0
    pitch: float = 1.0
    position: Optional[tuple] = None  # (x, y, z) for 3D sounds
    parameters: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class AudioEngineStub:
    """
    Stub for FMOD/Wwise audio engine
    Replace with actual implementation when integrating real audio middleware
    """
    
    def __init__(self):
        self.initialized = False
        self.events: Dict[str, Any] = {}
        self.channels: Dict[int, Any] = {}
        self.logger = logging.getLogger("AudioEngineStub")
    
    def initialize(self):
        """Initialize audio engine"""
        self.logger.info("AudioEngineStub initialized (FMOD/Wwise stub)")
        self.initialized = True
    
    def shutdown(self):
        """Shutdown audio engine"""
        self.logger.info("AudioEngineStub shut down")
        self.initialized = False
    
    def load_event(self, event_name: str) -> bool:
        """Load an audio event"""
        if not self.initialized:
            return False
        
        # Stub: just register the event name
        self.events[event_name] = {"loaded": True, "instances": []}
        self.logger.debug(f"Loaded audio event: {event_name}")
        return True
    
    def unload_event(self, event_name: str):
        """Unload an audio event"""
        if event_name in self.events:
            del self.events[event_name]
            self.logger.debug(f"Unloaded audio event: {event_name}")
    
    def play_event(self, event_name: str, **kwargs) -> Optional[int]:
        """Play an audio event"""
        if not self.initialized or event_name not in self.events:
            return None
        
        # Stub: create a channel ID
        channel_id = len(self.channels)
        self.channels[channel_id] = {
            "event": event_name,
            "playing": True,
            "parameters": kwargs
        }
        
        self.logger.debug(f"Playing event {event_name} on channel {channel_id}")
        return channel_id
    
    def stop_event(self, channel_id: int):
        """Stop playback on a channel"""
        if channel_id in self.channels:
            self.channels[channel_id]["playing"] = False
            self.logger.debug(f"Stopped channel {channel_id}")
    
    def set_parameter(self, channel_id: int, param_name: str, value: float):
        """Set event parameter"""
        if channel_id in self.channels:
            self.channels[channel_id]["parameters"][param_name] = value
    
    def update_3d_attributes(self, channel_id: int, position: tuple, velocity: tuple):
        """Update 3D sound attributes"""
        if channel_id in self.channels:
            self.channels[channel_id]["position"] = position
            self.channels[channel_id]["velocity"] = velocity
    
    def set_master_volume(self, volume: float):
        """Set master volume"""
        self.logger.info(f"Master volume set to {volume}")
    
    def set_category_volume(self, category: str, volume: float):
        """Set volume for audio category"""
        self.logger.info(f"{category} volume set to {volume}")


class AudioCorePlugin(GamePlugin):
    """
    Plugin for audio management with FMOD/Wwise integration
    """
    
    name = "audio_core"
    version = "1.0.0"
    description = "Audio engine integration with FMOD/Wwise stubs"
    
    dependencies = []
    
    def __init__(self):
        super().__init__()
        self.event_system: Optional[EventSystem] = None
        self.audio_engine: Optional[AudioEngineStub] = None
        
        # Audio state
        self.loaded_events: Dict[str, AudioEvent] = {}
        self.active_channels: Dict[int, AudioEvent] = {}
        self.next_channel_id: int = 0
        
        # Volume levels (0.0 to 1.0)
        self.volumes = {
            "master": 1.0,
            "music": 0.7,
            "sfx": 1.0,
            "voice": 1.0,
            "ambience": 0.5,
        }
        
        # Configuration
        self.config = {
            "max_channels": 64,
            "3d_enabled": True,
            "doppler_effect": True,
            "distance_model": "linear",
        }
    
    def initialize(self, config: dict = None):
        """Initialize the plugin"""
        if config:
            self.config.update(config)
        
        self.event_system = EventSystem.get_instance()
        self.audio_engine = AudioEngineStub()
        
        # Initialize audio engine
        self.audio_engine.initialize()
        
        # Register event handlers
        self.event_system.connect("on_game_start", self._on_game_start)
        self.event_system.connect("on_game_pause", self._on_game_pause)
        self.event_system.connect("on_game_resume", self._on_game_resume)
        self.event_system.connect("on_game_end", self._on_game_end)
        self.event_system.connect("on_update", self._on_update)
        
        # Game-specific events
        self.event_system.connect("on_combat_start", self._on_combat_start)
        self.event_system.connect("on_entity_spawned", self._on_entity_spawned)
        self.event_system.connect("on_entity_death", self._on_entity_death)
        self.event_system.connect("on_player_hit", self._on_player_hit)
        self.event_system.connect("on_quest_completed", self._on_quest_completed)
        
        self.logger.info("AudioCorePlugin initialized")
    
    def shutdown(self):
        """Cleanup plugin resources"""
        if self.event_system:
            self.event_system.disconnect("on_game_start", self._on_game_start)
            self.event_system.disconnect("on_game_pause", self._on_game_pause)
            self.event_system.disconnect("on_game_resume", self._on_game_resume)
            self.event_system.disconnect("on_game_end", self._on_game_end)
            self.event_system.disconnect("on_update", self._on_update)
            self.event_system.disconnect("on_combat_start", self._on_combat_start)
            self.event_system.disconnect("on_entity_spawned", self._on_entity_spawned)
            self.event_system.disconnect("on_entity_death", self._on_entity_death)
            self.event_system.disconnect("on_player_hit", self._on_player_hit)
            self.event_system.disconnect("on_quest_completed", self._on_quest_completed)
        
        if self.audio_engine:
            self.audio_engine.shutdown()
        
        self.loaded_events.clear()
        self.active_channels.clear()
        
        self.logger.info("AudioCorePlugin shut down")
    
    def update(self, delta_time: float):
        """Update audio system"""
        # Update active channels
        channels_to_remove = []
        for channel_id, event in self.active_channels.items():
            # In real implementation, check if event finished playing
            pass
        
        for channel_id in channels_to_remove:
            self.active_channels.pop(channel_id, None)
    
    def load_audio_event(self, event_name: str, audio_type: AudioType, 
                        default_volume: float = 1.0) -> bool:
        """Load an audio event"""
        if not self.audio_engine:
            return False
        
        if self.audio_engine.load_event(event_name):
            self.loaded_events[event_name] = AudioEvent(
                event_name=event_name,
                audio_type=audio_type,
                volume=default_volume
            )
            return True
        return False
    
    def play_sound(self, event_name: str, volume: float = 1.0, 
                  pitch: float = 1.0, position: Optional[tuple] = None) -> Optional[int]:
        """Play a sound effect"""
        if event_name not in self.loaded_events:
            self.logger.warning(f"Audio event {event_name} not loaded")
            return None
        
        event = self.loaded_events[event_name]
        
        # Apply category volume
        category = self._get_category_for_type(event.audio_type)
        final_volume = volume * self.volumes.get(category, 1.0) * self.volumes["master"]
        
        # Play through engine
        channel_id = self.audio_engine.play_event(
            event_name,
            volume=final_volume,
            pitch=pitch,
            position=position
        )
        
        if channel_id is not None:
            self.active_channels[channel_id] = event
            
            # Set 3D position if applicable
            if position and event.audio_type == AudioType.SFX_3D:
                self.audio_engine.update_3d_attributes(channel_id, position, (0, 0, 0))
            
            self.logger.debug(f"Playing sound {event_name} on channel {channel_id}")
        
        return channel_id
    
    def play_music(self, event_name: str, fade_in: float = 1.0) -> Optional[int]:
        """Play background music"""
        return self.play_sound(event_name, volume=self.volumes["music"])
    
    def stop_sound(self, channel_id: int):
        """Stop a playing sound"""
        if self.audio_engine:
            self.audio_engine.stop_event(channel_id)
            self.active_channels.pop(channel_id, None)
    
    def stop_all_sounds(self, exclude_music: bool = True):
        """Stop all playing sounds"""
        channels_to_stop = []
        for channel_id, event in self.active_channels.items():
            if exclude_music and event.audio_type == AudioType.MUSIC:
                continue
            channels_to_stop.append(channel_id)
        
        for channel_id in channels_to_stop:
            self.stop_sound(channel_id)
    
    def set_volume(self, category: str, volume: float):
        """Set volume for a category"""
        volume = max(0.0, min(1.0, volume))
        self.volumes[category] = volume
        
        if self.audio_engine:
            self.audio_engine.set_category_volume(category, volume)
    
    def set_master_volume(self, volume: float):
        """Set master volume"""
        volume = max(0.0, min(1.0, volume))
        self.volumes["master"] = volume
        
        if self.audio_engine:
            self.audio_engine.set_master_volume(volume)
    
    def _get_category_for_type(self, audio_type: AudioType) -> str:
        """Get volume category for audio type"""
        mapping = {
            AudioType.SFX_2D: "sfx",
            AudioType.SFX_3D: "sfx",
            AudioType.MUSIC: "music",
            AudioType.VOICE: "voice",
            AudioType.AMBIENCE: "ambience",
        }
        return mapping.get(audio_type, "sfx")
    
    # Event handlers
    def _on_game_start(self, **kwargs):
        """Handle game start - load common sounds"""
        # Load default sounds
        self.load_audio_event("ui_click", AudioType.SFX_2D)
        self.load_audio_event("combat_start", AudioType.MUSIC)
        self.load_audio_event("player_hit", AudioType.SFX_2D)
        self.load_audio_event("enemy_death", AudioType.SFX_2D)
    
    def _on_game_pause(self, **kwargs):
        """Handle game pause - reduce volumes"""
        self.set_volume("music", self.volumes["music"] * 0.3)
        self.set_volume("sfx", self.volumes["sfx"] * 0.5)
    
    def _on_game_resume(self, **kwargs):
        """Handle game resume - restore volumes"""
        self.set_volume("music", 0.7)
        self.set_volume("sfx", 1.0)
    
    def _on_game_end(self, **kwargs):
        """Handle game end - stop all sounds"""
        self.stop_all_sounds(exclude_music=False)
    
    def _on_combat_start(self, **kwargs):
        """Handle combat start - play combat music"""
        self.play_music("combat_music", fade_in=2.0)
    
    def _on_entity_spawned(self, entity_id: int, **kwargs):
        """Handle entity spawn"""
        # Could play spawn sound based on entity type
    
    def _on_entity_death(self, entity_id: int, **kwargs):
        """Handle entity death - play death sound"""
        self.play_sound("enemy_death")
    
    def _on_player_hit(self, damage: float, **kwargs):
        """Handle player hit - play hit sound"""
        self.play_sound("player_hit")
    
    def _on_quest_completed(self, quest_id: str, **kwargs):
        """Handle quest completion - play victory fanfare"""
        self.play_sound("quest_complete", audio_type=AudioType.MUSIC)
    
    def _on_update(self, delta_time: float, **kwargs):
        """Handle game update"""
        self.update(delta_time)


# Export for plugin manager
__all__ = ["AudioCorePlugin", "AudioEngineStub", "AudioEvent", "AudioType"]
