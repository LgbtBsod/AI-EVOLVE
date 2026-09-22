"""Event Tracker - Отслеживание событий игры."""

from enum import Enum
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
import time


class EventType(Enum):
    """Типы событий."""
    # Бой
    DAMAGE_DEALT = "damage_dealt"
    DAMAGE_TAKEN = "damage_taken"
    CRITICAL_HIT = "critical_hit"
    HEALING_DONE = "healing_done"
    HEALING_RECEIVED = "healing_received"
    
    # Стойкость
    TOUGHNESS_DAMAGE = "toughness_damage"
    TOUGHNESS_BREAK = "toughness_break"
    TOUGHNESS_RECOVERY = "toughness_recovery"
    
    # Эффекты
    EFFECT_APPLIED = "effect_applied"
    EFFECT_EXPIRED = "effect_expired"
    EFFECT_STACKED = "effect_stacked"
    EFFECT_REMOVED = "effect_removed"
    
    # Продвинутые механики
    DODGE_PERFORMED = "dodge_performed"
    PARRY_PERFORMED = "parry_performed"
    COMBO_STARTED = "combo_started"
    COMBO_FINISHED = "combo_finished"
    
    # Обучение
    LEVEL_UP = "level_up"
    SKILL_LEARNED = "skill_learned"
    XP_GAINED = "xp_gained"
    
    # Предметы
    ITEM_PICKED = "item_picked"
    ITEM_USED = "item_used"
    ITEM_DROPPED = "item_dropped"
    
    # Сессия
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    QUEST_COMPLETED = "quest_completed"


@dataclass
class GameEvent:
    """Событие игры."""
    event_type: EventType
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    frame: int = 0


class EventTracker:
    """Отслеживание и анализ событий игры."""
    
    def __init__(self):
        self.events: List[GameEvent] = []
        self.handlers: Dict[EventType, List[Callable]] = {}
        self.tracking_active = False
        self.start_time: Optional[float] = None
    
    def start_tracking(self):
        """Начать отслеживание."""
        self.tracking_active = True
        self.start_time = time.time()
        self.events = []
    
    def stop_tracking(self):
        """Остановить отслеживание."""
        self.tracking_active = False
    
    def register_handler(self, event_type: EventType, handler: Callable):
        """Зарегистрировать обработчик события."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    def track_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        frame: int = 0
    ):
        """Отследить событие."""
        if not self.tracking_active:
            return
        
        event = GameEvent(
            event_type=event_type,
            data=data,
            source_id=source_id,
            target_id=target_id,
            frame=frame
        )
        
        self.events.append(event)
        
        # Вызвать обработчики
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    print(f"Error in event handler: {e}")
    
    def get_events(
        self,
        event_type: Optional[EventType] = None,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        time_range: Optional[tuple] = None
    ) -> List[GameEvent]:
        """Получить события с фильтрацией."""
        result = self.events
        
        if event_type:
            result = [e for e in result if e.event_type == event_type]
        if source_id:
            result = [e for e in result if e.source_id == source_id]
        if target_id:
            result = [e for e in result if e.target_id == target_id]
        if time_range:
            result = [e for e in result if time_range[0] <= e.timestamp <= time_range[1]]
        
        return result
    
    def get_damage_stats(self) -> Dict[str, Any]:
        """Получить статистику урона."""
        damage_events = [e for e in self.events if e.event_type == EventType.DAMAGE_DEALT]
        
        if not damage_events:
            return {"total_damage": 0, "hit_count": 0, "crit_count": 0}
        
        total_damage = sum(e.data.get("damage", 0) for e in damage_events)
        crit_count = sum(1 for e in damage_events if e.data.get("is_critical", False))
        
        return {
            "total_damage": total_damage,
            "hit_count": len(damage_events),
            "crit_count": crit_count,
            "avg_damage": total_damage / len(damage_events) if damage_events else 0,
            "crit_rate": crit_count / len(damage_events) if damage_events else 0
        }
    
    def get_toughness_stats(self) -> Dict[str, Any]:
        """Получить статистику стойкости."""
        toughness_damage_events = [e for e in self.events if e.event_type == EventType.TOUGHNESS_DAMAGE]
        break_events = [e for e in self.events if e.event_type == EventType.TOUGHNESS_BREAK]
        
        return {
            "total_toughness_damage": sum(e.data.get("toughness_damage", 0) for e in toughness_damage_events),
            "total_breaks": len(break_events),
            "break_events": [
                {
                    "timestamp": e.timestamp,
                    "frame": e.frame,
                    "source_id": e.source_id,
                    "target_id": e.target_id
                }
                for e in break_events
            ]
        }
    
    def get_effect_stats(self) -> Dict[str, Any]:
        """Получить статистику эффектов."""
        applied = [e for e in self.events if e.event_type == EventType.EFFECT_APPLIED]
        expired = [e for e in self.events if e.event_type == EventType.EFFECT_EXPIRED]
        removed = [e for e in self.events if e.event_type == EventType.EFFECT_REMOVED]
        
        return {
            "total_applied": len(applied),
            "total_expired": len(expired),
            "total_removed": len(removed),
            "effects_by_type": self._count_by_field(applied, "effect_id")
        }
    
    def _count_by_field(self, events: List[GameEvent], field_name: str) -> Dict[str, int]:
        """Подсчитать события по полю."""
        counts = {}
        for e in events:
            key = e.data.get(field_name, "unknown") if field_name != "event_type" else e.event_type
            counts[key] = counts.get(key, 0) + 1
        return counts
    
    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку по всем событиям."""
        if not self.events:
            return {"total_events": 0}
        
        event_counts = self._count_by_field(self.events, "event_type")
        
        return {
            "total_events": len(self.events),
            "tracking_duration": time.time() - self.start_time if self.start_time else 0,
            "events_by_type": {k.value if hasattr(k, 'value') else k: v for k, v in event_counts.items()},
            "unique_sources": len(set(e.source_id for e in self.events if e.source_id)),
            "unique_targets": len(set(e.target_id for e in self.events if e.target_id))
        }
    
    def export_events(self, filepath: str, format: str = "json"):
        """Экспорт событий в файл."""
        import json
        
        events_data = [
            {
                "event_type": e.event_type.value,
                "data": e.data,
                "timestamp": e.timestamp,
                "source_id": e.source_id,
                "target_id": e.target_id,
                "frame": e.frame
            }
            for e in self.events
        ]
        
        with open(filepath, 'w') as f:
            if format == "json":
                json.dump(events_data, f, indent=2)
            elif format == "csv":
                # CSV экспорт
                if events_data:
                    keys = events_data[0].keys()
                    f.write(",".join(keys) + "\n")
                    for e in events_data:
                        values = [str(e.get(k, "")) for k in keys]
                        f.write(",".join(values) + "\n")
