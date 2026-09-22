"""
Entity Components Plugin for AI-EVOLVE

This plugin migrates Character, Enemy, and Boss entities to the plugin architecture.
Instead of monolithic classes, entities are now composed of components managed by plugins.

Architecture:
- EntityCore: Base entity with minimal state (id, position, health)
- EntityComponents: Plugin-managed components (Combat, AI, Stats, Effects)
- EntityFactory: Creates entities with appropriate component sets

Usage:
    # Register plugin
    from ai_evolve.plugins.entity_components import EntityComponentsPlugin
    plugin_manager.register(EntityComponentsPlugin())
    
    # Create entity
    entity = entity_factory.create_player(
        components=['combat', 'stats', 'ai', 'effects']
    )
"""
import logging
from typing import Dict, List, Any, Optional, Type
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from ..core.plugin_base import GamePlugin
from ..core.event_system import EventSystem

logger = logging.getLogger(__name__)


@dataclass
class EntityData:
    """Base data for all entities."""
    entity_id: str
    entity_type: str  # 'player', 'enemy', 'boss'
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    health: float = 100.0
    max_health: float = 100.0
    is_alive: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class EntityComponent(ABC):
    """
    Base class for entity components.
    Components are modular pieces of functionality that can be attached to entities.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Component name."""
        pass
    
    def on_attach(self, entity: 'GameEntity'):
        """Called when component is attached to an entity."""
        pass
    
    def on_detach(self, entity: 'GameEntity'):
        """Called when component is detached from an entity."""
        pass
    
    def on_update(self, entity: 'GameEntity', delta_time: float):
        """Called every frame update."""
        pass
    
    def get_state(self) -> Dict[str, Any]:
        """Return component state for serialization."""
        return {}
    
    def set_state(self, state: Dict[str, Any]):
        """Restore component state from serialization."""
        pass


class CombatComponent(EntityComponent):
    """Combat-related functionality for entities."""
    
    @property
    def name(self) -> str:
        return "combat"
    
    def __init__(self):
        self.damage = 10.0
        self.attack_speed = 1.0
        self.attack_range = 5.0
        self.critical_chance = 0.1
        self.critical_damage = 2.0
        self.dodge_chance = 0.05
        self.is_attacking = False
        self.attack_cooldown = 0.0
    
    def on_attach(self, entity: 'GameEntity'):
        logger.debug(f"Combat component attached to {entity.entity_id}")
    
    def on_update(self, entity: 'GameEntity', delta_time: float):
        if self.attack_cooldown > 0:
            self.attack_cooldown -= delta_time
    
    def can_attack(self) -> bool:
        return self.attack_cooldown <= 0 and not self.is_attacking
    
    def perform_attack(self):
        """Initiate an attack."""
        if not self.can_attack():
            return False
        
        self.is_attacking = True
        self.attack_cooldown = 1.0 / self.attack_speed
        
        # Emit attack event
        event_system = EventSystem()
        event_system.emit('entity_attack', {
            'entity_id': getattr(self, '_entity_id', None),
            'damage': self.damage,
            'critical_chance': self.critical_chance,
        })
        
        return True
    
    def get_state(self) -> Dict[str, Any]:
        return {
            'damage': self.damage,
            'attack_speed': self.attack_speed,
            'attack_range': self.attack_range,
            'critical_chance': self.critical_chance,
            'critical_damage': self.critical_damage,
            'dodge_chance': self.dodge_chance,
            'attack_cooldown': self.attack_cooldown,
        }
    
    def set_state(self, state: Dict[str, Any]):
        self.damage = state.get('damage', self.damage)
        self.attack_speed = state.get('attack_speed', self.attack_speed)
        self.attack_range = state.get('attack_range', self.attack_range)
        self.critical_chance = state.get('critical_chance', self.critical_chance)
        self.critical_damage = state.get('critical_damage', self.critical_damage)
        self.dodge_chance = state.get('dodge_chance', self.dodge_chance)
        self.attack_cooldown = state.get('attack_cooldown', 0.0)


class StatsComponent(EntityComponent):
    """Statistics and progression component."""
    
    @property
    def name(self) -> str:
        return "stats"
    
    def __init__(self):
        self.level = 1
        self.experience = 0
        self.experience_to_next_level = 100
        self.strength = 10
        self.agility = 10
        self.intelligence = 10
        self.vitality = 10
    
    def add_experience(self, amount: int) -> bool:
        """Add experience and check for level up."""
        self.experience += amount
        
        leveled_up = False
        while self.experience >= self.experience_to_next_level:
            self.experience -= self.experience_to_next_level
            self.level_up()
            leveled_up = True
        
        return leveled_up
    
    def level_up(self):
        """Increase entity level."""
        self.level += 1
        self.experience_to_next_level = int(self.experience_to_next_level * 1.5)
        
        # Stat increases
        self.strength += 2
        self.agility += 2
        self.intelligence += 2
        self.vitality += 2
        
        logger.info(f"Entity leveled up to {self.level}")
        
        # Emit level up event
        event_system = EventSystem()
        event_system.emit('entity_level_up', {
            'entity_id': getattr(self, '_entity_id', None),
            'level': self.level,
        })
    
    def get_state(self) -> Dict[str, Any]:
        return {
            'level': self.level,
            'experience': self.experience,
            'experience_to_next_level': self.experience_to_next_level,
            'strength': self.strength,
            'agility': self.agility,
            'intelligence': self.intelligence,
            'vitality': self.vitality,
        }
    
    def set_state(self, state: Dict[str, Any]):
        self.level = state.get('level', 1)
        self.experience = state.get('experience', 0)
        self.experience_to_next_level = state.get('experience_to_next_level', 100)
        self.strength = state.get('strength', 10)
        self.agility = state.get('agility', 10)
        self.intelligence = state.get('intelligence', 10)
        self.vitality = state.get('vitality', 10)


class AIComponent(EntityComponent):
    """AI behavior component for NPCs and enemies."""
    
    @property
    def name(self) -> str:
        return "ai"
    
    def __init__(self):
        self.enabled = True
        self.state = "idle"  # idle, patrol, chase, attack, flee
        self.target_entity_id: Optional[str] = None
        self.patrol_points: List[tuple] = []
        self.current_patrol_index = 0
        self.update_interval = 0.5
        self.update_timer = 0.0
        self.ai_parameters: Dict[str, Any] = {}
    
    def on_update(self, entity: 'GameEntity', delta_time: float):
        if not self.enabled:
            return
        
        self.update_timer += delta_time
        if self.update_timer < self.update_interval:
            return
        
        self.update_timer = 0.0
        self.think(entity)
    
    def think(self, entity: 'GameEntity'):
        """AI decision making."""
        if self.state == "idle":
            self._think_idle(entity)
        elif self.state == "patrol":
            self._think_patrol(entity)
        elif self.state == "chase":
            self._think_chase(entity)
        elif self.state == "attack":
            self._think_attack(entity)
        elif self.state == "flee":
            self._think_flee(entity)
    
    def _think_idle(self, entity: 'GameEntity'):
        """Idle behavior - look for targets."""
        # Simplified - in real implementation would scan for enemies
        pass
    
    def _think_patrol(self, entity: 'GameEntity'):
        """Patrol between points."""
        if not self.patrol_points:
            return
        
        target = self.patrol_points[self.current_patrol_index]
        dx = target[0] - entity.x
        dy = target[1] - entity.y
        distance = (dx**2 + dy**2) ** 0.5
        
        if distance < 1.0:
            self.current_patrol_index = (self.current_patrol_index + 1) % len(self.patrol_points)
        else:
            # Move towards target
            entity.x += (dx / distance) * 3.0 * 0.5  # speed * delta_time
            entity.y += (dy / distance) * 3.0 * 0.5
    
    def _think_chase(self, entity: 'GameEntity'):
        """Chase target."""
        pass
    
    def _think_attack(self, entity: 'GameEntity'):
        """Attack target."""
        pass
    
    def _think_flee(self, entity: 'GameEntity'):
        """Flee from threat."""
        pass
    
    def set_state(self, new_state: str):
        """Change AI state."""
        old_state = self.state
        self.state = new_state
        
        event_system = EventSystem()
        event_system.emit('ai_state_changed', {
            'entity_id': getattr(self, '_entity_id', None),
            'old_state': old_state,
            'new_state': new_state,
        })
    
    def get_state(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'state': self.state,
            'target_entity_id': self.target_entity_id,
            'patrol_points': self.patrol_points,
            'current_patrol_index': self.current_patrol_index,
        }
    
    def set_state_from_dict(self, state: Dict[str, Any]):
        self.enabled = state.get('enabled', True)
        self.state = state.get('state', 'idle')
        self.target_entity_id = state.get('target_entity_id')
        self.patrol_points = state.get('patrol_points', [])
        self.current_patrol_index = state.get('current_patrol_index', 0)


class GameEntity:
    """
    Composite entity made of components.
    This replaces the monolithic Character/Enemy classes.
    """
    
    def __init__(self, data: EntityData):
        self._data = data
        self._components: Dict[str, EntityComponent] = {}
        self._component_order: List[str] = []
    
    @property
    def entity_id(self) -> str:
        return self._data.entity_id
    
    @property
    def entity_type(self) -> str:
        return self._data.entity_type
    
    @property
    def x(self) -> float:
        return self._data.x
    
    @x.setter
    def x(self, value: float):
        self._data.x = value
    
    @property
    def y(self) -> float:
        return self._data.y
    
    @y.setter
    def y(self, value: float):
        self._data.y = value
    
    @property
    def z(self) -> float:
        return self._data.z
    
    @z.setter
    def z(self, value: float):
        self._data.z = value
    
    @property
    def health(self) -> float:
        return self._data.health
    
    @health.setter
    def health(self, value: float):
        old_health = self._data.health
        self._data.health = max(0, min(value, self._data.max_health))
        
        if self._data.health <= 0 and old_health > 0:
            self._data.is_alive = False
            event_system = EventSystem()
            event_system.emit('entity_death', {'entity_id': self.entity_id})
        elif self._data.health > 0 and old_health <= 0:
            self._data.is_alive = True
            event_system = EventSystem()
            event_system.emit('entity_revive', {'entity_id': self.entity_id})
    
    @property
    def max_health(self) -> float:
        return self._data.max_health
    
    @max_health.setter
    def max_health(self, value: float):
        self._data.max_health = value
    
    @property
    def is_alive(self) -> bool:
        return self._data.is_alive
    
    def add_component(self, component: EntityComponent):
        """Add a component to this entity."""
        if component.name in self._components:
            logger.warning(f"Component {component.name} already exists on {self.entity_id}")
            return
        
        self._components[component.name] = component
        self._component_order.append(component.name)
        component.on_attach(self)
        
        # Store entity reference in component for event handling
        setattr(component, '_entity_id', self.entity_id)
        
        logger.debug(f"Added component {component.name} to {self.entity_id}")
    
    def remove_component(self, component_name: str):
        """Remove a component from this entity."""
        if component_name not in self._components:
            return
        
        component = self._components.pop(component_name)
        self._component_order.remove(component_name)
        component.on_detach(self)
        
        logger.debug(f"Removed component {component_name} from {self.entity_id}")
    
    def get_component(self, component_name: str) -> Optional[EntityComponent]:
        """Get a component by name."""
        return self._components.get(component_name)
    
    def has_component(self, component_name: str) -> bool:
        """Check if entity has a component."""
        return component_name in self._components
    
    def update(self, delta_time: float):
        """Update all components."""
        for name in self._component_order:
            component = self._components[name]
            component.on_update(self, delta_time)
    
    def get_state(self) -> Dict[str, Any]:
        """Serialize entity state."""
        state = {
            'entity_id': self.entity_id,
            'entity_type': self.entity_type,
            'x': self.x,
            'y': self.y,
            'z': self.z,
            'health': self.health,
            'max_health': self.max_health,
            'is_alive': self.is_alive,
            'components': {}
        }
        
        for name, component in self._components.items():
            state['components'][name] = component.get_state()
        
        return state
    
    def set_state(self, state: Dict[str, Any]):
        """Deserialize entity state."""
        self._data.x = state.get('x', self._data.x)
        self._data.y = state.get('y', self._data.y)
        self._data.z = state.get('z', self._data.z)
        self._data.health = state.get('health', self._data.health)
        self._data.max_health = state.get('max_health', self._data.max_health)
        self._data.is_alive = state.get('is_alive', self._data.is_alive)
        
        components_state = state.get('components', {})
        for name, comp_state in components_state.items():
            if name in self._components:
                if hasattr(self._components[name], 'set_state'):
                    self._components[name].set_state(comp_state)
                elif hasattr(self._components[name], 'set_state_from_dict'):
                    self._components[name].set_state_from_dict(comp_state)


class EntityComponentsPlugin(GamePlugin):
    """
    Plugin that manages entity components system.
    
    Provides:
    - Component registration
    - Entity factory
    - Component updates
    """
    
    def __init__(self):
        self._component_registry: Dict[str, Type[EntityComponent]] = {}
        self._entities: Dict[str, GameEntity] = {}
        self._factory = EntityFactory(self)
        self.is_initialized = False
    
    @property
    def name(self) -> str:
        return "entity_components"
    
    def on_init(self):
        """Initialize the plugin."""
        # Register default components
        self.register_component(CombatComponent)
        self.register_component(StatsComponent)
        self.register_component(AIComponent)
        
        logger.info("EntityComponentsPlugin initialized")
    
    def on_update(self, delta_time: float):
        """Update all entities."""
        for entity in list(self._entities.values()):
            if entity.is_alive:
                entity.update(delta_time)
    
    def on_shutdown(self):
        """Clean up all entities."""
        self._entities.clear()
        logger.info("EntityComponentsPlugin shut down")
    
    def register_component(self, component_class: Type[EntityComponent]):
        """Register a component type."""
        instance = component_class()
        self._component_registry[instance.name] = component_class
        logger.debug(f"Registered component: {instance.name}")
    
    def create_entity(self, entity_data: EntityData, component_types: List[str]) -> GameEntity:
        """Create an entity with specified components."""
        entity = GameEntity(entity_data)
        
        for comp_type in component_types:
            if comp_type in self._component_registry:
                component = self._component_registry[comp_type]()
                entity.add_component(component)
            else:
                logger.warning(f"Unknown component type: {comp_type}")
        
        self._entities[entity_data.entity_id] = entity
        return entity
    
    def create_player(self, entity_id: str, **kwargs) -> GameEntity:
        """Create a player entity with standard components."""
        data = EntityData(
            entity_id=entity_id,
            entity_type='player',
            max_health=kwargs.get('max_health', 100.0),
        )
        return self.create_entity(data, ['combat', 'stats'])
    
    def create_enemy(self, entity_id: str, enemy_type: str = 'basic', **kwargs) -> GameEntity:
        """Create an enemy entity with standard components."""
        data = EntityData(
            entity_id=entity_id,
            entity_type='enemy',
            max_health=kwargs.get('max_health', 50.0),
        )
        data.metadata['enemy_type'] = enemy_type
        return self.create_entity(data, ['combat', 'ai'])
    
    def create_boss(self, entity_id: str, boss_type: str = 'major', **kwargs) -> GameEntity:
        """Create a boss entity with all components."""
        data = EntityData(
            entity_id=entity_id,
            entity_type='boss',
            max_health=kwargs.get('max_health', 500.0),
        )
        data.metadata['boss_type'] = boss_type
        return self.create_entity(data, ['combat', 'stats', 'ai'])
    
    def get_entity(self, entity_id: str) -> Optional[GameEntity]:
        """Get an entity by ID."""
        return self._entities.get(entity_id)
    
    def remove_entity(self, entity_id: str):
        """Remove an entity."""
        if entity_id in self._entities:
            del self._entities[entity_id]
            logger.debug(f"Removed entity {entity_id}")
    
    @property
    def factory(self) -> 'EntityFactory':
        return self._factory


class EntityFactory:
    """Factory for creating entities with predefined configurations."""
    
    def __init__(self, plugin: EntityComponentsPlugin):
        self._plugin = plugin
    
    def create_standard_player(self, entity_id: str) -> GameEntity:
        """Create a standard player character."""
        return self._plugin.create_player(
            entity_id=entity_id,
            max_health=100.0,
        )
    
    def create_basic_enemy(self, entity_id: str) -> GameEntity:
        """Create a basic enemy."""
        return self._plugin.create_enemy(
            entity_id=entity_id,
            enemy_type='basic',
            max_health=50.0,
        )
    
    def create_elite_enemy(self, entity_id: str) -> GameEntity:
        """Create an elite enemy."""
        entity = self._plugin.create_enemy(
            entity_id=entity_id,
            enemy_type='elite',
            max_health=150.0,
        )
        
        # Add stats component to elite
        if not entity.has_component('stats'):
            stats = StatsComponent()
            entity.add_component(stats)
        
        return entity
    
    def create_boss(self, entity_id: str, boss_name: str = "Major Boss") -> GameEntity:
        """Create a major boss."""
        return self._plugin.create_boss(
            entity_id=entity_id,
            boss_type='major',
            max_health=1000.0,
        )
