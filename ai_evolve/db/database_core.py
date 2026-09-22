"""
AI-EVOLVE Core Database Module
Centralized database management using SQLAlchemy.
Handles all DB operations: read, write, transactions, sequencing.
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
import os
import enum

# Base class for all models
Base = declarative_base()

# Test & Probe related models
class TestRunStatus(enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class TestRun(Base):
    __tablename__ = 'test_runs'
    id = Column(Integer, primary_key=True)
    run_id = Column(String, unique=True, nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    mode = Column(String, default="headless")  # headless or gui
    status = Column(SQLEnum(TestRunStatus), default=TestRunStatus.RUNNING)

class TestResult(Base):
    __tablename__ = 'test_results'
    id = Column(Integer, primary_key=True)
    run_id = Column(String, nullable=False, index=True)
    plugin_name = Column(String, nullable=False)
    status = Column(String, nullable=False)  # running, success, fail, anomaly
    message = Column(Text, nullable=True)
    metrics = Column(Text, nullable=True)  # JSON string
    timestamp = Column(DateTime, nullable=False)

class Entity(Base):
    """Базовая сущность игры."""
    __tablename__ = 'entities'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    health = Column(Float, default=100.0)
    level = Column(Integer, default=1)

# Example model for testing
class GameEntity(Base):
    __tablename__ = 'game_entities'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    health = Column(Float, default=100.0)
    level = Column(Integer, default=1)

class DatabaseCore:
    """
    Core Database Manager.
    Singleton pattern to ensure single connection pool.
    """
    _instance = None
    _engine = None
    _session_factory = None

    def __new__(cls, db_url: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_url: str = None):
        if self._initialized:
            return
        
        self.db_url = db_url or os.getenv("DATABASE_URL", "sqlite:///:memory:")
        self._engine = create_engine(
            self.db_url,
            poolclass=StaticPool,
            echo=False,
            future=True
        )
        self._session_factory = scoped_session(
            sessionmaker(bind=self._engine, autoflush=False, autocommit=False)
        )
        self._initialized = True

    def init_db(self):
        """Initialize database tables."""
        Base.metadata.create_all(self._engine)

    @contextmanager
    def session_scope(self):
        """
        Context manager for database sessions with automatic commit/rollback.
        Alternative name for get_session for compatibility.
        Ensures proper cleanup and rollback on errors.
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @contextmanager
    def get_session(self):
        """
        Context manager for database sessions.
        Ensures proper cleanup and rollback on errors.
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def execute_query(self, query, params=None):
        """Execute raw SQL query."""
        with self.get_session() as session:
            result = session.execute(query, params or {})
            return result.fetchall()

    def bulk_insert(self, model_class, data_list):
        """Bulk insert operation."""
        with self.get_session() as session:
            session.bulk_insert_mappings(model_class, data_list)

    def clear_db(self):
        """Clear all tables (for testing)."""
        Base.metadata.drop_all(self._engine)
        Base.metadata.create_all(self._engine)

# Global instance
db_core = DatabaseCore()

