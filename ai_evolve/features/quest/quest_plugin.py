"""Quest Plugin - система квестов и заданий."""

from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, select, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from ai_evolve.core.plugin_base import GamePlugin as PluginBase
from ai_evolve.core.event_system import EventSystem
from ai_evolve.db.database_core import Base


class QuestState(Enum):
    """Состояния квеста."""
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class QuestObjective(Base):
    """Цель квеста в БД."""
    __tablename__ = "quest_objectives"
    
    id = Column(Integer, primary_key=True)
    quest_id = Column(Integer, ForeignKey("quests.id"), nullable=False)
    description = Column(String(500), nullable=False)
    objective_type = Column(String(50), nullable=False)  # kill, collect, talk, reach_location
    target_count = Column(Integer, default=1)
    current_count = Column(Integer, default=0)
    is_completed = Column(Integer, default=0)  # SQLite boolean


class Quest(Base):
    """Модель квеста в БД."""
    __tablename__ = "quests"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000))
    giver_id = Column(Integer)  # NPC entity_id
    state = Column(String(50), default="not_started")
    reward_xp = Column(Integer, default=0)
    reward_gold = Column(Integer, default=0)
    reward_items = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    objectives = relationship("QuestObjective", backref="quest", cascade="all, delete-orphan")


class QuestPlugin(PluginBase):
    """Плагин управления квестами."""
    
    def __init__(self):
        super().__init__("QuestPlugin")
        self._quests: Dict[int, Dict[int, dict]] = {}  # entity_id -> {quest_id: quest_data}
        self._quest_templates: Dict[int, dict] = {}  # quest_id -> template
        self._event_system: Optional[EventSystem] = None
        self._objective_handlers: Dict[str, Callable] = {}
    
    @property
    def dependencies(self) -> List[str]:
        return ["DatabaseCore", "InventoryPlugin"]
    
    def on_init(self, game_core: Any = None) -> bool:
        """Инициализация плагина."""
        try:
            self._event_system = EventSystem.get_instance()
            
            # Регистрируем обработчики событий
            self._event_system.on("entity_created", self._on_entity_created)
            self._event_system.on("npc_talk", self._on_npc_talk)
            self._event_system.on("enemy_killed", self._on_enemy_killed)
            self._event_system.on("item_pickup", self._on_item_pickup)
            self._event_system.on("location_reached", self._on_location_reached)
            
            # Регистрируем обработчики целей
            self._register_objective_handlers()
            
            # Создаем таблицы БД
            if game_core:
                db_core = game_core.get_plugin("DatabaseCore")
                if db_core:
                    db_core.create_tables([Quest, QuestObjective])
            
            self.logger.info("QuestPlugin initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize QuestPlugin: {e}")
            return False
    
    def on_update(self, delta_time: float) -> None:
        """Обновление состояния квестов."""
        # Проверяем прогресс квестов (можно оптимизировать)
        for entity_id, quests in self._quests.items():
            for quest_id, quest_data in quests.items():
                if quest_data.get("state") == QuestState.ACTIVE.value:
                    self._check_quest_completion(entity_id, quest_id)
    
    def on_shutdown(self) -> None:
        """Очистка ресурсов."""
        if self._event_system:
            self._event_system.off("entity_created", self._on_entity_created)
            self._event_system.off("npc_talk", self._on_npc_talk)
            self._event_system.off("enemy_killed", self._on_enemy_killed)
            self._event_system.off("item_pickup", self._on_item_pickup)
            self._event_system.off("location_reached", self._on_location_reached)
        
        self._quests.clear()
        self._quest_templates.clear()
        self.logger.info("QuestPlugin shutdown complete")
    
    def _register_objective_handlers(self):
        """Регистрация обработчиков типов целей."""
        self._objective_handlers["kill"] = self._handle_kill_objective
        self._objective_handlers["collect"] = self._handle_collect_objective
        self._objective_handlers["talk"] = self._handle_talk_objective
        self._objective_handlers["reach_location"] = self._handle_location_objective
    
    def _on_entity_created(self, event_data: dict) -> None:
        """Инициализация пустого списка квестов для сущности."""
        entity_id = event_data.get("entity_id")
        if entity_id and entity_id not in self._quests:
            self._quests[entity_id] = {}
    
    def _on_npc_talk(self, event_data: dict) -> None:
        """Диалог с NPC - возможное начало квеста."""
        player_id = event_data.get("player_id")
        npc_id = event_data.get("npc_id")
        
        # Проверяем доступные квесты у NPC
        available_quests = [
            q for q in self._quest_templates.values() 
            if q.get("giver_id") == npc_id and q.get("state") == QuestState.NOT_STARTED.value
        ]
        
        for quest_template in available_quests:
            # Предлагаем квест (в реальной игре через UI/dialogue system)
            self._event_system.emit("quest_offered", {
                "player_id": player_id,
                "quest": quest_template
            })
    
    def _on_enemy_killed(self, event_data: dict) -> None:
        """Убийство врага - обновление целей квеста."""
        player_id = event_data.get("player_id")
        enemy_id = event_data.get("enemy_id")
        
        if player_id:
            self._handle_kill_objective(player_id, enemy_id)
    
    def _on_item_pickup(self, event_data: dict) -> None:
        """Подбор предмета - обновление целей сбора."""
        player_id = event_data.get("entity_id")
        item_data = event_data.get("item")
        
        if player_id and item_data:
            self._handle_collect_objective(player_id, item_data)
    
    def _on_location_reached(self, event_data: dict) -> None:
        """Достижение локации - обновление целей перемещения."""
        player_id = event_data.get("player_id")
        location_id = event_data.get("location_id")
        
        if player_id:
            self._handle_location_objective(player_id, location_id)
    
    def _handle_kill_objective(self, player_id: int, enemy_id: int) -> None:
        """Обработка цели убийства."""
        for quest_id, quest_data in self._quests.get(player_id, {}).items():
            if quest_data.get("state") != QuestState.ACTIVE.value:
                continue
            
            for obj in quest_data.get("objectives", []):
                if (obj.get("type") == "kill" and 
                    obj.get("target_id") == enemy_id and
                    not obj.get("is_completed", False)):
                    
                    obj["current_count"] = obj.get("current_count", 0) + 1
                    if obj["current_count"] >= obj.get("target_count", 1):
                        obj["is_completed"] = True
                    
                    self._emit_objective_updated(player_id, quest_id, obj)
    
    def _handle_collect_objective(self, player_id: int, item_data: dict) -> None:
        """Обработка цели сбора предметов."""
        item_id = item_data.get("id")
        
        for quest_id, quest_data in self._quests.get(player_id, {}).items():
            if quest_data.get("state") != QuestState.ACTIVE.value:
                continue
            
            for obj in quest_data.get("objectives", []):
                if (obj.get("type") == "collect" and 
                    obj.get("target_id") == item_id and
                    not obj.get("is_completed", False)):
                    
                    obj["current_count"] = obj.get("current_count", 0) + 1
                    if obj["current_count"] >= obj.get("target_count", 1):
                        obj["is_completed"] = True
                    
                    self._emit_objective_updated(player_id, quest_id, obj)
    
    def _handle_talk_objective(self, player_id: int, npc_id: int) -> None:
        """Обработка цели разговора."""
        for quest_id, quest_data in self._quests.get(player_id, {}).items():
            if quest_data.get("state") != QuestState.ACTIVE.value:
                continue
            
            for obj in quest_data.get("objectives", []):
                if (obj.get("type") == "talk" and 
                    obj.get("target_id") == npc_id and
                    not obj.get("is_completed", False)):
                    
                    obj["is_completed"] = True
                    self._emit_objective_updated(player_id, quest_id, obj)
    
    def _handle_location_objective(self, player_id: int, location_id: int) -> None:
        """Обработка цели достижения локации."""
        for quest_id, quest_data in self._quests.get(player_id, {}).items():
            if quest_data.get("state") != QuestState.ACTIVE.value:
                continue
            
            for obj in quest_data.get("objectives", []):
                if (obj.get("type") == "reach_location" and 
                    obj.get("target_id") == location_id and
                    not obj.get("is_completed", False)):
                    
                    obj["is_completed"] = True
                    self._emit_objective_updated(player_id, quest_id, obj)
    
    def _emit_objective_updated(self, player_id: int, quest_id: int, objective: dict) -> None:
        """Событие обновления цели."""
        self._event_system.emit("quest_objective_updated", {
            "player_id": player_id,
            "quest_id": quest_id,
            "objective": objective
        })
    
    def _check_quest_completion(self, entity_id: int, quest_id: int) -> None:
        """Проверка завершения квеста."""
        quest_data = self._quests.get(entity_id, {}).get(quest_id)
        if not quest_data:
            return
        
        objectives = quest_data.get("objectives", [])
        all_completed = all(obj.get("is_completed", False) for obj in objectives)
        
        if all_completed and quest_data.get("state") == QuestState.ACTIVE.value:
            quest_data["state"] = QuestState.COMPLETED.value
            self._complete_quest(entity_id, quest_id)
    
    def _complete_quest(self, entity_id: int, quest_id: int) -> None:
        """Завершение квеста и выдача наград."""
        quest_data = self._quests[entity_id][quest_id]
        
        # Выдача наград
        rewards = quest_data.get("rewards", {})
        
        if rewards.get("xp"):
            self._event_system.emit("gain_xp", {
                "entity_id": entity_id,
                "amount": rewards["xp"]
            })
        
        if rewards.get("gold"):
            self._event_system.emit("gain_gold", {
                "entity_id": entity_id,
                "amount": rewards["gold"]
            })
        
        if rewards.get("items"):
            for item in rewards["items"]:
                self._event_system.emit("item_pickup", {
                    "entity_id": entity_id,
                    "item": item
                })
        
        self._event_system.emit("quest_completed", {
            "entity_id": entity_id,
            "quest_id": quest_id,
            "rewards": rewards
        })
        
        # Сохраняем в БД
        self._sync_quest_to_db(entity_id, quest_id)
    
    def add_quest(self, entity_id: int, quest_template: dict) -> bool:
        """Добавить квест сущности."""
        quest_id = quest_template.get("id")
        
        if entity_id not in self._quests:
            self._quests[entity_id] = {}
        
        if quest_id in self._quests[entity_id]:
            return False  # Квест уже есть
        
        quest_data = quest_template.copy()
        quest_data["state"] = QuestState.ACTIVE.value
        quest_data["objectives"] = [obj.copy() for obj in quest_template.get("objectives", [])]
        
        self._quests[entity_id][quest_id] = quest_data
        
        # Сохраняем в БД
        self._save_quest_to_db(entity_id, quest_data)
        
        self._event_system.emit("quest_started", {
            "entity_id": entity_id,
            "quest": quest_data
        })
        
        return True
    
    def get_quest(self, entity_id: int, quest_id: int) -> Optional[dict]:
        """Получить данные квеста."""
        if entity_id in self._quests:
            return self._quests[entity_id].get(quest_id)
        return None
    
    def get_all_quests(self, entity_id: int) -> Dict[int, dict]:
        """Получить все квесты сущности."""
        return self._quests.get(entity_id, {})
    
    def get_active_quests(self, entity_id: int) -> List[dict]:
        """Получить активные квесты."""
        return [
            q for q in self._quests.get(entity_id, {}).values()
            if q.get("state") == QuestState.ACTIVE.value
        ]
    
    def abandon_quest(self, entity_id: int, quest_id: int) -> bool:
        """Отказаться от квеста."""
        if entity_id in self._quests and quest_id in self._quests[entity_id]:
            self._quests[entity_id][quest_id]["state"] = QuestState.ABANDONED.value
            self._sync_quest_to_db(entity_id, quest_id)
            
            self._event_system.emit("quest_abandoned", {
                "entity_id": entity_id,
                "quest_id": quest_id
            })
            return True
        return False
    
    def register_quest_template(self, quest_template: dict) -> None:
        """Зарегистрировать шаблон квеста."""
        self._quest_templates[quest_template.get("id")] = quest_template
    
    def _save_quest_to_db(self, entity_id: int, quest_data: dict) -> None:
        """Сохранить квест в БД."""
        try:
            db_core = self._event_system.get_context("db_core")
            if not db_core:
                return
            
            with db_core.session_factory() as session:
                # Создаем квест
                quest = Quest(
                    id=quest_data.get("id"),
                    title=quest_data.get("title", "Unknown Quest"),
                    description=quest_data.get("description", ""),
                    giver_id=quest_data.get("giver_id"),
                    state=quest_data.get("state", QuestState.NOT_STARTED.value),
                    reward_xp=quest_data.get("rewards", {}).get("xp", 0),
                    reward_gold=quest_data.get("rewards", {}).get("gold", 0),
                    reward_items=quest_data.get("rewards", {}).get("items", [])
                )
                session.add(quest)
                
                # Создаем цели
                for obj_data in quest_data.get("objectives", []):
                    obj = QuestObjective(
                        quest_id=quest.id,
                        description=obj_data.get("description", ""),
                        objective_type=obj_data.get("type", "generic"),
                        target_count=obj_data.get("target_count", 1),
                        current_count=obj_data.get("current_count", 0),
                        is_completed=1 if obj_data.get("is_completed", False) else 0
                    )
                    session.add(obj)
                
                session.commit()
        except Exception as e:
            self.logger.error(f"Error saving quest to DB: {e}")
    
    def _sync_quest_to_db(self, entity_id: int, quest_id: int) -> None:
        """Синхронизировать состояние квеста с БД."""
        # Упрощенная реализация - в продакшене нужна более сложная логика
        pass
