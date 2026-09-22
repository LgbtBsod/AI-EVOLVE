"""
Test Accelerator Plugin for Dev Probe
Цель: Ускорение тестовых сессий за счет автоматического пропуска "скучных" фаз и форсирования событий.
"""

from typing import Dict, List, Any, Optional
import time
from src.core.event_system import EventSystem
from src.core.base_plugin import BasePlugin

class TestAcceleratorPlugin(BasePlugin):
    """Плагин для ускорения симуляции и тестирования."""
    
    def __init__(self, event_system: EventSystem):
        super().__init__("TestAccelerator", "TestAccelerator", "1.0.0")
        self.event_system = event_system
        self.idle_threshold = 5.0  # секунд бездействия перед ускорением
        self.last_action_time = time.time()
        self.acceleration_factor = 10.0
        self.events_forced = 0
        
        # Авто-фикс балансовых ошибок
        self.auto_fix_enabled = True
        
    def enable(self) -> None:
        """Включение плагина."""
        if not self.enabled:
            self.initialize()
            self.start()
            self.on_enable()
            
    def disable(self) -> None:
        """Выключение плагина."""
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
        self.logger.info("TestAccelerator enabled. Simulation speed-up active.")
        self.event_system.subscribe("agent.action_complete", self._on_action)
        self.event_system.subscribe("simulation.update", self._on_update)
        
    def on_disable(self) -> None:
        self.event_system.unsubscribe("agent.action_complete", self._on_action)
        self.event_system.unsubscribe("simulation.update", self._on_update)
        
    def _on_action(self, sender: Any, event: Any) -> None:
        """Сброс таймера бездействия при любом действии."""
        self.last_action_time = time.time()
        
    def _on_update(self, sender: Any, event: Any) -> Optional[Dict[str, Any]]:
        """Проверка на простой и ускорение времени или форсирование событий."""
        data = event.event_data if hasattr(event, 'event_data') else {}
        current_time = time.time()
        idle_duration = current_time - self.last_action_time
        
        if idle_duration > self.idle_threshold:
            self.logger.warning(f"Idle detected ({idle_duration:.2f}s). Forcing combat event...")
            self._force_combat_encounter(data.get('agent_id'))
            return {"accelerated": True, "reason": "idle_timeout"}
            
        return None
    
    def _force_combat_encounter(self, agent_id: str) -> None:
        """Принудительно создает событие боя рядом с агентом."""
        self.events_forced += 1
        self.event_system.emit("world.spawn_enemy_nearby", {
            "target_agent": agent_id,
            "enemy_type": "slime", # Слабый враг для быстрого теста
            "level_delta": 0
        })
        self.logger.info(f"Forced combat encounter for {agent_id}")
        
    def auto_fix_stats(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Автоматически исправляет частые ошибки в статах (например, шанс крита > 1)."""
        if not self.auto_fix_enabled:
            return stats
            
        fixed_stats = stats.copy()
        
        # Исправление шанса крита
        if 'critical_chance' in fixed_stats:
            if fixed_stats['critical_chance'] > 1.0:
                self.logger.warning(f"Auto-fixing critical_chance: {fixed_stats['critical_chance']} -> 0.25")
                fixed_stats['critical_chance'] = 0.25
                
        # Исправление отрицательного здоровья
        if 'health' in fixed_stats and fixed_stats['health'] < 0:
            fixed_stats['health'] = 0
            
        # Исправление отрицательного урона
        if 'damage' in fixed_stats and fixed_stats['damage'] < 0:
            fixed_stats['damage'] = 1
            
        return fixed_stats

    def get_stats(self) -> Dict[str, Any]:
        return {
            "events_forced": self.events_forced,
            "idle_threshold": self.idle_threshold,
            "auto_fix_enabled": self.auto_fix_enabled
        }
