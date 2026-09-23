#!/usr/bin/env python3
"""
EntityManager - централизованное управление сущностями.
SRP: Создание, хранение, удаление и поиск игровых сущностей.
SSOT: Единый источник истины для всех сущностей в мире.
"""

import logging
import uuid
from typing import Any, Optional, Type, TypeVar, Dict, List, Set
from dataclasses import dataclass, field
from collections import defaultdict

from ..entities.base_entity import BaseEntity, EntityState
from ..entities.character import Character
from ..entities.enemy import EnhancedEnemy

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseEntity)


@dataclass
class EntityFilter:
    """Фильтр для поиска сущностей."""
    entity_type: Optional[str] = None
    state: Optional[EntityState] = None
    alive_only: bool = False
    tags: Set[str] = field(default_factory=set)
    max_results: int = -1  # -1 = без ограничений


class EntityManager:
    """
    Менеджер сущностей - SSOT для всех игровых объектов.
    
    Принципы:
    - SRP: Только управление жизненным циклом сущностей
    - DRY: Централизованная логика создания/удаления
    - SOLID: Интерфейс для работы со сущностями
    - SSOT: Все сущности хранятся здесь
    """
    
    def __init__(self):
        # Хранилище сущностей по ID
        self._entities: Dict[str, BaseEntity] = {}
        
        # Индексы для быстрого поиска
        self._by_type: Dict[str, Set[str]] = defaultdict(set)
        self._by_state: Dict[EntityState, Set[str]] = defaultdict(set)
        self._by_position: Dict[tuple, Set[str]] = defaultdict(set)
        
        # Счётчики для статистики
        self._created_count = 0
        self._destroyed_count = 0
        
        # Фабрики сущностей по типам
        self._factories: Dict[str, callable] = {
            'base': lambda **kw: BaseEntity(
                entity_id=kw.get('entity_id', str(uuid.uuid4())),
                entity_type=kw.get('entity_type', 'generic'),
                name=kw.get('name', '')
            ),
            'character': lambda **kw: Character(
                game=kw.get('game'),
                x=kw.get('x', 0),
                y=kw.get('y', 0),
                z=kw.get('z', 0),
                name=kw.get('name', 'Hero')
            ),
            'enemy': lambda **kw: EnhancedEnemy(
                game=kw.get('game'),
                x=kw.get('x', 0),
                y=kw.get('y', 0),
                z=kw.get('z', 0),
                enemy_type=kw.get('enemy_type', 'slime'),
                level=kw.get('level'),
                color=kw.get('color')
            )
        }
    
    def register_factory(self, entity_type: str, factory: callable):
        """Зарегистрировать фабрику для типа сущности."""
        self._factories[entity_type] = factory
        logger.debug(f"Зарегистрирована фабрика для типа '{entity_type}'")
    
    def create_entity(
        self,
        entity_type: str = 'base',
        position: Optional[List[float]] = None,
        **kwargs
    ) -> Optional[BaseEntity]:
        """
        Создать новую сущность.
        
        Args:
            entity_type: Тип сущности ('base', 'character', 'enemy', ...)
            position: Позиция [x, y, z]
            **kwargs: Дополнительные параметры для фабрики
        
        Returns:
            Созданная сущность или None при ошибке
        """
        try:
            if entity_type not in self._factories:
                logger.error(f"Неизвестный тип сущности: {entity_type}")
                return None
            
            # Создаём сущность через фабрику
            if position:
                kwargs['x'] = position[0]
                kwargs['y'] = position[1]
                kwargs['z'] = position[2]
            
            entity = self._factories[entity_type](**kwargs)
            
            if not entity:
                logger.error(f"Фабрика вернула None для типа {entity_type}")
                return None
            
            # Инициализируем сущность
            if not entity.initialize():
                logger.error(f"Ошибка инициализации сущности {entity.entity_id}")
                return None
            
            # Регистрируем сущность
            self._entities[entity.entity_id] = entity
            self._update_indices(entity, add=True)
            self._created_count += 1
            
            logger.info(f"Создана сущность {entity.entity_id} ({entity_type})")
            return entity
            
        except Exception as e:
            logger.error(f"Ошибка создания сущности: {e}", exc_info=True)
            return None
    
    def get_entity(self, entity_id: str) -> Optional[BaseEntity]:
        """Получить сущность по ID."""
        return self._entities.get(entity_id)
    
    def remove_entity(self, entity_id: str) -> bool:
        """
        Удалить сущность.
        
        Returns:
            True если успешно удалена
        """
        entity = self._entities.get(entity_id)
        if not entity:
            logger.warning(f"Сущность {entity_id} не найдена для удаления")
            return False
        
        try:
            # Уничтожаем сущность
            entity.destroy()
            
            # Удаляем из хранилища
            del self._entities[entity_id]
            self._update_indices(entity, add=False)
            self._destroyed_count += 1
            
            logger.info(f"Удалена сущность {entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления сущности {entity_id}: {e}")
            return False
    
    def find_entities(self, filter: EntityFilter) -> List[BaseEntity]:
        """
        Найти сущности по фильтру.
        
        Returns:
            Список найденных сущностей
        """
        results: List[BaseEntity] = []
        
        # Определяем начальный набор ID для поиска
        candidate_ids: Set[str] = set(self._entities.keys())
        
        # Фильтр по типу
        if filter.entity_type:
            type_ids = self._by_type.get(filter.entity_type, set())
            candidate_ids &= type_ids
        
        # Фильтр по состоянию
        if filter.state:
            state_ids = self._by_state.get(filter.state, set())
            candidate_ids &= state_ids
        
        # Фильтр только живые
        if filter.alive_only:
            alive_ids = self._by_state.get(EntityState.ALIVE, set())
            candidate_ids &= alive_ids
        
        # Применяем остальные фильтры и собираем результаты
        for entity_id in candidate_ids:
            entity = self._entities.get(entity_id)
            if not entity:
                continue
            
            # Проверка тегов (если есть в сущности)
            if filter.tags:
                entity_tags = getattr(entity, 'tags', set())
                if not filter.tags.issubset(entity_tags):
                    continue
            
            results.append(entity)
            
            # Проверка лимита
            if filter.max_results > 0 and len(results) >= filter.max_results:
                break
        
        return results
    
    def find_by_type(self, entity_type: str, alive_only: bool = False) -> List[BaseEntity]:
        """Найти все сущности указанного типа."""
        filter = EntityFilter(entity_type=entity_type, alive_only=alive_only)
        return self.find_entities(filter)
    
    def find_alive(self) -> List[BaseEntity]:
        """Найти все живые сущности."""
        return self.find_entities(EntityFilter(alive_only=True))
    
    def find_nearby(
        self,
        position: List[float],
        radius: float,
        alive_only: bool = True
    ) -> List[BaseEntity]:
        """
        Найти сущности в радиусе.
        
        Args:
            position: Центр поиска [x, y, z]
            radius: Радиус поиска
            alive_only: Искать только живые
        
        Returns:
            Список сущностей в радиусе
        """
        nearby = []
        for entity in self.find_entities(EntityFilter(alive_only=alive_only)):
            dx = entity.position[0] - position[0]
            dy = entity.position[1] - position[1]
            dz = entity.position[2] - position[2]
            distance = math.sqrt(dx*dx + dy*dy + dz*dz)
            
            if distance <= radius:
                nearby.append(entity)
        
        return nearby
    
    def update_all(self, delta_time: float):
        """Обновить все активные сущности."""
        for entity in self.find_entities(EntityFilter(state=EntityState.ALIVE)):
            try:
                entity.update(delta_time)
            except Exception as e:
                logger.error(f"Ошибка обновления сущности {entity.entity_id}: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику менеджера сущностей."""
        return {
            'total_entities': len(self._entities),
            'created': self._created_count,
            'destroyed': self._destroyed_count,
            'by_type': {k: len(v) for k, v in self._by_type.items()},
            'by_state': {k.value: len(v) for k, v in self._by_state.items()}
        }
    
    def clear(self):
        """Удалить все сущности."""
        for entity_id in list(self._entities.keys()):
            self.remove_entity(entity_id)
        logger.info("Все сущности удалены")
    
    def _update_indices(self, entity: BaseEntity, add: bool = True):
        """Обновить индексы для сущности."""
        if add:
            # По типу
            type_key = str(entity.entity_type.value if hasattr(entity.entity_type, 'value') else entity.entity_type)
            self._by_type[type_key].add(entity.entity_id)
            
            # По состоянию
            self._by_state[entity.state].add(entity.entity_id)
            
            # По позиции (округлённой для группировки)
            pos_key = (round(entity.position[0]), round(entity.position[1]))
            self._by_position[pos_key].add(entity.entity_id)
        else:
            # Удаляем из индексов
            type_key = str(entity.entity_type.value if hasattr(entity.entity_type, 'value') else entity.entity_type)
            self._by_type[type_key].discard(entity.entity_id)
            self._by_state[entity.state].discard(entity.entity_id)
            pos_key = (round(entity.position[0]), round(entity.position[1]))
            self._by_position[pos_key].discard(entity.entity_id)


# Импорт math здесь для избежания циклических зависимостей
import math
