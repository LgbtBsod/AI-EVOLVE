"""Inventory Plugin - система инвентаря и предметов."""

from typing import Dict, List, Optional, Any
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, select
from sqlalchemy.orm import relationship, Session

from ai_evolve.core.plugin_base import GamePlugin as PluginBase
from ai_evolve.core.event_system import EventSystem
from ai_evolve.db.database_core import Base


class Item(Base):
    """Модель предмета в БД."""
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    item_type = Column(String(50), nullable=False)  # weapon, armor, consumable, etc.
    stats = Column(JSON, default=dict)  # {attack: 10, defense: 5}
    effects = Column(JSON, default=list)  # [{"type": "poison", "duration": 3}]
    stack_size = Column(Integer, default=1)
    max_stack = Column(Integer, default=99)
    description = Column(String(500))


class InventorySlot(Base):
    """Слот инвентаря."""
    __tablename__ = "inventory_slots"
    
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    slot_index = Column(Integer, nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"))
    quantity = Column(Integer, default=1)
    
    item = relationship("Item")


class InventoryPlugin(PluginBase):
    """Плагин управления инвентарем."""
    
    def __init__(self):
        super().__init__("InventoryPlugin")
        self._inventories: Dict[int, Dict[int, dict]] = {}  # entity_id -> {slot_idx: item_data}
        self._event_system: Optional[EventSystem] = None
    
    @property
    def dependencies(self) -> List[str]:
        return ["DatabaseCore"]
    
    def on_init(self, game_core: Any = None) -> bool:
        """Инициализация плагина."""
        try:
            self._event_system = EventSystem.get_instance()
            
            # Регистрируем обработчики событий
            self._event_system.on("entity_created", self._on_entity_created)
            self._event_system.on("item_pickup", self._on_item_pickup)
            self._event_system.on("item_use", self._on_item_use)
            self._event_system.on("item_drop", self._on_item_drop)
            
            # Создаем таблицы БД если не существуют
            if game_core:
                db_core = game_core.get_plugin("DatabaseCore")
                if db_core:
                    db_core.create_tables([Item, InventorySlot])
            
            self.logger.info("InventoryPlugin initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize InventoryPlugin: {e}")
            return False
    
    def on_update(self, delta_time: float) -> None:
        """Обновление состояния инвентаря (если нужно)."""
        pass
    
    def on_shutdown(self) -> None:
        """Очистка ресурсов."""
        if self._event_system:
            self._event_system.off("entity_created", self._on_entity_created)
            self._event_system.off("item_pickup", self._on_item_pickup)
            self._event_system.off("item_use", self._on_item_use)
            self._event_system.off("item_drop", self._on_item_drop)
        
        self._inventories.clear()
        self.logger.info("InventoryPlugin shutdown complete")
    
    def _on_entity_created(self, event_data: dict) -> None:
        """Создание пустого инвентаря для новой сущности."""
        entity_id = event_data.get("entity_id")
        if entity_id and entity_id not in self._inventories:
            self._inventories[entity_id] = {}
            self.logger.debug(f"Created inventory for entity {entity_id}")
    
    def _on_item_pickup(self, event_data: dict) -> None:
        """Подбор предмета."""
        entity_id = event_data.get("entity_id")
        item_data = event_data.get("item")
        
        if entity_id and item_data:
            self.add_item(entity_id, item_data)
            self._event_system.emit("item_added", {
                "entity_id": entity_id,
                "item": item_data
            })
    
    def _on_item_use(self, event_data: dict) -> None:
        """Использование предмета."""
        entity_id = event_data.get("entity_id")
        slot_index = event_data.get("slot_index")
        
        if entity_id is not None and slot_index is not None:
            item = self.get_item_at_slot(entity_id, slot_index)
            if item:
                # Применяем эффекты предмета
                if "effects" in item:
                    for effect in item["effects"]:
                        self._event_system.emit("effect_apply", {
                            "target_id": entity_id,
                            "effect": effect
                        })
                
                # Уменьшаем количество или удаляем предмет
                if item.get("quantity", 1) > 1:
                    item["quantity"] -= 1
                else:
                    self.remove_item_at_slot(entity_id, slot_index)
                
                self._event_system.emit("item_used", {
                    "entity_id": entity_id,
                    "item": item
                })
    
    def _on_item_drop(self, event_data: dict) -> None:
        """Выбрасывание предмета."""
        entity_id = event_data.get("entity_id")
        slot_index = event_data.get("slot_index")
        
        if entity_id is not None and slot_index is not None:
            item = self.remove_item_at_slot(entity_id, slot_index)
            if item:
                self._event_system.emit("item_dropped", {
                    "entity_id": entity_id,
                    "item": item,
                    "position": event_data.get("position")
                })
    
    def add_item(self, entity_id: int, item_data: dict, quantity: int = 1) -> bool:
        """Добавить предмет в инвентарь."""
        if entity_id not in self._inventories:
            self._inventories[entity_id] = {}
        
        max_stack = item_data.get("max_stack", 99)
        
        # Пытаемся стакнуть с существующими
        for slot_idx, existing_item in list(self._inventories[entity_id].items()):
            if (existing_item.get("id") == item_data.get("id") and 
                existing_item.get("quantity", 1) < existing_item.get("max_stack", max_stack)):
                available_space = existing_item.get("max_stack", max_stack) - existing_item.get("quantity", 1)
                add_qty = min(quantity, available_space)
                existing_item["quantity"] = existing_item.get("quantity", 1) + add_qty
                quantity -= add_qty
                
                if quantity <= 0:
                    return True
        
        # Создаем новый слот если осталось количество
        while quantity > 0:
            new_slot_idx = len(self._inventories[entity_id])
            stack_qty = min(quantity, max_stack)
            new_item = item_data.copy()
            new_item["quantity"] = stack_qty
            new_item["max_stack"] = max_stack
            self._inventories[entity_id][new_slot_idx] = new_item
            
            # Сохраняем в БД
            self._save_to_db(entity_id, new_slot_idx, new_item)
            
            quantity -= stack_qty
            
        return True
    
    def remove_item_at_slot(self, entity_id: int, slot_index: int) -> Optional[dict]:
        """Удалить предмет из слота."""
        if entity_id in self._inventories and slot_index in self._inventories[entity_id]:
            item = self._inventories[entity_id].pop(slot_index)
            
            # Обновляем индексы слотов
            new_inventory = {}
            for new_idx, (old_idx, old_item) in enumerate(sorted(self._inventories[entity_id].items())):
                new_inventory[new_idx] = old_item
            self._inventories[entity_id] = new_inventory
            
            # Обновляем в БД
            self._sync_db(entity_id)
            
            return item
        return None
    
    def get_item_at_slot(self, entity_id: int, slot_index: int) -> Optional[dict]:
        """Получить предмет из слота."""
        if entity_id in self._inventories:
            return self._inventories[entity_id].get(slot_index)
        return None
    
    def get_inventory(self, entity_id: int) -> Dict[int, dict]:
        """Получить весь инвентарь сущности."""
        return self._inventories.get(entity_id, {})
    
    def has_item(self, entity_id: int, item_id: int, quantity: int = 1) -> bool:
        """Проверить наличие предмета в нужном количестве."""
        if entity_id not in self._inventories:
            return False
        
        total_quantity = sum(
            item.get("quantity", 1) 
            for item in self._inventories[entity_id].values() 
            if item.get("id") == item_id
        )
        return total_quantity >= quantity
    
    def _save_to_db(self, entity_id: int, slot_index: int, item_data: dict) -> None:
        """Сохранить предмет в БД."""
        try:
            db_core = EventSystem.get_instance().get_context("db_core")
            if not db_core:
                return
            
            with db_core.session_factory() as session:
                # Проверяем/создаем предмет
                item = session.execute(select(Item).where(Item.id == item_data.get("id"))).scalar_one_or_none()
                if not item:
                    item = Item(
                        id=item_data.get("id"),
                        name=item_data.get("name", "Unknown"),
                        item_type=item_data.get("type", "misc"),
                        stats=item_data.get("stats", {}),
                        effects=item_data.get("effects", []),
                        stack_size=item_data.get("quantity", 1),
                        max_stack=item_data.get("max_stack", 99),
                        description=item_data.get("description", "")
                    )
                    session.add(item)
                
                # Создаем/обновляем слот инвентаря
                slot = session.execute(
                    select(InventorySlot).where(
                        InventorySlot.entity_id == entity_id,
                        InventorySlot.slot_index == slot_index
                    )
                ).scalar_one_or_none()
                
                if slot:
                    slot.item_id = item.id
                    slot.quantity = item_data.get("quantity", 1)
                else:
                    slot = InventorySlot(
                        entity_id=entity_id,
                        slot_index=slot_index,
                        item_id=item.id,
                        quantity=item_data.get("quantity", 1)
                    )
                    session.add(slot)
                
                session.commit()
        except Exception as e:
            self.logger.error(f"Error saving inventory to DB: {e}")
    
    def _sync_db(self, entity_id: int) -> None:
        """Синхронизировать инвентарь с БД."""
        try:
            db_core = EventSystem.get_instance().get_context("db_core")
            if not db_core:
                return
            
            with db_core.session_factory() as session:
                # Удаляем все старые слоты
                session.query(InventorySlot).filter(
                    InventorySlot.entity_id == entity_id
                ).delete()
                
                # Добавляем актуальные
                for slot_idx, item_data in self._inventories.get(entity_id, {}).items():
                    slot = InventorySlot(
                        entity_id=entity_id,
                        slot_index=slot_idx,
                        item_id=item_data.get("id"),
                        quantity=item_data.get("quantity", 1)
                    )
                    session.add(slot)
                
                session.commit()
        except Exception as e:
            self.logger.error(f"Error syncing inventory with DB: {e}")
    
    def get_inventory_size(self, entity_id: int) -> int:
        """Получить размер инвентаря."""
        return len(self._inventories.get(entity_id, {}))
    
    def clear_inventory(self, entity_id: int) -> None:
        """Очистить инвентарь."""
        if entity_id in self._inventories:
            self._inventories[entity_id] = {}
            self._sync_db(entity_id)
            if self._event_system:
                self._event_system.emit("inventory_cleared", {"entity_id": entity_id})
