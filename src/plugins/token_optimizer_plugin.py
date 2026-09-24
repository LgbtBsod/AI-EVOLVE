"""
Token Optimizer Plugin for Dev Probe
Цель: Уменьшение потребления токенов LLM на 40-60% за счет умного кэширования и сжатия контекста.
"""

from typing import Dict, List, Any, Optional
import hashlib
import json
import time
from src.core.event_system import EventSystem
from src.core.base_plugin import BasePlugin

class TokenOptimizerPlugin(BasePlugin):
    """Плагин для оптимизации токенов при работе AI-агентов."""
    
    def __init__(self, event_system: EventSystem):
        super().__init__("TokenOptimizer", "TokenOptimizer", "1.0.0")
        self.event_system = event_system
        self.state_cache: Dict[str, str] = {}
        self.token_count_saved = 0
        self.compression_ratio = 0.6  # Целевой коэффициент сжатия
        
        # Конфигурация
        self.cache_ttl = 300  # секунд
        self.min_state_diff_for_update = 0.05  # Порог значимости изменений (5%)
        
    def enable(self) -> None:
        """Включение плагина (alias для start)."""
        if not self.enabled:
            self.initialize()
            self.start()
            self.on_enable()
            
    def disable(self) -> None:
        """Выключение плагина (alias для stop)."""
        if self.enabled:
            self.on_disable()
            self.stop()
            
    @property
    def enabled(self) -> bool:
        """Проверка включен ли плагин."""
        from src.core.architecture import LifecycleState
        return self.system_state == LifecycleState.RUNNING
        
    @property
    def logger(self):
        """Логгер для плагина."""
        import logging
        return logging.getLogger(self.plugin_id)
        
    def on_enable(self) -> None:
        self.logger.info("TokenOptimizer enabled. Caching active.")
        self.event_system.subscribe("agent.think_start", self._on_think_start)
        self.event_system.subscribe("agent.action_complete", self._on_action_complete)
        
    def on_disable(self) -> None:
        self.event_system.unsubscribe("agent.think_start", self._on_think_start)
        self.event_system.unsubscribe("agent.action_complete", self._on_action_complete)
        self.state_cache.clear()
        
    def _generate_state_hash(self, state: Dict[str, Any]) -> str:
        """Генерирует хэш состояния для кэширования."""
        # Исключаем временные данные (timestamp, fps)
        clean_state = {k: v for k, v in state.items() if k not in ['timestamp', 'fps', 'frame']}
        state_str = json.dumps(clean_state, sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()
    
    def _compress_context(self, full_history: List[Dict]) -> str:
        """Сжимает историю действий, оставляя только ключевые события."""
        if len(full_history) <= 5:
            return json.dumps(full_history)
        
        # Оставляем первое, последнее и 3 ключевых события (бой, лут, уровень)
        compressed = [full_history[0], full_history[-1]]
        key_events = [e for e in full_history[1:-1] if e.get('type') in ['combat_start', 'loot', 'level_up', 'death']]
        compressed.extend(key_events[-3:])
        
        estimated_save = len(json.dumps(full_history)) - len(json.dumps(compressed))
        self.token_count_saved += int(estimated_save * 0.5) # Грубая оценка токенов
        
        return json.dumps(compressed)
    
    def _on_think_start(self, sender: Any, event: Any) -> Optional[Dict[str, Any]]:
        """Перехват начала мышления агента. Проверяет кэш."""
        data = event.event_data if hasattr(event, 'event_data') else {}
        current_state = data.get('state', {})
        state_hash = self._generate_state_hash(current_state)
        
        if state_hash in self.state_cache:
            # Состояние не изменилось значительно, предлагаем пропустить шаг или использовать кэш
            self.logger.debug(f"State cache hit: {state_hash[:8]}... Skipping deep analysis.")
            return {
                "skip_thinking": True,
                "cached_action": self.state_cache[state_hash],
                "reason": "state_unchanged"
            }
        return None
    
    def _on_action_complete(self, sender: Any, event: Any) -> None:
        """Обновление кэша после действия."""
        data = event.event_data if hasattr(event, 'event_data') else {}
        state = data.get('state', {})
        action = data.get('action', {})
        state_hash = self._generate_state_hash(state)
        
        # Сохраняем только успешные действия в кэш
        if action.get('success', True):
            self.state_cache[state_hash] = action
            self.logger.debug(f"State cache updated: {state_hash[:8]}...")
            
        # Очистка старого кэша (упрощенная)
        if len(self.state_cache) > 100:
            # Удаляем половину oldest entries (в реальной реализации нужен LRU)
            keys = list(self.state_cache.keys())[:50]
            for k in keys:
                del self.state_cache[k]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "cache_size": len(self.state_cache),
            "tokens_saved_estimate": self.token_count_saved,
            "compression_ratio": self.compression_ratio
        }
