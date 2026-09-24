#!/usr/bin/env python3
"""
Plugin for AI-EVOLVE Dev Probe: Network Remote Control
Purpose: Allow remote control of the game via WebSocket/HTTP API.

This plugin enables external tools, CI/CD pipelines, or distributed AI agents
to control and monitor the game session over the network.
"""

import json
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, TYPE_CHECKING
from pathlib import Path
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import socketserver

if TYPE_CHECKING:
    from .agent_command_plugin import CommandType


@dataclass
class RemoteSession:
    """Represents a remote control session."""
    session_id: str
    client_ip: str
    connected_at: float
    last_activity: float
    commands_sent: int = 0
    permissions: List[str] = field(default_factory=list)


class RemoteControlHandler(BaseHTTPRequestHandler):
    """HTTP request handler for remote control API."""
    
    plugin_instance = None  # Set by server
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def _send_json_response(self, data: Dict[str, Any], status: int = 200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        
        if path == '/status':
            # Get plugin status
            if self.plugin_instance:
                status = self.plugin_instance.get_status()
                self._send_json_response(status)
            else:
                self._send_json_response({'error': 'Plugin not initialized'}, 500)
        
        elif path == '/game_state':
            # Query current game state
            if self.plugin_instance:
                state = self.plugin_instance.get_game_state()
                self._send_json_response(state)
            else:
                self._send_json_response({'error': 'Plugin not initialized'}, 500)
        
        elif path == '/history':
            # Get command history
            limit = int(query.get('limit', [100])[0])
            if self.plugin_instance:
                history = self.plugin_instance.get_command_history(limit)
                self._send_json_response({'history': history})
            else:
                self._send_json_response({'error': 'Plugin not initialized'}, 500)
        
        elif path == '/health':
            # Health check
            self._send_json_response({'status': 'healthy', 'timestamp': time.time()})
        
        else:
            self._send_json_response({'error': 'Not found'}, 404)
    
    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json_response({'error': 'Invalid JSON'}, 400)
            return
        
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == '/command':
            # Execute command
            if not self.plugin_instance:
                self._send_json_response({'error': 'Plugin not initialized'}, 500)
                return
            
            cmd_type = data.get('type')
            params = data.get('params', {})
            priority = data.get('priority', 0)
            
            if not cmd_type:
                self._send_json_response({'error': 'Command type required'}, 400)
                return
            
            result = self.plugin_instance.execute_remote_command(cmd_type, params, priority)
            self._send_json_response(result)
        
        elif path == '/batch':
            # Execute batch of commands
            if not self.plugin_instance:
                self._send_json_response({'error': 'Plugin not initialized'}, 500)
                return
            
            commands = data.get('commands', [])
            results = []
            for cmd in commands:
                result = self.plugin_instance.execute_remote_command(
                    cmd.get('type'),
                    cmd.get('params', {}),
                    cmd.get('priority', 0)
                )
                results.append(result)
            
            self._send_json_response({'results': results})
        
        elif path == '/session':
            # Create new session
            session_id = self.plugin_instance.create_session(
                client_ip=self.client_address[0],
                permissions=data.get('permissions', ['read'])
            )
            self._send_json_response({'session_id': session_id})
        
        else:
            self._send_json_response({'error': 'Not found'}, 404)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Thread-per-request HTTP server."""
    daemon_threads = True


class NetworkRemotePlugin:
    """
    Plugin for remote network control of the game.
    
    Features:
    - RESTful HTTP API for game control
    - Real-time state queries
    - Command batching
    - Session management
    - Thread-safe operation
    - Configurable port and permissions
    """
    
    def __init__(self, probe_instance, port: int = 8765, host: str = 'localhost'):
        self.probe = probe_instance
        self.port = port
        self.host = host
        self.server: Optional[ThreadedHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._game_ref = None
        self.sessions: Dict[str, RemoteSession] = {}
        self.command_history: deque = deque(maxlen=1000)
        self._lock = threading.Lock()
        self._session_counter = 0
        
        # Set up HTTP handler with reference to this instance
        RemoteControlHandler.plugin_instance = self
        
        self._register_hooks()
        print(f"🌐 NetworkRemotePlugin initialized (port {port})")
    
    def _register_hooks(self):
        """Register event hooks with the probe."""
        if hasattr(self.probe, 'register_hook'):
            self.probe.register_hook('session_start', self._on_session_start)
            self.probe.register_hook('session_end', self._on_session_end)
    
    def _on_session_start(self, data: Dict[str, Any]):
        """Initialize when session starts."""
        self._running = True
        self._game_ref = data.get('game')
        self._start_server()
        print(f"✅ NetworkRemotePlugin: Server started at http://{self.host}:{self.port}")
    
    def _on_session_end(self, data: Dict[str, Any]):
        """Cleanup when session ends."""
        self._running = False
        self._stop_server()
        print("✅ NetworkRemotePlugin: Server stopped")
    
    def _start_server(self):
        """Start HTTP server in background thread."""
        try:
            self.server = ThreadedHTTPServer((self.host, self.port), RemoteControlHandler)
            self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self._thread.start()
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
    
    def _stop_server(self):
        """Stop HTTP server."""
        if self.server:
            self.server.shutdown()
            self.server = None
    
    def create_session(self, client_ip: str, permissions: List[str] = None) -> str:
        """Create a new remote session."""
        with self._lock:
            self._session_counter += 1
            session_id = f"session_{int(time.time())}_{self._session_counter}"
            
            session = RemoteSession(
                session_id=session_id,
                client_ip=client_ip,
                connected_at=time.time(),
                last_activity=time.time(),
                permissions=permissions or ['read']
            )
            self.sessions[session_id] = session
            
            return session_id
    
    def execute_remote_command(self, cmd_type: str, params: Dict[str, Any], 
                               priority: int = 0) -> Dict[str, Any]:
        """Execute a command from remote client."""
        start_time = time.time()
        
        # Map string command types to enum
        from .agent_command_plugin import CommandType
        
        try:
            cmd_enum = CommandType(cmd_type)
        except ValueError:
            return {
                'success': False,
                'error': f'Unknown command type: {cmd_type}',
                'execution_time': 0
            }
        
        # Check if we have access to agent command plugin
        if not hasattr(self.probe, 'agent_command_plugin'):
            # Fallback: execute directly if possible
            return self._execute_direct(cmd_enum, params, start_time)
        
        # Use agent command plugin
        plugin = self.probe.agent_command_plugin
        cmd_id = plugin.send_command(cmd_enum, params, priority=priority)
        result = plugin.wait_for_result(cmd_id, timeout=10.0)
        
        if result:
            result_dict = result.to_dict()
            result_dict['execution_time'] = time.time() - start_time
            
            # Record in history
            with self._lock:
                self.command_history.append({
                    'timestamp': time.time(),
                    'type': cmd_type,
                    'params': params,
                    'result': result_dict
                })
            
            return result_dict
        
        return {
            'success': False,
            'error': 'Command execution failed',
            'execution_time': time.time() - start_time
        }
    
    def _execute_direct(self, cmd_type: Any, params: Dict[str, Any], 
                        start_time: float) -> Dict[str, Any]:
        """Execute command directly without agent plugin."""
        # Basic implementation for essential commands
        from .agent_command_plugin import CommandType
        
        if cmd_type == CommandType.QUERY_STATE:
            return {
                'success': True,
                'data': self.get_game_state(),
                'execution_time': time.time() - start_time
            }
        
        return {
            'success': False,
            'error': 'Direct execution not supported for this command',
            'execution_time': time.time() - start_time
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get plugin status."""
        return {
            'running': self._running,
            'host': self.host,
            'port': self.port,
            'active_sessions': len(self.sessions),
            'commands_executed': len(self.command_history),
            'server_status': 'online' if self.server else 'offline'
        }
    
    def get_game_state(self) -> Dict[str, Any]:
        """Get current game state."""
        if not self._game_ref:
            return {'error': 'Game not available'}
        
        state = {
            'timestamp': time.time(),
            'game_available': True
        }
        
        # Extract relevant state
        if hasattr(self._game_ref, 'scene'):
            scene = self._game_ref.scene
            if hasattr(scene, 'player'):
                player = scene.player
                state['player'] = {
                    'hp': getattr(player, 'health', 0),
                    'max_hp': getattr(player, 'max_health', 0),
                    'pos': [getattr(player, 'x', 0), getattr(player, 'y', 0)]
                }
            
            if hasattr(scene, 'enemies'):
                state['enemies'] = [
                    {
                        'type': getattr(e, 'enemy_type', 'unknown'),
                        'hp': getattr(e, 'health', 0),
                        'pos': [getattr(e, 'x', 0), getattr(e, 'y', 0)]
                    }
                    for e in scene.enemies
                ]
        
        return state
    
    def get_command_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent command history."""
        with self._lock:
            return list(self.command_history)[-limit:]


def register_plugin(probe_instance, port: int = 8765, host: str = 'localhost'):
    """Register the plugin with the probe."""
    plugin = NetworkRemotePlugin(probe_instance, port=port, host=host)
    print(f"✅ NetworkRemotePlugin registered successfully on {host}:{port}")
    return plugin


if __name__ == "__main__":
    print("NetworkRemotePlugin - Standalone Test")
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
    plugin = NetworkRemotePlugin(mock_probe, port=8766)
    
    # Test status
    status = plugin.get_status()
    print(f"\n📊 Plugin Status: {json.dumps(status, indent=2)}")
    
    print("\n✅ Plugin ready (start a session to activate server)")
