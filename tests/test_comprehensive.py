"""
Comprehensive Test Suite for AI-EVOLVE
Полное покрытие тестами всех ключевых компонентов проекта.
Цель: 80%+ test coverage.
"""
import pytest
import time
import threading
from typing import Dict, Any

# Core imports
from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState, ComponentRegistry
from src.core.state_manager import StateManager, StateWrapper
from src.core.di_container import DIContainer, ServiceLifetime, get_container, register_systems
from src.core.circuit_breaker import CircuitBreaker, CircuitState, circuit_breaker, CircuitBreakerError
from src.core.cache import LRUCache, cached
from src.core.interfaces import (
    IHealthComponent, IDamageDealer, ICombatStats
)
from src.core.validation import ComponentConfig, CombatStats, EventData, ValidationError

# Combat system imports
from src.systems.combat.refactored_combat_system import RefactoredCombatSystem, CombatEntity
from src.systems.combat.components.health_component import HealthComponent
from src.systems.combat.components.damage_component import DamageComponent
from src.systems.combat.components.combat_stats_component import CombatStatsComponent


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def container():
    """Фикстура: чистый DI контейнер."""
    return DIContainer()


@pytest.fixture
def state_manager():
    """Фикстура: менеджер состояний."""
    return StateManager()


@pytest.fixture
def cache():
    """Фикстура: LRU кэш."""
    return LRUCache(max_size=5, default_ttl=10.0)


@pytest.fixture
def combat_system():
    """Фикстура: рефакторенная боевая система."""
    system = RefactoredCombatSystem()
    system.initialize()
    yield system
    system.destroy()


@pytest.fixture
def health_component():
    """Фикстура: компонент здоровья."""
    return HealthComponent(max_health=100.0)


@pytest.fixture
def damage_component():
    """Фикстура: компонент урона."""
    return DamageComponent(base_damage=10.0)


# ============================================================================
# TEST: ARCHITECTURE (BaseComponent, ComponentRegistry)
# ============================================================================

class TestArchitecture:
    """Тесты базовой архитектуры."""
    
    def test_base_component_lifecycle(self):
        """Тест полного жизненного цикла компонента."""
        class TestComponent(BaseComponent):
            def _on_update(self, delta_time: float) -> None:
                pass
        
        comp = TestComponent(
            component_id="test_comp",
            component_type=ComponentType.SYSTEM,
            priority=Priority.NORMAL
        )
        
        # Initial state - using state property instead of lifecycle_state
        assert comp.state == LifecycleState.UNINITIALIZED
        
        # Initialize
        assert comp.initialize() is True
        assert comp.state == LifecycleState.READY
        
        # Start
        assert comp.start() is True
        assert comp.state == LifecycleState.RUNNING
        
        # Pause
        assert comp.pause() is True
        assert comp.state == LifecycleState.PAUSED
        
        # Resume
        assert comp.resume() is True
        assert comp.state == LifecycleState.RUNNING
        
        # Stop
        assert comp.stop() is True
        assert comp.state == LifecycleState.STOPPED
        
        # Destroy
        assert comp.destroy() is True
        assert comp.state == LifecycleState.DESTROYED
    
    def test_component_registry(self):
        """Тест реестра компонентов."""
        registry = ComponentRegistry()
        
        class TestComp(BaseComponent):
            def _on_update(self, delta_time: float) -> None:
                pass
        
        comp1 = TestComp("comp1", ComponentType.SYSTEM, Priority.NORMAL)
        comp2 = TestComp("comp2", ComponentType.ENTITY, Priority.HIGH)
        
        registry.register(comp1)
        registry.register(comp2)
        
        # Get by ID
        assert registry.get("comp1") == comp1
        assert registry.get("comp2") == comp2
        
        # Get all
        all_comps = registry.get_all()
        assert len(all_comps) == 2
        
        # Filter by type (using get_by_type instead of filter_by_type)
        systems = registry.get_by_type(ComponentType.SYSTEM)
        assert len(systems) == 1
        assert systems[0] == comp1
        
        # Unregister
        registry.unregister("comp1")
        assert registry.get("comp1") is None


# ============================================================================
# TEST: STATE MANAGER (SSOT)
# ============================================================================

class TestStateManager:
    """Тесты менеджера состояний (Single Source of Truth)."""
    
    def test_set_get_state(self, state_manager: StateManager):
        """Тест установки и получения состояния."""
        state_manager.set_state("player.health", 100.0)
        assert state_manager.get_state("player.health") == 100.0
        
        state_manager.set_state("player.name", "Hero")
        assert state_manager.get_state("player.name") == "Hero"
    
    def test_state_history(self, state_manager: StateManager):
        """Тест истории состояний."""
        state_manager.set_state("counter", 0)
        state_manager.set_state("counter", 1)
        state_manager.set_state("counter", 2)
        
        history = state_manager.get_history("counter")
        assert len(history) >= 2  # Минимум 2 перехода
    
    def test_state_subscription(self, state_manager: StateManager):
        """Тест подписки на изменения состояний."""
        changes = []
        
        def on_change(old_val: Any, new_val: Any):
            changes.append(("test.key", old_val, new_val))
        
        # Сначала создаем состояние, затем подписываемся
        state_manager.set_state("test.key", "initial")
        state_manager.subscribe("test.key", on_change)
        state_manager.set_state("test.key", "value1")
        state_manager.set_state("test.key", "value2")
        
        assert len(changes) == 2
        assert changes[0] == ("test.key", "initial", "value1")
    
    def test_state_ttl(self, state_manager: StateManager):
        """Тест TTL состояний."""
        state_manager.set_state("temp.value", "expires", ttl=0.1)
        assert state_manager.get_state("temp.value") == "expires"
        
        time.sleep(0.15)
        # TTL истек
        assert state_manager.get_state("temp.value") is None


# ============================================================================
# TEST: DI CONTAINER
# ============================================================================

class TestDIContainer:
    """Тесты Dependency Injection контейнера."""
    
    def test_transient_lifetime(self, container: DIContainer):
        """Тест transient lifetime (новый экземпляр каждый раз)."""
        class TestService:
            def __init__(self, value: int = 42):
                self.value = value
        
        container.register(TestService, lifetime=ServiceLifetime.TRANSIENT)
        
        instance1 = container.resolve(TestService)
        instance2 = container.resolve(TestService)
        
        assert instance1 is not instance2
        assert instance1.value == 42
    
    def test_singleton_lifetime(self, container: DIContainer):
        """Тест singleton lifetime (один экземпляр)."""
        class TestService:
            def __init__(self, value: str = "singleton"):
                self.value = value
        
        container.register(TestService, lifetime=ServiceLifetime.SINGLETON)
        
        instance1 = container.resolve(TestService)
        instance2 = container.resolve(TestService)
        
        assert instance1 is instance2
        assert instance1.value == "singleton"
    
    def test_instance_registration(self, container: DIContainer):
        """Тест регистрации готового экземпляра."""
        service = {"name": "test_service"}
        container.register(dict, instance=service)
        
        resolved = container.resolve(dict)
        assert resolved is service
    
    def test_automatic_dependency_injection(self, container: DIContainer):
        """Тест автоматического внедрения зависимостей."""
        class Database:
            def __init__(self, connection_string: str = "default"):
                self.connection_string = connection_string
        
        class UserService:
            def __init__(self, db: Database):
                self.db = db
        
        container.register(Database, lifetime=ServiceLifetime.SINGLETON)
        container.register(UserService, lifetime=ServiceLifetime.TRANSIENT)
        
        user_service = container.resolve(UserService)
        assert isinstance(user_service.db, Database)
    
    def test_scoped_lifetime(self, container: DIContainer):
        """Тест scoped lifetime (экземпляр на область видимости)."""
        class ScopedService:
            def __init__(self, scope_id: int = 1):
                self.scope_id = scope_id
        
        container.register(ScopedService, lifetime=ServiceLifetime.SCOPED)
        
        with container.scoped() as scope:
            instance1 = scope.resolve(ScopedService)
            instance2 = scope.resolve(ScopedService)
            assert instance1 is instance2  # В одной области - один экземпляр
        
        # В новой области - новый экземпляр
        with container.scoped() as scope:
            instance3 = scope.resolve(ScopedService)
            assert instance3 is not instance1


# ============================================================================
# TEST: CIRCUIT BREAKER
# ============================================================================

class TestCircuitBreaker:
    """Тесты Circuit Breaker паттерна."""
    
    def test_closed_state_normal_operation(self):
        """Тест нормальной работы в CLOSED состоянии."""
        breaker = CircuitBreaker(failure_threshold=3)
        
        result = breaker.call(lambda: "success")
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
    
    def test_open_state_after_failures(self):
        """Тест перехода в OPEN состояние после сбоев."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        
        def failing_func():
            raise ValueError("Simulated failure")
        
        for _ in range(3):
            try:
                breaker.call(failing_func)
            except ValueError:
                pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Попытка вызова в OPEN состоянии
        with pytest.raises(CircuitBreakerError):
            breaker.call(lambda: "should not execute")
    
    def test_half_open_state_recovery(self):
        """Тест восстановления через HALF_OPEN состояние."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        
        def failing_func():
            raise ValueError("Failure")
        
        # Доводим до OPEN
        for _ in range(2):
            try:
                breaker.call(failing_func)
            except ValueError:
                pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Ждем восстановления
        time.sleep(0.15)
        
        # Автоматический переход в HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN
        
        # Успешный вызов восстанавливает цепь
        result = breaker.call(lambda: "recovered")
        assert result == "recovered"
        assert breaker.state == CircuitState.CLOSED
    
    def test_circuit_breaker_decorator(self):
        """Тест декоратора circuit_breaker."""
        @circuit_breaker(failure_threshold=2, recovery_timeout=60.0)
        def risky_operation():
            raise RuntimeError("Risky!")
        
        for _ in range(2):
            try:
                risky_operation()
            except RuntimeError:
                pass
        
        with pytest.raises(CircuitBreakerError):
            risky_operation()


# ============================================================================
# TEST: LRU CACHE
# ============================================================================

class TestLRUCache:
    """Тесты LRU кэша с TTL."""
    
    def test_basic_set_get(self, cache: LRUCache):
        """Тест базовой установки и получения."""
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_lru_eviction(self):
        """Тест вытеснения по LRU."""
        cache = LRUCache(max_size=3)
        
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        
        # Переполнение - самый старый ('a') должен быть вытеснен
        cache.set("d", 4)
        
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("d") == 4
    
    def test_ttl_expiration(self):
        """Тест истечения TTL."""
        cache = LRUCache(max_size=5, default_ttl=0.1)
        
        cache.set("temp", "value")
        assert cache.get("temp") == "value"
        
        time.sleep(0.15)
        assert cache.get("temp") is None
    
    def test_cache_stats(self, cache: LRUCache):
        """Тест статистики кэша."""
        cache.set("key1", "val1")
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss
        
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 50.0
    
    def test_cached_decorator(self):
        """Тест декоратора cached."""
        call_count = [0]
        
        @cached(max_size=10, ttl=10.0)
        def expensive_calculation(x: int) -> int:
            call_count[0] += 1
            return x * 2
        
        result1 = expensive_calculation(5)
        result2 = expensive_calculation(5)  # Из кэша
        result3 = expensive_calculation(10)  # Новый расчет
        
        assert result1 == 10
        assert result2 == 10
        assert result3 == 20
        assert call_count[0] == 2  # Только 2 реальных вызова


# ============================================================================
# TEST: VALIDATION (Pydantic)
# ============================================================================

class TestValidation:
    """Тесты валидации Pydantic."""
    
    def test_component_config_valid(self):
        """Тест валидного конфига компонента."""
        config = ComponentConfig(
            name="test_component",
            enabled=True,
            priority=5,
            tags=["core", "system"]
        )
        assert config.name == "test_component"
        assert config.priority == 5
    
    def test_component_config_invalid_name(self):
        """Тест невалидного имени компонента."""
        with pytest.raises(ValidationError):
            ComponentConfig(name="invalid name!", enabled=True)
    
    def test_combat_stats_valid(self):
        """Тест валидных боевых статов."""
        stats = CombatStats(
            health=80.0,
            max_health=100.0,
            damage=15.0,
            defense=5.0,
            speed=1.2
        )
        assert stats.health_percent == 80.0
    
    def test_combat_stats_auto_clamp_health(self):
        """Тест авто-ограничения здоровья максимумом."""
        stats = CombatStats(
            health=150.0,  # Больше max
            max_health=100.0,
            damage=10.0
        )
        assert stats.health == 100.0  # Должно быть обрезано


# ============================================================================
# TEST: COMBAT SYSTEM (Refactored)
# ============================================================================

class TestCombatSystem:
    """Тесты рефакторенной боевой системы."""
    
    def test_create_entity(self, combat_system: RefactoredCombatSystem):
        """Тест создания боевой сущности."""
        entity = combat_system.create_entity("player1")
        assert entity.entity_id == "player1"
        assert entity.is_alive is False  # Еще нет компонента здоровья
    
    def test_entity_with_components(self, combat_system: RefactoredCombatSystem):
        """Тест сущности со всеми компонентами."""
        entity = combat_system.create_entity("warrior")
        entity.add_health_component(max_health=100.0)
        entity.add_damage_component(base_damage=15.0)
        entity.add_stats_component(base_damage=15.0, base_defense=5.0)
        
        assert entity.is_alive is True
        assert entity.health.current_health == 100.0
        assert entity.damage.base_damage == 15.0
    
    def test_attack_deals_damage(self, combat_system: RefactoredCombatSystem):
        """Тест атаки и нанесения урона."""
        attacker = combat_system.create_entity("attacker")
        target = combat_system.create_entity("target")
        
        attacker.add_damage_component(base_damage=20.0)
        target.add_health_component(max_health=100.0)
        
        damage_dealt, is_crit = combat_system.attack("attacker", "target")
        
        assert damage_dealt > 0
        assert target.health.current_health < 100.0
    
    def test_entity_death(self, combat_system: RefactoredCombatSystem):
        """Тест смерти сущности."""
        attacker = combat_system.create_entity("killer")
        target = combat_system.create_entity("victim")
        
        attacker.add_damage_component(base_damage=50.0)
        target.add_health_component(max_health=80.0)
        
        # Первая атака
        combat_system.attack("killer", "victim")
        assert target.is_alive is True
        
        # Вторая атака - смерть
        combat_system.attack("killer", "victim")
        assert target.is_alive is False
        assert target.is_dead is True
    
    def test_healing(self, combat_system: RefactoredCombatSystem):
        """Тест лечения."""
        entity = combat_system.create_entity("healer_target")
        entity.add_health_component(max_health=100.0)
        
        # Получаем урон
        entity.health.take_damage(30.0)
        assert entity.health.current_health == 70.0
        
        # Лечимся
        healed = combat_system.heal("healer_target", 20.0)
        assert entity.health.current_health == 90.0
    
    def test_circuit_breaker_protection(self, combat_system: RefactoredCombatSystem):
        """Тест защиты Circuit Breaker'ом."""
        # Метод attack защищен декоратором
        assert hasattr(combat_system.attack, 'circuit_breaker')


# ============================================================================
# TEST: INTERFACES (ISP)
# ============================================================================

class TestInterfaces:
    """Тесты интерфейсов (Interface Segregation Principle)."""
    
    def test_health_component_interface(self, health_component: HealthComponent):
        """Тест соответствия интерфейсу IHealthComponent."""
        assert isinstance(health_component, IHealthComponent)
        
        damage = health_component.take_damage(20.0)
        assert damage == 20.0
        assert health_component.current_health == 80.0
        
        healed = health_component.heal(10.0)
        assert health_component.current_health == 90.0
        
        assert health_component.is_alive is True
    
    def test_damage_component_interface(self, damage_component: DamageComponent):
        """Тест соответствия интерфейсу IDamageDealer."""
        assert isinstance(damage_component, IDamageDealer)
        
        target = HealthComponent(max_health=100.0)
        damage = damage_component.attack(target)
        
        assert damage > 0
        assert target.current_health < 100.0


# ============================================================================
# TEST: THREAD SAFETY
# ============================================================================

class TestThreadSafety:
    """Тесты потокобезопасности."""
    
    def test_state_manager_thread_safety(self, state_manager: StateManager):
        """Тест потокобезопасности менеджера состояний."""
        results = []
        
        def worker(thread_id: int):
            for i in range(10):
                state_manager.set(f"thread_{thread_id}.counter", i)
                val = state_manager.get(f"thread_{thread_id}.counter")
                results.append(val)
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(results) == 50
        # Проверяем что все значения записаны корректно
        for thread_id in range(5):
            final_val = state_manager.get(f"thread_{thread_id}.counter")
            assert final_val == 9  # Последнее значение должно быть 9
    
    def test_cache_thread_safety(self):
        """Тест потокобезопасности кэша."""
        cache = LRUCache(max_size=100)
        errors = []
        
        def writer(thread_id: int):
            try:
                for i in range(50):
                    cache.set(f"key_{thread_id}_{i}", i)
            except Exception as e:
                errors.append(e)
        
        def reader(thread_id: int):
            try:
                for i in range(50):
                    cache.get(f"key_{thread_id}_{i}")
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


# ============================================================================
# TEST: BUSINESS SCENARIOS
# ============================================================================

class TestBusinessScenarios:
    """Тесты бизнес-сценариев (end-to-end)."""
    
    def test_full_combat_scenario(self, combat_system: RefactoredCombatSystem):
        """Сценарий: полный бой между двумя сущностями."""
        # Создание бойцов
        hero = combat_system.create_entity("hero")
        monster = combat_system.create_entity("monster")
        
        # Настройка героя
        hero.add_health_component(max_health=120.0)
        hero.add_damage_component(base_damage=15.0)
        hero.add_stats_component(base_damage=15.0, base_speed=1.1)
        
        # Настройка монстра
        monster.add_health_component(max_health=80.0)
        monster.add_damage_component(base_damage=10.0)
        
        # Начало боя
        combat_started = combat_system.start_combat("battle_1", ["hero", "monster"])
        assert combat_started is True
        
        # Раунды атак
        round_count = 0
        while hero.is_alive and monster.is_alive and round_count < 20:
            combat_system.attack("hero", "monster")
            if monster.is_alive:
                combat_system.attack("monster", "hero")
            round_count += 1
        
        # Проверка результата
        assert not (hero.is_alive and monster.is_alive)  # Хотя бы один мертв
        
        # Завершение боя
        combat_system.end_combat("battle_1")
        
        # Статистика
        metrics = combat_system.get_system_metrics()
        assert metrics["total_combats"] == 1
    
    def test_di_container_full_workflow(self, container: DIContainer):
        """Сценарий: полная работа с DI контейнером."""
        register_systems(container)
        
        # Получение систем
        state_mgr = container.resolve(StateManager)
        event_sys = container.resolve(EventSystem)
        
        # Использование
        state_mgr.set("game.score", 100)
        assert state_mgr.get("game.score") == 100
        
        # Синглтоны должны быть одинаковыми
        state_mgr2 = container.resolve(StateManager)
        assert state_mgr is state_mgr2


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src", "--cov-report=term-missing"])
