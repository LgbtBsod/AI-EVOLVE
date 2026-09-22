"""
DB Sync Plugin - Синхронизация данных между игрой и DevProbe DB.
Позволяет использовать единую БД для игры и инструментов отладки.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import json
import time

from .base import DevProbePlugin, PluginReport


@dataclass
class SyncEvent:
    """Событие синхронизации."""
    entity_id: str
    sync_type: str  # "item_acquire", "skill_learn", "stat_change"
    data: Dict[str, Any]
    timestamp: float
    synced_to_db: bool = False


class DBSyncPlugin(DevProbePlugin):
    """Плагин для синхронизации игровых данных с БД."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.sync_events: List[SyncEvent] = []
        self.db_path = db_path
        self.db_connection = None
        self.sync_stats = {
            "total_syncs": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "items_synced": 0,
            "skills_synced": 0,
            "stats_updated": 0
        }
        self.pending_syncs: List[SyncEvent] = []
        self.batch_size = 50
    
    @property
    def name(self) -> str:
        return "DBSyncPlugin"
    
    def initialize(self, context: Any) -> bool:
        """Инициализация подключения к БД."""
        if self.db_path:
            try:
                import sqlite3
                self.db_connection = sqlite3.connect(self.db_path, check_same_thread=False)
                self._create_tables_if_not_exist()
                return True
            except Exception as e:
                print(f"[DBSyncPlugin] Failed to connect to DB: {e}")
                return False
        return True
    
    def _create_tables_if_not_exist(self):
        """Создать таблицы если не существуют."""
        if not self.db_connection:
            return
        
        cursor = self.db_connection.cursor()
        
        # Таблица событий синхронизации
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                sync_type TEXT NOT NULL,
                data_json TEXT NOT NULL,
                timestamp REAL NOT NULL,
                synced_at REAL,
                success BOOLEAN
            )
        """)
        
        # Индексы для ускорения запросов
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_entity ON sync_events(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_type ON sync_events(sync_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_timestamp ON sync_events(timestamp)")
        
        self.db_connection.commit()
    
    def on_event(self, event: Any) -> None:
        """Обработка событий для синхронизации."""
        from ..core.event_tracker import EventType
        
        if not hasattr(event, 'event_type'):
            return
        
        event_type = event.event_type
        entity_id = getattr(event, 'source_id', None) or getattr(event, 'target_id', None) or "unknown"
        
        sync_type = None
        sync_data = {}
        
        # Предметы
        if event_type == EventType.ITEM_PICKED:
            sync_type = "item_acquire"
            sync_data = {
                "item_id": event.data.get("item_id"),
                "item_name": event.data.get("item_name"),
                "quantity": event.data.get("quantity", 1),
                "source": event.data.get("source", "unknown")
            }
            self.sync_stats["items_synced"] += 1
        
        # Навыки
        elif event_type == EventType.SKILL_LEARNED:
            sync_type = "skill_learn"
            sync_data = {
                "skill_id": event.data.get("skill_id"),
                "skill_name": event.data.get("skill_name"),
                "skill_level": event.data.get("skill_level", 1),
                "source": event.data.get("source", "scroll")
            }
            self.sync_stats["skills_synced"] += 1
        
        # Изменение статов (уровень, опыт)
        elif event_type == EventType.LEVEL_UP:
            sync_type = "stat_change"
            sync_data = {
                "stat_type": "level",
                "old_value": event.data.get("old_level"),
                "new_value": event.data.get("new_level"),
                "xp": event.data.get("xp", 0)
            }
            self.sync_stats["stats_updated"] += 1
        
        elif event_type == EventType.XP_GAINED:
            sync_type = "stat_change"
            sync_data = {
                "stat_type": "xp",
                "xp_gained": event.data.get("xp_amount", 0),
                "total_xp": event.data.get("total_xp", 0)
            }
            self.sync_stats["stats_updated"] += 1
        
        if sync_type and entity_id:
            sync_event = SyncEvent(
                entity_id=entity_id,
                sync_type=sync_type,
                data=sync_data,
                timestamp=event.timestamp
            )
            self.sync_events.append(sync_event)
            self.pending_syncs.append(sync_event)
            self.sync_stats["total_syncs"] += 1
            
            # Пакетная синхронизация
            if len(self.pending_syncs) >= self.batch_size:
                self._flush_pending_syncs()
    
    def _flush_pending_syncs(self):
        """Синхронизировать ожидающие события с БД."""
        if not self.db_connection or not self.pending_syncs:
            return
        
        try:
            cursor = self.db_connection.cursor()
            
            for sync_event in self.pending_syncs:
                cursor.execute("""
                    INSERT INTO sync_events (entity_id, sync_type, data_json, timestamp, synced_at, success)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    sync_event.entity_id,
                    sync_event.sync_type,
                    json.dumps(sync_event.data),
                    sync_event.timestamp,
                    time.time(),
                    1
                ))
                sync_event.synced_to_db = True
                self.sync_stats["successful_syncs"] += 1
            
            self.db_connection.commit()
            self.pending_syncs = []
            
        except Exception as e:
            print(f"[DBSyncPlugin] Sync failed: {e}")
            self.sync_stats["failed_syncs"] += 1
    
    def on_snapshot(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Анализ состояния синхронизации."""
        return {
            "pending_syncs": len(self.pending_syncs),
            "total_syncs": self.sync_stats["total_syncs"],
            "success_rate": (
                self.sync_stats["successful_syncs"] / self.sync_stats["total_syncs"]
                if self.sync_stats["total_syncs"] > 0 else 1.0
            )
        }
    
    def on_finish(self) -> PluginReport:
        """Финальный отчет по синхронизации."""
        # Флеш остатков
        self._flush_pending_syncs()
        
        # Закрыть соединение
        if self.db_connection:
            self.db_connection.close()
        
        return PluginReport(
            plugin_name=self.name,
            summary={
                "total_syncs": self.sync_stats["total_syncs"],
                "successful_syncs": self.sync_stats["successful_syncs"],
                "failed_syncs": self.sync_stats["failed_syncs"],
                "items_synced": self.sync_stats["items_synced"],
                "skills_synced": self.sync_stats["skills_synced"],
                "stats_updated": self.sync_stats["stats_updated"],
                "success_rate": (
                    self.sync_stats["successful_syncs"] / self.sync_stats["total_syncs"]
                    if self.sync_stats["total_syncs"] > 0 else 1.0
                )
            },
            recommendations=[
                "Используйте пакетную синхронизацию для производительности",
                "Проверьте failed_syncs > 0 для ошибок БД",
                "Индексы созданы для entity_id, sync_type, timestamp"
            ] if self.sync_stats["failed_syncs"] > 0 else []
        )
    
    def query_entity_history(self, entity_id: str) -> List[Dict]:
        """Получить историю событий для сущности."""
        if not self.db_connection:
            return []
        
        cursor = self.db_connection.cursor()
        cursor.execute("""
            SELECT sync_type, data_json, timestamp, success
            FROM sync_events
            WHERE entity_id = ?
            ORDER BY timestamp ASC
        """, (entity_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "sync_type": row[0],
                "data": json.loads(row[1]),
                "timestamp": row[2],
                "success": bool(row[3])
            })
        
        return results
    
    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Получить сводку по сессии."""
        if not self.db_connection:
            return {}
        
        cursor = self.db_connection.cursor()
        
        # Всего событий
        cursor.execute("SELECT COUNT(*) FROM sync_events")
        total_events = cursor.fetchone()[0]
        
        # По типам
        cursor.execute("""
            SELECT sync_type, COUNT(*) 
            FROM sync_events 
            GROUP BY sync_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        # По сущностям
        cursor.execute("""
            SELECT entity_id, COUNT(*) 
            FROM sync_events 
            GROUP BY entity_id
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """)
        top_entities = {row[0]: row[1] for row in cursor.fetchall()}
        
        return {
            "session_id": session_id,
            "total_events": total_events,
            "events_by_type": by_type,
            "top_entities": top_entities
        }
