"""
Dialogue Plugin - Modular dialogue system with branching and events.
Part of the AI-EVOLVE plugin architecture.
"""
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
import json
from pathlib import Path

from ai_evolve.core.plugin_base import GamePlugin
from ai_evolve.core.event_system import EventSystem


@dataclass
class DialogueNode:
    """Represents a single node in a dialogue tree."""
    id: str
    speaker: str
    text: str
    choices: List[Dict[str, Any]] = field(default_factory=list)
    # Format: {"text": "Choice", "next_id": "id", "condition": callable, "effects": []}
    on_enter: Optional[Callable] = None
    on_exit: Optional[Callable] = None


@dataclass
class DialogueData:
    """Container for a full dialogue script."""
    id: str
    title: str
    nodes: Dict[str, DialogueNode] = field(default_factory=dict)
    start_node_id: str = "start"


class DialoguePlugin(GamePlugin):
    """
    Plugin for handling NPC dialogues, branching conversations, and narrative events.
    Integrates with EventSystem for triggering game actions based on dialogue choices.
    """
    
    name = "DialoguePlugin"
    version = "1.0.0"
    dependencies = ["EventSystem", "DatabaseCore"]

    def __init__(self):
        super().__init__()
        self.dialogues: Dict[str, DialogueData] = {}
        self.active_dialogue: Optional[DialogueData] = None
        self.current_node: Optional[DialogueNode] = None
        self.history: List[str] = []  # History of visited node IDs
        
        # Events
        self.on_dialogue_started = EventSystem.get_event("dialogue_started")
        self.on_dialogue_ended = EventSystem.get_event("dialogue_ended")
        self.on_node_entered = EventSystem.get_event("dialogue_node_entered")
        self.on_choice_made = EventSystem.get_event("dialogue_choice_made")

    def initialize(self, config: Optional[Dict] = None) -> bool:
        """Initialize the plugin, load dialogues from DB or files."""
        try:
            if config and "load_path" in config:
                self.load_dialogues_from_path(Path(config["load_path"]))
            
            self.logger.info(f"{self.name} initialized with {len(self.dialogues)} dialogues.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize {self.name}: {e}")
            return False

    def shutdown(self) -> None:
        """Cleanup resources."""
        self.active_dialogue = None
        self.current_node = None
        self.history.clear()
        self.logger.info(f"{self.name} shut down.")

    def load_dialogue_from_data(self, data: Dict) -> None:
        """Load a single dialogue from dictionary data."""
        dialogue_id = data.get("id")
        if not dialogue_id:
            raise ValueError("Dialogue must have an 'id'")
        
        nodes = {}
        for node_data in data.get("nodes", []):
            node = DialogueNode(
                id=node_data["id"],
                speaker=node_data.get("speaker", "Unknown"),
                text=node_data.get("text", ""),
                choices=node_data.get("choices", [])
            )
            nodes[node.id] = node
        
        self.dialogues[dialogue_id] = DialogueData(
            id=dialogue_id,
            title=data.get("title", "Untitled"),
            nodes=nodes,
            start_node_id=data.get("start_node_id", "start")
        )

    def load_dialogues_from_path(self, path: Path) -> None:
        """Load all JSON dialogue files from a directory."""
        if not path.exists():
            self.logger.warning(f"Dialogue path {path} does not exist.")
            return

        for file in path.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.load_dialogue_from_data(data)
            except Exception as e:
                self.logger.error(f"Failed to load dialogue {file}: {e}")

    def start_dialogue(self, dialogue_id: str, context: Optional[Dict] = None) -> bool:
        """Start a new dialogue session."""
        if dialogue_id not in self.dialogues:
            self.logger.error(f"Dialogue {dialogue_id} not found.")
            return False
        
        self.active_dialogue = self.dialogues[dialogue_id]
        self.history = []
        
        # Determine start node (could be conditional based on context)
        start_id = self.active_dialogue.start_node_id
        if context and "start_node" in context:
            start_id = context["start_node"]
            
        return self._goto_node(start_id)

    def _goto_node(self, node_id: str) -> bool:
        """Navigate to a specific node."""
        if not self.active_dialogue:
            return False
            
        if node_id not in self.active_dialogue.nodes:
            self.logger.error(f"Node {node_id} not found in active dialogue.")
            self.end_dialogue()
            return False
        
        # Exit previous node
        if self.current_node and self.current_node.on_exit:
            try:
                self.current_node.on_exit()
            except Exception as e:
                self.logger.error(f"Error in node exit callback: {e}")

        self.current_node = self.active_dialogue.nodes[node_id]
        self.history.append(node_id)
        
        # Enter new node
        if self.current_node.on_enter:
            try:
                self.current_node.on_enter()
            except Exception as e:
                self.logger.error(f"Error in node enter callback: {e}")
        
        # Emit events
        self.on_node_entered.send(
            self, 
            dialogue_id=self.active_dialogue.id, 
            node_id=node_id, 
            text=self.current_node.text,
            speaker=self.current_node.speaker
        )
        
        return True

    def get_current_options(self, context: Optional[Dict] = None) -> List[Dict]:
        """Get available choices for the current node, filtering by conditions."""
        if not self.current_node:
            return []
        
        valid_choices = []
        for choice in self.current_node.choices:
            condition = choice.get("condition")
            # If condition is a string, we might resolve it from a registry (not implemented here)
            # If it's a callable, execute it
            if callable(condition):
                try:
                    if not condition(context):
                        continue
                except Exception:
                    continue
            
            valid_choices.append({
                "text": choice.get("text", "..."),
                "next_id": choice.get("next_id"),
                "data": choice.get("data")
            })
        
        return valid_choices

    def make_choice(self, index: int, context: Optional[Dict] = None) -> bool:
        """Select a choice from the current node."""
        options = self.get_current_options(context)
        if not options or index < 0 or index >= len(options):
            return False
        
        choice = options[index]
        next_id = choice.get("next_id")
        
        # Emit choice event
        self.on_choice_made.send(
            self,
            dialogue_id=self.active_dialogue.id if self.active_dialogue else None,
            node_id=self.current_node.id if self.current_node else None,
            choice_text=choice["text"],
            next_id=next_id
        )
        
        if next_id:
            return self._goto_node(next_id)
        else:
            self.end_dialogue()
            return True

    def end_dialogue(self) -> None:
        """End the current dialogue session."""
        if self.active_dialogue:
            self.on_dialogue_ended.send(
                self, 
                dialogue_id=self.active_dialogue.id,
                completed=len(self.history) > 0
            )
        
        self.active_dialogue = None
        self.current_node = None
        self.history = []

    def update(self, dt: float) -> None:
        """Update loop (mostly for animations/timers if needed)."""
        pass
