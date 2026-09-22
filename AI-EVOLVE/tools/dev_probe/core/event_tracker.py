"""Event Tracker - отслеживание событий игры."""
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EventType(Enum):
    """Типы отслеживаемых событий."""
    COMBAT_START = "combat_start"
    COMBAT_END = "combat_end"
    DAMAGE_DEALT = "damage_dealt"
    DAMAGE_TAKEN = "damage_taken"
    EFFECT_APPLIED = "effect_applied"
    EFFECT_EXPIRED = "effect_expired"
    TOUGHNESS_DAMAGE = "toughness_damage"
    TOUGHNESS_BREAK = "toughness_break"
    TOUGHNESS_RECOVERED = "toughness_recovered"
    ENTITY_DIED = "entity_died"
    ENTITY_SPAWNED = "entity_spawned"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class TrackedEvent:
    """Представление отслеженного события."""
    event_type: EventType
    timestamp: float
    frame: int
    data: Dict[str, Any]
    source_entity_id: Optional[str] = None
    target_entity_id: Optional[str] = None


class EventTracker:
    """Отслеживает и агрегирует события игры для анализа."""
    
    def __init__(self):
        self.events: List[TrackedEvent] = []
        self.event_counts: Counter = Counter()
        self.handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self.start_time: float = 0.0
        self.current_frame: int = 0
        
    def start_tracking(self, timestamp: float = 0.0):
        """Начать отслеживание событий."""
        self.start_time = timestamp
        self.events.clear()
        self.event_counts.clear()
        
    def register_handler(self, event_type: EventType, handler: Callable):
        """Зарегистрировать обработчик для типа событий."""
        self.handlers[event_type].append(handler)
        
    def track_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
    ):
        """Отследить событие.
        
        Args:
            event_type: Тип события
            data: Данные события
            source_id: ID источника (кто вызвал)
            target_id: ID цели (на кого направлено)
        """
        elapsed = time.time() - self.start_time if self.start_time else 0.0
        
        event = TrackedEvent(
            event_type=event_type,
            timestamp=elapsed,
            frame=self.current_frame,
            data=data,
            source_entity_id=source_id,
            target_entity_id=target_id,
        )
        
        self.events.append(event)
        self.event_counts[event_type.value] += 1
        
        # Вызвать зарегистрированные обработчики
        for handler in self.handlers.get(event_type, []):
            try:
                handler(event)
            except Exception as e:
                print(f"Error in event handler for {event_type}: {e}")
    
    def update_frame(self, frame: int):
        """Обновить текущий номер кадра."""
        self.current_frame = frame
    
    def get_events_by_type(self, event_type: EventType) -> List[TrackedEvent]:
        """Получить все события указанного типа."""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_events_for_entity(self, entity_id: str) -> List[TrackedEvent]:
        """Получить все события для сущности (как источник или цель)."""
        return [
            e for e in self.events
            if e.source_entity_id == entity_id or e.target_entity_id == entity_id
        ]
    
    def get_damage_stats(self) -> Dict[str, Any]:
        """Получить статистику по урону.
        
        Returns:
            Словарь со статистикой урона
        """
        damage_events = self.get_events_by_type(EventType.DAMAGE_DEALT)
        
        if not damage_events:
            return {"total_damage": 0, "hit_count": 0, "avg_damage": 0}
        
        total_damage = sum(e.data.get("damage", 0) for e in damage_events)
        crit_count = sum(1 for e in damage_events if e.data.get("is_critical", False))
        
        return {
            "total_damage": total_damage,
            "hit_count": len(damage_events),
            "avg_damage": total_damage / len(damage_events) if damage_events else 0,
            "crit_count": crit_count,
            "crit_rate": crit_count / len(damage_events) if damage_events else 0,
        }
    
    def get_toughness_stats(self) -> Dict[str, Any]:
        """Получить статистику по стойкости.
        
        Returns:
            Словарь со статистикой стойкости
        """
        break_events = self.get_events_by_type(EventType.TOUGHNESS_BREAK)
        toughness_dmg_events = self.get_events_by_type(EventType.TOUGHNESS_DAMAGE)
        
        return {
            "total_breaks": len(break_events),
            "total_toughness_damage": sum(
                e.data.get("toughness_damage", 0) for e in toughness_dmg_events
            ),
            "entities_broken": list(set(
                e.target_entity_id for e in break_events if e.target_entity_id
            )),
        }
    
    def get_effect_stats(self) -> Dict[str, Any]:
        """Получить статистику по эффектам.
        
        Returns:
            Словарь со статистикой эффектов
        """
        applied_events = self.get_events_by_type(EventType.EFFECT_APPLIED)
        expired_events = self.get_events_by_type(EventType.EFFECT_EXPIRED)
        
        effects_by_tag = defaultdict(int)
        for event in applied_events:
            tags = event.data.get("tags", [])
            for tag in tags:
                effects_by_tag[str(tag)] += 1
        
        return {
            "total_applied": len(applied_events),
            "total_expired": len(expired_events),
            "active_effects": len(applied_events) - len(expired_events),
            "effects_by_tag": dict(effects_by_tag),
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку по всем событиям.
        
        Returns:
            Словарь со сводной статистикой
        """
        return {
            "total_events": len(self.events),
            "event_counts": dict(self.event_counts),
            "damage_stats": self.get_damage_stats(),
            "toughness_stats": self.get_toughness_stats(),
            "effect_stats": self.get_effect_stats(),
        }
