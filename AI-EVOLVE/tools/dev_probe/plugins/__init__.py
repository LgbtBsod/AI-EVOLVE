"""
Plugin system for Dev Probe.
Allows modular analysis of game state through plugins.
"""
from .base import DevProbePlugin, PluginReport, PluginManager

# Import built-in plugins
from .toughness_plugin import ToughnessPlugin
from .effects_plugin import EffectsPlugin
from .combat_plugin import CombatPlugin

__all__ = [
    'DevProbePlugin',
    'PluginReport', 
    'PluginManager',
    'ToughnessPlugin',
    'EffectsPlugin',
    'CombatPlugin',
]
