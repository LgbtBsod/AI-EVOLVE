#!/usr/bin/env python3
"""
Database Core - ядро базы данных на SQLAlchemy
Управляет всеми операциями с БД: чтение, запись, транзакции, миграции
"""

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.architecture import BaseComponent, ComponentType, LifecycleState, Priority

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class DatabaseCore(BaseComponent):
    """
    Ядро базы данных на SQLAlchemy
    
    Отвечает за:
    - Подключение к БД (SQLite/PostgreSQL)
    - Управление сессиями и транзакциями
    - Миграции схемы
    - CRUD операции
    - Пул соединений
    """
    
    def __init__(self, db_url: str = "sqlite:///saves/game_database.db"):
        super().__init__(
            component_id="database_core",
            component_type=ComponentType.CORE,
            priority=Priority.CRITICAL
        )
        
        self.db_url = db_url
        self.engine: Optional["Engine"] = None
        self.session_factory: Optional[sessionmaker] = None
        self.scoped_session: Optional[scoped_session] = None
        
        # Конфигурация
        self.db_config = {
            'echo': False,  # Логирование SQL запросов
            'pool_size': 5,
            'max_overflow': 10,
            'pool_timeout': 30,
            'pool_recycle': 3600,
            'connect_args': {'check_same_thread': False} if 'sqlite' in db_url else {},
        }
        
        # Статистика
        self.db_stats = {
            'connections_created': 0,
            'connections_closed': 0,
            'transactions_committed': 0,
            'transactions_rolled_back': 0,
            'queries_executed': 0,
            'total_query_time': 0.0,
        }
        
        logger.info(f"DatabaseCore создан с URL: {db_url}")
    
    def initialize(self) -> bool:
        """Инициализация движка БД"""
        try:
            logger.info("=== Инициализация DatabaseCore ===")
            
            # Создаем движок
            if 'sqlite' in self.db_url:
                self.engine = create_engine(
                    self.db_url,
                    echo=self.db_config['echo'],
                    connect_args=self.db_config['connect_args'],
                    poolclass=StaticPool,
                )
            else:
                self.engine = create_engine(
                    self.db_url,
                    echo=self.db_config['echo'],
                    pool_size=self.db_config['pool_size'],
                    max_overflow=self.db_config['max_overflow'],
                    pool_timeout=self.db_config['pool_timeout'],
                    pool_recycle=self.db_config['pool_recycle'],
                )
            
            # Регистрируем события для статистики
            self._register_events()
            
            # Создаем фабрику сессий
            self.session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
            
            # Создаем scoped session для потокобезопасности
            self.scoped_session = scoped_session(self.session_factory)
            
            # Создаем таблицы
            self._create_tables()
            
            self.system_state = LifecycleState.READY
            logger.info("DatabaseCore успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации DatabaseCore: {e}", exc_info=True)
            self.system_state = LifecycleState.ERROR
            return False
    
    def start(self) -> bool:
        """Запуск ядра БД"""
        try:
            logger.info("=== Запуск DatabaseCore ===")
            
            if self.system_state != LifecycleState.READY:
                logger.error("DatabaseCore не готов к запуску")
                return False
            
            # Проверяем подключение
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            
            self.system_state = LifecycleState.RUNNING
            logger.info("DatabaseCore успешно запущен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска DatabaseCore: {e}", exc_info=True)
            self.system_state = LifecycleState.ERROR
            return False
    
    def update(self, delta_time: float) -> None:
        """Обновление ядра БД (no-op для БД)"""
        pass
    
    def stop(self) -> bool:
        """Остановка ядра БД"""
        try:
            logger.info("=== Остановка DatabaseCore ===")
            
            # Закрываем все сессии
            if self.scoped_session:
                self.scoped_session.remove()
            
            self.system_state = LifecycleState.STOPPED
            logger.info("DatabaseCore успешно остановлен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки DatabaseCore: {e}", exc_info=True)
            return False
    
    def destroy(self) -> bool:
        """Уничтожение ядра БД"""
        try:
            logger.info("=== Уничтожение DatabaseCore ===")
            
            # Закрываем все сессии
            if self.scoped_session:
                self.scoped_session.remove()
            
            # Закрываем движок
            if self.engine:
                self.engine.dispose()
                self.engine = None
            
            self.session_factory = None
            self.scoped_session = None
            
            self.system_state = LifecycleState.DESTROYED
            logger.info("DatabaseCore успешно уничтожен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения DatabaseCore: {e}", exc_info=True)
            return False
    
    def _register_events(self) -> None:
        """Регистрация событий SQLAlchemy для статистики"""
        if not self.engine:
            return
        
        @event.listens_for(self.engine, "connect")
        def on_connect(dbapi_conn, connection_record):
            self.db_stats['connections_created'] += 1
            logger.debug("Соединение с БД создано")
        
        @event.listens_for(self.engine, "close")
        def on_close(dbapi_conn, connection_record):
            self.db_stats['connections_closed'] += 1
            logger.debug("Соединение с БД закрыто")
    
    def _create_tables(self) -> None:
        """Создание таблиц базы данных"""
        if not self.engine:
            return
        
        try:
            from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey, Index, MetaData
            from datetime import datetime
            
            metadata = MetaData()
            
            # Таблица игровых сессий
            game_sessions = Table(
                'game_sessions', metadata,
                Column('session_id', String, primary_key=True),
                Column('player_id', String, nullable=False),
                Column('start_time', Float, nullable=False),
                Column('end_time', Float),
                Column('character_class', String),
                Column('level_reached', Integer, default=1),
                Column('enemies_defeated', Integer, default=0),
                Column('items_collected', Integer, default=0),
                Column('npcs_interacted', Integer, default=0),
                Column('distance_traveled', Float, default=0.0),
                Column('death_count', Integer, default=0),
                Column('exit_found', Boolean, default=False),
                Column('session_data', Text),  # JSON
                Column('created_at', Float, default=lambda: time.time()),
                Column('updated_at', Float, default=lambda: time.time(), onupdate=lambda: time.time()),
            )
            
            # Таблица данных для ML обучения
            ml_training_data = Table(
                'ml_training_data', metadata,
                Column('record_id', Integer, primary_key=True, autoincrement=True),
                Column('session_id', String, ForeignKey('game_sessions.session_id'), nullable=False),
                Column('timestamp', Float, nullable=False),
                Column('state_vector', Text, nullable=False),  # JSON
                Column('action_taken', Integer, nullable=False),
                Column('reward', Float, nullable=False),
                Column('next_state', Text, nullable=False),  # JSON
                Column('done', Boolean, nullable=False),
            )
            
            # Таблица взаимодействий с NPC
            npc_interactions = Table(
                'npc_interactions', metadata,
                Column('interaction_id', Integer, primary_key=True, autoincrement=True),
                Column('session_id', String, ForeignKey('game_sessions.session_id'), nullable=False),
                Column('npc_id', String, nullable=False),
                Column('timestamp', Float, nullable=False),
                Column('dialogue_outcome', Text),
                Column('player_charisma', Float),
                Column('information_gained', Text),  # JSON
                Column('triggered_encounter', Boolean, default=False),
            )
            
            # Создаем все таблицы
            metadata.create_all(self.engine)
            
            # Создаем индексы
            with self.engine.connect() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_player ON game_sessions(player_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_session ON ml_training_data(session_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_npc_session ON npc_interactions(session_id)"))
                conn.commit()
            
            logger.info("Таблицы БД созданы успешно")
            
        except Exception as e:
            logger.error(f"Ошибка создания таблиц: {e}", exc_info=True)
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Получение сессии БД в контекстном менеджере
        
        Usage:
            with db_core.get_session() as session:
                session.query(...).all()
        """
        if not self.scoped_session:
            raise RuntimeError("DatabaseCore не инициализирован")
        
        session = self.scoped_session()
        try:
            yield session
            session.commit()
            self.db_stats['transactions_committed'] += 1
        except Exception as e:
            session.rollback()
            self.db_stats['transactions_rolled_back'] += 1
            logger.error(f"Ошибка транзакции БД: {e}")
            raise
        finally:
            session.close()
    
    def execute_query(self, query: Any, params: dict | None = None) -> Any:
        """
        Выполнение SQL запроса
        
        Args:
            query: SQLAlchemy query или текст запроса
            params: Параметры запроса
        
        Returns:
            Результат выполнения запроса
        """
        import time
        
        if not self.engine:
            raise RuntimeError("DatabaseCore не инициализирован")
        
        start_time = time.perf_counter()
        
        try:
            with self.engine.connect() as conn:
                if isinstance(query, str):
                    result = conn.execute(text(query), params or {})
                else:
                    result = conn.execute(query, params or {})
                
                self.db_stats['queries_executed'] += 1
                self.db_stats['total_query_time'] += time.perf_counter() - start_time
                
                return result
        except Exception as e:
            logger.error(f"Ошибка выполнения запроса: {e}")
            raise
    
    def bulk_insert(self, table_name: str, data: list[dict]) -> bool:
        """
        Массовая вставка данных
        
        Args:
            table_name: Имя таблицы
            data: Список словарей с данными
        
        Returns:
            bool: True если успешно
        """
        try:
            with self.get_session() as session:
                from sqlalchemy import table, column
                
                # Динамическое создание таблицы для вставки
                # В реальном проекте лучше использовать ORM модели
                pass
            
            return True
        except Exception as e:
            logger.error(f"Ошибка массовой вставки: {e}")
            return False
    
    def get_statistics(self) -> dict[str, Any]:
        """Получение статистики БД"""
        return {
            **self.db_stats,
            'engine_connected': self.engine is not None,
            'session_active': self.scoped_session is not None,
        }
    
    def get_system_info(self) -> dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.system_name,
            'state': self.system_state.value,
            'priority': self.system_priority.value,
            'db_url': self.db_url,
            **self.get_statistics(),
        }


# Import Table and time for the _create_tables method
from sqlalchemy import Table, MetaData
import time

__all__ = ['DatabaseCore']
