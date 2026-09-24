"""Dialogue Plugin - система диалогов и ветвлений."""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from ai_evolve.core.plugin_base import GamePlugin as PluginBase
from ai_evolve.core.event_system import EventSystem


class DialogueState(Enum):
    """Состояния диалога."""
    INACTIVE = "inactive"
    ACTIVE = "active"
    WAITING_CHOICE = "waiting_choice"
    COMPLETED = "completed"


@dataclass
class DialogueNode:
    """Узел диалога."""
    id: str
    text: str
    speaker: Optional[int] = None  # Changed from speaker_id to match usage
    choices: List[dict] = field(default_factory=list)  # [{text, next_node_id, condition}]
    on_enter: Optional[str] = None  # event to trigger
    on_exit: Optional[str] = None  # event to trigger


@dataclass
class Dialogue:
    """Диалог."""
    id: str
    title: str
    nodes: Dict[str, DialogueNode] = field(default_factory=dict)
    start_node_id: str = ""
    conditions: Dict[str, Callable] = field(default_factory=dict)  # condition_name -> func


class DialoguePlugin(PluginBase):
    """Плагин управления диалогами."""
    
    def __init__(self):
        super().__init__("DialoguePlugin")
        self._dialogues: Dict[str, Dialogue] = {}
        self._active_dialogues: Dict[int, dict] = {}  # entity_id -> dialogue_state
        self._event_system: Optional[EventSystem] = None
        self._condition_handlers: Dict[str, Callable] = {}
    
    @property
    def dependencies(self) -> List[str]:
        return ["DatabaseCore", "QuestPlugin"]
    
    def on_init(self, game_core: Any = None) -> bool:
        """Инициализация плагина."""
        try:
            self._event_system = EventSystem.get_instance()
            
            # Регистрируем обработчики событий
            self._event_system.on("entity_created", self._on_entity_created)
            self._event_system.on("npc_interact", self._on_npc_interact)
            self._event_system.on("dialogue_choice_selected", self._on_choice_selected)
            
            # Регистрируем стандартные условия
            self._register_default_conditions()
            
            self.logger.info("DialoguePlugin initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize DialoguePlugin: {e}")
            return False
    
    def on_update(self, delta_time: float) -> None:
        """Обновление состояния диалогов."""
        pass
    
    def on_shutdown(self) -> None:
        """Очистка ресурсов."""
        if self._event_system:
            self._event_system.off("entity_created", self._on_entity_created)
            self._event_system.off("npc_interact", self._on_npc_interact)
            self._event_system.off("dialogue_choice_selected", self._on_choice_selected)
        
        self._dialogues.clear()
        self._active_dialogues.clear()
        self.logger.info("DialoguePlugin shutdown complete")
    
    def _register_default_conditions(self):
        """Регистрация стандартных условий."""
        self._condition_handlers["has_quest"] = self._check_has_quest
        self._condition_handlers["quest_completed"] = self._check_quest_completed
        self._condition_handlers["has_item"] = self._check_has_item
        self._condition_handlers["stat_greater"] = self._check_stat_greater
    
    def _on_entity_created(self, event_data: dict) -> None:
        """Инициализация состояния для новой сущности."""
        entity_id = event_data.get("entity_id")
        if entity_id and entity_id not in self._active_dialogues:
            self._active_dialogues[entity_id] = {"state": DialogueState.INACTIVE}
    
    def _on_npc_interact(self, event_data: dict) -> None:
        """Взаимодействие с NPC - запуск диалога."""
        player_id = event_data.get("player_id")
        npc_id = event_data.get("npc_id")
        dialogue_id = event_data.get("dialogue_id")
        
        if player_id and dialogue_id:
            self.start_dialogue(player_id, dialogue_id, npc_id)
    
    def _on_choice_selected(self, event_data: dict) -> None:
        """Выбор варианта ответа в диалоге."""
        player_id = event_data.get("player_id")
        choice_index = event_data.get("choice_index")
        
        if player_id and choice_index is not None:
            self.select_choice(player_id, choice_index)
    
    def register_dialogue(self, dialogue_data: dict) -> None:
        """Зарегистрировать диалог."""
        dialogue_id = dialogue_data.get("id")
        
        nodes = {}
        for node_data in dialogue_data.get("nodes", []):
            node = DialogueNode(
                id=node_data["id"],
                text=node_data["text"],
                speaker_id=node_data.get("speaker_id"),
                choices=node_data.get("choices", []),
                on_enter=node_data.get("on_enter"),
                on_exit=node_data.get("on_exit")
            )
            nodes[node_data["id"]] = node
        
        dialogue = Dialogue(
            id=dialogue_id,
            title=dialogue_data.get("title", "Untitled"),
            nodes=nodes,
            start_node_id=dialogue_data.get("start_node_id", ""),
            conditions=dialogue_data.get("conditions", {})
        )
        
        self._dialogues[dialogue_id] = dialogue
        self.logger.debug(f"Registered dialogue: {dialogue_id}")
    
    @property
    def dialogues(self) -> Dict[str, Dialogue]:
        """Публичный доступ к диалогам (для тестов)."""
        return self._dialogues
    
    def start_dialogue(self, entity_id: int, dialogue_id: str, speaker_id: Optional[int] = None) -> bool:
        """Начать диалог."""
        if dialogue_id not in self._dialogues:
            self.logger.warning(f"Dialogue {dialogue_id} not found")
            return False
        
        dialogue = self._dialogues[dialogue_id]
        
        if not dialogue.start_node_id or dialogue.start_node_id not in dialogue.nodes:
            self.logger.warning(f"Invalid start node for dialogue {dialogue_id}")
            return False
        
        self._active_dialogues[entity_id] = {
            "state": DialogueState.ACTIVE,
            "dialogue_id": dialogue_id,
            "current_node_id": dialogue.start_node_id,
            "speaker_id": speaker_id,
            "history": []
        }
        
        # Триггерим событие начала диалога
        self._event_system.emit("dialogue_started", {
            "entity_id": entity_id,
            "dialogue_id": dialogue_id,
            "speaker_id": speaker_id
        })
        
        # Показываем первый узел
        self._show_current_node(entity_id)
        
        return True
    
    def _show_current_node(self, entity_id: int) -> None:
        """Показать текущий узел диалога."""
        dialogue_state = self._active_dialogues.get(entity_id)
        if not dialogue_state:
            return
        
        dialogue_id = dialogue_state.get("dialogue_id")
        current_node_id = dialogue_state.get("current_node_id")
        
        dialogue = self._dialogues.get(dialogue_id)
        if not dialogue or current_node_id not in dialogue.nodes:
            self.end_dialogue(entity_id)
            return
        
        node = dialogue.nodes[current_node_id]
        
        # Фильтруем выборы по условиям
        available_choices = []
        for choice in node.choices:
            condition = choice.get("condition")
            if condition is None or self._check_condition(entity_id, condition):
                available_choices.append(choice)
        
        dialogue_state["available_choices"] = available_choices
        dialogue_state["state"] = DialogueState.WAITING_CHOICE if available_choices else DialogueState.ACTIVE
        
        # Триггерим событие показа узла
        self._event_system.emit("dialogue_node_shown", {
            "entity_id": entity_id,
            "node_id": node.id,
            "text": node.text,
            "speaker_id": node.speaker,  # Changed from speaker_id to speaker
            "choices": available_choices
        })
        
        # Триггерим on_enter событие узла
        if node.on_enter:
            self._event_system.emit(node.on_enter, {"entity_id": entity_id})
    
    def select_choice(self, entity_id: int, choice_index: int) -> bool:
        """Выбрать вариант ответа."""
        return self._select_choice_internal(entity_id, choice_index)
    
    def make_choice(self, choice_index: int) -> bool:
        """Alias for select_choice for backward compatibility (tests)."""
        # Use the last active dialogue entity
        for entity_id, state in self._active_dialogues.items():
            if state.get("state") == DialogueState.WAITING_CHOICE:
                return self._select_choice_internal(entity_id, choice_index)
        return False
    
    def _select_choice_internal(self, entity_id: int, choice_index: int) -> bool:
        dialogue_state = self._active_dialogues.get(entity_id)
        if not dialogue_state:
            return False
        
        available_choices = dialogue_state.get("available_choices", [])
        if choice_index < 0 or choice_index >= len(available_choices):
            self.logger.warning(f"Invalid choice index {choice_index}")
            return False
        
        choice = available_choices[choice_index]
        dialogue = self._dialogues.get(dialogue_state["dialogue_id"])
        current_node = dialogue.nodes.get(dialogue_state["current_node_id"])
        
        # Триггерим on_exit текущего узла
        if current_node and current_node.on_exit:
            self._event_system.emit(current_node.on_exit, {"entity_id": entity_id})
        
        # Сохраняем в историю
        dialogue_state["history"].append({
            "node_id": current_node.id,
            "choice_index": choice_index,
            "choice_text": choice.get("text")
        })
        
        # Переходим к следующему узлу
        next_node_id = choice.get("next_node_id")
        
        if next_node_id is None:
            # Конец диалога
            self.end_dialogue(entity_id)
        elif next_node_id in dialogue.nodes:
            dialogue_state["current_node_id"] = next_node_id
            dialogue_state["state"] = DialogueState.ACTIVE
            self._show_current_node(entity_id)
        else:
            self.logger.warning(f"Next node {next_node_id} not found")
            self.end_dialogue(entity_id)
        
        return True
    
    def end_dialogue(self, entity_id: int) -> None:
        """Завершить диалог."""
        dialogue_state = self._active_dialogues.get(entity_id)
        if not dialogue_state:
            return
        
        dialogue_id = dialogue_state.get("dialogue_id")
        
        # Триггерим on_exit последнего узла если есть
        dialogue = self._dialogues.get(dialogue_id)
        if dialogue:
            current_node = dialogue.nodes.get(dialogue_state.get("current_node_id"))
            if current_node and current_node.on_exit:
                self._event_system.emit(current_node.on_exit, {"entity_id": entity_id})
        
        self._active_dialogues[entity_id] = {"state": DialogueState.INACTIVE}
        
        self._event_system.emit("dialogue_ended", {
            "entity_id": entity_id,
            "dialogue_id": dialogue_id
        })
        
        self.logger.debug(f"Ended dialogue for entity {entity_id}")
    
    def _check_condition(self, entity_id: int, condition: dict) -> bool:
        """Проверить условие."""
        condition_type = condition.get("type")
        
        if condition_type in self._condition_handlers:
            return self._condition_handlers[condition_type](entity_id, condition)
        
        self.logger.warning(f"Unknown condition type: {condition_type}")
        return False
    
    def _check_has_quest(self, entity_id: int, condition: dict) -> bool:
        """Проверка наличия квеста."""
        quest_plugin = self._event_system.get_context("quest_plugin")
        if not quest_plugin:
            return False
        
        quest_id = condition.get("quest_id")
        return quest_plugin.has_quest(entity_id, quest_id)
    
    def _check_quest_completed(self, entity_id: int, condition: dict) -> bool:
        """Проверка завершения квеста."""
        quest_plugin = self._event_system.get_context("quest_plugin")
        if not quest_plugin:
            return False
        
        quest_id = condition.get("quest_id")
        quest = quest_plugin.get_quest(entity_id, quest_id)
        return quest and quest.get("state") == "completed"
    
    def _check_has_item(self, entity_id: int, condition: dict) -> bool:
        """Проверка наличия предмета."""
        inventory_plugin = self._event_system.get_context("inventory_plugin")
        if not inventory_plugin:
            return False
        
        item_id = condition.get("item_id")
        quantity = condition.get("quantity", 1)
        return inventory_plugin.has_item(entity_id, item_id, quantity)
    
    def _check_stat_greater(self, entity_id: int, condition: dict) -> bool:
        """Проверка характеристики."""
        # Заглушка - в реальной игре обращаться к Character/Entity plugin
        stat_name = condition.get("stat")
        value = condition.get("value", 0)
        
        # Пример: проверяем через событие
        result = {"value": 0}
        self._event_system.emit("get_stat", {
            "entity_id": entity_id,
            "stat": stat_name,
            "result": result
        })
        
        return result.get("value", 0) > value
    
    def get_active_dialogue(self, entity_id: int) -> Optional[dict]:
        """Получить активный диалог."""
        return self._active_dialogues.get(entity_id)
    
    def is_in_dialogue(self, entity_id: int) -> bool:
        """Проверить, находится ли сущность в диалоге."""
        state = self._active_dialogues.get(entity_id, {}).get("state")
        return state in [DialogueState.ACTIVE, DialogueState.WAITING_CHOICE]
