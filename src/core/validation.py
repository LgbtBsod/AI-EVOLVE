"""
Pydantic Validation Models
Строгая валидация конфигураций и данных с использованием Pydantic.
Обеспечивает типобезопасность и автоматическую проверку данных.
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class ComponentStateEnum(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    STARTED = "started"
    PAUSED = "paused"
    STOPPED = "stopped"
    DESTROYED = "destroyed"
    ERROR = "error"


class ComponentConfig(BaseModel):
    """Конфигурация компонента."""
    name: str = Field(..., min_length=1, max_length=64, description="Имя компонента")
    enabled: bool = Field(default=True, description="Флаг активности")
    priority: int = Field(default=0, ge=-100, le=100, description="Приоритет выполнения")
    tags: list[str] = Field(default_factory=list, description="Теги для группировки")
    
    @field_validator('name')
    @classmethod
    def name_must_be_alphanumeric(cls, v):
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Имя должно содержать только буквы, цифры, _ и -")
        return v


class StateTransitionRequest(BaseModel):
    """Запрос на переход состояния."""
    component_id: str
    target_state: ComponentStateEnum
    force: bool = Field(default=False, description="Принудительный переход")
    reason: str | None = Field(None, max_length=255)


class EventData(BaseModel):
    """Данные события."""
    event_type: str = Field(..., min_length=1, description="Тип события")
    source: str = Field(..., description="Источник события")
    payload: dict[str, Any] = Field(default_factory=dict, description="Полезная нагрузка")
    timestamp: float | None = None
    
    model_config = {
        'arbitrary_types_allowed': True
    }


class CombatStats(BaseModel):
    """Боевые характеристики сущности."""
    health: float = Field(..., gt=0, description="Здоровье")
    max_health: float = Field(..., gt=0, description="Макс. здоровье")
    damage: float = Field(..., ge=0, description="Урон")
    defense: float = Field(default=0, ge=0, description="Защита")
    speed: float = Field(default=1.0, gt=0, description="Скорость")
    
    @model_validator(mode='after')
    def clamp_health_to_max(self):
        """Обрезает health до max_health если превышает."""
        self.health = min(self.health, self.max_health)
        return self
    
    @property
    def health_percent(self) -> float:
        return (self.health / self.max_health) * 100.0


class AttributeDefinition(BaseModel):
    """Определение атрибута."""
    key: str
    value: Any
    min_value: Any | None = None
    max_value: Any | None = None
    is_derived: bool = False
    formula: str | None = None


def validate_component_config(config: dict) -> ComponentConfig:
    """Валидация конфига компонента."""
    try:
        return ComponentConfig(**config)
    except ValidationError as e:
        raise ValueError(f"Invalid component config: {e}")


def validate_event_data(data: dict) -> EventData:
    """Валидация данных события."""
    try:
        return EventData(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid event data: {e}")


def validate_combat_stats(stats: dict) -> CombatStats:
    """Валидация боевых статов."""
    try:
        return CombatStats(**stats)
    except ValidationError as e:
        raise ValueError(f"Invalid combat stats: {e}")
