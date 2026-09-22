"""
Toughness Plugin for AI-EVOLVE
Implements advanced toughness/armor mechanics with elemental effectiveness,
stance states, and break progression as a modular plugin.

Features:
- Stance states: NORMAL, WEAKENED, BROKEN, RECOVERING
- Elemental effectiveness (fire > ice, ice > wind, etc.)
- Cumulative max toughness increase on break (up to 20% of HP)
- Damage multipliers based on stance state
- Event-driven callbacks for game integration
"""
from ai_evolve.core.plugin_base import GamePlugin
from ai_evolve.core.event_system import event_system
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)


class StanceState(Enum):
    """Состояния стойкости"""
    NORMAL = "normal"           # Обычное состояние
    WEAKENED = "weakened"       # Ослабленная стойкость (<25%)
    BROKEN = "broken"           # Пробитая стойкость
    RECOVERING = "recovering"   # Восстановление стойкости


@dataclass(slots=True)
class ToughnessConfig:
    """Конфигурация системы стойкости"""
    max_toughness: float = 100.0
    recovery_rate: float = 10.0  # Единиц стойкости в секунду
    recovery_delay: float = 3.0  # Задержка перед началом восстановления после удара
    break_duration: float = 5.0  # Длительность состояния BROKEN
    damage_taken_multiplier_broken: float = 0.25  # +25% урона когда сломан
    toughness_from_hp_ratio: float = 0.05  # 5% от макс HP при каждом пробитии
    max_toughness_cap_ratio: float = 0.2  # Максимум 20% от HP
    auto_recover_on_break_end: bool = True  # Авто-восстановление до full после BREAK


@dataclass(slots=True)
class ToughnessBreakEvent:
    """Событие пробития стойкости"""
    entity_id: str
    previous_state: StanceState
    new_state: StanceState
    toughness_damage: float
    remaining_toughness: float
    break_count: int
    timestamp: float = field(default_factory=time.perf_counter)


@dataclass(slots=True)
class ToughnessRecoveryEvent:
    """Событие восстановления стойкости"""
    entity_id: str
    recovered_amount: float
    current_toughness: float
    timestamp: float = field(default_factory=time.perf_counter)


# Элементальная эффективность (атака -> защита)
ELEMENTAL_EFFECTIVENESS = {
    "physical": {"physical": 1.0, "fire": 0.5, "ice": 0.5, "lightning": 0.5, "wind": 0.5, "quantum": 0.3, "imaginary": 0.3, "universal": 1.0},
    "fire": {"physical": 0.5, "fire": 1.0, "ice": 2.0, "lightning": 0.5, "wind": 0.5, "quantum": 0.3, "imaginary": 0.3, "universal": 1.0},
    "ice": {"physical": 0.5, "fire": 0.5, "ice": 1.0, "lightning": 0.5, "wind": 2.0, "quantum": 0.3, "imaginary": 0.3, "universal": 1.0},
    "lightning": {"physical": 0.5, "fire": 0.5, "ice": 0.5, "lightning": 1.0, "wind": 0.5, "quantum": 2.0, "imaginary": 0.3, "universal": 1.0},
    "wind": {"physical": 0.5, "fire": 0.5, "ice": 0.5, "lightning": 0.5, "wind": 1.0, "quantum": 0.3, "imaginary": 2.0, "universal": 1.0},
    "quantum": {"physical": 0.3, "fire": 0.3, "ice": 0.3, "lightning": 0.3, "wind": 0.3, "quantum": 1.0, "imaginary": 0.5, "universal": 1.0},
    "imaginary": {"physical": 0.3, "fire": 0.3, "ice": 0.3, "lightning": 0.3, "wind": 0.3, "quantum": 0.5, "imaginary": 1.0, "universal": 1.0},
    "universal": {"physical": 1.0, "fire": 1.0, "ice": 1.0, "lightning": 1.0, "wind": 1.0, "quantum": 1.0, "imaginary": 1.0, "universal": 1.0},
}


class ToughnessComponent:
    """Компонент стойкости сущности"""
    
    def __init__(self, entity_id: str, config: ToughnessConfig, max_health: float = 100.0):
        self.entity_id = entity_id
        self._config = config
        self._base_max_toughness = config.max_toughness
        self._max_toughness = self._base_max_toughness
        self._current_toughness = self._max_toughness
        self._state = StanceState.NORMAL
        self._break_count = 0
        self._last_damage_time: float = 0.0
        self._break_start_time: float = 0.0
        self._hp_based_bonus: float = 0.0
        self._max_health = max_health
        
        # Callbacks
        self.on_toughness_changed: Optional[Callable] = None
        self.on_toughness_broken: Optional[Callable] = None
        self.on_toughness_recovered: Optional[Callable] = None
        self.on_state_changed: Optional[Callable] = None
    
    @property
    def current_toughness(self) -> float:
        return self._current_toughness
    
    @property
    def max_toughness(self) -> float:
        return self._max_toughness
    
    @property
    def state(self) -> StanceState:
        return self._state
    
    @property
    def break_count(self) -> int:
        return self._break_count
    
    @property
    def is_broken(self) -> bool:
        return self._state == StanceState.BROKEN
    
    @property
    def damage_multiplier(self) -> float:
        """Множитель входящего урона в зависимости от состояния"""
        if self._state == StanceState.BROKEN:
            return 1.0 + self._config.damage_taken_multiplier_broken
        elif self._state == StanceState.WEAKENED:
            return 1.0 + (self._config.damage_taken_multiplier_broken * 0.5)
        elif self._state == StanceState.RECOVERING:
            return 1.0 + (self._config.damage_taken_multiplier_broken * 0.2)
        return 1.0
    
    def update(self, delta_time: float):
        """Обновление компонента"""
        current_time = time.perf_counter()
        
        # Обработка состояния BROKEN
        if self._state == StanceState.BROKEN:
            time_in_break = current_time - self._break_start_time
            if time_in_break >= self._config.break_duration:
                self._exit_break_state(current_time)
                return
        
        # Восстановление стойкости
        if self._state in (StanceState.NORMAL, StanceState.RECOVERING):
            self._recover_toughness(delta_time, current_time)
    
    def take_toughness_damage(
        self,
        damage: float,
        toughness_type: str = "universal",
        enemy_toughness_type: str = "physical"
    ) -> float:
        """
        Получение урона по стойкости.
        
        Returns:
            Фактический нанесенный урон с учетом множителей
        """
        if self._state == StanceState.BROKEN:
            return 0.0
        
        if damage <= 0:
            return 0.0
        
        # Расчет множителя эффективности стихии
        effectiveness = self._get_elemental_effectiveness(toughness_type, enemy_toughness_type)
        actual_damage = damage * effectiveness
        
        # Применение урона
        old_toughness = self._current_toughness
        self._current_toughness = max(0.0, self._current_toughness - actual_damage)
        self._last_damage_time = time.perf_counter()
        
        # Проверка на ослабленную стойкость (ниже 25%)
        if self._state == StanceState.NORMAL and self._current_toughness < self._max_toughness * 0.25:
            self._set_state(StanceState.WEAKENED)
        
        # Проверка на пробитие
        if self._current_toughness <= 0.0:
            self._trigger_break()
        
        # Вызов callback
        if self.on_toughness_changed:
            self.on_toughness_changed(self._current_toughness, old_toughness)
        
        return actual_damage
    
    def _get_elemental_effectiveness(self, attack_type: str, defense_type: str) -> float:
        """Получение множителя эффективности стихии"""
        if attack_type in ELEMENTAL_EFFECTIVENESS and defense_type in ELEMENTAL_EFFECTIVENESS.get(attack_type, {}):
            return ELEMENTAL_EFFECTIVENESS[attack_type][defense_type]
        return 1.0
    
    def _trigger_break(self) -> None:
        """Срабатывание пробития стойкости"""
        self._break_count += 1
        self._current_toughness = 0.0
        self._break_start_time = time.perf_counter()
        
        previous_state = self._state
        self._set_state(StanceState.BROKEN)
        
        # Увеличение максимальной стойкости на % от макс HP
        self._increase_max_toughness()
        
        logger.info(f"СТОЙКОСТЬ ПРОБИТА! #{self._break_count}, новый макс: {self._max_toughness:.1f}")
        
        # Событие пробития
        if self.on_toughness_broken:
            event = ToughnessBreakEvent(
                entity_id=self.entity_id,
                previous_state=previous_state,
                new_state=StanceState.BROKEN,
                toughness_damage=self._max_toughness,
                remaining_toughness=0.0,
                break_count=self._break_count
            )
            self.on_toughness_broken(event)
    
    def _increase_max_toughness(self) -> None:
        """Увеличение максимальной стойкости после пробития"""
        if self._max_health <= 0:
            return
        
        # Бонус от HP с накоплением
        hp_bonus = self._max_health * self._config.toughness_from_hp_ratio
        
        # Текущий бонус увеличивается с каждым пробитием
        self._hp_based_bonus += hp_bonus
        
        # Ограничение максимумом
        max_allowed_bonus = self._max_health * self._config.max_toughness_cap_ratio
        self._hp_based_bonus = min(self._hp_based_bonus, max_allowed_bonus)
        
        # Пересчет максимума
        self._max_toughness = self._base_max_toughness + self._hp_based_bonus
    
    def _exit_break_state(self, current_time: float) -> None:
        """Выход из состояния BROKEN"""
        if self._config.auto_recover_on_break_end:
            # Полное восстановление стойкости
            old_toughness = self._current_toughness
            self._current_toughness = self._max_toughness
            
            logger.info(f"Стойкость восстановлена полностью: {self._current_toughness:.1f}")
            
            if self.on_toughness_recovered:
                event = ToughnessRecoveryEvent(
                    entity_id=self.entity_id,
                    recovered_amount=self._current_toughness - old_toughness,
                    current_toughness=self._current_toughness
                )
                self.on_toughness_recovered(event)
        
        # Переход в NORMAL
        self._set_state(StanceState.NORMAL)
        self._break_start_time = current_time
        
        if self.on_state_changed:
            self.on_state_changed(StanceState.NORMAL)
    
    def _recover_toughness(self, delta_time: float, current_time: float) -> None:
        """Восстановление стойкости со временем"""
        # Проверка задержки после получения урона
        time_since_damage = current_time - self._last_damage_time
        if time_since_damage < self._config.recovery_delay:
            return
        
        # Восстановление
        recovery_amount = self._config.recovery_rate * delta_time
        old_toughness = self._current_toughness
        
        if self._current_toughness < self._max_toughness:
            self._current_toughness = min(self._max_toughness, self._current_toughness + recovery_amount)
            
            if abs(self._current_toughness - old_toughness) > 0.01 and self.on_toughness_changed:
                self.on_toughness_changed(self._current_toughness, old_toughness)
    
    def _set_state(self, new_state: StanceState) -> None:
        """Установка нового состояния"""
        if self._state == new_state:
            return
        
        old_state = self._state
        self._state = new_state
        
        logger.debug(f"Состояние стойкости: {old_state.value} -> {new_state.value}")
        
        if self.on_state_changed:
            self.on_state_changed(new_state)
    
    def reset(self) -> None:
        """Сброс компонента к начальному состоянию"""
        self._current_toughness = self._base_max_toughness
        self._max_toughness = self._base_max_toughness
        self._hp_based_bonus = 0.0
        self._break_count = 0
        self._state = StanceState.NORMAL
        self._last_damage_time = 0.0
        self._break_start_time = 0.0
    
    def get_metrics(self) -> dict:
        """Метрики компонента"""
        return {
            "entity_id": self.entity_id,
            "current_toughness": self._current_toughness,
            "max_toughness": self._max_toughness,
            "toughness_percent": (self._current_toughness / self._max_toughness * 100.0) if self._max_toughness > 0 else 0.0,
            "state": self._state.value,
            "break_count": self._break_count,
            "damage_multiplier": self.damage_multiplier,
            "hp_based_bonus": self._hp_based_bonus,
        }


class ToughnessPlugin(GamePlugin):
    """
    Advanced toughness system plugin.
    Handles stance states, elemental effectiveness, and break progression.
    """
    
    def __init__(self):
        super().__init__("toughness")
        self.components: Dict[str, ToughnessComponent] = {}
        self.default_config = ToughnessConfig(
            max_toughness=100.0,
            recovery_rate=10.0,
            recovery_delay=3.0,
            break_duration=5.0,
            damage_taken_multiplier_broken=0.25,
            toughness_from_hp_ratio=0.05,
            max_toughness_cap_ratio=0.2,
            auto_recover_on_break_end=True
        )
    
    def on_init(self):
        """Initialize toughness system."""
        print("[ToughnessPlugin] Initialized with advanced stance system")
    
    def on_update(self, delta_time: float):
        """Update all toughness components."""
        for component in self.components.values():
            component.update(delta_time)
    
    def on_shutdown(self):
        """Shutdown toughness system."""
        self.components.clear()
        print("[ToughnessPlugin] Shutdown")
    
    def register_events(self, event_system):
        """Register toughness event handlers."""
        event_system.subscribe("damage_dealt", self.handle_damage_dealt)
        event_system.subscribe("entity_registered", self.handle_entity_registered)
        event_system.subscribe("entity_removed", self.handle_entity_removed)
    
    def handle_entity_registered(self, sender, **data):
        """Handle new entity registration."""
        entity = data.get("entity")
        entity_id = data.get("entity_id")
        max_health = getattr(entity, 'max_health', 100.0)
        
        if entity_id and entity_id not in self.components:
            config = self.default_config
            component = ToughnessComponent(entity_id, config, max_health)
            
            # Setup callbacks to emit events
            component.on_toughness_broken = lambda e: event_system.emit("toughness_broken", {
                "entity_id": e.entity_id,
                "break_count": e.break_count,
                "new_max_toughness": component.max_toughness
            })
            component.on_toughness_recovered = lambda e: event_system.emit("toughness_recovered", {
                "entity_id": e.entity_id,
                "recovered_amount": e.recovered_amount
            })
            component.on_state_changed = lambda s: event_system.emit("toughness_state_changed", {
                "entity_id": entity_id,
                "new_state": s.value
            })
            
            self.components[entity_id] = component
            logger.debug(f"[ToughnessPlugin] Created component for {entity_id}")
    
    def handle_entity_removed(self, sender, **data):
        """Handle entity removal."""
        entity_id = data.get("entity_id")
        if entity_id and entity_id in self.components:
            del self.components[entity_id]
            logger.debug(f"[ToughnessPlugin] Removed component for {entity_id}")
    
    def handle_damage_dealt(self, sender, **data):
        """Handle damage dealt event - apply toughness damage."""
        target = data.get("target")
        target_id = getattr(target, 'entity_id', None)
        
        if not target_id or target_id not in self.components:
            return
        
        component = self.components[target_id]
        toughness_damage = data.get("toughness_damage", 0.0)
        attack_type = data.get("toughness_type", "universal")
        defense_type = data.get("enemy_toughness_type", "physical")
        
        if toughness_damage > 0:
            actual_damage = component.take_toughness_damage(toughness_damage, attack_type, defense_type)
            
            # Emit toughness damage event
            event_system.emit("toughness_damage_applied", {
                "entity_id": target_id,
                "base_damage": toughness_damage,
                "actual_damage": actual_damage,
                "current_toughness": component.current_toughness,
                "max_toughness": component.max_toughness,
                "state": component.state.value,
                "is_broken": component.is_broken
            })
    
    def get_component(self, entity_id: str) -> Optional[ToughnessComponent]:
        """Get toughness component for an entity."""
        return self.components.get(entity_id)
    
    def create_component(self, entity_id: str, max_health: float = 100.0, config: Optional[ToughnessConfig] = None) -> ToughnessComponent:
        """Create a new toughness component for an entity."""
        if entity_id in self.components:
            return self.components[entity_id]
        
        cfg = config or self.default_config
        component = ToughnessComponent(entity_id, cfg, max_health)
        self.components[entity_id] = component
        return component
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "default_max_toughness": self.default_config.max_toughness,
            "recovery_rate": self.default_config.recovery_rate,
            "recovery_delay": self.default_config.recovery_delay,
            "break_duration": self.default_config.break_duration,
            "damage_multiplier_broken": self.default_config.damage_taken_multiplier_broken,
            "hp_ratio_per_break": self.default_config.toughness_from_hp_ratio,
            "max_hp_ratio_cap": self.default_config.max_toughness_cap_ratio,
            "active_components": len(self.components)
        }
