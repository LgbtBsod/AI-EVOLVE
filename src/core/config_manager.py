"""Simple configuration manager for project runtime settings."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DisplayConfig:
    width: int = 1600
    height: int = 900
    fullscreen: bool = False
    vsync: bool = True


@dataclass(slots=True)
class AudioConfig:
    master_volume: float = 1.0
    music_volume: float = 0.7
    sfx_volume: float = 0.8


@dataclass(slots=True)
class GameplayConfig:
    difficulty: str = "normal"
    auto_save: bool = True
    save_interval: int = 300


@dataclass(slots=True)
class CharacterStatsConfig:
    """Configuration for character base stats and class multipliers."""
    health: float = 100.0
    mana: float = 50.0
    stamina: float = 100.0
    defense: float = 5.0
    physical_damage: float = 20.0
    magical_damage: float = 0.0
    attack_speed: float = 1.0
    attack_range: float = 2.0
    critical_chance: float = 5.0
    critical_damage: float = 150.0
    dodge_chance: float = 0.0
    magic_resistance: float = 0.0
    speed: float = 8.0
    health_regen: float = 1.0
    mana_regen: float = 5.0
    stamina_regen: float = 10.0


class ConfigManager:
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path("config")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.display = DisplayConfig()
        self.audio = AudioConfig()
        self.gameplay = GameplayConfig()
        self.character_stats = CharacterStatsConfig()
        self._stats_cache: dict[str, Any] = {}

    def _path(self, name: str) -> Path:
        return self.config_dir / f"{name}.json"

    def load(self, name: str) -> dict[str, Any]:
        path = self._path(name)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, name: str, payload: dict[str, Any]) -> None:
        self._path(name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_defaults(self) -> None:
        self.save("display_config", asdict(self.display))
        self.save("audio_config", asdict(self.audio))
        self.save("gameplay_config", asdict(self.gameplay))

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        Example: config.get("characters.base.health", default=100)
        """
        keys = key.split(".")
        
        # Load the appropriate config file based on the first key
        config_file_map = {
            "characters": "character_stats",
            "enemies": "enemy_stats",
            "display": "display_config",
            "audio": "audio_config",
            "gameplay": "gameplay_config",
            "performance": "performance_config"
        }
        
        root_key = keys[0]
        if root_key in config_file_map:
            config_name = config_file_map[root_key]
            if config_name not in self._stats_cache:
                self._stats_cache[config_name] = self.load(config_name)
            data = self._stats_cache[config_name]
            
            # Navigate through the nested keys
            for k in keys[1:]:
                if isinstance(data, dict) and k in data:
                    data = data[k]
                else:
                    return default
            return data
        
        # Fallback to dataclass attributes
        if len(keys) == 1:
            return getattr(self, keys[0], default)
        
        return default

    def set(self, key: str, value: Any) -> bool:
        """
        Set a configuration value using dot notation.
        Example: config.set("characters.base.health", 120)
        Returns True if successful, False otherwise.
        """
        keys = key.split(".")
        
        config_file_map = {
            "characters": "character_stats",
            "enemies": "enemy_stats"
        }
        
        root_key = keys[0]
        if root_key in config_file_map:
            config_name = config_file_map[root_key]
            if config_name not in self._stats_cache:
                self._stats_cache[config_name] = self.load(config_name)
            
            data = self._stats_cache[config_name]
            
            # Navigate to the second-to-last key
            for k in keys[1:-1]:
                if k not in data:
                    data[k] = {}
                data = data[k]
            
            # Set the value at the last key
            if keys[-1]:
                data[keys[-1]] = value
                self.save(config_name, data)
                return True
        
        return False

    def reload(self, config_name: str | None = None) -> None:
        """Reload configuration from disk."""
        if config_name:
            self._stats_cache.pop(config_name, None)
            self.load(config_name)
        else:
            self._stats_cache.clear()

    def get_class_stats(self, character_class: str) -> dict[str, Any]:
        """Get stats multiplier for a specific character class."""
        classes = self.get("characters.classes", {})
        return classes.get(character_class, {})

    def get_enemy_stats(self, enemy_type: str, level: int = 1) -> dict[str, Any]:
        """Get stats for a specific enemy type with level scaling."""
        enemies = self.get("enemies.enemies", {})
        base_stats = enemies.get(enemy_type, {})
        
        if not base_stats:
            return {}
        
        # Apply level scaling
        scaling = self.get("enemies.scaling", {})
        scaled_stats = base_stats.copy()
        
        levels_gained = max(0, level - base_stats.get("level", 1))
        if levels_gained > 0:
            scaled_stats["health"] = base_stats.get("health", 50) + levels_gained * scaling.get("health_per_level", 15)
            scaled_stats["damage"] = base_stats.get("damage", 10) + levels_gained * scaling.get("damage_per_level", 5)
            scaled_stats["defense"] = base_stats.get("defense", 2) + levels_gained * scaling.get("defense_per_level", 2)
            scaled_stats["exp_reward"] = int(base_stats.get("exp_reward", 20) * (scaling.get("exp_multiplier", 1.3) ** levels_gained))
        
        return scaled_stats
