"""State Analyzer - Анализ состояния и детекция аномалий."""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class AnomalyType(Enum):
    """Типы аномалий."""
    LOW_HEALTH = "low_health"
    NEGATIVE_TOUGHNESS = "negative_toughness"
    EXCESSIVE_DAMAGE = "excessive_damage"
    MISSING_ENTITY = "missing_entity"
    DUPLICATE_EFFECT = "duplicate_effect"
    RESOURCE_OVERFLOW = "resource_overflow"
    UNEXPECTED_STATE = "unexpected_state"
    PERFORMANCE_SPIKE = "performance_spike"


class Severity(Enum):
    """Уровень серьезности."""
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Anomaly:
    """Аномалия в состоянии игры."""
    anomaly_type: AnomalyType
    severity: Severity
    description: str
    entity_id: Optional[str] = None
    frame: int = 0
    timestamp: float = 0.0
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.anomaly_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "entity_id": self.entity_id,
            "frame": self.frame,
            "timestamp": self.timestamp,
            "data": self.data or {}
        }


class StateAnalyzer:
    """Анализатор состояния игры для обнаружения аномалий."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.low_hp_threshold = self.config.get("low_hp_threshold", 0.2)
        self.excessive_damage_threshold = self.config.get("excessive_damage_threshold", 1000)
        self.max_effect_stacks = self.config.get("max_effect_stacks", 99)
        
        # История для сравнения
        self.previous_state: Optional[Dict] = None
        self.damage_history: List[float] = []
    
    def analyze_snapshot(self, snapshot: Dict[str, Any]) -> List[Anomaly]:
        """Анализировать снимок состояния на наличие аномалий."""
        anomalies = []
        
        state = snapshot.get("state", {})
        timestamp = snapshot.get("timestamp", 0.0)
        frame = snapshot.get("frame", 0)
        
        entities = state.get("entities", [])
        
        for entity in entities:
            entity_anomalies = self._analyze_entity(entity, timestamp, frame)
            anomalies.extend(entity_anomalies)
        
        # Анализ глобального состояния
        global_anomalies = self._analyze_global_state(state, timestamp, frame)
        anomalies.extend(global_anomalies)
        
        # Сохранить состояние для следующего сравнения
        self.previous_state = state
        
        return anomalies
    
    def _analyze_entity(
        self, 
        entity: Dict[str, Any], 
        timestamp: float, 
        frame: int
    ) -> List[Anomaly]:
        """Анализировать сущность на аномалии."""
        anomalies = []
        entity_id = entity.get("id", "unknown")
        
        # Низкое HP
        max_health = entity.get("max_health", 0)
        health = entity.get("health", 0)
        
        if max_health > 0 and health >= 0:
            hp_ratio = health / max_health
            if hp_ratio < self.low_hp_threshold and entity.get("is_alive", True):
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.LOW_HEALTH,
                    severity=Severity.MEDIUM if hp_ratio > 0.1 else Severity.HIGH,
                    description=f"Entity {entity_id} has low health ({hp_ratio:.1%})",
                    entity_id=entity_id,
                    frame=frame,
                    timestamp=timestamp,
                    data={"hp_ratio": hp_ratio, "health": health, "max_health": max_health}
                ))
        
        # Отрицательная стойкость
        toughness = entity.get("toughness", {})
        if isinstance(toughness, dict):
            toughness_current = toughness.get("current", 0)
            if toughness_current < 0:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.NEGATIVE_TOUGHNESS,
                    severity=Severity.MEDIUM,
                    description=f"Entity {entity_id} has negative toughness ({toughness_current})",
                    entity_id=entity_id,
                    frame=frame,
                    timestamp=timestamp,
                    data={"toughness": toughness_current}
                ))
        
        return anomalies
    
    def _analyze_global_state(
        self, 
        state: Dict[str, Any], 
        timestamp: float, 
        frame: int
    ) -> List[Anomaly]:
        """Анализировать глобальное состояние."""
        anomalies = []
        
        # Сравнение с предыдущим состоянием
        if self.previous_state:
            prev_entities = {e["id"]: e for e in self.previous_state.get("entities", [])}
            curr_entities = {e["id"]: e for e in state.get("entities", [])}
            
            # Исчезнувшие сущности (кроме смерти)
            for entity_id, prev_entity in prev_entities.items():
                if entity_id not in curr_entities:
                    if prev_entity.get("is_alive", True):
                        anomalies.append(Anomaly(
                            anomaly_type=AnomalyType.MISSING_ENTITY,
                            severity=Severity.HIGH,
                            description=f"Entity {entity_id} disappeared unexpectedly",
                            entity_id=entity_id,
                            frame=frame,
                            timestamp=timestamp
                        ))
        
        return anomalies
    
    def track_damage(self, damage: float):
        """Отследить урон для анализа всплесков."""
        self.damage_history.append(damage)
        # Хранить последние 100 значений
        if len(self.damage_history) > 100:
            self.damage_history.pop(0)
    
    def check_damage_spike(self, threshold_multiplier: float = 3.0) -> Optional[Anomaly]:
        """Проверить всплеск урона."""
        if len(self.damage_history) < 10:
            return None
        
        recent = self.damage_history[-5:]
        previous = self.damage_history[:-5]
        
        avg_recent = sum(recent) / len(recent)
        avg_previous = sum(previous) / len(previous) if previous else 0
        
        if avg_previous > 0 and avg_recent > avg_previous * threshold_multiplier:
            return Anomaly(
                anomaly_type=AnomalyType.EXCESSIVE_DAMAGE,
                severity=Severity.HIGH,
                description=f"Damage spike detected: {avg_recent:.1f} vs avg {avg_previous:.1f}",
                frame=0,
                timestamp=0.0,
                data={"recent_avg": avg_recent, "previous_avg": avg_previous}
            )
        
        return None
    
    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку анализатора."""
        return {
            "config": self.config,
            "damage_samples": len(self.damage_history),
            "has_previous_state": self.previous_state is not None
        }
