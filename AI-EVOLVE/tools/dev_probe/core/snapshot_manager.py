"""Snapshot Manager - управление снимками состояния игры."""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class SnapshotManager:
    """Управляет созданием, хранением и анализом снапшотов состояния игры."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.snapshots_dir = output_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots: List[Dict[str, Any]] = []
        self.frame_counter = 0
        
    def take_snapshot(self, state: Dict[str, Any], timestamp: float, frame: int) -> Path:
        """Сделать снимок состояния игры.
        
        Args:
            state: Словарь с состоянием (сущности, эффекты, стойкость и т.д.)
            timestamp: Время в секундах от начала
            frame: Номер кадра
            
        Returns:
            Путь к сохраненному JSON файлу
        """
        snapshot = {
            "timestamp": timestamp,
            "frame": frame,
            "state": state,
        }
        self.snapshots.append(snapshot)
        
        filename = f"frame_{frame:06d}.json"
        filepath = self.snapshots_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)
            
        self.frame_counter = frame
        return filepath
    
    def get_entities_with_effects(self, entities: List[Any]) -> List[Dict[str, Any]]:
        """Извлечь данные о сущностях с их эффектами и стойкостью.
        
        Args:
            entities: Список сущностей игры
            
        Returns:
            Список словарей с данными для снапшота
        """
        result = []
        for entity in entities:
            entity_data = {
                "id": getattr(entity, "entity_id", None),
                "type": "player" if getattr(entity, "is_player", False) else "enemy",
                "health": getattr(entity, "health", 0),
                "max_health": getattr(entity, "max_health", 100),
                "position": {"x": getattr(entity, "x", 0), "y": getattr(entity, "y", 0)},
                "is_alive": getattr(entity, "is_alive", lambda: True)(),
                "effects": [],
                "toughness": None,
            }
            
            # Извлечь эффекты если есть компонент эффектов
            effects_component = getattr(entity, "effects", None)
            if effects_component and hasattr(effects_component, "get_all_effects"):
                for effect in effects_component.get_all_effects():
                    effect_data = {
                        "id": getattr(effect, "id", "unknown"),
                        "target": str(getattr(effect, "target", None)),
                        "value": getattr(effect, "value", 0),
                        "duration": getattr(effect, "duration", 0),
                        "remaining": getattr(effect, "remaining_time", getattr(effect, "duration", 0)),
                        "tags": [str(tag) for tag in getattr(effect, "tags", [])],
                        "modifier_id": getattr(effect, "modifier_id", None),
                        "stacks": getattr(effect, "stacks", 1),
                    }
                    entity_data["effects"].append(effect_data)
            
            # Извлечь стойкость если есть компонент
            toughness_component = getattr(entity, "toughness", None)
            if toughness_component:
                entity_data["toughness"] = {
                    "current": getattr(toughness_component, "current_toughness", 0),
                    "max": getattr(toughness_component, "max_toughness", 100),
                    "state": str(getattr(toughness_component, "current_state", "NORMAL")),
                    "recovery_timer": getattr(toughness_component, "recovery_timer", 0),
                    "break_count": getattr(toughness_component, "break_count", 0),
                }
                
            result.append(entity_data)
        
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку по всем снапшотам.
        
        Returns:
            Словарь со статистикой
        """
        if not self.snapshots:
            return {"total_snapshots": 0}
            
        return {
            "total_snapshots": len(self.snapshots),
            "first_frame": self.snapshots[0]["frame"],
            "last_frame": self.snapshots[-1]["frame"],
            "duration_seconds": self.snapshots[-1]["timestamp"] - self.snapshots[0]["timestamp"],
        }
    
    def clear(self):
        """Очистить все сохраненные снапшоты."""
        self.snapshots.clear()
        self.frame_counter = 0
