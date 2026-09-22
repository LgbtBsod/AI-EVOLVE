"""
Core DevProbe Instrument - Ядро инструмента для агентов
Архитектура: Ядро -> Плагины -> Конкретные тесты/анализы
Поддерживает динамическое подключение модулей анализа
"""

import time
import json
import hashlib
from typing import Dict, List, Any, Optional, Callable, Type
from dataclasses import dataclass, field
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ProbeContext:
    """Контекст выполнения探针 (probe)"""
    session_id: str
    start_time: float = field(default_factory=time.time)
    entities: Dict[str, Any] = field(default_factory=dict)
    global_state: Dict[str, Any] = field(default_factory=dict)
    metrics_history: List[Dict] = field(default_factory=list)
    anomalies: List[Dict] = field(default_factory=list)
    logs: List[Dict] = field(default_factory=list)
    
    def add_log(self, level: str, message: str, category: str = "general", data: Optional[Dict] = None):
        self.logs.append({
            "timestamp": time.time(),
            "level": level,
            "message": message,
            "category": category,
            "data": data or {}
        })
    
    def add_metric(self, metric_name: str, value: Any, entity_id: Optional[str] = None):
        self.metrics_history.append({
            "timestamp": time.time(),
            "metric": metric_name,
            "value": value,
            "entity_id": entity_id
        })
    
    def add_anomaly(self, anomaly_type: str, severity: str, description: str, data: Optional[Dict] = None):
        self.anomalies.append({
            "timestamp": time.time(),
            "type": anomaly_type,
            "severity": severity,
            "description": description,
            "data": data or {}
        })
    
    def get_session_duration(self) -> float:
        return time.time() - self.start_time
    
    def to_compact_dict(self) -> Dict:
        """Сжатое представление контекста для экономии токенов"""
        return {
            "session_id": self.session_id,
            "duration_sec": round(self.get_session_duration(), 2),
            "entities_count": len(self.entities),
            "metrics_count": len(self.metrics_history),
            "anomalies_count": len(self.anomalies),
            "logs_count": len(self.logs),
            "anomaly_summary": {
                "critical": sum(1 for a in self.anomalies if a["severity"] == "CRITICAL"),
                "high": sum(1 for a in self.anomalies if a["severity"] == "HIGH"),
                "medium": sum(1 for a in self.anomalies if a["severity"] == "MEDIUM"),
                "low": sum(1 for a in self.anomalies if a["severity"] == "LOW")
            }
        }


class PluginBase:
    """Базовый класс для плагинов"""
    
    name: str = "base_plugin"
    version: str = "1.0.0"
    description: str = ""
    dependencies: List[str] = []
    
    def __init__(self, core: 'DevProbeCore'):
        self.core = core
        self.initialized = False
    
    def initialize(self, context: ProbeContext) -> bool:
        """Инициализация плагина"""
        logger.info(f"[{self.name}] Initializing...")
        self.initialized = True
        return True
    
    def execute(self, context: ProbeContext) -> Dict[str, Any]:
        """Выполнение плагина"""
        raise NotImplementedError
    
    def cleanup(self, context: ProbeContext):
        """Очистка ресурсов"""
        logger.info(f"[{self.name}] Cleanup completed")
        self.initialized = False
    
    def get_report(self, context: ProbeContext) -> Dict:
        """Генерация отчета плагина"""
        return {
            "plugin": self.name,
            "version": self.version,
            "status": "active" if self.initialized else "inactive"
        }


class DevProbeCore:
    """
    Ядро инструмента DevProbe
    Управление плагинами, контекстом и выполнением тестов
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
        self.context = ProbeContext(session_id=self.session_id)
        self.plugins: Dict[str, PluginBase] = {}
        self.plugin_registry: Dict[str, Type[PluginBase]] = {}
        self.execution_order: List[str] = []
        self.config: Dict[str, Any] = {
            "enable_caching": True,
            "max_metrics_history": 10000,
            "anomaly_detection_enabled": True,
            "compact_reports": True,
            "log_level": "INFO"
        }
        self.cache: Dict[str, Any] = {}
        self.cache_timestamps: Dict[str, float] = {}
        
        logger.info(f"[CORE] DevProbe Core initialized with session: {self.session_id}")
    
    def register_plugin(self, plugin_class: Type[PluginBase], auto_enable: bool = False):
        """Регистрация плагина в ядре"""
        plugin_name = plugin_class.name
        self.plugin_registry[plugin_name] = plugin_class
        logger.info(f"[CORE] Registered plugin: {plugin_name} v{plugin_class.version}")
        
        if auto_enable:
            self.enable_plugin(plugin_name)
    
    def enable_plugin(self, plugin_name: str, config: Optional[Dict] = None) -> bool:
        """Включение плагина"""
        if plugin_name not in self.plugin_registry:
            logger.error(f"[CORE] Plugin {plugin_name} not found in registry")
            return False
        
        if plugin_name in self.plugins:
            logger.warning(f"[CORE] Plugin {plugin_name} already enabled")
            return True
        
        plugin_class = self.plugin_registry[plugin_name]
        
        # Проверка зависимостей
        for dep in plugin_class.dependencies:
            if dep not in self.plugins:
                logger.error(f"[CORE] Dependency {dep} not satisfied for {plugin_name}")
                return False
        
        plugin_instance = plugin_class(self)
        
        if config:
            for key, value in config.items():
                setattr(plugin_instance, key, value)
        
        if plugin_instance.initialize(self.context):
            self.plugins[plugin_name] = plugin_instance
            self.execution_order.append(plugin_name)
            logger.info(f"[CORE] Enabled plugin: {plugin_name}")
            return True
        
        return False
    
    def disable_plugin(self, plugin_name: str):
        """Отключение плагина"""
        if plugin_name in self.plugins:
            self.plugins[plugin_name].cleanup(self.context)
            del self.plugins[plugin_name]
            self.execution_order.remove(plugin_name)
            logger.info(f"[CORE] Disabled plugin: {plugin_name}")
    
    def execute_all(self) -> Dict[str, Any]:
        """Выполнение всех активных плагинов по порядку"""
        results = {}
        logger.info(f"[CORE] Executing {len(self.plugins)} plugins...")
        
        for plugin_name in self.execution_order:
            plugin = self.plugins[plugin_name]
            try:
                start_time = time.time()
                result = plugin.execute(self.context)
                execution_time = time.time() - start_time
                
                results[plugin_name] = {
                    "success": True,
                    "execution_time_sec": round(execution_time, 3),
                    "result": result
                }
                
                self.context.add_log(
                    "INFO",
                    f"Plugin {plugin_name} executed successfully",
                    category="execution",
                    data={"execution_time": execution_time}
                )
                
            except Exception as e:
                logger.error(f"[CORE] Plugin {plugin_name} failed: {str(e)}")
                results[plugin_name] = {
                    "success": False,
                    "error": str(e),
                    "traceback": self._get_traceback()
                }
                
                self.context.add_anomaly(
                    "plugin_failure",
                    "CRITICAL",
                    f"Plugin {plugin_name} failed: {str(e)}",
                    data={"plugin": plugin_name, "error": str(e)}
                )
        
        return results
    
    def get_combined_report(self, compact: bool = True) -> Dict:
        """Получение комбинированного отчета от всех плагинов"""
        report = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "core_config": self.config if not compact else {},
            "context_summary": self.context.to_compact_dict(),
            "plugins": {}
        }
        
        for plugin_name, plugin in self.plugins.items():
            plugin_report = plugin.get_report(self.context)
            report["plugins"][plugin_name] = plugin_report
        
        if compact:
            report["anomalies"] = self.context.anomalies
            report["logs"] = [log for log in self.context.logs if log["level"] in ["ERROR", "CRITICAL"]]
        else:
            report["all_logs"] = self.context.logs
            report["all_metrics"] = self.context.metrics_history
        
        return report
    
    def cache_set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Установка значения в кэш с TTL"""
        if not self.config["enable_caching"]:
            return
        
        self.cache[key] = value
        self.cache_timestamps[key] = time.time() + ttl_seconds
        logger.debug(f"[CORE] Cache set: {key} (TTL: {ttl_seconds}s)")
    
    def cache_get(self, key: str, default: Any = None) -> Any:
        """Получение значения из кэша"""
        if key in self.cache:
            if time.time() < self.cache_timestamps.get(key, 0):
                logger.debug(f"[CORE] Cache hit: {key}")
                return self.cache[key]
            else:
                # Истекло время жизни
                del self.cache[key]
                del self.cache_timestamps[key]
                logger.debug(f"[CORE] Cache expired: {key}")
        
        logger.debug(f"[CORE] Cache miss: {key}")
        return default
    
    def _get_traceback(self) -> str:
        """Получение traceback последней ошибки"""
        import traceback
        return traceback.format_exc()
    
    def export_session(self, filepath: str):
        """Экспорт сессии в файл"""
        report = self.get_combined_report(compact=False)
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"[CORE] Session exported to {filepath}")
    
    def generate_bug_script(self, anomaly: Optional[Dict] = None) -> str:
        """Генерация скрипта воспроизведения бага"""
        if not anomaly and self.context.anomalies:
            anomaly = self.context.anomalies[0]
        
        if not anomaly:
            return "# No anomalies detected for bug script generation"
        
        script = f'''#!/usr/bin/env python3
"""
Auto-generated bug reproduction script
Session: {self.session_id}
Anomaly: {anomaly.get("type", "unknown")}
Severity: {anomaly.get("severity", "unknown")}
Description: {anomaly.get("description", "N/A")}
Generated: {datetime.now().isoformat()}
"""

def reproduce_bug():
    """Reproduce the detected anomaly"""
    print("Reproducing bug...")
    print(f"Anomaly Type: {anomaly.get('type')}")
    print(f"Severity: {anomaly.get('severity')}")
    print(f"Description: {anomaly.get('description')}")
    
    # TODO: Add specific reproduction steps based on anomaly data
    # Anomaly data: {json.dumps(anomaly.get("data", {}), indent=2)}
    
    # Example placeholder:
    # from game.engine import GameSession
    # session = GameSession()
    # session.load_state({json.dumps(anomaly.get("data", {}).get("state", {}))})
    # session.trigger_event("{anomaly.get('type')}")
    
    return True

if __name__ == "__main__":
    success = reproduce_bug()
    print(f"Reproduction {'successful' if success else 'failed'}")
'''
        return script


# Глобальный экземпляр ядра
_core_instance: Optional[DevProbeCore] = None


def get_core(session_id: Optional[str] = None) -> DevProbeCore:
    """Получение экземпляра ядра (singleton pattern)"""
    global _core_instance
    if _core_instance is None or (session_id and session_id != _core_instance.session_id):
        _core_instance = DevProbeCore(session_id=session_id)
    return _core_instance


def reset_core():
    """Сброс ядра для новой сессии"""
    global _core_instance
    if _core_instance:
        _core_instance.context = ProbeContext(session_id=_core_instance.session_id)
        _core_instance.plugins.clear()
        _core_instance.execution_order.clear()
        _core_instance.cache.clear()
        _core_instance.cache_timestamps.clear()
