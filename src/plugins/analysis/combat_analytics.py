"""
Plugin: Combat Analytics & Token Saver
Цель: Ускорение тестов, снижение токенов, глубокий анализ боевки
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import time
import json
from pathlib import Path

@dataclass
class CombatMetrics:
    """Метрики одной симуляции боя"""
    duration_ms: float = 0.0
    total_turns: int = 0
    damage_dealt: int = 0
    damage_taken: int = 0
    critical_hits: int = 0
    dodges: int = 0
    effects_applied: int = 0
    tokens_saved: int = 0
    ai_decisions: List[str] = field(default_factory=list)

class CombatAnalyticsPlugin:
    """
    Плагин для анализа боевых сессий и оптимизации токенов
    
    Функции:
    1. Кэширование повторяющихся состояний (экономия токенов)
    2. Предсказание исхода боя (ранний выход)
    3. Генерация кратких саммари вместо полных логов
    4. Выявление аномалий баланса
    """
    
    def __init__(self):
        self.session_metrics: List[CombatMetrics] = []
        self.state_cache: Dict[str, Any] = {}
        self.anomalies: List[Dict[str, Any]] = []
        self.enabled = True
        
    def start_session(self) -> str:
        """Начать новую сессию анализа"""
        session_id = f"session_{int(time.time() * 1000)}"
        return session_id
        
    def record_turn(self, 
                    turn_data: Dict[str, Any], 
                    state_hash: str) -> Optional[Dict[str, Any]]:
        """
        Записать ход. Если состояние уже было - вернуть кэш (экономия токенов)
        
        Args:
            turn_data: Данные хода
            state_hash: Хэш текущего состояния
            
        Returns:
            Кэшированный результат или None если состояние новое
        """
        if not self.enabled:
            return None
            
        if state_hash in self.state_cache:
            # Экономия токенов: возвращаем готовый ответ
            cached = self.state_cache[state_hash]
            cached['tokens_saved'] = cached.get('tokens_saved', 0) + cached.get('estimated_tokens', 50)
            return cached
            
        # Новое состояние - обрабатываем и инициализируем tokens_saved
        turn_data['tokens_saved'] = 0
        turn_data['estimated_tokens'] = turn_data.get('estimated_tokens', 50)
        self.state_cache[state_hash] = turn_data
        return None
        
    def predict_outcome(self, 
                       attacker_hp: int, 
                       defender_hp: int,
                       avg_damage: float) -> Optional[str]:
        """
        Предсказать исход боя для раннего завершения (ускорение тестов)
        
        Returns:
            'attacker_wins', 'defender_wins', или None (неясно)
        """
        if avg_damage <= 0:
            return None
            
        turns_to_kill_defender = defender_hp / avg_damage
        turns_to_kill_attacker = attacker_hp / (avg_damage * 0.8)  # Defender deals less
        
        if turns_to_kill_defender < turns_to_kill_attacker - 2:
            return 'attacker_wins'
        elif turns_to_kill_attacker < turns_to_kill_defender - 2:
            return 'defender_wins'
            
        return None  # Бой будет напряженным
        
    def generate_summary(self, metrics: CombatMetrics) -> str:
        """
        Сгенерировать краткое саммари вместо полного лога (экономия токенов)
        """
        outcome = "Победа" if metrics.damage_dealt > metrics.damage_taken else "Поражение"
        efficiency = metrics.damage_dealt / max(1, metrics.total_turns)
        
        summary = (
            f"[{outcome}] {metrics.total_turns} ходов, "
            f"урон: {metrics.damage_dealt}/{metrics.damage_taken}, "
            f"криты: {metrics.critical_hits}, уклонения: {metrics.dodges}, "
            f"эффектов: {metrics.effects_applied}, "
            f"токенов сэкономлено: {metrics.tokens_saved}"
        )
        
        return summary
        
    def detect_anomalies(self, metrics: CombatMetrics) -> List[str]:
        """Выявить аномалии баланса"""
        anomalies = []
        
        # Аномалия 1: Бой слишком короткий (< 3 ходов)
        if metrics.total_turns < 3:
            anomalies.append("ONE_SHOT_RISK: Бой завершен слишком быстро")
            
        # Аномалия 2: Нет критов/уклонений за долгий бой
        if metrics.total_turns > 10 and metrics.critical_hits == 0:
            anomalies.append("CRIT_RATE_LOW: Криты не срабатывают")
            
        # Аномалия 3: Урон слишком высокий/низкий
        avg_dmg = metrics.damage_dealt / max(1, metrics.total_turns)
        if avg_dmg > 100:
            anomalies.append("DAMAGE_TOO_HIGH: Средний урон > 100 за ход")
        elif avg_dmg < 5:
            anomalies.append("DAMAGE_TOO_LOW: Средний урон < 5 за ход")
            
        # Аномалия 4: Эффекты не применяются
        if metrics.total_turns > 5 and metrics.effects_applied == 0:
            anomalies.append("EFFECTS_UNUSED: Баффы/дебаффы не используются")
            
        self.anomalies.extend([{
            'session': len(self.session_metrics),
            'anomalies': anomalies
        }])
        
        return anomalies
        
    def finalize_session(self, metrics: CombatMetrics) -> Dict[str, Any]:
        """Завершить сессию и вернуть полную статистику"""
        self.session_metrics.append(metrics)
        
        total_tokens_saved = sum(m.tokens_saved for m in self.session_metrics)
        avg_duration = sum(m.duration_ms for m in self.session_metrics) / len(self.session_metrics)
        
        report = {
            'sessions_completed': len(self.session_metrics),
            'total_tokens_saved': total_tokens_saved,
            'avg_battle_duration_ms': avg_duration,
            'anomalies_detected': len(self.anomalies),
            'cache_hit_rate': len(self.state_cache) / max(1, len(self.session_metrics)),
        }
        
        return report
        
    def export_report(self, path: str = "combat_analysis_report.json"):
        """Экспортировать полный отчет в JSON"""
        report = {
            'summary': self.finalize_session(CombatMetrics()),
            'anomalies': self.anomalies,
            'session_count': len(self.session_metrics),
        }
        
        with open(path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
            
        print(f"📊 Отчет экспортирован: {path}")
        return path


# Singleton instance
analytics_plugin = CombatAnalyticsPlugin()
