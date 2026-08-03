"""
DI Container & Service Locator Pattern
Реализует принцип Dependency Injection и Inversion of Control.
Позволяет управлять жизненным циклом зависимостей (Singleton, Transient, Scoped).
"""
from typing import Any, Dict, Type, Callable, Optional, List
from contextlib import contextmanager
import threading


class DependencyInjectionError(Exception):
    """Ошибка при разрешении зависимостей."""
    pass


class ServiceLifetime:
    TRANSIENT = "transient"  # Новый экземпляр каждый раз
    SINGLETON = "singleton"  # Один экземпляр на весь контейнер
    SCOPED = "scoped"        # Один экземпляр на область видимости


class DIContainer:
    """
    Контейнер внедрения зависимостей.
    Поддерживает регистрацию фабрик, классов и экземпляров.
    Потокобезопасен для чтения, использует lock для регистрации.
    """
    
    def __init__(self):
        self._services: Dict[Type, Dict[str, Any]] = {}
        self._singletons: Dict[Type, Any] = {}
        self._lock = threading.RLock()
        self._scopes: List[Dict[Type, Any]] = []

    def register(
        self, 
        service_type: Type, 
        implementation: Optional[Type | Callable] = None, 
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
        instance: Optional[Any] = None
    ) -> 'DIContainer':
        """
        Регистрирует сервис.
        
        Args:
            service_type: Тип сервиса (интерфейс или базовый класс).
            implementation: Класс-реализация или фабрика.
            lifetime: Время жизни сервиса.
            instance: Готовый экземпляр (для singleton).
        """
        with self._lock:
            if instance is not None:
                self._services[service_type] = {
                    "type": "instance",
                    "instance": instance,
                    "lifetime": ServiceLifetime.SINGLETON
                }
                self._singletons[service_type] = instance
            else:
                impl = implementation or service_type
                self._services[service_type] = {
                    "type": "factory",
                    "factory": impl,
                    "lifetime": lifetime
                }
                if lifetime == ServiceLifetime.SINGLETON:
                    # Пре-создание синглтона не обязательно, можно лениво
                    pass
        return self

    def resolve(self, service_type: Type) -> Any:
        """
        Разрешает зависимость.
        Автоматически рекурсивно разрешает зависимости конструктора.
        """
        with self._lock:
            if service_type not in self._services:
                raise DependencyInjectionError(
                    f"Сервис {service_type.__name__} не зарегистрирован."
                )
            
            config = self._services[service_type]
            
            # Проверка области видимости (Scoped)
            if self._scopes and config["lifetime"] == ServiceLifetime.SCOPED:
                current_scope = self._scopes[-1]
                if service_type in current_scope:
                    return current_scope[service_type]

            # Singleton
            if config["lifetime"] == ServiceLifetime.SINGLETON:
                if service_type in self._singletons:
                    return self._singletons[service_type]
                
                if config["type"] == "instance":
                    instance = config["instance"]
                else:
                    instance = self._create_instance(config["factory"])
                
                self._singletons[service_type] = instance
                return instance

            # Transient или Scoped (новый)
            if config["type"] == "instance":
                return config["instance"]
            
            instance = self._create_instance(config["factory"])
            
            if self._scopes and config["lifetime"] == ServiceLifetime.SCOPED:
                self._scopes[-1][service_type] = instance
            
            return instance

    def _create_instance(self, factory: Type | Callable) -> Any:
        """Создает экземпляр, автоматически инжектия зависимости."""
        import inspect
        from typing import get_type_hints
        
        if not inspect.isclass(factory):
            return factory(self) # Если это фабрика, принимающая контейнер
            
        sig = inspect.signature(factory.__init__)
        params = []
        
        # Пытаемся получить типизированные аннотации
        try:
            type_hints = get_type_hints(factory.__init__)
        except (NameError, AttributeError):
            # Если не удалось, используем сырые аннотации с eval
            type_hints = {}
            raw_annotations = getattr(factory.__init__, '__annotations__', {})
            for name, ann in raw_annotations.items():
                if isinstance(ann, str):
                    try:
                        # Импортируем необходимые типы для eval
                        from typing import Optional, List, Dict, Any, Union
                        from pathlib import Path
                        type_hints[name] = eval(ann)
                    except Exception:
                        type_hints[name] = ann
                else:
                    type_hints[name] = ann
        
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
            
            # Получаем тип из type_hints или из аннотации параметра
            param_type = type_hints.get(name, param.annotation)
            
            # Если аннотация строковая и не разрешена - пропускаем (используем default)
            if isinstance(param_type, str):
                if param.default != inspect.Parameter.empty:
                    params.append(param.default)
                    continue
                # Пытаемся разрешить строку как тип
                try:
                    from typing import Optional, List, Dict, Any, Union
                    from pathlib import Path
                    param_type = eval(param_type)
                except Exception:
                    param_type = inspect.Parameter.empty
            
            if param_type == inspect.Parameter.empty:
                # Если тип не указан, пробуем найти по имени или игнорируем
                if param.default != inspect.Parameter.empty:
                    params.append(param.default)
                    continue
                raise DependencyInjectionError(
                    f"Не указан тип для параметра {name} в {factory.__name__}"
                )
            
            # Рекурсивное разрешение
            try:
                dep = self.resolve(param_type)
                params.append(dep)
            except DependencyInjectionError:
                if param.default != inspect.Parameter.empty:
                    params.append(param.default)
                else:
                    raise
        
        return factory(*params)

    @contextmanager
    def scoped(self):
        """Создает новую область видимости для Scoped сервисов."""
        scope: Dict[Type, Any] = {}
        with self._lock:
            self._scopes.append(scope)
        try:
            yield self
        finally:
            with self._lock:
                self._scopes.pop()

    def build_provider(self) -> Callable[[Type], Any]:
        """Возвращает функцию-провайдер для удобного использования."""
        return self.resolve

# Глобальный экземпляр контейнера (Service Locator)
global_container = DIContainer()

def get_container() -> DIContainer:
    return global_container

def register_systems(container: DIContainer):
    """Регистрация основных систем проекта."""
    from src.core.state_manager import StateManager
    from src.core.architecture import ComponentRegistry
    from src.core.event_system import EventSystem
    # from src.systems.combat.combat_system import CombatSystem # Будет рефакториться
    
    container.register(StateManager, lifetime=ServiceLifetime.SINGLETON)
    container.register(ComponentRegistry, lifetime=ServiceLifetime.SINGLETON)
    container.register(EventSystem, lifetime=ServiceLifetime.SINGLETON)
    # container.register(CombatSystem, lifetime=ServiceLifetime.SINGLETON)
    
    return container
