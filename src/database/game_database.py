#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простая база данных для хранения игровых сессий и статистики
Использует SQLite для легковесного хранения
"""

import sqlite3
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class GameSession:
    """Данные игровой сессии"""
    session_id: str
    player_id: str
    start_time: float
    end_time: Optional[float] = None
    character_class: str = ""
    level_reached: int = 1
    enemies_defeated: int = 0
    items_collected: int = 0
    npcs_interacted: int = 0
    distance_traveled: float = 0.0
    death_count: int = 0
    exit_found: bool = False
    session_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.session_data is None:
            self.session_data = {}


@dataclass
class MLTrainingData:
    """Данные для обучения ML-агента"""
    record_id: int
    session_id: str
    timestamp: float
    state_vector: List[float]
    action_taken: int
    reward: float
    next_state: List[float]
    done: bool


class GameDatabase:
    """
    База данных для хранения игровых сессий и данных обучения
    """
    
    def __init__(self, db_path: str = "saves/game_database.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Инициализировать базу данных и создать таблицы"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        
        # Таблица игровых сессий
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_sessions (
                session_id TEXT PRIMARY KEY,
                player_id TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL,
                character_class TEXT,
                level_reached INTEGER DEFAULT 1,
                enemies_defeated INTEGER DEFAULT 0,
                items_collected INTEGER DEFAULT 0,
                npcs_interacted INTEGER DEFAULT 0,
                distance_traveled REAL DEFAULT 0.0,
                death_count INTEGER DEFAULT 0,
                exit_found BOOLEAN DEFAULT 0,
                session_data TEXT
            )
        ''')
        
        # Таблица данных для ML обучения
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ml_training_data (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                state_vector TEXT NOT NULL,
                action_taken INTEGER NOT NULL,
                reward REAL NOT NULL,
                next_state TEXT NOT NULL,
                done BOOLEAN NOT NULL,
                FOREIGN KEY (session_id) REFERENCES game_sessions(session_id)
            )
        ''')
        
        # Таблица статистики NPC взаимодействий
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS npc_interactions (
                interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                npc_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                dialogue_outcome TEXT,
                player_charisma REAL,
                information_gained TEXT,
                triggered_encounter BOOLEAN DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES game_sessions(session_id)
            )
        ''')
        
        # Индексы для ускорения поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_player ON game_sessions(player_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_session ON ml_training_data(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_npc_session ON npc_interactions(session_id)')
        
        self.conn.commit()
    
    # === Game Sessions ===
    
    def create_session(self, session: GameSession) -> bool:
        """Создать новую игровую сессию"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO game_sessions (
                    session_id, player_id, start_time, character_class,
                    level_reached, enemies_defeated, items_collected,
                    npcs_interacted, distance_traveled, death_count,
                    exit_found, session_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session.session_id,
                session.player_id,
                session.start_time,
                session.character_class,
                session.level_reached,
                session.enemies_defeated,
                session.items_collected,
                session.npcs_interacted,
                session.distance_traveled,
                session.death_count,
                1 if session.exit_found else 0,
                json.dumps(session.session_data)
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return False
    
    def update_session(self, session_id: str, **kwargs) -> bool:
        """Обновить данные сессии"""
        try:
            allowed_fields = {
                'end_time', 'level_reached', 'enemies_defeated',
                'items_collected', 'npcs_interacted', 'distance_traveled',
                'death_count', 'exit_found', 'session_data'
            }
            
            updates = []
            values = []
            
            for key, value in kwargs.items():
                if key in allowed_fields:
                    if key == 'exit_found':
                        value = 1 if value else 0
                    elif key == 'session_data':
                        value = json.dumps(value)
                    updates.append(f"{key} = ?")
                    values.append(value)
            
            if not updates:
                return False
            
            values.append(session_id)
            query = f"UPDATE game_sessions SET {', '.join(updates)} WHERE session_id = ?"
            
            cursor = self.conn.cursor()
            cursor.execute(query, values)
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating session: {e}")
            return False
    
    def get_session(self, session_id: str) -> Optional[GameSession]:
        """Получить данные сессии по ID"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM game_sessions WHERE session_id = ?', (session_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_session(row)
            return None
        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None
    
    def get_all_sessions(self, player_id: Optional[str] = None) -> List[GameSession]:
        """Получить все сессии (опционально для игрока)"""
        try:
            cursor = self.conn.cursor()
            if player_id:
                cursor.execute('SELECT * FROM game_sessions WHERE player_id = ?', (player_id,))
            else:
                cursor.execute('SELECT * FROM game_sessions')
            
            return [self._row_to_session(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return []
    
    def _row_to_session(self, row: sqlite3.Row) -> GameSession:
        """Преобразовать строку БД в объект GameSession"""
        return GameSession(
            session_id=row['session_id'],
            player_id=row['player_id'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            character_class=row['character_class'],
            level_reached=row['level_reached'],
            enemies_defeated=row['enemies_defeated'],
            items_collected=row['items_collected'],
            npcs_interacted=row['npcs_interacted'],
            distance_traveled=row['distance_traveled'],
            death_count=row['death_count'],
            exit_found=bool(row['exit_found']),
            session_data=json.loads(row['session_data']) if row['session_data'] else {}
        )
    
    # === ML Training Data ===
    
    def add_training_record(self, session_id: str, state_vector: List[float],
                           action_taken: int, reward: float,
                           next_state: List[float], done: bool) -> bool:
        """Добавить запись для обучения ML"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO ml_training_data (
                    session_id, timestamp, state_vector, action_taken,
                    reward, next_state, done
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                time.time(),
                json.dumps(state_vector),
                action_taken,
                reward,
                json.dumps(next_state),
                1 if done else 0
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding training record: {e}")
            return False
    
    def get_training_data(self, session_id: Optional[str] = None, 
                         limit: int = 1000) -> List[MLTrainingData]:
        """Получить данные для обучения"""
        try:
            cursor = self.conn.cursor()
            if session_id:
                cursor.execute(
                    'SELECT * FROM ml_training_data WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?',
                    (session_id, limit)
                )
            else:
                cursor.execute(
                    'SELECT * FROM ml_training_data ORDER BY timestamp DESC LIMIT ?',
                    (limit,)
                )
            
            return [
                MLTrainingData(
                    record_id=row['record_id'],
                    session_id=row['session_id'],
                    timestamp=row['timestamp'],
                    state_vector=json.loads(row['state_vector']),
                    action_taken=row['action_taken'],
                    reward=row['reward'],
                    next_state=json.loads(row['next_state']),
                    done=bool(row['done'])
                )
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"Error getting training data: {e}")
            return []
    
    # === NPC Interactions ===
    
    def log_npc_interaction(self, session_id: str, npc_id: str,
                           dialogue_outcome: str, player_charisma: float,
                           information_gained: Optional[Dict] = None,
                           triggered_encounter: bool = False) -> bool:
        """Записать взаимодействие с NPC"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO npc_interactions (
                    session_id, npc_id, timestamp, dialogue_outcome,
                    player_charisma, information_gained, triggered_encounter
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                npc_id,
                time.time(),
                dialogue_outcome,
                player_charisma,
                json.dumps(information_gained) if information_gained else None,
                1 if triggered_encounter else 0
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error logging NPC interaction: {e}")
            return False
    
    # === Statistics ===
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получить общую статистику"""
        try:
            cursor = self.conn.cursor()
            
            # Общая статистика сессий
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_sessions,
                    AVG(level_reached) as avg_level,
                    SUM(enemies_defeated) as total_enemies,
                    SUM(death_count) as total_deaths,
                    SUM(CASE WHEN exit_found THEN 1 ELSE 0 END) as exits_found
                FROM game_sessions
            ''')
            stats_row = cursor.fetchone()
            
            return {
                'total_sessions': stats_row['total_sessions'] or 0,
                'average_level': stats_row['avg_level'] or 0.0,
                'total_enemies_defeated': stats_row['total_enemies'] or 0,
                'total_deaths': stats_row['total_deaths'] or 0,
                'total_exits_found': stats_row['exits_found'] or 0,
                'ml_records_count': self._get_ml_records_count()
            }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
    
    def _get_ml_records_count(self) -> int:
        """Получить количество записей ML обучения"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM ml_training_data')
            return cursor.fetchone()[0]
        except:
            return 0
    
    def close(self):
        """Закрыть соединение с БД"""
        if self.conn:
            self.conn.close()
            self.conn = None
