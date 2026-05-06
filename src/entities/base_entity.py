#!/usr/bin/env python3
"""Базовая сущность для всех игровых объектов"""

import logging
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)

class EntityState(Enum):
    """Состояния сущности"""
    ALIVE = "alive"
    DEAD = "dead"
    INACTIVE = "inactive"
    SPAWNING = "spawning"
    DESPAWNING = "despawning"

class BaseEntity:
    """Базовый класс для всех игровых сущностей"""
    
    def __init__(self, entity_id: str, entity_type: Enum, name: str = ""):
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.name = name or entity_id
        self.state = EntityState.INACTIVE
        
        # Позиция и трансформация
        self.position = [0.0, 0.0, 0.0]
        self.rotation = 0.0
        self.scale = 1.0
        
        # Характеристики
        self.health = 100.0
        self.max_health = 100.0
        self.is_alive = True
        
        # Компоненты
        self.components: Dict[str, Any] = {}
        
        # Metadata
        self.created_at = None
        self.updated_at = None
        
        logger.debug(f"Сущность {self.entity_id} ({self.entity_type}) создана")
    
    def initialize(self) -> bool:
        """Инициализация сущности"""
        try:
            self.state = EntityState.SPAWNING
            self.is_alive = True
            self.state = EntityState.ALIVE
            logger.debug(f"Сущность {self.entity_id} инициализирована")
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации сущности {self.entity_id}: {e}")
            self.state = EntityState.INACTIVE
            return False
    
    def update(self, delta_time: float) -> None:
        """Обновление сущности"""
        if self.state != EntityState.ALIVE:
            return
        
        # Обновление логики сущности (переопределяется в наследниках)
        pass
    
    def take_damage(self, damage: float, damage_type: str = "physical") -> float:
        """Получение урона"""
        if not self.is_alive:
            return 0.0
        
        actual_damage = max(0, damage)
        self.health -= actual_damage
        
        if self.health <= 0:
            self.health = 0
            self.die()
        
        logger.debug(f"Сущность {self.entity_id} получила {actual_damage} урона, осталось {self.health} HP")
        return actual_damage
    
    def heal(self, amount: float) -> float:
        """Лечение сущности"""
        if not self.is_alive:
            return 0.0
        
        actual_heal = min(amount, self.max_health - self.health)
        self.health += actual_heal
        
        logger.debug(f"Сущность {self.entity_id} вылечена на {actual_heal}, теперь {self.health} HP")
        return actual_heal
    
    def die(self) -> None:
        """Смерть сущности"""
        self.is_alive = False
        self.state = EntityState.DEAD
        logger.info(f"Сущность {self.entity_id} умерла")
    
    def respawn(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> bool:
        """Возрождение сущности"""
        try:
            self.position = [x, y, z]
            self.health = self.max_health
            self.is_alive = True
            self.state = EntityState.ALIVE
            logger.info(f"Сущность {self.entity_id} возрождена в ({x}, {y}, {z})")
            return True
        except Exception as e:
            logger.error(f"Ошибка возрождения сущности {self.entity_id}: {e}")
            return False
    
    def add_component(self, component_name: str, component: Any) -> bool:
        """Добавление компонента"""
        try:
            self.components[component_name] = component
            logger.debug(f"Компонент {component_name} добавлен к {self.entity_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления компонента {component_name}: {e}")
            return False
    
    def get_component(self, component_name: str) -> Optional[Any]:
        """Получение компонента"""
        return self.components.get(component_name)
    
    def remove_component(self, component_name: str) -> bool:
        """Удаление компонента"""
        if component_name in self.components:
            del self.components[component_name]
            logger.debug(f"Компонент {component_name} удалён из {self.entity_id}")
            return True
        return False
    
    def destroy(self) -> bool:
        """Уничтожение сущности"""
        try:
            self.state = EntityState.DESPAWNING
            self.components.clear()
            self.state = EntityState.INACTIVE
            logger.info(f"Сущность {self.entity_id} уничтожена")
            return True
        except Exception as e:
            logger.error(f"Ошибка уничтожения сущности {self.entity_id}: {e}")
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь"""
        return {
            'entity_id': self.entity_id,
            'entity_type': self.entity_type.value if hasattr(self.entity_type, 'value') else str(self.entity_type),
            'name': self.name,
            'state': self.state.value,
            'position': self.position.copy(),
            'rotation': self.rotation,
            'scale': self.scale,
            'health': self.health,
            'max_health': self.max_health,
            'is_alive': self.is_alive,
            'components': list(self.components.keys())
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], game=None) -> 'BaseEntity':
        """Десериализация из словаря"""
        entity = cls(
            entity_id=data['entity_id'],
            entity_type=data['entity_type'],
            name=data.get('name', '')
        )
        entity.position = data.get('position', [0.0, 0.0, 0.0])
        entity.rotation = data.get('rotation', 0.0)
        entity.scale = data.get('scale', 1.0)
        entity.health = data.get('health', 100.0)
        entity.max_health = data.get('max_health', 100.0)
        entity.is_alive = data.get('is_alive', True)
        entity.state = EntityState(data.get('state', 'inactive'))
        return entity
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(id={self.entity_id}, type={self.entity_type}, health={self.health}/{self.max_health})"
    
    def __repr__(self) -> str:
        return self.__str__()
