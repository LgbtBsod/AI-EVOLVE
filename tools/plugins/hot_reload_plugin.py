"""
Plugin 8: Code Hot-Reload Plugin
Allows updating game logic without restarting the session.
Uses importlib to reload modules dynamically.
"""
import logging
import importlib
import sys
from typing import List, Dict, Any

logger = logging.getLogger("HotReloadPlugin")

class HotReloadPlugin:
    """
    Enables live code updates for specific game modules.
    Useful for tweaking balance or AI behavior mid-session.
    """
    
    SAFE_MODULES = [
        'src.core.game_master',
        'src.features.combat_plugin',
        'tools.plugins.auto_balance_plugin'
    ]
    
    def __init__(self):
        self.reload_history: List[Dict] = []
        
    def reload_module(self, module_name: str) -> bool:
        if module_name not in self.SAFE_MODULES:
            logger.warning(f"Blocked unsafe reload: {module_name}")
            return False
            
        try:
            if module_name in sys.modules:
                module = sys.modules[module_name]
                importlib.reload(module)
                logger.info(f"Hot-reloaded: {module_name}")
                self.reload_history.append({"module": module_name, "status": "success"})
                return True
            else:
                logger.error(f"Module not loaded: {module_name}")
                return False
        except Exception as e:
            logger.error(f"Reload failed: {e}")
            self.reload_history.append({"module": module_name, "status": "failed", "error": str(e)})
            return False
            
    def get_history(self) -> List[Dict]:
        return self.reload_history[-10:]  # Last 10 reloads

    def check_syntax(self, code: str, module_name: str) -> bool:
        """Validate code before applying."""
        try:
            compile(code, f"<{module_name}>", 'exec')
            return True
        except SyntaxError as e:
            logger.error(f"Syntax error in {module_name}: {e}")
            return False
