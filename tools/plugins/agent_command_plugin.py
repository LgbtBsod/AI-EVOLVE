#!/usr/bin/env python3
"""
Plugin for AI-EVOLVE Dev Probe: Agent Command Interface
Purpose: Allow AI agents to send commands to the game during runtime sessions.

This plugin creates a bidirectional communication channel between AI agents
and the running game, enabling real-time intervention and testing.
"""

import json
import time
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple
from pathlib import Path
from collections import deque
from enum import Enum
import threading
import queue


class CommandType(Enum):
    """Types of commands that can be sent to the game."""
    SPAWN_ENTITY = "spawn_entity"
    DESPAWN_ENTITY = "despawn_entity"
    MODIFY_STATS = "modify_stats"
    TRIGGER_EVENT = "trigger_event"
    CHANGE_STATE = "change_state"
    TELEPORT = "teleport"
    GIVE_ITEM = "give_item"
    REMOVE_ITEM = "remove_item"
    SET_WEATHER = "set_weather"
    SET_TIME = "set_time"
    PAUSE_GAME = "pause_game"
    RESUME_GAME = "resume_game"
    SPEED_UP = "speed_up"
    SLOW_DOWN = "slow_down"
    SAVE_STATE = "save_state"
    LOAD_STATE = "load_state"
    EXECUTE_CODE = "execute_code"  # For advanced debugging
    QUERY_STATE = "query_state"


@dataclass
class Command:
    """A command to be executed in the game."""
    cmd_type: CommandType
    params: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    priority: int = 0  # Higher = more urgent
    callback: Optional[Callable[[Dict[str, Any]], None]] = None
    timeout: float = 30.0  # seconds
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.cmd_type.value,
            'params': self.params,
            'timestamp': self.timestamp,
            'priority': self.priority,
            'timeout': self.timeout
        }


@dataclass
class CommandResult:
    """Result of a command execution."""
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'message': self.message,
            'data': self.data,
            'execution_time': round(self.execution_time, 3),
            'error': self.error
        }


class AgentCommandPlugin:
    """
    Plugin for AI agent interaction with the game.
    
    Features:
    - Real-time command injection during gameplay
    - State queries for decision making
    - Event-driven callbacks
    - Command queue with priority handling
    - Timeout and error handling
    - Async support for non-blocking operations
    - Thread-safe command processing
    """
    
    def __init__(self, probe_instance):
        self.probe = probe_instance
        self.command_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.pending_commands: Dict[str, Command] = {}
        self.results: Dict[str, CommandResult] = {}
        self.command_history: deque = deque(maxlen=1000)
        self.state_cache: Dict[str, Any] = {}
        self.callbacks: Dict[str, List[Callable]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._game_ref = None
        self._command_id_counter = 0
        
        self._register_hooks()
        self._start_processor_thread()
        
        print("🎮 AgentCommandPlugin initialized")
    
    def _register_hooks(self):
        """Register event hooks with the probe."""
        if hasattr(self.probe, 'register_hook'):
            self.probe.register_hook('session_start', self._on_session_start)
            self.probe.register_hook('session_end', self._on_session_end)
            self.probe.register_hook('frame_update', self._on_frame_update)
    
    def _on_session_start(self, data: Dict[str, Any]):
        """Initialize when session starts."""
        self._running = True
        self._game_ref = data.get('game')
        print(f"✅ AgentCommandPlugin: Session started, game ref: {self._game_ref is not None}")
    
    def _on_session_end(self, data: Dict[str, Any]):
        """Cleanup when session ends."""
        self._running = False
        self._flush_results()
        print("✅ AgentCommandPlugin: Session ended")
    
    def _on_frame_update(self, data: Dict[str, Any]):
        """Update state cache on each frame."""
        with self._lock:
            self.state_cache.update({
                'timestamp': time.time(),
                'entities': data.get('entities', []),
                'player': data.get('player', {}),
                'enemies': data.get('enemies', []),
                'combat_active': data.get('combat_active', False)
            })
    
    def _start_processor_thread(self):
        """Start background thread for command processing."""
        self._thread = threading.Thread(target=self._process_commands_loop, daemon=True)
        self._thread.start()
    
    def _process_commands_loop(self):
        """Main loop for processing commands from queue."""
        while self._running or not self.command_queue.empty():
            try:
                # Get command with timeout to allow checking _running flag
                try:
                    priority, cmd_id, command = self.command_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                # Execute command
                result = self._execute_command(command)
                
                # Store result
                with self._lock:
                    self.results[cmd_id] = result
                    self.command_history.append({
                        'id': cmd_id,
                        'command': command.to_dict(),
                        'result': result.to_dict(),
                        'timestamp': time.time()
                    })
                
                # Call callback if present
                if command.callback:
                    try:
                        command.callback(result.to_dict())
                    except Exception as e:
                        print(f"⚠️ Callback error: {e}")
                
                self.command_queue.task_done()
                
            except Exception as e:
                print(f"❌ Command processor error: {e}")
                time.sleep(0.1)
    
    def _generate_command_id(self) -> str:
        """Generate unique command ID."""
        with self._lock:
            self._command_id_counter += 1
            return f"cmd_{int(time.time())}_{self._command_id_counter}"
    
    def send_command(self, cmd_type: CommandType, params: Dict[str, Any], 
                     priority: int = 0, timeout: float = 30.0,
                     callback: Optional[Callable] = None) -> str:
        """
        Send a command to the game.
        
        Args:
            cmd_type: Type of command to execute
            params: Command parameters
            priority: Execution priority (higher = sooner)
            timeout: Maximum time to wait for execution
            callback: Function to call with result
            
        Returns:
            Command ID for tracking
        """
        cmd_id = self._generate_command_id()
        command = Command(
            cmd_type=cmd_type,
            params=params,
            priority=priority,
            timeout=timeout,
            callback=callback
        )
        
        # Negative priority for max-heap behavior (higher priority = lower number)
        self.command_queue.put((-priority, cmd_id, command))
        self.pending_commands[cmd_id] = command
        
        return cmd_id
    
    def wait_for_result(self, cmd_id: str, timeout: float = 30.0) -> Optional[CommandResult]:
        """Wait for command result."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._lock:
                if cmd_id in self.results:
                    return self.results.pop(cmd_id)
                if cmd_id not in self.pending_commands:
                    # Command was removed (expired)
                    return CommandResult(
                        success=False,
                        message="Command expired or not found",
                        error="Command timeout"
                    )
            time.sleep(0.05)
        
        return CommandResult(
            success=False,
            message="Command timeout",
            error=f"No result after {timeout}s"
        )
    
    def _execute_command(self, command: Command) -> CommandResult:
        """Execute a single command."""
        start_time = time.time()
        
        try:
            if not self._game_ref:
                return CommandResult(
                    success=False,
                    message="Game reference not available",
                    error="No game instance"
                )
            
            handler = getattr(self, f'_handle_{command.cmd_type.value}', None)
            if not handler:
                return CommandResult(
                    success=False,
                    message=f"Unknown command type: {command.cmd_type.value}",
                    error="Unsupported command"
                )
            
            result_data = handler(command.params)
            execution_time = time.time() - start_time
            
            return CommandResult(
                success=True,
                message=f"Command {command.cmd_type.value} executed successfully",
                data=result_data,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return CommandResult(
                success=False,
                message=f"Command failed: {str(e)}",
                error=str(e),
                execution_time=execution_time
            )
    
    # Command Handlers
    def _handle_spawn_entity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Spawn an entity in the game."""
        entity_type = params.get('type', 'enemy')
        x = params.get('x', 0)
        y = params.get('y', 0)
        stats = params.get('stats', {})
        
        if hasattr(self._game_ref, 'scene'):
            if entity_type == 'enemy':
                # Use game's spawn mechanism
                if hasattr(self._game_ref.scene, 'spawn_enemy'):
                    entity = self._game_ref.scene.spawn_enemy(x=x, y=y, **stats)
                    return {'entity_id': getattr(entity, 'entity_id', 'unknown')}
            
            elif entity_type == 'item':
                if hasattr(self._game_ref.scene, 'spawn_item'):
                    item = self._game_ref.scene.spawn_item(x=x, y=y, **stats)
                    return {'item_id': getattr(item, 'item_id', 'unknown')}
        
        return {'status': 'spawned', 'type': entity_type, 'pos': [x, y]}
    
    def _handle_despawn_entity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Remove an entity from the game."""
        entity_id = params.get('entity_id')
        if entity_id and hasattr(self._game_ref, 'scene'):
            if hasattr(self._game_ref.scene, 'remove_entity'):
                self._game_ref.scene.remove_entity(entity_id)
                return {'despawned': entity_id}
        return {'status': 'not_found'}
    
    def _handle_modify_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Modify entity stats."""
        entity_id = params.get('entity_id')
        stats = params.get('stats', {})
        
        # Find entity and modify
        if hasattr(self._game_ref, 'scene'):
            for entity in getattr(self._game_ref.scene, 'enemies', []) + \
                         [getattr(self._game_ref.scene, 'player', None)]:
                if entity and getattr(entity, 'entity_id', None) == entity_id:
                    for stat, value in stats.items():
                        if hasattr(entity, stat):
                            setattr(entity, stat, value)
                    return {'modified': entity_id, 'stats': stats}
        
        return {'status': 'not_found'}
    
    def _handle_trigger_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger a game event."""
        event_type = params.get('event_type')
        event_data = params.get('data', {})
        
        if hasattr(self._game_ref, 'trigger_event'):
            self._game_ref.trigger_event(event_type, **event_data)
            return {'triggered': event_type}
        
        return {'status': 'event_system_not_found'}
    
    def _handle_change_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Change game state."""
        new_state = params.get('state')
        if hasattr(self._game_ref, 'set_state'):
            self._game_ref.set_state(new_state)
            return {'new_state': new_state}
        return {'status': 'state_system_not_found'}
    
    def _handle_teleport(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Teleport an entity."""
        entity_id = params.get('entity_id')
        x = params.get('x', 0)
        y = params.get('y', 0)
        
        if hasattr(self._game_ref, 'scene'):
            for entity in getattr(self._game_ref.scene, 'enemies', []) + \
                         [getattr(self._game_ref.scene, 'player', None)]:
                if entity and getattr(entity, 'entity_id', None) == entity_id:
                    if hasattr(entity, 'set_position'):
                        entity.set_position(x, y)
                        return {'teleported': entity_id, 'pos': [x, y]}
        
        return {'status': 'not_found'}
    
    def _handle_give_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Give item to player."""
        item_type = params.get('item_type')
        quantity = params.get('quantity', 1)
        
        if hasattr(self._game_ref, 'inventory'):
            if hasattr(self._game_ref.inventory, 'add_item'):
                self._game_ref.inventory.add_item(item_type, quantity)
                return {'item': item_type, 'quantity': quantity}
        
        return {'status': 'inventory_not_found'}
    
    def _handle_remove_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Remove item from player."""
        item_type = params.get('item_type')
        quantity = params.get('quantity', 1)
        
        if hasattr(self._game_ref, 'inventory'):
            if hasattr(self._game_ref.inventory, 'remove_item'):
                self._game_ref.inventory.remove_item(item_type, quantity)
                return {'removed': item_type, 'quantity': quantity}
        
        return {'status': 'inventory_not_found'}
    
    def _handle_set_weather(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set weather conditions."""
        weather_type = params.get('weather')
        if hasattr(self._game_ref, 'set_weather'):
            self._game_ref.set_weather(weather_type)
            return {'weather': weather_type}
        return {'status': 'weather_system_not_found'}
    
    def _handle_set_time(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set game time."""
        hour = params.get('hour', 12)
        if hasattr(self._game_ref, 'set_time'):
            self._game_ref.set_time(hour)
            return {'hour': hour}
        return {'status': 'time_system_not_found'}
    
    def _handle_pause_game(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Pause the game."""
        if hasattr(self._game_ref, 'pause'):
            self._game_ref.pause()
            return {'paused': True}
        return {'status': 'pause_not_supported'}
    
    def _handle_resume_game(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resume the game."""
        if hasattr(self._game_ref, 'resume'):
            self._game_ref.resume()
            return {'resumed': True}
        return {'status': 'resume_not_supported'}
    
    def _handle_speed_up(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Increase game speed."""
        factor = params.get('factor', 2.0)
        if hasattr(self._game_ref, 'set_time_scale'):
            self._game_ref.set_time_scale(factor)
            return {'speed_factor': factor}
        return {'status': 'time_scale_not_supported'}
    
    def _handle_slow_down(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Decrease game speed."""
        factor = params.get('factor', 0.5)
        if hasattr(self._game_ref, 'set_time_scale'):
            self._game_ref.set_time_scale(factor)
            return {'speed_factor': factor}
        return {'status': 'time_scale_not_supported'}
    
    def _handle_save_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Save current game state."""
        slot = params.get('slot', 'autosave')
        if hasattr(self._game_ref, 'save_game'):
            self._game_ref.save_game(slot)
            return {'saved_slot': slot}
        return {'status': 'save_not_supported'}
    
    def _handle_load_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Load saved game state."""
        slot = params.get('slot', 'autosave')
        if hasattr(self._game_ref, 'load_game'):
            self._game_ref.load_game(slot)
            return {'loaded_slot': slot}
        return {'status': 'load_not_supported'}
    
    def _handle_execute_code(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute arbitrary Python code (for advanced debugging)."""
        code = params.get('code', '')
        if not code:
            return {'error': 'No code provided'}
        
        try:
            # Create safe execution context
            context = {
                'game': self._game_ref,
                'scene': getattr(self._game_ref, 'scene', None),
                'player': getattr(getattr(self._game_ref, 'scene', None), 'player', None),
                'enemies': getattr(getattr(self._game_ref, 'scene', None), 'enemies', []),
                'combat_system': getattr(self._game_ref, 'combat_system', None)
            }
            
            exec(code, {"__builtins__": {}}, context)
            return {'executed': True, 'context_keys': list(context.keys())}
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_query_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Query current game state."""
        query_type = params.get('query', 'full')
        
        with self._lock:
            if query_type == 'full':
                return dict(self.state_cache)
            elif query_type == 'player':
                return {'player': self.state_cache.get('player', {})}
            elif query_type == 'enemies':
                return {'enemies': self.state_cache.get('enemies', [])}
            elif query_type == 'entities':
                return {'entities': self.state_cache.get('entities', [])}
            elif query_type == 'combat':
                return {'combat_active': self.state_cache.get('combat_active', False)}
        
        return {'error': f'Unknown query type: {query_type}'}
    
    def _flush_results(self):
        """Save all results before shutdown."""
        report_path = Path('tools/agent_command_reports')
        report_path.mkdir(exist_ok=True)
        
        report = {
            'timestamp': time.time(),
            'total_commands': len(self.command_history),
            'history': [dict(h) for h in self.command_history]
        }
        
        report_file = report_path / f'agent_commands_{int(time.time())}.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📊 Agent command report saved: {report_file}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get plugin status."""
        return {
            'running': self._running,
            'pending_commands': len(self.pending_commands),
            'queue_size': self.command_queue.qsize(),
            'history_size': len(self.command_history),
            'game_connected': self._game_ref is not None
        }


def register_plugin(probe_instance):
    """Register the plugin with the probe."""
    plugin = AgentCommandPlugin(probe_instance)
    print("✅ AgentCommandPlugin registered successfully")
    return plugin


if __name__ == "__main__":
    print("AgentCommandPlugin - Standalone Test")
    print("=" * 50)
    
    # Mock probe for testing
    class MockProbe:
        def __init__(self):
            self.hooks = {}
        
        def register_hook(self, event: str, callback: Callable):
            if event not in self.hooks:
                self.hooks[event] = []
            self.hooks[event].append(callback)
            print(f"  Registered hook: {event}")
    
    mock_probe = MockProbe()
    plugin = AgentCommandPlugin(mock_probe)
    
    # Test command sending
    print("\n📤 Testing command sending...")
    cmd_id = plugin.send_command(
        CommandType.SPAWN_ENTITY,
        {'type': 'enemy', 'x': 10, 'y': 20},
        priority=5
    )
    print(f"  Sent command: {cmd_id}")
    
    # Test status
    status = plugin.get_status()
    print(f"\n📊 Plugin Status: {json.dumps(status, indent=2)}")
    
    print("\n✅ All tests passed!")
