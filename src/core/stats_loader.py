"""
Stats Loader - Data-driven character and enemy statistics.
Loads stats from JSON configuration files instead of hardcoding.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.config_manager import ConfigManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CharacterBaseStats:
    """Base statistics for any character."""
    health: float = 100.0
    mana: float = 50.0
    stamina: float = 100.0
    defense: float = 5.0
    physical_damage: float = 20.0
    magical_damage: float = 0.0
    attack_speed: float = 1.0
    attack_range: float = 2.0
    critical_chance: float = 0.05
    critical_damage: float = 1.5
    dodge_chance: float = 0.0
    magic_resistance: float = 0.0
    speed: float = 8.0
    health_regen: float = 1.0
    mana_regen: float = 5.0
    stamina_regen: float = 10.0


@dataclass(slots=True)
class ClassMultiplier:
    """Multipliers for character classes."""
    health_mult: float = 1.0
    mana_mult: float = 1.0
    stamina_mult: float = 1.0
    defense_mult: float = 1.0
    physical_damage_mult: float = 1.0
    magical_damage_mult: float = 1.0
    crit_chance_bonus: float = 0.0
    crit_damage_bonus: float = 0.0
    dodge_chance_bonus: float = 0.0
    speed_mult: float = 1.0


@dataclass(slots=True)
class LevelScaling:
    """Per-level stat increases."""
    health_per_level: float = 10.0
    mana_per_level: float = 5.0
    stamina_per_level: float = 8.0
    damage_per_level: float = 2.0
    defense_per_level: float = 0.5
    exp_base: float = 100.0
    exp_multiplier: float = 1.5


class StatsLoader:
    """
    Loads character and enemy statistics from configuration files.
    Replaces hardcoded values with data-driven approach.
    """
    
    _instance: StatsLoader | None = None
    _config_manager: ConfigManager | None = None
    
    def __new__(cls, config_dir: Path | None = None) -> StatsLoader:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config_dir: Path | None = None):
        if self._initialized:
            return
        
        self._config_manager = ConfigManager(config_dir)
        self._base_stats_cache: CharacterBaseStats | None = None
        self._class_multipliers_cache: dict[str, ClassMultiplier] = {}
        self._level_scaling_cache: LevelScaling | None = None
        self._enemy_stats_cache: dict[str, dict[str, Any]] = {}
        
        self._load_all_configs()
        self._initialized = True
        logger.info("StatsLoader initialized with data-driven configs")
    
    @classmethod
    def get_instance(cls, config_dir: Path | None = None) -> StatsLoader:
        """Get singleton instance of StatsLoader."""
        if cls._instance is None:
            cls._instance = cls(config_dir)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for testing)."""
        cls._instance = None
    
    def _load_all_configs(self) -> None:
        """Load all configuration files into cache."""
        # Load base stats
        base = self._config_manager.get("characters.base", {})
        if base:
            self._base_stats_cache = CharacterBaseStats(
                health=base.get("health", 100.0),
                mana=base.get("mana", 50.0),
                stamina=base.get("stamina", 100.0),
                defense=base.get("defense", 5.0),
                physical_damage=base.get("physical_damage", 20.0),
                magical_damage=base.get("magical_damage", 0.0),
                attack_speed=base.get("attack_speed", 1.0),
                attack_range=base.get("attack_range", 2.0),
                critical_chance=base.get("critical_chance", 5.0),
                critical_damage=base.get("critical_damage", 150.0),
                dodge_chance=base.get("dodge_chance", 0.0),
                magic_resistance=base.get("magic_resistance", 0.0),
                speed=base.get("speed", 8.0),
                health_regen=base.get("health_regen", 1.0),
                mana_regen=base.get("mana_regen", 5.0),
                stamina_regen=base.get("stamina_regen", 10.0)
            )
            logger.debug(f"Loaded base stats: {self._base_stats_cache}")
        
        # Load class multipliers
        classes = self._config_manager.get("characters.classes", {})
        for class_name, class_data in classes.items():
            self._class_multipliers_cache[class_name] = ClassMultiplier(
                health_mult=class_data.get("health_mult", 1.0),
                mana_mult=class_data.get("mana_mult", 1.0),
                stamina_mult=class_data.get("stamina_mult", 1.0),
                defense_mult=class_data.get("defense_mult", 1.0),
                physical_damage_mult=class_data.get("physical_damage_mult", 1.0),
                magical_damage_mult=class_data.get("magical_damage_mult", 1.0),
                crit_chance_bonus=class_data.get("crit_chance_bonus", 0.0),
                crit_damage_bonus=class_data.get("crit_damage_bonus", 0.0),
                dodge_chance_bonus=class_data.get("dodge_chance_bonus", 0.0),
                speed_mult=class_data.get("speed_mult", 1.0)
            )
        logger.debug(f"Loaded {len(self._class_multipliers_cache)} class multipliers")
        
        # Load level scaling
        scaling = self._config_manager.get("characters.level_scaling", {})
        if scaling:
            self._level_scaling_cache = LevelScaling(
                health_per_level=scaling.get("health_per_level", 10.0),
                mana_per_level=scaling.get("mana_per_level", 5.0),
                stamina_per_level=scaling.get("stamina_per_level", 8.0),
                damage_per_level=scaling.get("damage_per_level", 2.0),
                defense_per_level=scaling.get("defense_per_level", 0.5),
                exp_base=scaling.get("exp_base", 100.0),
                exp_multiplier=scaling.get("exp_multiplier", 1.5)
            )
            logger.debug(f"Loaded level scaling: {self._level_scaling_cache}")
    
    def get_base_stats(self) -> CharacterBaseStats:
        """Get base character statistics."""
        if self._base_stats_cache is None:
            logger.warning("Base stats not loaded, returning defaults")
            return CharacterBaseStats()
        return self._base_stats_cache
    
    def get_class_multiplier(self, character_class: str) -> ClassMultiplier:
        """Get multiplier for a specific character class."""
        if character_class in self._class_multipliers_cache:
            return self._class_multipliers_cache[character_class]
        
        logger.warning(f"Class '{character_class}' not found, using warrior defaults")
        return self._class_multipliers_cache.get("warrior", ClassMultiplier())
    
    def get_stats_for_class(self, character_class: str, level: int = 1) -> CharacterBaseStats:
        """
        Calculate final stats for a character class at a specific level.
        Applies base stats, class multipliers, and level scaling.
        """
        base = self.get_base_stats()
        multiplier = self.get_class_multiplier(character_class)
        scaling = self._level_scaling_cache or LevelScaling()
        
        levels_gained = max(0, level - 1)
        
        return CharacterBaseStats(
            health=(base.health * multiplier.health_mult) + (levels_gained * scaling.health_per_level),
            mana=(base.mana * multiplier.mana_mult) + (levels_gained * scaling.mana_per_level),
            stamina=(base.stamina * multiplier.stamina_mult) + (levels_gained * scaling.stamina_per_level),
            defense=(base.defense * multiplier.defense_mult) + (levels_gained * scaling.defense_per_level),
            physical_damage=(base.physical_damage * multiplier.physical_damage_mult) + (levels_gained * scaling.damage_per_level),
            magical_damage=(base.magical_damage * multiplier.magical_damage_mult) + (levels_gained * scaling.damage_per_level),
            attack_speed=base.attack_speed,
            attack_range=base.attack_range,
            critical_chance=base.critical_chance + multiplier.crit_chance_bonus,
            critical_damage=base.critical_damage + multiplier.crit_damage_bonus,
            dodge_chance=base.dodge_chance + multiplier.dodge_chance_bonus,
            magic_resistance=base.magic_resistance,
            speed=base.speed * multiplier.speed_mult,
            health_regen=base.health_regen,
            mana_regen=base.mana_regen,
            stamina_regen=base.stamina_regen
        )
    
    def get_enemy_stats(self, enemy_type: str, level: int = 1) -> dict[str, Any]:
        """Get scaled stats for an enemy type at a specific level."""
        return self._config_manager.get_enemy_stats(enemy_type, level)
    
    def get_exp_required(self, level: int) -> float:
        """Calculate experience required to reach the next level."""
        scaling = self._level_scaling_cache or LevelScaling()
        return scaling.exp_base * (scaling.exp_multiplier ** (level - 1))
    
    def reload_configs(self) -> None:
        """Reload all configurations from disk (for hot-reload during balancing)."""
        if self._config_manager:
            self._config_manager.reload()
            self._base_stats_cache = None
            self._class_multipliers_cache.clear()
            self._level_scaling_cache = None
            self._enemy_stats_cache.clear()
            self._load_all_configs()
            logger.info("Stats configs reloaded")
    
    def export_current_stats(self) -> dict[str, Any]:
        """Export current stats configuration for debugging/balancing."""
        return {
            "base": {
                "health": self._base_stats_cache.health if self._base_stats_cache else 100.0,
                "mana": self._base_stats_cache.mana if self._base_stats_cache else 50.0,
                "stamina": self._base_stats_cache.stamina if self._base_stats_cache else 100.0,
            },
            "classes": {
                name: {
                    "health_mult": mult.health_mult,
                    "physical_damage_mult": mult.physical_damage_mult,
                    "crit_chance_bonus": mult.crit_chance_bonus,
                }
                for name, mult in self._class_multipliers_cache.items()
            },
            "level_scaling": {
                "health_per_level": self._level_scaling_cache.health_per_level if self._level_scaling_cache else 10.0,
                "damage_per_level": self._level_scaling_cache.damage_per_level if self._level_scaling_cache else 2.0,
            }
        }
