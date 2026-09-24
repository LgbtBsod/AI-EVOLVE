"""
Data Layer: Session Database
Хранение и управление данными сессии в SQLite
Оптимизация расчетов через кэширование и индексацию
"""

import sqlite3
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import asdict
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class SessionDatabase:
    """
    База данных игровой сессии
    Хранит предметы, навыки, прогресс сущностей, события
    """
    
    def __init__(self, db_path: str = ":memory:"):
        """
        Инициализация БД
        
        Args:
            db_path: Путь к файлу БД или ":memory:" для временной БД
        """
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_tables()
        self._create_indexes()
        
        logger.info(f"[SessionDB] Initialized at {db_path}")
    
    def _connect(self):
        """Подключение к БД"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
    
    @contextmanager
    def transaction(self):
        """Контекстный менеджер для транзакций"""
        try:
            yield self.conn
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"[SessionDB] Transaction failed: {e}")
            raise
    
    def _create_tables(self):
        """Создание таблиц"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            
            # Таблица предметов сессии
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    item_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    base_stats TEXT,
                    effects TEXT,
                    min_level INTEGER DEFAULT 1,
                    source_types TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица навыков сессии
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    skill_type TEXT NOT NULL,
                    element TEXT NOT NULL,
                    base_power REAL DEFAULT 0,
                    cooldown REAL DEFAULT 0,
                    mana_cost INTEGER DEFAULT 0,
                    min_level INTEGER DEFAULT 1,
                    required_stats TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица сущностей и их прогресса
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    level INTEGER DEFAULT 1,
                    experience REAL DEFAULT 0,
                    max_hp REAL DEFAULT 100,
                    current_hp REAL DEFAULT 100,
                    stats TEXT,
                    skills TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица событий обучения
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    timestamp REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
                )
            """)
            
            # Таблица событий получения предметов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_acquisition_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    source TEXT NOT NULL,
                    timestamp REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
                    FOREIGN KEY (item_id) REFERENCES items(item_id)
                )
            """)
            
            # Таблица событий получения навыков
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skill_acquisition_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
                    FOREIGN KEY (skill_id) REFERENCES skills(skill_id)
                )
            """)
            
            # Таблица метрик производительности
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    entity_id TEXT,
                    timestamp REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица конфигурации сессии
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
    
    def _create_indexes(self):
        """Создание индексов для ускорения запросов"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_rarity ON items(rarity)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_element ON skills(element)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_type ON skills(skill_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_level ON entities(level)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_entity ON learning_events(entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_type ON learning_events(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_events_entity ON item_acquisition_events(entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_events_entity ON skill_acquisition_events(entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_perf_metrics_name ON performance_metrics(metric_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_perf_metrics_timestamp ON performance_metrics(timestamp)")
    
    # === CRUD операции для предметов ===
    
    def insert_item(self, item_data: Dict[str, Any]) -> bool:
        """Вставка предмета"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO items 
                    (item_id, name, item_type, rarity, base_stats, effects, min_level, source_types)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item_data["item_id"],
                    item_data["name"],
                    item_data["item_type"],
                    item_data["rarity"],
                    json.dumps(item_data.get("base_stats", {})),
                    json.dumps(item_data.get("effects", [])),
                    item_data.get("min_level", 1),
                    json.dumps(item_data.get("source_types", []))
                ))
            return True
        except Exception as e:
            logger.error(f"[SessionDB] Failed to insert item: {e}")
            return False
    
    def insert_items_batch(self, items: List[Dict[str, Any]]) -> int:
        """Пакетная вставка предметов"""
        count = 0
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                for item in items:
                    cursor.execute("""
                        INSERT OR REPLACE INTO items 
                        (item_id, name, item_type, rarity, base_stats, effects, min_level, source_types)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item["item_id"],
                        item["name"],
                        item["item_type"],
                        item["rarity"],
                        json.dumps(item.get("base_stats", {})),
                        json.dumps(item.get("effects", [])),
                        item.get("min_level", 1),
                        json.dumps(item.get("source_types", []))
                    ))
                    count += 1
            return count
        except Exception as e:
            logger.error(f"[SessionDB] Failed batch insert: {e}")
            return count
    
    def get_items_by_rarity(self, rarity: str) -> List[Dict]:
        """Получение предметов по редкости"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM items WHERE rarity = ?", (rarity,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_items_by_source(self, source_type: str) -> List[Dict]:
        """Получение предметов по источнику"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM items WHERE source_types LIKE ?", (f'%"{source_type}"%',))
        items = [dict(row) for row in cursor.fetchall()]
        
        # Фильтрация по JSON полю
        filtered = []
        for item in items:
            sources = json.loads(item.get("source_types", "[]"))
            if source_type in sources:
                filtered.append(item)
        
        return filtered
    
    # === CRUD операции для навыков ===
    
    def insert_skill(self, skill_data: Dict[str, Any]) -> bool:
        """Вставка навыка"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO skills 
                    (skill_id, name, skill_type, element, base_power, cooldown, mana_cost, min_level, required_stats)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    skill_data["skill_id"],
                    skill_data["name"],
                    skill_data["skill_type"],
                    skill_data["element"],
                    skill_data.get("base_power", 0),
                    skill_data.get("cooldown", 0),
                    skill_data.get("mana_cost", 0),
                    skill_data.get("min_level", 1),
                    json.dumps(skill_data.get("required_stats", {}))
                ))
            return True
        except Exception as e:
            logger.error(f"[SessionDB] Failed to insert skill: {e}")
            return False
    
    def insert_skills_batch(self, skills: List[Dict[str, Any]]) -> int:
        """Пакетная вставка навыков"""
        count = 0
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                for skill in skills:
                    cursor.execute("""
                        INSERT OR REPLACE INTO skills 
                        (skill_id, name, skill_type, element, base_power, cooldown, mana_cost, min_level, required_stats)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        skill["skill_id"],
                        skill["name"],
                        skill["skill_type"],
                        skill["element"],
                        skill.get("base_power", 0),
                        skill.get("cooldown", 0),
                        skill.get("mana_cost", 0),
                        skill.get("min_level", 1),
                        json.dumps(skill.get("required_stats", {}))
                    ))
                    count += 1
            return count
        except Exception as e:
            logger.error(f"[SessionDB] Failed batch insert skills: {e}")
            return count
    
    def get_skills_by_element(self, element: str) -> List[Dict]:
        """Получение навыков по элементу"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM skills WHERE element = ?", (element,))
        return [dict(row) for row in cursor.fetchall()]
    
    # === CRUD операции для сущностей ===
    
    def upsert_entity(self, entity_data: Dict[str, Any]) -> bool:
        """Вставка или обновление сущности"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO entities 
                    (entity_id, entity_type, level, experience, max_hp, current_hp, stats, skills, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
                """, (
                    entity_data["entity_id"],
                    entity_data["entity_type"],
                    entity_data.get("level", 1),
                    entity_data.get("experience", 0),
                    entity_data.get("max_hp", 100),
                    entity_data.get("current_hp", 100),
                    json.dumps(entity_data.get("stats", {})),
                    json.dumps(entity_data.get("skills", []))
                ))
            return True
        except Exception as e:
            logger.error(f"[SessionDB] Failed to upsert entity: {e}")
            return False
    
    def get_entity(self, entity_id: str) -> Optional[Dict]:
        """Получение сущности по ID"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM entities WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def update_entity_level(self, entity_id: str, new_level: int, new_experience: float) -> bool:
        """Обновление уровня сущности"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE entities 
                    SET level = ?, experience = ?, updated_at = strftime('%s', 'now')
                    WHERE entity_id = ?
                """, (new_level, new_experience, entity_id))
                
                # Запись события
                cursor.execute("""
                    INSERT INTO learning_events (entity_id, event_type, old_value, new_value)
                    SELECT ?, 'level_up', level, ? FROM entities WHERE entity_id = ?
                """, (entity_id, new_level, entity_id))
            
            return True
        except Exception as e:
            logger.error(f"[SessionDB] Failed to update entity level: {e}")
            return False
    
    # === События ===
    
    def record_item_acquisition(self, entity_id: str, item_id: str, count: int, source: str) -> bool:
        """Запись получения предмета"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO item_acquisition_events (entity_id, item_id, count, source)
                    VALUES (?, ?, ?, ?)
                """, (entity_id, item_id, count, source))
            return True
        except Exception as e:
            logger.error(f"[SessionDB] Failed to record item acquisition: {e}")
            return False
    
    def record_skill_acquisition(self, entity_id: str, skill_id: str, source: str) -> bool:
        """Запись получения навыка"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO skill_acquisition_events (entity_id, skill_id, source)
                    VALUES (?, ?, ?)
                """, (entity_id, skill_id, source))
            return True
        except Exception as e:
            logger.error(f"[SessionDB] Failed to record skill acquisition: {e}")
            return False
    
    def get_entity_skills(self, entity_id: str) -> List[Dict]:
        """Получение всех навыков сущности"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT s.*, sae.source, sae.timestamp
            FROM skill_acquisition_events sae
            JOIN skills s ON sae.skill_id = s.skill_id
            WHERE sae.entity_id = ?
            ORDER BY sae.timestamp DESC
        """, (entity_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_entity_items(self, entity_id: str) -> List[Dict]:
        """Получение всех предметов сущности"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT i.*, iae.count, iae.source, iae.timestamp
            FROM item_acquisition_events iae
            JOIN items i ON iae.item_id = i.item_id
            WHERE iae.entity_id = ?
            GROUP BY iae.item_id
            ORDER BY iae.timestamp DESC
        """, (entity_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    # === Метрики и аналитика ===
    
    def record_metric(self, metric_name: str, metric_value: float, entity_id: Optional[str] = None):
        """Запись метрики производительности"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO performance_metrics (metric_name, metric_value, entity_id)
            VALUES (?, ?, ?)
        """, (metric_name, metric_value, entity_id))
    
    def get_metrics_summary(self, metric_name: str, time_window_seconds: int = 3600) -> Dict:
        """Получение сводки по метрике за период"""
        cursor = self.conn.cursor()
        cutoff_time = time.time() - time_window_seconds
        
        cursor.execute("""
            SELECT 
                COUNT(*) as count,
                AVG(metric_value) as avg_value,
                MIN(metric_value) as min_value,
                MAX(metric_value) as max_value,
                SUM(metric_value) as sum_value
            FROM performance_metrics
            WHERE metric_name = ? AND timestamp >= ?
        """, (metric_name, cutoff_time))
        
        row = cursor.fetchone()
        if row:
            return {
                "count": row[0],
                "avg": row[1],
                "min": row[2],
                "max": row[3],
                "sum": row[4]
            }
        return {"count": 0, "avg": 0, "min": 0, "max": 0, "sum": 0}
    
    def get_learning_statistics(self, entity_id: Optional[str] = None) -> Dict:
        """Получение статистики обучения"""
        cursor = self.conn.cursor()
        
        where_clause = "WHERE entity_id = ?" if entity_id else ""
        params = (entity_id,) if entity_id else ()
        
        cursor.execute(f"""
            SELECT 
                event_type,
                COUNT(*) as count
            FROM learning_events
            {where_clause}
            GROUP BY event_type
        """, params)
        
        return {row[0]: row[1] for row in cursor.fetchall()}
    
    # === Конфигурация сессии ===
    
    def set_config(self, key: str, value: Any):
        """Установка значения конфигурации"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO session_config (key, value, updated_at)
                VALUES (?, ?, strftime('%s', 'now'))
            """, (key, json.dumps(value)))
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Получение значения конфигурации"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM session_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return default
    
    # === Утилиты ===
    
    def export_session_data(self) -> Dict[str, Any]:
        """Экспорт всех данных сессии"""
        cursor = self.conn.cursor()
        
        tables = ["items", "skills", "entities", "learning_events", 
                  "item_acquisition_events", "skill_acquisition_events", 
                  "performance_metrics", "session_config"]
        
        export_data = {}
        for table in tables:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            export_data[table] = [dict(row) for row in rows]
        
        return export_data
    
    def close(self):
        """Закрытие соединения с БД"""
        if self.conn:
            self.conn.close()
            logger.info("[SessionDB] Connection closed")
