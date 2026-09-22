"""Snapshot Manager - Снимки состояния для анализа и отладки."""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class SnapshotMetadata:
    """Метаданные снимка."""
    timestamp: float
    frame: int
    session_id: str
    checksum: str
    entity_count: int
    event_count: int = 0


class SnapshotManager:
    """Управление снимками состояния игры."""
    
    def __init__(self, output_dir: Path, max_snapshots: int = 1000):
        self.output_dir = output_dir
        self.max_snapshots = max_snapshots
        self.snapshots: List[Dict] = []
        self.metadata_list: List[SnapshotMetadata] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def take_snapshot(
        self, 
        state: Dict[str, Any], 
        timestamp: float, 
        frame: int,
        session_id: str = "default",
        events: Optional[List[Dict]] = None
    ) -> Path:
        """Сделать снимок состояния."""
        
        # Вычислить контрольную сумму
        state_str = json.dumps(state, sort_keys=True)
        checksum = hashlib.md5(state_str.encode()).hexdigest()[:12]
        
        snapshot_data = {
            "timestamp": timestamp,
            "frame": frame,
            "session_id": session_id,
            "checksum": checksum,
            "state": state,
            "events": events or []
        }
        
        # Сохранить в память
        self.snapshots.append(snapshot_data)
        
        # Метаданные
        metadata = SnapshotMetadata(
            timestamp=timestamp,
            frame=frame,
            session_id=session_id,
            checksum=checksum,
            entity_count=len(state.get("entities", [])),
            event_count=len(events or [])
        )
        self.metadata_list.append(metadata)
        
        # Сохранить на диск (последние N снимков)
        if len(self.snapshots) <= self.max_snapshots:
            filepath = self.output_dir / f"snapshot_{frame:08d}_{checksum}.json"
            with open(filepath, 'w') as f:
                json.dump(snapshot_data, f, indent=2)
            return filepath
        
        return None
    
    def get_diff(self, snapshot1_idx: int, snapshot2_idx: int) -> Dict[str, Any]:
        """Получить разницу между двумя снимками (для экономии токенов)."""
        if snapshot1_idx >= len(self.snapshots) or snapshot2_idx >= len(self.snapshots):
            return {"error": "Snapshot index out of range"}
        
        snap1 = self.snapshots[snapshot1_idx]
        snap2 = self.snapshots[snapshot2_idx]
        
        diff = {
            "from_frame": snap1["frame"],
            "to_frame": snap2["frame"],
            "time_delta": snap2["timestamp"] - snap1["timestamp"],
            "changes": []
        }
        
        # Сравнить сущности
        entities1 = {e["id"]: e for e in snap1["state"].get("entities", [])}
        entities2 = {e["id"]: e for e in snap2["state"].get("entities", [])}
        
        all_ids = set(entities1.keys()) | set(entities2.keys())
        
        for entity_id in all_ids:
            e1 = entities1.get(entity_id)
            e2 = entities2.get(entity_id)
            
            if e1 and not e2:
                diff["changes"].append({
                    "type": "entity_removed",
                    "entity_id": entity_id,
                    "data": e1
                })
            elif e2 and not e1:
                diff["changes"].append({
                    "type": "entity_spawned",
                    "entity_id": entity_id,
                    "data": e2
                })
            elif e1 and e2:
                # Сравнить поля
                changes_in_entity = {}
                for key in set(list(e1.keys()) + list(e2.keys())):
                    if e1.get(key) != e2.get(key):
                        changes_in_entity[key] = {
                            "from": e1.get(key),
                            "to": e2.get(key)
                        }
                
                if changes_in_entity:
                    diff["changes"].append({
                        "type": "entity_modified",
                        "entity_id": entity_id,
                        "changes": changes_in_entity
                    })
        
        # Новые события
        events1 = set(json.dumps(e, sort_keys=True) for e in snap1.get("events", []))
        events2 = set(json.dumps(e, sort_keys=True) for e in snap2.get("events", []))
        new_events = [json.loads(e) for e in events2 - events1]
        
        if new_events:
            diff["new_events"] = new_events
        
        return diff
    
    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку по всем снимкам."""
        if not self.snapshots:
            return {"total_snapshots": 0}
        
        return {
            "total_snapshots": len(self.snapshots),
            "first_frame": self.metadata_list[0].frame if self.metadata_list else 0,
            "last_frame": self.metadata_list[-1].frame if self.metadata_list else 0,
            "time_span": (
                self.metadata_list[-1].timestamp - self.metadata_list[0].timestamp
                if len(self.metadata_list) > 1 else 0
            ),
            "total_entities_tracked": sum(m.entity_count for m in self.metadata_list),
            "total_events_tracked": sum(m.event_count for m in self.metadata_list)
        }
    
    def find_anomalies(self, threshold_hp: float = 0.2) -> List[Dict]:
        """Найти аномалии в снимках (низкое HP, отрицательная стойкость и т.д.)."""
        anomalies = []
        
        for i, snap in enumerate(self.snapshots):
            for entity in snap["state"].get("entities", []):
                # Низкое HP
                if entity.get("max_health", 0) > 0:
                    hp_ratio = entity.get("health", 0) / entity["max_health"]
                    if hp_ratio < threshold_hp and entity.get("is_alive", True):
                        anomalies.append({
                            "snapshot_idx": i,
                            "frame": snap["frame"],
                            "type": "low_health",
                            "entity_id": entity["id"],
                            "hp_ratio": hp_ratio
                        })
                
                # Отрицательная стойкость
                toughness = entity.get("toughness", {})
                if toughness.get("current", 0) < 0:
                    anomalies.append({
                        "snapshot_idx": i,
                        "frame": snap["frame"],
                        "type": "negative_toughness",
                        "entity_id": entity["id"],
                        "toughness_value": toughness["current"]
                    })
        
        return anomalies
