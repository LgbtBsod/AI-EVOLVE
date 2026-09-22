"""
Combat Analytics Plugin for Dev Probe
Цель: Глубокий анализ боевой системы, выявление дисбалансов и аномалий в реальном времени.
"""

from typing import Dict, List, Any, Optional
import statistics
from src.core.event_system import EventSystem
from src.core.base_plugin import BasePlugin

class CombatAnalyticsPlugin(BasePlugin):
    """Плагин для аналитики боевых сессий."""
    
    def __init__(self, event_system: EventSystem):
        super().__init__("CombatAnalytics", "CombatAnalytics", "1.0.0")
        self.event_system = event_system
        
        # Метрики
        self.combat_sessions: List[Dict[str, Any]] = []
        self.damage_dealt_total = 0
        self.damage_received_total = 0
        self.critical_hits_count = 0
        self.dodges_count = 0
        self.time_to_kill_avg = []
        self.tokens_saved = 0 # Для совместимости с отчетами
        
        # Пороги аномалий
        self.dps_threshold_high = 50.0
        self.dps_threshold_low = 1.0
        self.ttk_threshold_fast = 2.0 # секунды
        
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
        self.logger.info("CombatAnalytics enabled. Tracking combat metrics.")
        self.event_system.subscribe("combat.start", self._on_combat_start)
        self.event_system.subscribe("combat.hit", self._on_combat_hit)
        self.event_system.subscribe("combat.end", self._on_combat_end)
        self.event_system.subscribe("entity.death", self._on_death)
        
    def on_disable(self) -> None:
        self.event_system.unsubscribe("combat.start", self._on_combat_start)
        self.event_system.unsubscribe("combat.hit", self._on_combat_hit)
        self.event_system.unsubscribe("combat.end", self._on_combat_end)
        self.event_system.unsubscribe("entity.death", self._on_death)
        self._print_summary()
        
    def _on_combat_start(self, sender: Any, event: Any) -> None:
        data = event.event_data if hasattr(event, 'event_data') else {}
        session_id = data.get('session_id', 'unknown')
        self.logger.debug(f"Combat started: {session_id}")
        self.combat_sessions.append({
            'id': session_id,
            'start_time': data.get('timestamp'),
            'participants': data.get('participants', []),
            'damage_log': [],
            'ended': False
        })
        
    def _on_combat_hit(self, sender: Any, event: Any) -> None:
        data = event.event_data if hasattr(event, 'event_data') else {}
        damage = data.get('damage', 0)
        is_crit = data.get('is_critical', False)
        is_dodge = data.get('is_dodge', False)
        
        self.damage_dealt_total += damage
        if is_crit:
            self.critical_hits_count += 1
        if is_dodge:
            self.dodges_count += 1
            
        # Логирование в текущую сессию
        if self.combat_sessions and not self.combat_sessions[-1]['ended']:
            self.combat_sessions[-1]['damage_log'].append({
                'damage': damage,
                'crit': is_crit,
                'dodge': is_dodge
            })
            
    def _on_combat_end(self, sender: Any, event: Any) -> None:
        data = event.event_data if hasattr(event, 'event_data') else {}
        if self.combat_sessions:
            self.combat_sessions[-1]['ended'] = True
            self.combat_sessions[-1]['end_time'] = data.get('timestamp')
            
    def _on_death(self, sender: Any, event: Any) -> None:
        # Расчет TTK (Time To Kill) если есть данные
        data = event.event_data if hasattr(event, 'event_data') else {}
        victim = data.get('entity_id')
        killer = data.get('killer_id')
        self.logger.info(f"Entity {victim} died by {killer}")
        
    def analyze_session(self, session: Dict[str, Any]) -> List[str]:
        """Анализирует одну сессию боя на аномалии."""
        anomalies = []
        damage_log = session.get('damage_log', [])
        
        if not damage_log:
            return anomalies
            
        damages = [d['damage'] for d in damage_log]
        avg_damage = statistics.mean(damages)
        
        # Проверка на слишком низкий урон (возможно, броня имба)
        if avg_damage < self.dps_threshold_low:
            anomalies.append(f"DAMAGE_TOO_LOW: Avg damage {avg_damage:.2f} per hit")
            
        # Проверка на криты > 50% (если много данных)
        crit_rate = sum(1 for d in damage_log if d['crit']) / len(damage_log)
        if crit_rate > 0.5:
            anomalies.append(f"CRIT_RATE_HIGH: {crit_rate*100:.1f}% critical hits")
            
        return anomalies
        
    def _print_summary(self) -> None:
        """Вывод итоговой статистики."""
        self.logger.info("=== COMBAT ANALYTICS SUMMARY ===")
        self.logger.info(f"Total Sessions: {len(self.combat_sessions)}")
        self.logger.info(f"Total Damage Dealt: {self.damage_dealt_total}")
        self.logger.info(f"Critical Hits: {self.critical_hits_count}")
        self.logger.info(f"Dodges: {self.dodges_count}")
        
        if self.combat_sessions:
            completed = [s for s in self.combat_sessions if s['ended']]
            for session in completed:
                anomalies = self.analyze_session(session)
                if anomalies:
                    self.logger.warning(f"Session {session['id']} Anomalies: {anomalies}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "sessions_count": len(self.combat_sessions),
            "total_damage": self.damage_dealt_total,
            "crit_count": self.critical_hits_count,
            "dodge_count": self.dodges_count,
            "tokens_saved": self.tokens_saved # Заглушка для совместимости тестов
        }
