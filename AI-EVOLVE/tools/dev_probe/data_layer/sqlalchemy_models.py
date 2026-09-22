"""
Data Layer: SQLAlchemy ORM Models
Современный слой данных на основе SQLAlchemy 2.0
Поддержка async, валидация через Pydantic, миграции
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Text, 
    ForeignKey, DateTime, JSON, Index, event, func
)
from sqlalchemy.orm import (
    declarative_base, relationship, sessionmaker, 
    validates, Session, Mapped, mapped_column
)
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker, 
    async_scoped_session
)
from pydantic import BaseModel, Field, field_validator
import structlog

logger = structlog.get_logger(__name__)

Base = declarative_base()


# === Enums для типизации ===

class ItemType(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"
    SCROLL = "scroll"
    MATERIAL = "material"
    QUEST = "quest"


class Rarity(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"


class SkillType(str, Enum):
    ACTIVE = "active"
    PASSIVE = "passive"
    ULTIMATE = "ultimate"


class Element(str, Enum):
    PHYSICAL = "physical"
    FIRE = "fire"
    WATER = "water"
    EARTH = "earth"
    AIR = "air"
    LIGHT = "light"
    DARK = "dark"


class EventType(str, Enum):
    LEVEL_UP = "level_up"
    SKILL_LEARNED = "skill_learned"
    ITEM_ACQUIRED = "item_acquired"
    QUEST_COMPLETED = "quest_completed"
    BOSS_DEFEATED = "boss_defeated"
    TOUGHNESS_BREAK = "toughness_break"


# === Pydantic модели для валидации и API ===

class ItemCreate(BaseModel):
    """Модель создания предмета с валидацией"""
    name: str = Field(..., min_length=1, max_length=100)
    item_type: ItemType
    rarity: Rarity = Rarity.COMMON
    base_stats: Dict[str, Any] = Field(default_factory=dict)
    effects: List[str] = Field(default_factory=list)
    min_level: int = Field(default=1, ge=1, le=100)
    source_types: List[str] = Field(default_factory=list)
    
    @field_validator('base_stats')
    @classmethod
    def validate_stats(cls, v):
        if not isinstance(v, dict):
            raise ValueError("base_stats must be a dictionary")
        return v


class SkillCreate(BaseModel):
    """Модель создания навыка"""
    name: str = Field(..., min_length=1, max_length=100)
    skill_type: SkillType
    element: Element
    base_power: float = Field(default=0, ge=0)
    cooldown: float = Field(default=0, ge=0)
    mana_cost: int = Field(default=0, ge=0)
    min_level: int = Field(default=1, ge=1, le=100)
    required_stats: Dict[str, Any] = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    """Модель обновления сущности"""
    level: Optional[int] = Field(None, ge=1, le=100)
    experience: Optional[float] = Field(None, ge=0)
    current_hp: Optional[float] = Field(None, ge=0)
    stats: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = None


# === SQLAlchemy ORM модели ===

class ItemModel(Base):
    """ORM модель предмета"""
    __tablename__ = "items"
    
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rarity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    base_stats: Mapped[Dict] = mapped_column(JSON, default=dict)
    effects: Mapped[List] = mapped_column(JSON, default=list)
    min_level: Mapped[int] = mapped_column(Integer, default=1)
    source_types: Mapped[List] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    
    # Relationships
    acquisition_events: Mapped[List["ItemAcquisitionEvent"]] = relationship(
        back_populates="item", lazy="selectin"
    )
    
    __table_args__ = (
        Index("idx_items_rarity_type", "rarity", "item_type"),
        Index("idx_items_min_level", "min_level"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            "item_id": self.item_id,
            "name": self.name,
            "item_type": self.item_type,
            "rarity": self.rarity,
            "base_stats": self.base_stats,
            "effects": self.effects,
            "min_level": self.min_level,
            "source_types": self.source_types,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_pydantic(cls, data: ItemCreate, item_id: str) -> "ItemModel":
        """Создание из Pydantic модели"""
        return cls(
            item_id=item_id,
            name=data.name,
            item_type=data.item_type.value,
            rarity=data.rarity.value,
            base_stats=data.base_stats,
            effects=data.effects,
            min_level=data.min_level,
            source_types=data.source_types
        )


class SkillModel(Base):
    """ORM модель навыка"""
    __tablename__ = "skills"
    
    skill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    skill_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    element: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    base_power: Mapped[float] = mapped_column(Float, default=0)
    cooldown: Mapped[float] = mapped_column(Float, default=0)
    mana_cost: Mapped[int] = mapped_column(Integer, default=0)
    min_level: Mapped[int] = mapped_column(Integer, default=1)
    required_stats: Mapped[Dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    
    # Relationships
    acquisition_events: Mapped[List["SkillAcquisitionEvent"]] = relationship(
        back_populates="skill", lazy="selectin"
    )
    
    __table_args__ = (
        Index("idx_skills_element_type", "element", "skill_type"),
        Index("idx_skills_power", "base_power"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "skill_type": self.skill_type,
            "element": self.element,
            "base_power": self.base_power,
            "cooldown": self.cooldown,
            "mana_cost": self.mana_cost,
            "min_level": self.min_level,
            "required_stats": self.required_stats,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_pydantic(cls, data: SkillCreate, skill_id: str) -> "SkillModel":
        """Создание из Pydantic модели"""
        return cls(
            skill_id=skill_id,
            name=data.name,
            skill_type=data.skill_type.value,
            element=data.element.value,
            base_power=data.base_power,
            cooldown=data.cooldown,
            mana_cost=data.mana_cost,
            min_level=data.min_level,
            required_stats=data.required_stats
        )


class EntityModel(Base):
    """ORM модель сущности"""
    __tablename__ = "entities"
    
    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, default=1, index=True)
    experience: Mapped[float] = mapped_column(Float, default=0)
    max_hp: Mapped[float] = mapped_column(Float, default=100)
    current_hp: Mapped[float] = mapped_column(Float, default=100)
    stats: Mapped[Dict] = mapped_column(JSON, default=dict)
    skills: Mapped[List] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Relationships
    learning_events: Mapped[List["LearningEvent"]] = relationship(
        back_populates="entity", lazy="selectin", cascade="all, delete-orphan"
    )
    item_acquisitions: Mapped[List["ItemAcquisitionEvent"]] = relationship(
        back_populates="entity", lazy="selectin", cascade="all, delete-orphan"
    )
    skill_acquisitions: Mapped[List["SkillAcquisitionEvent"]] = relationship(
        back_populates="entity", lazy="selectin", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("idx_entities_level_type", "level", "entity_type"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "level": self.level,
            "experience": self.experience,
            "max_hp": self.max_hp,
            "current_hp": self.current_hp,
            "stats": self.stats,
            "skills": self.skills,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class LearningEvent(Base):
    """ORM модель события обучения"""
    __tablename__ = "learning_events"
    
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.entity_id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    
    # Relationship
    entity: Mapped["EntityModel"] = relationship(back_populates="learning_events")
    
    __table_args__ = (
        Index("idx_learning_entity_type", "entity_id", "event_type"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "entity_id": self.entity_id,
            "event_type": self.event_type,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class ItemAcquisitionEvent(Base):
    """ORM модель получения предмета"""
    __tablename__ = "item_acquisition_events"
    
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.entity_id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("items.item_id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    count: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    
    # Relationships
    entity: Mapped["EntityModel"] = relationship(back_populates="item_acquisitions")
    item: Mapped["ItemModel"] = relationship(back_populates="acquisition_events")
    
    __table_args__ = (
        Index("idx_item_acq_entity_source", "entity_id", "source"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "entity_id": self.entity_id,
            "item_id": self.item_id,
            "count": self.count,
            "source": self.source,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class SkillAcquisitionEvent(Base):
    """ORM модель получения навыка"""
    __tablename__ = "skill_acquisition_events"
    
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.entity_id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("skills.skill_id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    
    # Relationships
    entity: Mapped["EntityModel"] = relationship(back_populates="skill_acquisitions")
    skill: Mapped["SkillModel"] = relationship(back_populates="acquisition_events")
    
    __table_args__ = (
        Index("idx_skill_acq_entity_source", "entity_id", "source"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "entity_id": self.entity_id,
            "skill_id": self.skill_id,
            "source": self.source,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class PerformanceMetric(Base):
    """ORM модель метрики производительности"""
    __tablename__ = "performance_metrics"
    
    metric_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("entities.entity_id"), nullable=True, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    
    __table_args__ = (
        Index("idx_perf_name_timestamp", "metric_name", "timestamp"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "entity_id": self.entity_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class SessionConfig(Base):
    """ORM модель конфигурации сессии"""
    __tablename__ = "session_config"
    
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


# === Менеджер сессий ===

class DatabaseManager:
    """
    Универсальный менеджер базы данных
    Поддержка sync/async режимов, пул соединений, транзакции
    """
    
    def __init__(
        self, 
        db_url: str = "sqlite+aiosqlite:///game_session.db",
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10
    ):
        """
        Инициализация менеджера БД
        
        Args:
            db_url: URL подключения (sqlite+aiosqlite://, postgresql+asyncpg://)
            echo: Логирование SQL запросов
            pool_size: Размер пула соединений (игнорируется для SQLite)
            max_overflow: Максимальное количество overflow соединений (игнорируется для SQLite)
        """
        self.db_url = db_url
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        
        self._async_engine = None
        self._async_session_factory = None
        self._sync_engine = None
        self._sync_session_factory = None
        
        # Определение типа БД
        self._is_sqlite = "sqlite" in db_url.lower()
        
        logger.info("[DatabaseManager] Initialized", db_url=db_url, is_sqlite=self._is_sqlite)
    
    async def init_async(self):
        """Инициализация async движка"""
        if self._async_engine is None:
            # Для SQLite не используем pool_size и max_overflow
            engine_kwargs = {
                "echo": self.echo,
                "pool_pre_ping": True,
                "future": True
            }
            
            if not self._is_sqlite:
                engine_kwargs.update({
                    "pool_size": self.pool_size,
                    "max_overflow": self.max_overflow
                })
            
            self._async_engine = create_async_engine(
                self.db_url,
                **engine_kwargs
            )
            
            self._async_session_factory = async_sessionmaker(
                self._async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                future=True
            )
            
            # Создание таблиц
            async with self._async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            logger.info("[DatabaseManager] Async engine initialized")
    
    def init_sync(self):
        """Инициализация sync движка"""
        if self._sync_engine is None:
            sync_url = self.db_url.replace("+aiosqlite", "")
            
            # Для SQLite не используем max_overflow
            engine_kwargs = {
                "echo": self.echo,
                "pool_pre_ping": True,
                "future": True
            }
            
            if not self._is_sqlite:
                engine_kwargs.update({
                    "pool_size": self.pool_size,
                    "max_overflow": self.max_overflow
                })
            
            self._sync_engine = create_engine(
                sync_url,
                **engine_kwargs
            )
            
            self._sync_session_factory = sessionmaker(
                self._sync_engine,
                class_=Session,
                expire_on_commit=False,
                future=True
            )
            
            # Создание таблиц
            Base.metadata.create_all(self._sync_engine)
            
            logger.info("[DatabaseManager] Sync engine initialized")
    
    async def get_async_session(self) -> AsyncSession:
        """Получение async сессии"""
        if self._async_session_factory is None:
            await self.init_async()
        
        async with self._async_session_factory() as session:
            yield session
    
    def get_sync_session(self) -> Session:
        """Получение sync сессии"""
        if self._sync_session_factory is None:
            self.init_sync()
        
        with self._sync_session_factory() as session:
            yield session
    
    async def close(self):
        """Закрытие соединений"""
        if self._async_engine:
            await self._async_engine.dispose()
            logger.info("[DatabaseManager] Async engine disposed")
        
        if self._sync_engine:
            self._sync_engine.dispose()
            logger.info("[DatabaseManager] Sync engine disposed")


# === Репозитории (Repository Pattern) ===

class BaseRepository:
    """Базовый репозиторий с CRUD операциями"""
    
    def __init__(self, session: Session | AsyncSession):
        self.session = session
    
    async def get(self, model_class, entity_id: str) -> Optional[Any]:
        """Получение записи по ID"""
        return await self.session.get(model_class, entity_id)
    
    async def get_all(self, model_class) -> List[Any]:
        """Получение всех записей"""
        result = await self.session.execute(
            select(model_class).order_by(model_class.created_at.desc())
        )
        return result.scalars().all()
    
    async def create(self, instance: Any) -> Any:
        """Создание записи"""
        self.session.add(instance)
        await self.session.flush()
        return instance
    
    async def update(self, instance: Any, updates: Dict[str, Any]) -> Any:
        """Обновление записи"""
        for key, value in updates.items():
            setattr(instance, key, value)
        await self.session.flush()
        return instance
    
    async def delete(self, instance: Any) -> bool:
        """Удаление записи"""
        await self.session.delete(instance)
        return True


class ItemRepository(BaseRepository):
    """Репозиторий для работы с предметами"""
    
    async def get_by_rarity(self, rarity: str) -> List[ItemModel]:
        """Получение предметов по редкости"""
        result = await self.session.execute(
            select(ItemModel).where(ItemModel.rarity == rarity)
        )
        return result.scalars().all()
    
    async def get_by_type(self, item_type: str) -> List[ItemModel]:
        """Получение предметов по типу"""
        result = await self.session.execute(
            select(ItemModel).where(ItemModel.item_type == item_type)
        )
        return result.scalars().all()
    
    async def get_by_source(self, source_type: str) -> List[ItemModel]:
        """Получение предметов по источнику получения"""
        # JSON поиск зависит от СУБД, для SQLite упрощенная версия
        result = await self.session.execute(
            select(ItemModel).where(
                ItemModel.source_types.contains([source_type])
            )
        )
        return result.scalars().all()
    
    async def batch_create(self, items: List[ItemModel]) -> int:
        """Пакетное создание предметов"""
        self.session.add_all(items)
        await self.session.flush()
        return len(items)


class SkillRepository(BaseRepository):
    """Репозиторий для работы с навыками"""
    
    async def get_by_element(self, element: str) -> List[SkillModel]:
        """Получение навыков по элементу"""
        result = await self.session.execute(
            select(SkillModel).where(SkillModel.element == element)
        )
        return result.scalars().all()
    
    async def get_by_type(self, skill_type: str) -> List[SkillModel]:
        """Получение навыков по типу"""
        result = await self.session.execute(
            select(SkillModel).where(SkillModel.skill_type == skill_type)
        )
        return result.scalars().all()


class EntityRepository(BaseRepository):
    """Репозиторий для работы с сущностями"""
    
    async def get_by_level_range(self, min_level: int, max_level: int) -> List[EntityModel]:
        """Получение сущностей в диапазоне уровней"""
        result = await self.session.execute(
            select(EntityModel).where(
                EntityModel.level >= min_level,
                EntityModel.level <= max_level
            )
        )
        return result.scalars().all()
    
    async def update_level(self, entity_id: str, new_level: int, new_exp: float) -> bool:
        """Обновление уровня сущности"""
        entity = await self.get(EntityModel, entity_id)
        if entity:
            entity.level = new_level
            entity.experience = new_exp
            await self.session.flush()
            
            # Создание события
            event = LearningEvent(
                entity_id=entity_id,
                event_type=EventType.LEVEL_UP.value,
                old_value=str(entity.level - 1),
                new_value=str(new_level)
            )
            self.session.add(event)
            return True
        return False


# === Import для select
from sqlalchemy import select
