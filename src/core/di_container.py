"""
DI Container using dependency-injector library.

Refactored for Python 3.14 Best Practices:
- Replaced custom DI container with dependency-injector (Don't Reinvent The Wheel)
- Added from __future__ import annotations
- Using typing.Self for method chaining
- Added @override decorator where applicable
- Type hints updated to Python 3.10+ style
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Callable, TypeVar

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

T = TypeVar('T')


class ServiceLifetime:
    """Service lifetime constants."""
    TRANSIENT = "transient"  # New instance each time
    SINGLETON = "singleton"  # One instance per container
    SCOPED = "scoped"        # One instance per scope


class DIContainer:
    """
    Dependency Injection Container wrapper around dependency-injector.
    
    This provides a simple API while leveraging the powerful 
    dependency-injector library for complex dependency resolution.
    
    Example:
        >>> container = DIContainer()
        >>> container.register(ServiceA, ServiceAImpl, ServiceLifetime.SINGLETON)
        >>> service = container.resolve(ServiceA)
    """
    
    def __init__(self):
        self._container = containers.DynamicContainer()
        self._singletons: dict[type, Any] = {}
        self._lock = threading.RLock()
        self._scopes: list[dict[type, Any]] = []
        self._registrations: dict[type, dict[str, Any]] = {}

    def register(
        self, 
        service_type: type[T], 
        implementation: type | Callable[..., T] | None = None, 
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
        instance: Any | None = None
    ) -> Self:
        """
        Registers a service.
        
        Args:
            service_type: Service type (interface or base class).
            implementation: Implementation class or factory.
            lifetime: Service lifetime.
            instance: Ready-made instance (for singleton).
        
        Returns:
            Self for method chaining.
        """
        with self._lock:
            if instance is not None:
                # Register as instance provider
                self._registrations[service_type] = {
                    "type": "instance",
                    "instance": instance,
                    "lifetime": ServiceLifetime.SINGLETON
                }
                self._singletons[service_type] = instance
            else:
                impl = implementation or service_type
                self._registrations[service_type] = {
                    "type": "factory",
                    "factory": impl,
                    "lifetime": lifetime
                }
                
                # Add to dynamic container
                if lifetime == ServiceLifetime.SINGLETON:
                    provider = providers.Singleton(impl)
                elif lifetime == ServiceLifetime.SCOPED:
                    provider = providers.ThreadLocalSingleton(impl)
                else:
                    provider = providers.Factory(impl)
                
                setattr(self._container, service_type.__name__, provider)
                
        return self

    @inject
    def resolve(self, service_type: type[T]) -> T:
        """
        Resolves a dependency.
        Automatically resolves constructor dependencies recursively.
        
        Args:
            service_type: Type of service to resolve.
        
        Returns:
            Resolved instance.
        
        Raises:
            DependencyInjectionError: If service is not registered.
        """
        with self._lock:
            # Check registrations first
            if service_type in self._registrations:
                config = self._registrations[service_type]
                
                # Check scoped lifetime
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
                
                # Transient or new Scoped
                if config["type"] == "instance":
                    return config["instance"]
                
                instance = self._create_instance(config["factory"])
                
                if self._scopes and config["lifetime"] == ServiceLifetime.SCOPED:
                    self._scopes[-1][service_type] = instance
                
                return instance
            
            # Try dependency-injector's automatic resolution
            try:
                provider = getattr(self._container, service_type.__name__, None)
                if provider:
                    return provider()
            except Exception as e:
                logger.warning(f"Dependency-injector failed to resolve {service_type.__name__}: {e}")
            
            # Fallback: try to instantiate directly
            try:
                return self._create_instance(service_type)
            except Exception as e:
                raise DependencyInjectionError(
                    f"Service {service_type.__name__} not registered and cannot be auto-resolved: {e}"
                )

    def _create_instance(self, factory: type | Callable) -> Any:
        """Creates an instance, automatically injecting dependencies."""
        import inspect
        from typing import get_type_hints
        
        if not inspect.isclass(factory):
            # If it's a factory function that takes container
            try:
                sig = inspect.signature(factory)
                if len(sig.parameters) > 0:
                    return factory(self)
                return factory()
            except Exception:
                return factory(self)
        
        sig = inspect.signature(factory.__init__)
        params = []
        
        # Get typed annotations
        try:
            type_hints = get_type_hints(factory.__init__)
        except (NameError, AttributeError):
            # Fallback to raw annotations
            type_hints = {}
            raw_annotations = getattr(factory.__init__, '__annotations__', {})
            for name, ann in raw_annotations.items():
                if isinstance(ann, str):
                    try:
                        type_hints[name] = eval(ann)
                    except Exception:
                        type_hints[name] = ann
                else:
                    type_hints[name] = ann
        
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
            
            # Get type from type_hints or parameter annotation
            param_type = type_hints.get(name, param.annotation)
            
            # Handle string annotations
            if isinstance(param_type, str):
                if param.default != inspect.Parameter.empty:
                    params.append(param.default)
                    continue
                # Try to resolve string as type
                try:
                    param_type = eval(param_type)
                except Exception:
                    param_type = inspect.Parameter.empty
            
            if param_type == inspect.Parameter.empty:
                # If no type specified, use default or raise error
                if param.default != inspect.Parameter.empty:
                    params.append(param.default)
                    continue
                raise DependencyInjectionError(
                    f"No type specified for parameter {name} in {factory.__name__}"
                )
            
            # Recursive resolution
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
        """Creates a new scope for Scoped services."""
        scope: dict[type, Any] = {}
        with self._lock:
            self._scopes.append(scope)
        try:
            yield self
        finally:
            with self._lock:
                self._scopes.pop()

    def build_provider(self) -> Callable[[type], Any]:
        """Returns a provider function for convenient usage."""
        return self.resolve

    def wire(self, *args: Any, **kwargs: Any) -> None:
        """Wires up injections in modules/packages."""
        from dependency_injector.wiring import wire
        wire(container=self._container, *args, **kwargs)


# Backward compatibility alias
DependencyInjectionError = Exception


# Global container instance (Service Locator pattern)
global_container = DIContainer()


def get_container() -> DIContainer:
    """Gets the global container instance."""
    return global_container


def register_systems(container: DIContainer) -> DIContainer:
    """Registers core project systems."""
    from src.core.architecture import ComponentRegistry
    from src.core.event_system import EventSystem
    from src.core.state_manager import StateManager
    
    container.register(StateManager, lifetime=ServiceLifetime.SINGLETON)
    container.register(ComponentRegistry, lifetime=ServiceLifetime.SINGLETON)
    container.register(EventSystem, lifetime=ServiceLifetime.SINGLETON)
    
    return container
