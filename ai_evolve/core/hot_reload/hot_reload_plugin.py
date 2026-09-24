"""Hot Reload System - система горячей перезагрузки конфигов и плагинов."""

import os
import importlib
import hashlib
from typing import Dict, Optional, Any, List, Callable
from pathlib import Path
import json
import threading

from ai_evolve.core.plugin_base import GamePlugin as PluginBase
from ai_evolve.core.event_system import EventSystem


class HotReloadPlugin(PluginBase):
    """Плагин горячей перезагрузки конфигов и модулей."""
    
    def __init__(self):
        super().__init__("HotReloadPlugin")
        self._watched_paths: Dict[str, dict] = {}
        self._event_system: Optional[EventSystem] = None
        self._config_cache: Dict[str, Any] = {}
        self._module_cache: Dict[str, dict] = {}
        self._file_hashes: Dict[str, str] = {}
        self._check_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    @property
    def dependencies(self) -> List[str]:
        return ["DatabaseCore"]
    
    def on_init(self, game_core: Any) -> bool:
        """Инициализация плагина."""
        try:
            self._event_system = EventSystem.get_instance()
            
            # Регистрируем обработчики событий
            self._event_system.on("request_config_reload", self._on_config_reload_request)
            self._event_system.on("request_plugin_reload", self._on_plugin_reload_request)
            
            # Запускаем поток проверки изменений
            self._start_file_checker()
            
            # Кэшируем начальные хеши файлов
            self._cache_initial_hashes()
            
            self.logger.info("HotReloadPlugin initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize HotReloadPlugin: {e}")
            return False
    
    def on_update(self, delta_time: float) -> None:
        """Обновление (проверка необходимости reload)."""
        pass
    
    def on_shutdown(self) -> None:
        """Остановка checker и очистка."""
        self._stop_event.set()
        
        if self._check_thread:
            self._check_thread.join(timeout=2.0)
        
        if self._event_system:
            self._event_system.off("request_config_reload", self._on_config_reload_request)
            self._event_system.off("request_plugin_reload", self._on_plugin_reload_request)
        
        self._watched_paths.clear()
        self._config_cache.clear()
        self.logger.info("HotReloadPlugin shutdown complete")
    
    def _cache_initial_hashes(self):
        """Кэшировать начальные хеши файлов."""
        base_path = Path(__file__).parent.parent
        config_path = base_path / "config"
        features_path = base_path / "features"
        
        for path in [config_path, features_path]:
            if path.exists():
                for file_path in path.rglob("*"):
                    if file_path.is_file() and (file_path.suffix in ['.json', '.py']):
                        self._file_hashes[str(file_path)] = self._get_file_hash(str(file_path))
    
    def _get_file_hash(self, filepath: str) -> str:
        """Получить хеш файла."""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def _start_file_checker(self):
        """Запустить поток проверки изменений файлов."""
        def check_files():
            while not self._stop_event.is_set():
                self._check_changed_files()
                self._stop_event.wait(1.0)  # Проверка каждую секунду
        
        self._check_thread = threading.Thread(target=check_files, daemon=True)
        self._check_thread.start()
        self.logger.debug("File checker thread started")
    
    def _check_changed_files(self):
        """Проверить измененные файлы."""
        base_path = Path(__file__).parent.parent
        config_path = base_path / "config"
        features_path = base_path / "features"
        
        for path in [config_path, features_path]:
            if not path.exists():
                continue
                
            for file_path in path.rglob("*"):
                if not file_path.is_file():
                    continue
                
                if file_path.suffix not in ['.json', '.py']:
                    continue
                
                # Пропускаем временные файлы
                filename = file_path.name
                if filename.endswith('~') or filename.endswith('.swp') or filename.startswith('.'):
                    continue
                
                filepath_str = str(file_path)
                new_hash = self._get_file_hash(filepath_str)
                old_hash = self._file_hashes.get(filepath_str)
                
                if new_hash and new_hash != old_hash:
                    self._file_hashes[filepath_str] = new_hash
                    
                    if file_path.suffix == '.json':
                        self._reload_config(filepath_str)
                    elif file_path.suffix == '.py':
                        self._reload_module(filepath_str)
    
    def _reload_config(self, filepath: str) -> bool:
        """Перезагрузить конфиг файл."""
        try:
            if filepath.endswith('.json'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                self._config_cache[filepath] = config_data
                
                # Определяем тип конфига по пути
                config_type = self._detect_config_type(filepath)
                
                self._event_system.emit("config_reloaded", {
                    "filepath": filepath,
                    "config_type": config_type,
                    "data": config_data
                })
                
                self.logger.info(f"Config reloaded: {filepath}")
                return True
            
        except Exception as e:
            self.logger.error(f"Failed to reload config {filepath}: {e}")
            return False
        
        return False
    
    def _reload_module(self, filepath: str) -> bool:
        """Перезагрузить Python модуль."""
        try:
            # Преобразуем путь в имя модуля
            base_path = Path(__file__).parent.parent
            rel_path = Path(filepath).relative_to(base_path.parent)
            module_name = str(rel_path.with_suffix('')).replace(os.sep, '.')
            
            # Импортируем модуль заново
            if module_name in globals() or module_name in locals():
                module = importlib.import_module(module_name)
                importlib.reload(module)
            else:
                try:
                    module = importlib.import_module(module_name)
                    importlib.reload(module)
                except ImportError:
                    self.logger.warning(f"Cannot import module {module_name}")
                    return False
            
            self._module_cache[module_name] = {
                "path": filepath,
                "hash": self._get_file_hash(filepath),
                "module": module
            }
            
            self._event_system.emit("module_reloaded", {
                "filepath": filepath,
                "module_name": module_name
            })
            
            self.logger.info(f"Module reloaded: {module_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reload module {filepath}: {e}")
            return False
    
    def _detect_config_type(self, filepath: str) -> str:
        """Определить тип конфига по пути."""
        filename = os.path.basename(filepath).lower()
        
        if 'balance' in filename:
            return 'balance'
        elif 'enemy' in filename:
            return 'enemy_config'
        elif 'item' in filename:
            return 'item_config'
        elif 'quest' in filename:
            return 'quest_config'
        elif 'dialogue' in filename:
            return 'dialogue_config'
        else:
            return 'general'
    
    def _on_config_reload_request(self, event_data: dict) -> None:
        """Обработка запроса на перезагрузку конфига."""
        config_type = event_data.get("config_type")
        filepath = event_data.get("filepath")
        
        if filepath:
            self._reload_config(filepath)
        elif config_type:
            # Ищем конфиги этого типа
            base_path = Path(__file__).parent.parent / "config"
            for config_file in base_path.glob(f"*{config_type}*.json"):
                self._reload_config(str(config_file))
    
    def _on_plugin_reload_request(self, event_data: dict) -> None:
        """Обработка запроса на перезагрузку плагина."""
        plugin_name = event_data.get("plugin_name")
        
        if not plugin_name:
            return
        
        # Находим файл плагина
        base_path = Path(__file__).parent.parent / "features"
        plugin_dir = None
        
        for feature_dir in base_path.iterdir():
            if feature_dir.is_dir():
                plugin_file = feature_dir / f"{plugin_name.lower().replace('plugin', '')}_plugin.py"
                if plugin_file.exists():
                    plugin_dir = feature_dir
                    break
        
        if plugin_dir:
            # Перезагружаем модуль
            for py_file in plugin_dir.glob("*.py"):
                if not py_file.name.startswith('__'):
                    self._reload_module(str(py_file))
            
            # Эмитим событие для PluginManager
            self._event_system.emit("plugin_reload_requested", {
                "plugin_name": plugin_name
            })
    
    def get_config(self, filepath: str) -> Optional[Any]:
        """Получить закэшированный конфиг."""
        return self._config_cache.get(filepath)
    
    def load_config(self, filepath: str) -> Optional[Any]:
        """Загрузить конфиг и закэшировать."""
        try:
            if filepath.endswith('.json'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                self._config_cache[filepath] = config_data
                return config_data
        except Exception as e:
            self.logger.error(f"Failed to load config {filepath}: {e}")
        
        return None
    
    def watch_path(self, path: str, watch_type: str = "file") -> bool:
        """Добавить путь для наблюдения."""
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                self.logger.warning(f"Path does not exist: {path}")
                return False
            
            self._watched_paths[str(path_obj)] = {"type": watch_type}
            self._file_hashes[str(path_obj)] = self._get_file_hash(str(path_obj))
            
            self.logger.info(f"Added watch for {path} ({watch_type})")
            return True
        except Exception as e:
            self.logger.error(f"Failed to watch path {path}: {e}")
            return False
