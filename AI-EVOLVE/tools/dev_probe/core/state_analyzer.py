"""State Analyzer - анализ состояния игры и детекция аномалий."""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Anomaly:
    """Представление обнаруженной аномалии."""
    anomaly_type: str
    description: str
    timestamp: float
    frame: int
    severity: str  # "low", "medium", "high", "critical"
    entity_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class StateAnalyzer:
    """Анализирует состояние игры и обнаруживает аномалии."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.anomalies: List[Anomaly] = []
        
        # Пороги для детекции аномалий
        self.low_hp_threshold = self.config.get("low_hp_threshold", 0.2)
        self.pinned_duration_threshold = self.config.get("pinned_duration_threshold", 5.0)
        self.zero_damage_threshold = self.config.get("zero_damage_threshold", 3)
        
        # Для отслеживания состояний
        self._entity_states: Dict[str, Dict[str, Any]] = {}
        self._consecutive_zero_damage = 0
        
    def analyze_snapshot(self, snapshot: Dict[str, Any]) -> List[Anomaly]:
        """Проанализировать снапшот состояния на наличие аномалий.
        
        Args:
            snapshot: Снапшот состояния игры
            
        Returns:
            Список обнаруженных аномалий
        """
        anomalies = []
        timestamp = snapshot.get("timestamp", 0.0)
        frame = snapshot.get("frame", 0)
        state = snapshot.get("state", {})
        entities = state.get("entities", [])
        
        for entity in entities:
            entity_anomalies = self._analyze_entity(entity, timestamp, frame)
            anomalies.extend(entity_anomalies)
        
        # Проверка глобальных аномалий
        global_anomalies = self._analyze_global_state(state, timestamp, frame)
        anomalies.extend(global_anomalies)
        
        self.anomalies.extend(anomalies)
        return anomalies
    
    def _analyze_entity(
        self, 
        entity: Dict[str, Any], 
        timestamp: float, 
        frame: int
    ) -> List[Anomaly]:
        """Проанализировать сущность на аномалии."""
        anomalies = []
        entity_id = entity.get("id", "unknown")
        
        # Обновить сохраненное состояние
        if entity_id not in self._entity_states:
            self._entity_states[entity_id] = {
                "last_hp": entity.get("health", 100),
                "last_position": entity.get("position", {"x": 0, "y": 0}),
                "hp_crossed_low": False,
                "pinned_start": None,
            }
        
        saved_state = self._entity_states[entity_id]
        
        # 1. Детекция низкого HP
        health = entity.get("health", 100)
        max_health = entity.get("max_health", 100)
        hp_fraction = health / max_health if max_health > 0 else 0
        
        if hp_fraction <= self.low_hp_threshold and not saved_state["hp_crossed_low"]:
            anomalies.append(Anomaly(
                anomaly_type="low_health",
                description=f"{entity_id} имеет критически низкое HP: {health}/{max_health} ({hp_fraction:.1%})",
                timestamp=timestamp,
                frame=frame,
                severity="high" if hp_fraction < 0.1 else "medium",
                entity_id=entity_id,
                data={"health": health, "max_health": max_health, "fraction": hp_fraction},
            ))
            saved_state["hp_crossed_low"] = True
        
        # 2. Детекция застревания (позиция не меняется)
        current_pos = entity.get("position", {"x": 0, "y": 0})
        last_pos = saved_state["last_position"]
        
        if current_pos == last_pos and entity.get("is_alive", True):
            if saved_state["pinned_start"] is None:
                saved_state["pinned_start"] = timestamp
            else:
                pinned_duration = timestamp - saved_state["pinned_start"]
                if pinned_duration >= self.pinned_duration_threshold:
                    anomalies.append(Anomaly(
                        anomaly_type="entity_pinned",
                        description=f"{entity_id} застрял в одной позиции на {pinned_duration:.1f}с",
                        timestamp=timestamp,
                        frame=frame,
                        severity="medium",
                        entity_id=entity_id,
                        data={
                            "position": current_pos,
                            "duration": pinned_duration,
                        },
                    ))
        else:
            saved_state["pinned_start"] = None
            saved_state["last_position"] = current_pos
        
        saved_state["last_hp"] = health
        
        # 3. Детекция зависших эффектов
        effects = entity.get("effects", [])
        for effect in effects:
            duration = effect.get("duration", 0)
            remaining = effect.get("remaining", duration)
            
            # Если эффект длится дольше чем должен
            if remaining < 0:
                anomalies.append(Anomaly(
                    anomaly_type="negative_effect_duration",
                    description=f"У эффекта {effect.get('id')} отрицательное время: {remaining}",
                    timestamp=timestamp,
                    frame=frame,
                    severity="low",
                    entity_id=entity_id,
                    data={"effect": effect},
                ))
        
        # 4. Детекция аномалий стойкости
        toughness = entity.get("toughness")
        if toughness:
            current_tough = toughness.get("current", 0)
            max_tough = toughness.get("max", 100)
            tough_state = toughness.get("state", "NORMAL")
            
            # Стойкость ниже 0
            if current_tough < 0:
                anomalies.append(Anomaly(
                    anomaly_type="negative_toughness",
                    description=f"{entity_id} имеет отрицательную стойкость: {current_tough}",
                    timestamp=timestamp,
                    frame=frame,
                    severity="high",
                    entity_id=entity_id,
                    data=toughness,
                ))
            
            # Состояние BROKEN но стойкость не 0
            if tough_state == "BROKEN" and current_tough > 0:
                anomalies.append(Anomaly(
                    anomaly_type="broken_with_positive_toughness",
                    description=f"{entity_id} в состоянии BROKEN но стойкость = {current_tough}",
                    timestamp=timestamp,
                    frame=frame,
                    severity="medium",
                    entity_id=entity_id,
                    data=toughness,
                ))
        
        return anomalies
    
    def _analyze_global_state(
        self, 
        state: Dict[str, Any], 
        timestamp: float, 
        frame: int
    ) -> List[Anomaly]:
        """Проанализировать глобальное состояние игры."""
        anomalies = []
        
        # Проверка что все сущности мертвы но бой продолжается
        entities = state.get("entities", [])
        alive_count = sum(1 for e in entities if e.get("is_alive", False))
        
        if alive_count == 0 and len(entities) > 0:
            anomalies.append(Anomaly(
                anomaly_type="all_entities_dead",
                description="Все сущности мертвы но игра продолжается",
                timestamp=timestamp,
                frame=frame,
                severity="critical",
                data={"entity_count": len(entities)},
            ))
        
        return anomalies
    
    def track_damage_event(self, damage: float, timestamp: float, frame: int):
        """Отследить событие урона для детекции аномалий.
        
        Args:
            damage: Нанесенный урон
            timestamp: Время события
            frame: Номер кадра
        """
        if damage == 0:
            self._consecutive_zero_damage += 1
            
            if self._consecutive_zero_damage >= self.zero_damage_threshold:
                self.anomalies.append(Anomaly(
                    anomaly_type="consecutive_zero_damage",
                    description=f"{self._consecutive_zero_damage} ударов подряд без урона",
                    timestamp=timestamp,
                    frame=frame,
                    severity="medium",
                    data={"consecutive_count": self._consecutive_zero_damage},
                ))
        else:
            self._consecutive_zero_damage = 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку по аномалиям.
        
        Returns:
            Словарь со статистикой аномалий
        """
        if not self.anomalies:
            return {"total_anomalies": 0}
        
        by_type = {}
        by_severity = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        
        for anomaly in self.anomalies:
            by_type[anomaly.anomaly_type] = by_type.get(anomaly.anomaly_type, 0) + 1
            by_severity[anomaly.severity] = by_severity.get(anomaly.severity, 0) + 1
        
        return {
            "total_anomalies": len(self.anomalies),
            "by_type": by_type,
            "by_severity": by_severity,
            "critical_count": by_severity["critical"],
            "high_count": by_severity["high"],
        }
    
    def clear(self):
        """Очистить все данные анализатора."""
        self.anomalies.clear()
        self._entity_states.clear()
        self._consecutive_zero_damage = 0
