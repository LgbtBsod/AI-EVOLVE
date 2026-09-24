"""L8 Probe Config Loader - Lua configuration management

Loads probe configuration from Lua files using mlua.
Provides profile-based configs (quick/standard/detailed).
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

try:
    # Единый загрузчик Lua-контента проекта (rust_core/mlua или lupa, данные
    # одним JSON). Раньше здесь была своя копия конвертера lupa -> dict,
    # которая превращала Lua-массивы в словари {1: ..., 2: ...}.
    from tools import lua_bridge
    LUPA_AVAILABLE = bool(lua_bridge.available_backends())
except ImportError:
    lua_bridge = None
    LUPA_AVAILABLE = False
if not LUPA_AVAILABLE:
    logging.warning("no Lua backend (rust_core / lupa), Lua config loading disabled")

logger = logging.getLogger(__name__)


class LuaConfigLoader:
    """Load and manage probe configuration from Lua files"""
    
    def __init__(self, lua_path: Optional[str] = None):
        """
        Initialize config loader.
        
        Args:
            lua_path: Path to probe_config.lua
                     If None, searches standard locations
        """
        self.lua_path = self._find_lua_config(lua_path)
        self._config_cache: Dict[str, Dict[str, Any]] = {}
        self._lua_runtime = lua_bridge if LUPA_AVAILABLE else None
    
    def _find_lua_config(self, lua_path: Optional[str]) -> Optional[Path]:
        """Find probe_config.lua in standard locations"""
        if lua_path:
            path = Path(lua_path)
            if path.exists():
                return path
            logger.warning(f"Specified Lua config not found: {lua_path}")
            return None
        
        # Search standard locations
        search_paths = [
            Path(__file__).parent.parent.parent / 'lua_content' / 'probe_config.lua',
            Path.cwd() / 'lua_content' / 'probe_config.lua',
            Path.cwd() / 'config' / 'probe_config.lua',
        ]
        
        for path in search_paths:
            if path.exists():
                logger.debug(f"Found Lua config at {path}")
                return path
        
        logger.info("No Lua config found, will use defaults")
        return None
    
    def load_config(self, profile: str = 'standard') -> Dict[str, Any]:
        """
        Load configuration from Lua file.
        
        Args:
            profile: Configuration profile name (quick/standard/detailed)
            
        Returns:
            Configuration dict ready for ProbeAnalyzer
        """
        cache_key = f"{self.lua_path}:{profile}"
        if cache_key in self._config_cache:
            logger.debug(f"Returning cached config for {profile}")
            return self._config_cache[cache_key]
        
        config = self._load_from_lua(profile) if self.lua_path else self._get_defaults(profile)
        
        self._config_cache[cache_key] = config
        logger.info(f"Loaded {profile} config from {self.lua_path or 'defaults'}")
        return config
    
    def _load_from_lua(self, profile: str) -> Dict[str, Any]:
        """Load and parse Lua configuration file"""
        if not self._lua_runtime or not self.lua_path:
            return self._get_defaults(profile)
        
        try:
            config = lua_bridge.load(Path(self.lua_path))
            
            # Apply profile overrides if specified
            if profile != 'standard' and 'profiles' in config:
                profile_config = config['profiles'].get(profile, {})
                if profile_config:
                    logger.info(f"Applying {profile} profile overrides")
                    config.update(profile_config)
            
            # Extract only the parameters needed by Rust analyzer
            rust_config = {
                'blank_frame_stddev_threshold': config.get('blank_frame_stddev_threshold', 2.0),
                'visual_hash_bits': config.get('visual_hash_bits', 16),
                'hamming_threshold': config.get('hamming_threshold', 8),
                'motion_detection_threshold': config.get('motion_detection_threshold', 5.0),
                'brightness_anomaly_threshold': config.get('brightness_anomaly_threshold', 30.0),
                'ssim_threshold': config.get('ssim_threshold', 0.95),
            }
            
            # Store full config for issue detection rules
            rust_config['_full_config'] = config
            
            return rust_config
            
        except Exception as e:
            logger.error(f"Failed to load Lua config: {e}")
            return self._get_defaults(profile)
    
    def _get_defaults(self, profile: str) -> Dict[str, Any]:
        """Get default configuration for a profile"""
        profiles = {
            'quick': {
                'blank_frame_stddev_threshold': 2.0,
                'visual_hash_bits': 8,
                'hamming_threshold': 10,
                'motion_detection_threshold': 8.0,
                'brightness_anomaly_threshold': 40.0,
                'ssim_threshold': 0.90,
            },
            'standard': {
                'blank_frame_stddev_threshold': 2.0,
                'visual_hash_bits': 16,
                'hamming_threshold': 8,
                'motion_detection_threshold': 5.0,
                'brightness_anomaly_threshold': 30.0,
                'ssim_threshold': 0.95,
            },
            'detailed': {
                'blank_frame_stddev_threshold': 1.5,
                'visual_hash_bits': 32,
                'hamming_threshold': 5,
                'motion_detection_threshold': 3.0,
                'brightness_anomaly_threshold': 20.0,
                'ssim_threshold': 0.98,
            },
        }
        
        return profiles.get(profile, profiles['standard'])
    
    def get_issue_rules(self) -> list:
        """Get issue detection rules from config"""
        if not self.lua_path or not self._config_cache:
            return self._get_default_issue_rules()
        
        # Find most recent loaded config
        for config in reversed(self._config_cache.values()):
            full_config = config.get('_full_config', {})
            if 'issues' in full_config:
                return full_config['issues']
        
        return self._get_default_issue_rules()
    
    def _get_default_issue_rules(self) -> list:
        """Default issue detection rules"""
        return [
            {
                'name': 'broken_ui',
                'description': 'Damage dealt but no damage numbers visible',
                'condition': 'combat_damage > 0 AND damage_numbers_count == 0',
            },
            {
                'name': 'render_blackout',
                'description': 'Black screen while game state is active',
                'condition': 'brightness_stddev < 2.0 AND entities_alive > 0',
            },
            {
                'name': 'frozen_game',
                'description': 'No motion detected for extended period',
                'condition': 'motion_ratio < 0.01 FOR 10 FRAMES',
            },
            {
                'name': 'flash_bang',
                'description': 'Sudden brightness change (flash/fade)',
                'condition': 'brightness_delta > 30.0',
            },
        ]
