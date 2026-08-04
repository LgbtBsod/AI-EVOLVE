#!/usr/bin/env python3
"""Система предметов - управление предметами, экипировкой и инвентарем

Refactored:
- Убран wildcard import from typing import *
- Добавлены type hints (Python 3.10+)
- dataclass добавлен slots=True для оптимизации памяти
- time.perf_counter() заменен на time.perf_counter() для точности
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable, Set
import logging
import math
import time
import json

from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState
from src.core.constants import DamageType, constants_manager
from src.core.rng_manager import RNGManager
from src.core.state_manager import StateManager, StateType
from src.systems.attributes.attribute_system import AttributeSystem, AttributeSet, AttributeModifier, StatModifier, BaseAttribute, DerivedStat

logger = logging.getLogger(__name__)

# = ТИПЫ ПРЕДМЕТОВ

class ItemType(Enum):
    """Типы предметов"""
    WEAPON = "weapon"          # Оружие
    ARMOR = "armor"            # Броня
    ACCESSORY = "accessory"    # Аксессуары
    CONSUMABLE = "consumable"  # Расходники
    MATERIAL = "material"      # Материалы
    QUEST = "quest"            # Квестовые предметы
    CURRENCY = "currency"      # Валюта

class ItemRarity(Enum):
    """Редкость предметов"""
    COMMON = "common"          # Обычный
    UNCOMMON = "uncommon"      # Необычный
    RARE = "rare"              # Редкий
    EPIC = "epic"              # Эпический
    LEGENDARY = "legendary"    # Легендарный
    MYTHIC = "mythic"          # Мифический

class ItemSlot(Enum):
    """Слоты экипировки"""
    WEAPON_MAIN = "weapon_main"        # Основное оружие
    WEAPON_OFF = "weapon_off"          # Дополнительное оружие
    HEAD = "head"                      # Голова
    CHEST = "chest"                    # Грудь
    LEGS = "legs"                      # Ноги
    FEET = "feet"                      # Обувь
    HANDS = "hands"                    # Руки
    SHOULDERS = "shoulders"            # Плечи
    BACK = "back"                      # Спина
    WAIST = "waist"                    # Пояс
    NECK = "neck"                      # Шея
    RING_1 = "ring_1"                  # Кольцо 1
    RING_2 = "ring_2"                  # Кольцо 2
    TRINKET_1 = "trinket_1"            # Аксессуар 1
    TRINKET_2 = "trinket_2"            # Аксессуар 2

class ItemEffect(Enum):
    """Эффекты предметов"""
    DAMAGE = "damage"                  # Урон
    HEAL = "heal"                      # Лечение
    BUFF = "buff"                      # Усиление
    DEBUFF = "debuff"                  # Ослабление
    TELEPORT = "teleport"              # Телепортация
    SUMMON = "summon"                  # Призыв
    CRAFT = "craft"                    # Крафт

# = СТРУКТУРЫ ДАННЫХ

@dataclass(slots=True)
class ItemModifier:
    """Модификатор предмета (интеграция с системой атрибутов)"""
    modifier_type: str  # attribute, stat, temporary
    target: str  # attribute_name или stat_name
    value: float
    duration: float = -1.0  # -1 для постоянных модификаторов
    is_percentage: bool = False
    condition: Optional[str] = None
    source: str = "item"

@dataclass(slots=True)
class ItemRequirement:
    """Требование для использования предмета"""
    requirement_type: str  # level, attribute, skill, class
    target: str
    value: int
    description: str

@dataclass(slots=True)
class ItemEffect:
    """Эффект предмета"""
    effect_type: str  # damage, heal, buff, debuff, movement
    value: float
    target: str
    duration: float = 0.0
    radius: float = 0.0
    condition: Optional[str] = None

@dataclass(slots=True)
class ItemTemplate:
    """Шаблон предмета"""
    item_id: str
    name: str
    description: str
    item_type: ItemType
    rarity: ItemRarity
    level_requirement: int = 1
    slot: Optional[ItemSlot] = None
    stack_size: int = 1
    max_durability: int = 100
    weight: float = 1.0
    value: int = 0
    
    # Интеграция с системой атрибутов
    attribute_requirements: Dict[str, int] = field(default_factory=dict)  # attribute_name -> min_value
    stat_requirements: Dict[str, int] = field(default_factory=dict)  # stat_name -> min_value
    attribute_modifiers: List[ItemModifier] = field(default_factory=list)
    stat_modifiers: List[ItemModifier] = field(default_factory=list)
    
    # Эффекты предмета
    effects: List[ItemEffect] = field(default_factory=list)
    requirements: List[ItemRequirement] = field(default_factory=list)
    
    # Визуальные параметры
    icon_path: Optional[str] = None
    model_path: Optional[str] = None
    scale: float = 1.0
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    position_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)

@dataclass(slots=True)
class ItemInstance:
    """Экземпляр предмета"""
    instance_id: str
    template_id: str
    owner_id: Optional[str] = None
    quantity: int = 1
    durability: int = 100
    level: int = 1
    experience: int = 0
    is_equipped: bool = False
    equipped_slot: Optional[ItemSlot] = None
    created_at: float = field(default_factory=time.perf_counter)
    last_used: float = 0.0
    
    # Интеграция с системой атрибутов
    active_attribute_modifiers: List[AttributeModifier] = field(default_factory=list)
    active_stat_modifiers: List[StatModifier] = field(default_factory=list)
    
# Дополнительные свойства
    custom_properties: Dict[str, Any] = field(default_factory=dict)
    enchantments: List[str] = field(default_factory=list)

@dataclass(slots=True)
class Inventory:
    """Инвентарь сущности"""
    entity_id: str
    max_slots: int = 50
    max_weight: float = 100.0
    current_weight: float = 0.0
    items: Dict[str, ItemInstance] = field(default_factory=dict)  # instance_id -> item
    equipped_items: Dict[ItemSlot, str] = field(default_factory=dict)  # slot -> instance_id

@dataclass(slots=True)
class EquipmentSet:
    """Набор экипировки"""
    set_id: str
    name: str
    description: str
    pieces: List[str]  # item_ids
    bonus_effects: List[ItemEffect] = field(default_factory=list)
    bonus_modifiers: List[ItemModifier] = field(default_factory=list)

class ItemSystem(BaseComponent):
    """Система предметов"""
    
    def __init__(self):
        # RNG Manager для воспроизводимости
        self._rng = RNGManager()
        super().__init__(
            component_id="item_system",
            component_type=ComponentType.SYSTEM,
            priority=Priority.NORMAL
        )
        
        # Архитектурные компоненты
        self.state_manager: Optional[StateManager] = None
        self.attribute_system: Optional[AttributeSystem] = None
        
        # Шаблоны предметов
        self.item_templates: Dict[str, ItemTemplate] = {}
        self.equipment_sets: Dict[str, EquipmentSet] = {}
        
        # Инвентари сущностей
        self.inventories: Dict[str, Inventory] = {}
        
        # Настройки системы
        self.system_settings = {
            'auto_apply_item_modifiers': True,
            'enable_item_durability': True,
            'enable_item_leveling': True,
            'max_item_level': 100,
            'item_break_chance_on_death': 0.1,
            'allow_item_stacking': True,
            'max_stack_size': 999
        }
        
        # Статистика
        self.system_stats = {
            'total_items_created': 0,
            'total_items_destroyed': 0,
            'total_items_equipped': 0,
            'total_items_unequipped': 0,
            'active_modifiers': 0,
            'update_time': 0.0
        }
        
        # Callbacks
        self.on_item_created: Optional[Callable] = None
        self.on_item_destroyed: Optional[Callable] = None
        self.on_item_equipped: Optional[Callable] = None
        self.on_item_unequipped: Optional[Callable] = None
        self.on_item_used: Optional[Callable] = None
        
        logger.info("Система предметов инициализирована")
    
    def set_architecture_components(self, state_manager: StateManager, attribute_system: AttributeSystem):
        """Установка архитектурных компонентов"""
        self.state_manager = state_manager
        self.attribute_system = attribute_system
        logger.info("Архитектурные компоненты установлены в ItemSystem")
    
    def _register_system_states(self):
        """Регистрация состояний системы"""
        if self.state_manager:
            self.state_manager.set_state(
                f"{self.component_id}_settings",
                self.system_settings,
                StateType.SETTINGS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_stats",
                self.system_stats,
                StateType.STATISTICS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_state",
                self.state,
                StateType.SYSTEM_STATE
            )
    
    def initialize(self) -> bool:
        """Инициализация системы предметов"""
        try:
            logger.info("Инициализация ItemSystem...")
            
            self._register_system_states()
            
            # Создание базовых шаблонов предметов
            self._create_item_templates()
            
            # Создание наборов экипировки
            self._create_equipment_sets()
            
            self._state = LifecycleState.READY
            logger.info("ItemSystem инициализирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации ItemSystem: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def start(self) -> bool:
        """Запуск системы предметов"""
        try:
            logger.info("Запуск ItemSystem...")
            
            if self.state != LifecycleState.READY:
                logger.error("ItemSystem не готов к запуску")
                return False
            
            self._state = LifecycleState.RUNNING
            logger.info("ItemSystem запущен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска ItemSystem: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def update(self, delta_time: float):
        """Обновление системы предметов"""
        if self.state != LifecycleState.RUNNING:
            return
        
        try:
            start_time = time.perf_counter()
            
            # Обновление активных модификаторов предметов
            self._update_item_modifiers(delta_time)
            
            # Обновление износа предметов
            if self.system_settings['enable_item_durability']:
                self._update_item_durability(delta_time)
            
            self.system_stats['update_time'] = time.perf_counter() - start_time
            
            # Обновляем состояние в менеджере состояний
            if self.state_manager:
                self.state_manager.set_state(
                    f"{self.component_id}_stats",
                    self.system_stats,
                    StateType.STATISTICS
                )
                
        except Exception as e:
            logger.error(f"Ошибка обновления ItemSystem: {e}")
    
    def stop(self) -> bool:
        """Остановка системы предметов"""
        try:
            logger.info("Остановка ItemSystem...")
            
            self._state = LifecycleState.STOPPED
            logger.info("ItemSystem остановлен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки ItemSystem: {e}")
            return False
    
    def destroy(self) -> bool:
        """Уничтожение системы предметов"""
        try:
            logger.info("Уничтожение ItemSystem...")
            
            # Очистка всех модификаторов предметов
            self._clear_all_item_modifiers()
            
            self.item_templates.clear()
            self.equipment_sets.clear()
            self.inventories.clear()
            
            self._state = LifecycleState.DESTROYED
            logger.info("ItemSystem уничтожен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения ItemSystem: {e}")
            return False
    
    def _update_item_modifiers(self, delta_time: float):
        """Обновление модификаторов предметов"""
        current_time = time.perf_counter()
        
        for inventory in self.inventories.values():
            for item in inventory.items.values():
                # Очищаем истекшие модификаторы
                item.active_attribute_modifiers = [
                    mod for mod in item.active_attribute_modifiers
                    if mod.duration == -1.0 or current_time - mod.start_time < mod.duration
                ]
                
                item.active_stat_modifiers = [
                    mod for mod in item.active_stat_modifiers
                    if mod.duration == -1.0 or current_time - mod.start_time < mod.duration
                ]
        
        # Обновляем статистику
        total_modifiers = sum(
            len(item.active_attribute_modifiers) + len(item.active_stat_modifiers)
            for inventory in self.inventories.values()
            for item in inventory.items.values()
        )
        self.system_stats['active_modifiers'] = total_modifiers
    
    def _update_item_durability(self, delta_time: float):
        """Обновление износа предметов"""
        # Здесь может быть логика постепенного износа предметов
        # Например, износ при использовании, при получении урона и т.д.
        pass
    
    def _clear_all_item_modifiers(self):
        """Очистка всех модификаторов предметов"""
        for inventory in self.inventories.values():
            for item in inventory.items.values():
                item.active_attribute_modifiers.clear()
                item.active_stat_modifiers.clear()
    
    def _create_item_templates(self):
        """Создание базовых шаблонов предметов"""
        try:
            # Оружие с модификаторами атрибутов
            iron_sword = ItemTemplate(
                item_id="iron_sword",
                name="Железный меч",
                description="Надежный железный меч",
                item_type=ItemType.WEAPON,
                rarity=ItemRarity.COMMON,
                level_requirement=1,
                slot=ItemSlot.WEAPON_MAIN,
                max_durability=100,
                weight=3.0,
                value=50,
                attribute_requirements={"strength": 10},
                attribute_modifiers=[
                    ItemModifier("attribute", "strength", 5.0, duration=-1.0),
                    ItemModifier("stat", "physical_damage", 15.0, duration=-1.0)
                ],
                effects=[
                    ItemEffect("damage", 20.0, target="target")
                ],
                icon_path="assets/textures/items/iron_sword.png",
                model_path="assets/models/items/iron_sword.obj"
            )
            
            # Броня с модификаторами характеристик
            leather_armor = ItemTemplate(
                item_id="leather_armor",
                name="Кожаная броня",
                description="Легкая кожаная броня",
                item_type=ItemType.ARMOR,
                rarity=ItemRarity.COMMON,
                level_requirement=1,
                slot=ItemSlot.CHEST,
                max_durability=80,
                weight=2.0,
                value=30,
                attribute_requirements={"agility": 8},
                stat_modifiers=[
                    ItemModifier("stat", "defense", 10.0, duration=-1.0),
                    ItemModifier("stat", "dodge_chance", 0.05, duration=-1.0, is_percentage=True)
                ],
                icon_path="assets/textures/items/leather_armor.png",
                model_path="assets/models/items/leather_armor.obj"
            )
            
            # Кольцо с временными модификаторами
            ring_of_strength = ItemTemplate(
                item_id="ring_of_strength",
                name="Кольцо силы",
                description="Кольцо, увеличивающее силу",
                item_type=ItemType.ACCESSORY,
                rarity=ItemRarity.UNCOMMON,
                level_requirement=5,
                slot=ItemSlot.RING_1,
                max_durability=200,
                weight=0.1,
                value=100,
                attribute_modifiers=[
                    ItemModifier("attribute", "strength", 8.0, duration=-1.0),
                    ItemModifier("stat", "health", 20.0, duration=-1.0)
                ],
                icon_path="assets/textures/items/ring_of_strength.png",
                model_path="assets/models/items/ring.obj"
            )
            
            # Зелье лечения
            health_potion = ItemTemplate(
                item_id="health_potion",
                name="Зелье здоровья",
                description="Восстанавливает здоровье",
                item_type=ItemType.CONSUMABLE,
                rarity=ItemRarity.COMMON,
                level_requirement=1,
                stack_size=10,
                weight=0.5,
                value=25,
                effects=[
                    ItemEffect("heal", 50.0, target="self")
                ],
                icon_path="assets/textures/items/health_potion.png",
                model_path="assets/models/items/potion.obj"
            )
            
            # Добавляем шаблоны в систему
            self.item_templates["iron_sword"] = iron_sword
            self.item_templates["leather_armor"] = leather_armor
            self.item_templates["ring_of_strength"] = ring_of_strength
            self.item_templates["health_potion"] = health_potion
            
            logger.info(f"Создано {len(self.item_templates)} шаблонов предметов")
            
        except Exception as e:
            logger.error(f"Ошибка создания шаблонов предметов: {e}")
    
    def _create_equipment_sets(self):
        """Создание наборов экипировки"""
        try:
            # Набор воина
            warrior_set = EquipmentSet(
                set_id="warrior_set",
                name="Набор воина",
                description="Комплект брони для воина",
                pieces=["iron_sword", "leather_armor"],
                bonus_effects=[
                    ItemEffect("damage", 10.0, target="self")
                ],
                bonus_modifiers=[
                    ItemModifier("attribute", "strength", 10.0, duration=-1.0),
                    ItemModifier("stat", "defense", 15.0, duration=-1.0)
                ]
            )
            
            self.equipment_sets["warrior_set"] = warrior_set
            
            logger.info(f"Создано {len(self.equipment_sets)} наборов экипировки")
            
        except Exception as e:
            logger.error(f"Ошибка создания наборов экипировки: {e}")
    
    def create_item(self, template_id: str, owner_id: str = None, quantity: int = 1) -> Optional[ItemInstance]:
        """Создание предмета из шаблона"""
        try:
            if template_id not in self.item_templates:
                logger.warning(f"Шаблон предмета {template_id} не найден")
                return None
            
            template = self.item_templates[template_id]
            instance_id = f"{template_id}_{int(time.perf_counter() * 1000)}_{self._rng.randint(1000, 9999)}"
            
            item_instance = ItemInstance(
                instance_id=instance_id,
                template_id=template_id,
                owner_id=owner_id,
                quantity=quantity,
                durability=template.max_durability,
                level=1
            )
            
            # Обновляем статистику
            self.system_stats['total_items_created'] += 1
            
            # Вызываем callback
            if self.on_item_created:
                self.on_item_created(item_instance)
            
            logger.info(f"Создан предмет {template_id} (ID: {instance_id})")
            return item_instance
            
        except Exception as e:
            logger.error(f"Ошибка создания предмета {template_id}: {e}")
            return None
    
    def add_item_to_inventory(self, entity_id: str, item_instance: ItemInstance) -> bool:
        """Добавление предмета в инвентарь"""
        try:
            # Создаем инвентарь, если его нет
            if entity_id not in self.inventories:
                self.inventories[entity_id] = Inventory(entity_id=entity_id)
            
            inventory = self.inventories[entity_id]
            
            # Проверяем место в инвентаре
            if len(inventory.items) >= inventory.max_slots:
                logger.warning(f"Инвентарь сущности {entity_id} переполнен")
                return False
            
            # Проверяем вес
            template = self.item_templates[item_instance.template_id]
            if inventory.current_weight + template.weight > inventory.max_weight:
                logger.warning(f"Превышен максимальный вес инвентаря сущности {entity_id}")
                return False
            
            # Добавляем предмет
            inventory.items[item_instance.instance_id] = item_instance
            inventory.current_weight += template.weight
            item_instance.owner_id = entity_id
            
            logger.info(f"Предмет {item_instance.instance_id} добавлен в инвентарь {entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления предмета в инвентарь: {e}")
            return False
    
    def equip_item(self, entity_id: str, item_instance_id: str, slot: ItemSlot) -> bool:
        """Экипировка предмета"""
        try:
            if entity_id not in self.inventories:
                logger.warning(f"Инвентарь сущности {entity_id} не найден")
                return False
            
            inventory = self.inventories[entity_id]
            
            if item_instance_id not in inventory.items:
                logger.warning(f"Предмет {item_instance_id} не найден в инвентаре {entity_id}")
                return False
            
            item_instance = inventory.items[item_instance_id]
            template = self.item_templates[item_instance.template_id]
            
            # Проверяем слот
            if template.slot != slot:
                logger.warning(f"Предмет {item_instance_id} не подходит для слота {slot}")
                return False
            
            # Проверяем требования атрибутов
            if not self._check_item_requirements(template, entity_id):
                logger.warning(f"Сущность {entity_id} не соответствует требованиям предмета {item_instance_id}")
                return False
            
            # Снимаем предмет из этого слота, если он уже занят
            if slot in inventory.equipped_items:
                self.unequip_item(entity_id, slot)
            
            # Экипируем предмет
            inventory.equipped_items[slot] = item_instance_id
            item_instance.is_equipped = True
            item_instance.equipped_slot = slot
            
            # Применяем модификаторы предмета
            if self.system_settings['auto_apply_item_modifiers']:
                self._apply_item_modifiers(item_instance, template)
            
            # Обновляем статистику
            self.system_stats['total_items_equipped'] += 1
            
            # Вызываем callback
            if self.on_item_equipped:
                self.on_item_equipped(entity_id, item_instance, slot)
            
            logger.info(f"Предмет {item_instance_id} экипирован в слот {slot}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка экипировки предмета {item_instance_id}: {e}")
            return False
    
    def unequip_item(self, entity_id: str, slot: ItemSlot) -> bool:
        """Снятие предмета"""
        try:
            if entity_id not in self.inventories:
                logger.warning(f"Инвентарь сущности {entity_id} не найден")
                return False
            
            inventory = self.inventories[entity_id]
            
            if slot not in inventory.equipped_items:
                logger.warning(f"Слот {slot} не занят")
                return False
            
            item_instance_id = inventory.equipped_items[slot]
            item_instance = inventory.items[item_instance_id]
            
            # Убираем модификаторы предмета
            if self.system_settings['auto_apply_item_modifiers']:
                self._remove_item_modifiers(item_instance)
            
            # Снимаем предмет
            del inventory.equipped_items[slot]
            item_instance.is_equipped = False
            item_instance.equipped_slot = None
            
            # Обновляем статистику
            self.system_stats['total_items_unequipped'] += 1
            
            # Вызываем callback
            if self.on_item_unequipped:
                self.on_item_unequipped(entity_id, item_instance, slot)
            
            logger.info(f"Предмет {item_instance_id} снят из слота {slot}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка снятия предмета из слота {slot}: {e}")
            return False
    
    def use_item(self, entity_id: str, item_instance_id: str, target_id: str = None) -> bool:
        """Использование предмета"""
        try:
            if entity_id not in self.inventories:
                logger.warning(f"Инвентарь сущности {entity_id} не найден")
                return False
            
            inventory = self.inventories[entity_id]
            
            if item_instance_id not in inventory.items:
                logger.warning(f"Предмет {item_instance_id} не найден в инвентаре {entity_id}")
                return False
            
            item_instance = inventory.items[item_instance_id]
            template = self.item_templates[item_instance.template_id]
            
            # Проверяем, что предмет можно использовать
            if template.item_type != ItemType.CONSUMABLE:
                logger.warning(f"Предмет {item_instance_id} нельзя использовать")
                return False
            
            # Применяем эффекты предмета
            self._apply_item_effects(template, entity_id, target_id)
            
            # Уменьшаем количество
            item_instance.quantity -= 1
            item_instance.last_used = time.perf_counter()
            
            # Удаляем предмет, если количество стало 0
            if item_instance.quantity <= 0:
                self.destroy_item(entity_id, item_instance_id)
            
            # Вызываем callback
            if self.on_item_used:
                self.on_item_used(entity_id, item_instance, target_id)
            
            logger.info(f"Предмет {item_instance_id} использован сущностью {entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка использования предмета {item_instance_id}: {e}")
            return False
    
    def destroy_item(self, entity_id: str, item_instance_id: str) -> bool:
        """Уничтожение предмета"""
        try:
            if entity_id not in self.inventories:
                logger.warning(f"Инвентарь сущности {entity_id} не найден")
                return False
            
            inventory = self.inventories[entity_id]
            
            if item_instance_id not in inventory.items:
                logger.warning(f"Предмет {item_instance_id} не найден в инвентаре {entity_id}")
                return False
            
            item_instance = inventory.items[item_instance_id]
            template = self.item_templates[item_instance.template_id]
            
            # Убираем модификаторы, если предмет экипирован
            if item_instance.is_equipped:
                self._remove_item_modifiers(item_instance)
                
                # Убираем из экипировки
                if item_instance.equipped_slot in inventory.equipped_items:
                    del inventory.equipped_items[item_instance.equipped_slot]
            
            # Убираем вес
            inventory.current_weight -= template.weight
            
            # Удаляем предмет
            del inventory.items[item_instance_id]
            
            # Обновляем статистику
            self.system_stats['total_items_destroyed'] += 1
            
            # Вызываем callback
            if self.on_item_destroyed:
                self.on_item_destroyed(entity_id, item_instance)
            
            logger.info(f"Предмет {item_instance_id} уничтожен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения предмета {item_instance_id}: {e}")
            return False
    
    def _check_item_requirements(self, template: ItemTemplate, entity_id: str) -> bool:
        """Проверка требований предмета"""
        try:
            # Здесь должна быть проверка требований атрибутов и характеристик
            # через систему атрибутов
                return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки требований предмета: {e}")
            return False
    
    def _apply_item_modifiers(self, item_instance: ItemInstance, template: ItemTemplate):
        """Применение модификаторов предмета"""
        try:
            current_time = time.perf_counter()
            
            # Применяем модификаторы атрибутов
            for modifier in template.attribute_modifiers:
                attr_modifier = AttributeModifier(
                    modifier_id=f"item_{item_instance.instance_id}_{modifier.target}",
                    attribute=BaseAttribute(modifier.target),
                    value=modifier.value,
                    source=f"item_{template.item_id}",
                    duration=modifier.duration,
                    start_time=current_time,
                    is_percentage=modifier.is_percentage
                )
                item_instance.active_attribute_modifiers.append(attr_modifier)
            
            # Применяем модификаторы характеристик
            for modifier in template.stat_modifiers:
                stat_modifier = StatModifier(
                    modifier_id=f"item_{item_instance.instance_id}_{modifier.target}",
                    stat=DerivedStat(modifier.target),
                    value=modifier.value,
                    source=f"item_{template.item_id}",
                    duration=modifier.duration,
                    start_time=current_time,
                    is_percentage=modifier.is_percentage
                )
                item_instance.active_stat_modifiers.append(stat_modifier)
            
            logger.debug(f"Применены модификаторы предмета {template.item_id}")
            
        except Exception as e:
            logger.error(f"Ошибка применения модификаторов предмета: {e}")
    
    def _remove_item_modifiers(self, item_instance: ItemInstance):
        """Удаление модификаторов предмета"""
        try:
            item_instance.active_attribute_modifiers.clear()
            item_instance.active_stat_modifiers.clear()
            
            logger.debug(f"Удалены модификаторы предмета {item_instance.instance_id}")
            
        except Exception as e:
            logger.error(f"Ошибка удаления модификаторов предмета: {e}")
    
    def _apply_item_effects(self, template: ItemTemplate, caster_id: str, target_id: str):
        """Применение эффектов предмета"""
        try:
            for effect in template.effects:
                # Здесь должна быть логика применения эффектов
                # Например, лечение, нанесение урона, баффы и т.д.
                logger.debug(f"Применен эффект {effect.effect_type} от предмета {template.item_id}")
                
        except Exception as e:
            logger.error(f"Ошибка применения эффектов предмета: {e}")
    
    def get_item_modifiers_for_entity(self, entity_id: str) -> Tuple[List[AttributeModifier], List[StatModifier]]:
        """Получение всех активных модификаторов предметов для сущности"""
        try:
            if entity_id not in self.inventories:
                return [], []
            
            inventory = self.inventories[entity_id]
            all_attribute_modifiers = []
            all_stat_modifiers = []
            
            # Собираем модификаторы от экипированных предметов
            for slot, item_instance_id in inventory.equipped_items.items():
                if item_instance_id in inventory.items:
                    item_instance = inventory.items[item_instance_id]
                    all_attribute_modifiers.extend(item_instance.active_attribute_modifiers)
                    all_stat_modifiers.extend(item_instance.active_stat_modifiers)
            
            return all_attribute_modifiers, all_stat_modifiers
            
        except Exception as e:
            logger.error(f"Ошибка получения модификаторов предметов для сущности {entity_id}: {e}")
            return [], []
    
    def get_equipment_set_bonuses(self, entity_id: str) -> Tuple[List[AttributeModifier], List[StatModifier]]:
        """Получение бонусов от наборов экипировки"""
        try:
            if entity_id not in self.inventories:
                return [], []
            
            inventory = self.inventories[entity_id]
            all_attribute_modifiers = []
            all_stat_modifiers = []
            
            # Проверяем каждый набор экипировки
            for set_id, equipment_set in self.equipment_sets.items():
                equipped_pieces = 0
                
                for piece_id in equipment_set.pieces:
                    # Проверяем, экипирован ли предмет из набора
                    for item_instance in inventory.items.values():
                        if (item_instance.template_id == piece_id and 
                            item_instance.is_equipped):
                            equipped_pieces += 1
                        break
                
                # Если все предметы набора экипированы, применяем бонусы
                if equipped_pieces == len(equipment_set.pieces):
                    current_time = time.perf_counter()
                    
                    for modifier in equipment_set.bonus_modifiers:
                        if modifier.modifier_type == "attribute":
                            attr_modifier = AttributeModifier(
                                modifier_id=f"set_{set_id}_{modifier.target}",
                                attribute=BaseAttribute(modifier.target),
                                value=modifier.value,
                                source=f"equipment_set_{set_id}",
                                duration=modifier.duration,
                                start_time=current_time,
                                is_percentage=modifier.is_percentage
                            )
                            all_attribute_modifiers.append(attr_modifier)
                        
                        elif modifier.modifier_type == "stat":
                            stat_modifier = StatModifier(
                                modifier_id=f"set_{set_id}_{modifier.target}",
                                stat=DerivedStat(modifier.target),
                                value=modifier.value,
                                source=f"equipment_set_{set_id}",
                                duration=modifier.duration,
                                start_time=current_time,
                                is_percentage=modifier.is_percentage
                            )
                            all_stat_modifiers.append(stat_modifier)
            
            return all_attribute_modifiers, all_stat_modifiers
            
        except Exception as e:
            logger.error(f"Ошибка получения бонусов наборов экипировки для сущности {entity_id}: {e}")
            return [], []
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
                    'name': self.component_id,
                    'state': self.state.value,
                    'priority': self.priority.value,
                    'item_templates_count': len(self.item_templates),
                    'equipment_sets_count': len(self.equipment_sets),
                    'inventories_count': len(self.inventories),
                    'total_items_created': self.system_stats['total_items_created'],
                    'total_items_destroyed': self.system_stats['total_items_destroyed'],
                    'total_items_equipped': self.system_stats['total_items_equipped'],
                    'total_items_unequipped': self.system_stats['total_items_unequipped'],
                    'active_modifiers': self.system_stats['active_modifiers'],
                    'update_time': self.system_stats['update_time']
                }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.system_stats = {
            'total_items_created': 0,
            'total_items_destroyed': 0,
            'total_items_equipped': 0,
            'total_items_unequipped': 0,
            'active_modifiers': 0,
            'update_time': 0.0
        }
