"""
Effects Plugin for AI-EVOLVE
Implements negative status effects with combo mechanics.

Features:
- Stackable effects (bleed, burn, freeze, shock, poison)
- Combo reactions between effects (Melt, Freeze, Superconduct, etc.)
- Duration-based and stack-based effects
- Effect resistance and immunity system
- Event-driven callbacks for game integration
"""
from ai_evolve.core.plugin_base import GamePlugin
from ai_evolve.core.event_system import event_system
from typing import Dict, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)


class EffectType(Enum):
    """Типы эффектов"""
    BLEED = "bleed"           # Кровотечение - DoT, стакается
    BURN = "burn"             # Горение - DoT, снижает защиту
    FREEZE = "freeze"         # Заморозка - оглушение, увеличивает урон
    SHOCK = "shock"           # Шок - снижает скорость атаки
    POISON = "poison"         # Яд - DoT, распространяется
    FROZEN = "frozen"         # Полная заморозка - нельзя действовать
    STUN = "stun"             # Оглушение
    WEAKEN = "weaken"         # Снижение урона
    VULNERABLE = "vulnerable" # Повышенный входящий урон


class EffectTickType(Enum):
    """Когда тикает эффект"""
    ON_APPLY = "on_apply"           
    PER_SECOND = "per_second"       
    PER_TURN = "per_turn"           
    ON_DAMAGE_TAKEN = "on_damage_taken"  
    ON_ACTION = "on_action"         


@dataclass(slots=True)
class EffectConfig:
    """Конфигурация эффекта"""
    effect_type: EffectType
    base_duration: float = 0.0          
    base_damage: float = 0.0            
    max_stacks: int = 1                 
    damage_per_stack: float = 0.0       
    tick_type: EffectTickType = EffectTickType.PER_SECOND
    can_crit: bool = False              
    cleansable: bool = True             
    priority: int = 0                   


@dataclass(slots=True)
class ActiveEffect:
    """Активный эффект на цели"""
    config: EffectConfig
    stacks: int = 1
    remaining_duration: float = 0.0
    applied_at: float = field(default_factory=time.perf_counter)
    last_tick_time: float = field(default_factory=time.perf_counter)
    source_id: Optional[str] = None
    
    @property
    def total_damage_per_tick(self) -> float:
        return self.config.base_damage + (self.config.damage_per_stack * self.stacks)
    
    @property
    def is_expired(self) -> bool:
        if self.config.base_duration <= 0:
            return True
        return self.remaining_duration <= 0


DEFAULT_EFFECTS = {
    EffectType.BLEED: EffectConfig(
        effect_type=EffectType.BLEED,
        base_duration=8.0,
        base_damage=5.0,
        max_stacks=5,
        damage_per_stack=2.0,
        tick_type=EffectTickType.PER_SECOND,
        can_crit=False,
    ),
    EffectType.BURN: EffectConfig(
        effect_type=EffectType.BURN,
        base_duration=6.0,
        base_damage=8.0,
        max_stacks=3,
        damage_per_stack=3.0,
        tick_type=EffectTickType.PER_SECOND,
        can_crit=False,
    ),
    EffectType.FREEZE: EffectConfig(
        effect_type=EffectType.FREEZE,
        base_duration=2.0,
        base_damage=0.0,
        max_stacks=1,
        tick_type=EffectTickType.ON_APPLY,
    ),
    EffectType.SHOCK: EffectConfig(
        effect_type=EffectType.SHOCK,
        base_duration=4.0,
        base_damage=3.0,
        max_stacks=4,
        damage_per_stack=1.5,
        tick_type=EffectTickType.PER_SECOND,
    ),
    EffectType.POISON: EffectConfig(
        effect_type=EffectType.POISON,
        base_duration=10.0,
        base_damage=4.0,
        max_stacks=6,
        damage_per_stack=1.5,
        tick_type=EffectTickType.PER_SECOND,
    ),
    EffectType.FROZEN: EffectConfig(
        effect_type=EffectType.FROZEN,
        base_duration=3.0,
        base_damage=0.0,
        max_stacks=1,
        tick_type=EffectTickType.ON_APPLY,
    ),
    EffectType.STUN: EffectConfig(
        effect_type=EffectType.STUN,
        base_duration=1.5,
        base_damage=0.0,
        max_stacks=1,
        tick_type=EffectTickType.ON_APPLY,
    ),
    EffectType.WEAKEN: EffectConfig(
        effect_type=EffectType.WEAKEN,
        base_duration=5.0,
        base_damage=0.0,
        max_stacks=3,
        tick_type=EffectTickType.PER_SECOND,
    ),
    EffectType.VULNERABLE: EffectConfig(
        effect_type=EffectType.VULNERABLE,
        base_duration=4.0,
        base_damage=0.0,
        max_stacks=2,
        tick_type=EffectTickType.PER_SECOND,
    ),
}


COMBO_REACTIONS = {
    (EffectType.FREEZE, EffectType.BURN): ("melt", 50.0),
    (EffectType.BURN, EffectType.FREEZE): ("melt", 50.0),
    (EffectType.FREEZE, EffectType.SHOCK): ("superconduct", 80.0),
    (EffectType.SHOCK, EffectType.FREEZE): ("superconduct", 80.0),
    (EffectType.BURN, EffectType.POISON): ("explosion", 60.0),
    (EffectType.POISON, EffectType.BURN): ("explosion", 60.0),
    (EffectType.BLEED, EffectType.BLEED): ("hemorrhage", 30.0),
    (EffectType.SHOCK, EffectType.SHOCK): ("overload", 20.0),
}


@dataclass(slots=True)
class EffectAppliedEvent:
    entity_id: str
    effect_type: EffectType
    stacks: int
    duration: float
    source_id: Optional[str] = None
    timestamp: float = field(default_factory=time.perf_counter)


@dataclass(slots=True)
class EffectTickEvent:
    entity_id: str
    effect_type: EffectType
    damage: float
    is_critical: bool = False
    timestamp: float = field(default_factory=time.perf_counter)


@dataclass(slots=True)
class EffectRemovedEvent:
    entity_id: str
    effect_type: EffectType
    reason: str
    timestamp: float = field(default_factory=time.perf_counter)


@dataclass(slots=True)
class ComboTriggeredEvent:
    entity_id: str
    combo_name: str
    effects_consumed: List[EffectType]
    damage: float = 0.0
    timestamp: float = field(default_factory=time.perf_counter)


class EffectComponent:
    """Компонент эффектов сущности"""
    
    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self.active_effects: Dict[EffectType, ActiveEffect] = {}
        self.effect_resistances: Dict[EffectType, float] = {}
        self.effect_immunities: Set[EffectType] = set()
        
        self.on_effect_applied: Optional[Callable] = None
        self.on_effect_removed: Optional[Callable] = None
        self.on_effect_ticked: Optional[Callable] = None
        self.on_combo_triggered: Optional[Callable] = None
    
    def apply_effect(
        self,
        effect_type: EffectType,
        config: Optional[EffectConfig] = None,
        stacks: int = 1,
        duration: Optional[float] = None,
        source_id: Optional[str] = None
    ) -> bool:
        if effect_type in self.effect_immunities:
            return False
        
        cfg = config or DEFAULT_EFFECTS.get(effect_type)
        if not cfg:
            logger.warning(f"Неизвестный эффект {effect_type}")
            return False
        
        resistance = self.effect_resistances.get(effect_type, 0.0)
        if resistance >= 1.0:
            return False
        
        import random
        if random.random() < resistance:
            return False
        
        # Проверка на комбо реакцию с существующими эффектами
        existing_effects = list(self.active_effects.keys())
        combo_triggered = False
        for existing in existing_effects:
            # Не триггерим комбо если это тот же самый тип эффекта (просто добавляем стаки)
            if existing == effect_type:
                continue
                
            combo_key = (existing, effect_type)
            if combo_key in COMBO_REACTIONS:
                self._trigger_combo(existing, effect_type, COMBO_REACTIONS[combo_key])
                # Удаляем только существующий эффект из комбо, новый ещё не добавлен
                if existing in self.active_effects:
                    del self.active_effects[existing]
                combo_triggered = True
                # Не возвращаем True сразу - даём возможность применить эффект
        
        current_time = time.perf_counter()
        
        if effect_type in self.active_effects:
            # Обновление существующего эффекта - добавляем стаки
            active = self.active_effects[effect_type]
            new_stacks = min(active.stacks + stacks, cfg.max_stacks)
            active.stacks = new_stacks
            # Продлеваем длительность при добавлении стаков
            active.remaining_duration = duration or cfg.base_duration
            active.last_tick_time = current_time
        else:
            # Новый эффект (или после комбо)
            active = ActiveEffect(
                config=cfg,
                stacks=min(stacks, cfg.max_stacks),
                remaining_duration=duration or cfg.base_duration,
                applied_at=current_time,
                last_tick_time=current_time,
                source_id=source_id
            )
            self.active_effects[effect_type] = active
        
        # Эмитим событие о применении эффекта
        if self.on_effect_applied:
            event = EffectAppliedEvent(
                entity_id=self.entity_id,
                effect_type=effect_type,
                stacks=active.stacks,
                duration=active.remaining_duration,
                source_id=source_id
            )
            self.on_effect_applied(event)
        
        return True
    
    def update(self, delta_time: float) -> List[float]:
        damage_dealt = []
        current_time = time.perf_counter()
        effects_to_remove = []
        
        for effect_type, active in self.active_effects.items():
            if active.config.tick_type == EffectTickType.ON_APPLY:
                continue
            
            if active.config.base_duration > 0:
                active.remaining_duration -= delta_time
                if active.is_expired:
                    effects_to_remove.append(effect_type)
                    continue
            
            if active.config.tick_type == EffectTickType.PER_SECOND:
                time_since_tick = current_time - active.last_tick_time
                if time_since_tick >= 1.0:
                    tick_damage = active.total_damage_per_tick
                    
                    is_crit = False
                    if active.config.can_crit:
                        import random
                        if random.random() < 0.1:
                            tick_damage *= 2.0
                            is_crit = True
                    
                    damage_dealt.append(tick_damage)
                    active.last_tick_time = current_time
                    
                    if self.on_effect_ticked:
                        event = EffectTickEvent(
                            entity_id=self.entity_id,
                            effect_type=effect_type,
                            damage=tick_damage,
                            is_critical=is_crit
                        )
                        self.on_effect_ticked(event)
        
        for effect_type in effects_to_remove:
            self._remove_effect(effect_type, "expired")
        
        return damage_dealt
    
    def _trigger_combo(self, effect1: EffectType, effect2: EffectType, combo_data: tuple):
        combo_name, damage = combo_data
        
        logger.info(f"КОМБО: {combo_name} на {self.entity_id}!")
        
        if self.on_combo_triggered:
            event = ComboTriggeredEvent(
                entity_id=self.entity_id,
                combo_name=combo_name,
                effects_consumed=[effect1, effect2],
                damage=damage
            )
            self.on_combo_triggered(event)
    
    def _remove_effect(self, effect_type: EffectType, reason: str):
        if effect_type not in self.active_effects:
            return
        
        del self.active_effects[effect_type]
        
        if self.on_effect_removed:
            event = EffectRemovedEvent(
                entity_id=self.entity_id,
                effect_type=effect_type,
                reason=reason
            )
            self.on_effect_removed(event)
    
    def remove_effect(self, effect_type: EffectType) -> bool:
        if effect_type not in self.active_effects:
            return False
        self._remove_effect(effect_type, "cleansed")
        return True
    
    def has_effect(self, effect_type: EffectType) -> bool:
        return effect_type in self.active_effects
    
    def get_effect_stacks(self, effect_type: EffectType) -> int:
        active = self.active_effects.get(effect_type)
        return active.stacks if active else 0
    
    def is_ccd(self) -> bool:
        ccd_effects = {EffectType.STUN, EffectType.FROZEN, EffectType.FREEZE}
        return any(e in self.active_effects for e in ccd_effects)
    
    def get_metrics(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "active_effects": [
                {"type": e.value, "stacks": a.stacks, "remaining": a.remaining_duration}
                for e, a in self.active_effects.items()
            ],
            "effect_count": len(self.active_effects),
            "is_ccd": self.is_ccd(),
        }
    
    def reset(self):
        for effect_type in list(self.active_effects.keys()):
            self._remove_effect(effect_type, "reset")
        self.active_effects.clear()


class EffectsPlugin(GamePlugin):
    """Plugin для системы негативных эффектов и комбо."""
    
    def __init__(self):
        super().__init__("effects")
        self.components: Dict[str, EffectComponent] = {}
        self.custom_effects: Dict[EffectType, EffectConfig] = {}
    
    def on_init(self, game_core=None):
        """Initialize effects system."""
        print("[EffectsPlugin] Initialized with combo system")
        return True
    
    def on_update(self, delta_time: float):
        for component in self.components.values():
            component.update(delta_time)
    
    def on_shutdown(self):
        for component in self.components.values():
            component.reset()
        self.components.clear()
        print("[EffectsPlugin] Shutdown")
    
    def register_events(self, event_system):
        event_system.subscribe("entity_registered", self.handle_entity_registered)
        event_system.subscribe("entity_removed", self.handle_entity_removed)
        event_system.subscribe("effect_apply", self.handle_effect_apply)
        
        # Store reference to event_system for use in lambdas
        self._event_system = event_system
    
    def handle_entity_registered(self, sender, **data):
        entity_id = data.get("entity_id")
        
        if entity_id and entity_id not in self.components:
            component = EffectComponent(entity_id)
            
            # Use stored reference instead of closure variable
            es = self._event_system
            component.on_effect_applied = lambda e: es.emit("effect_applied", {
                "entity_id": e.entity_id,
                "effect_type": e.effect_type.value,
                "stacks": e.stacks,
                "duration": e.duration,
            })
            component.on_effect_removed = lambda e: es.emit("effect_removed", {
                "entity_id": e.entity_id,
                "effect_type": e.effect_type.value,
                "reason": e.reason,
            })
            component.on_combo_triggered = lambda e: es.emit("combo_triggered", {
                "entity_id": e.entity_id,
                "combo_name": e.combo_name,
                "damage": e.damage,
            })
            
            self.components[entity_id] = component
    
    def handle_entity_removed(self, sender, **data):
        entity_id = data.get("entity_id")
        if entity_id and entity_id in self.components:
            self.components[entity_id].reset()
            del self.components[entity_id]
    
    def handle_effect_apply(self, sender, **data):
        target_id = data.get("target_id")
        effect_type_str = data.get("effect_type")
        stacks = data.get("stacks", 1)
        duration = data.get("duration")
        source_id = data.get("source_id")
        
        if not target_id or not effect_type_str:
            return
        
        try:
            effect_type = EffectType(effect_type_str)
        except ValueError:
            logger.warning(f"Неизвестный тип эффекта: {effect_type_str}")
            return
        
        if target_id not in self.components:
            return
        
        component = self.components[target_id]
        config = self.custom_effects.get(effect_type)
        
        component.apply_effect(
            effect_type=effect_type,
            config=config,
            stacks=stacks,
            duration=duration,
            source_id=source_id
        )
    
    def get_component(self, entity_id: str) -> Optional[EffectComponent]:
        return self.components.get(entity_id)
    
    def create_component(self, entity_id: str) -> EffectComponent:
        if entity_id in self.components:
            return self.components[entity_id]
        
        component = EffectComponent(entity_id)
        self.components[entity_id] = component
        return component
    
    def register_custom_effect(self, effect_type: EffectType, config: EffectConfig):
        self.custom_effects[effect_type] = config
    
    def get_config(self) -> Dict:
        return {
            "registered_effects": len(DEFAULT_EFFECTS) + len(self.custom_effects),
            "active_components": len(self.components),
        }
