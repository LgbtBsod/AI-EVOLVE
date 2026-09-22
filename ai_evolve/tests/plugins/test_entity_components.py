"""
Tests for Entity Components Plugin
"""
import pytest
from ai_evolve.plugins.entity_components import (
    EntityData,
    GameEntity,
    CombatComponent,
    StatsComponent,
    AIComponent,
    EntityComponentsPlugin,
    EntityFactory,
)


class TestEntityData:
    """Test EntityData dataclass."""
    
    def test_create_minimal(self):
        data = EntityData(entity_id="test_1", entity_type="player")
        assert data.entity_id == "test_1"
        assert data.entity_type == "player"
        assert data.health == 100.0
        assert data.max_health == 100.0
        assert data.is_alive is True
    
    def test_create_with_values(self):
        data = EntityData(
            entity_id="boss_1",
            entity_type="boss",
            x=10.0,
            y=20.0,
            health=500.0,
            max_health=500.0,
        )
        assert data.x == 10.0
        assert data.y == 20.0
        assert data.health == 500.0


class TestCombatComponent:
    """Test CombatComponent."""
    
    def test_component_name(self):
        component = CombatComponent()
        assert component.name == "combat"
    
    def test_initial_values(self):
        component = CombatComponent()
        assert component.damage == 10.0
        assert component.attack_speed == 1.0
        assert component.critical_chance == 0.1
    
    def test_can_attack(self):
        component = CombatComponent()
        assert component.can_attack() is True
        
        component.is_attacking = True
        assert component.can_attack() is False
        
        component.is_attacking = False
        component.attack_cooldown = 1.0
        assert component.can_attack() is False
    
    def test_perform_attack(self):
        component = CombatComponent()
        result = component.perform_attack()
        
        assert result is True
        assert component.is_attacking is True
        assert component.attack_cooldown > 0
    
    def test_attack_cooldown_update(self):
        component = CombatComponent()
        component.attack_cooldown = 2.0
        
        component.on_update(None, 0.5)
        assert component.attack_cooldown == 1.5
        
        component.on_update(None, 0.5)
        assert component.attack_cooldown == 1.0
    
    def test_get_set_state(self):
        component = CombatComponent()
        component.damage = 25.0
        component.attack_speed = 2.0
        
        state = component.get_state()
        assert state['damage'] == 25.0
        assert state['attack_speed'] == 2.0
        
        component.set_state({'damage': 50.0})
        assert component.damage == 50.0


class TestStatsComponent:
    """Test StatsComponent."""
    
    def test_component_name(self):
        component = StatsComponent()
        assert component.name == "stats"
    
    def test_level_up(self):
        component = StatsComponent()
        initial_level = component.level
        
        component.level_up()
        
        assert component.level == initial_level + 1
        assert component.strength > 10
        assert component.experience_to_next_level > 100
    
    def test_add_experience_no_levelup(self):
        component = StatsComponent()
        result = component.add_experience(50)
        
        assert result is False
        assert component.experience == 50
        assert component.level == 1
    
    def test_add_experience_with_levelup(self):
        component = StatsComponent()
        component.experience = 90
        
        result = component.add_experience(20)
        
        assert result is True
        assert component.level == 2
    
    def test_get_set_state(self):
        component = StatsComponent()
        component.level = 5
        component.strength = 50
        
        state = component.get_state()
        assert state['level'] == 5
        assert state['strength'] == 50
        
        component.set_state({'level': 10})
        assert component.level == 10


class TestAIComponent:
    """Test AIComponent."""
    
    def test_component_name(self):
        component = AIComponent()
        assert component.name == "ai"
    
    def test_initial_state(self):
        component = AIComponent()
        assert component.state == "idle"
        assert component.enabled is True
    
    def test_patrol_movement(self):
        component = AIComponent()
        component.state = "patrol"
        component.patrol_points = [(10.0, 10.0), (20.0, 20.0)]
        
        entity_data = EntityData(entity_id="test", entity_type="enemy")
        entity = GameEntity(entity_data)
        entity.x = 0.0
        entity.y = 0.0
        
        # Update should move entity towards first patrol point
        component.on_update(entity, 0.5)
        
        assert entity.x > 0.0 or entity.y > 0.0


class TestGameEntity:
    """Test GameEntity composite class."""
    
    def test_create_entity(self):
        data = EntityData(entity_id="hero_1", entity_type="player")
        entity = GameEntity(data)
        
        assert entity.entity_id == "hero_1"
        assert entity.entity_type == "player"
        assert entity.is_alive is True
    
    def test_add_component(self):
        data = EntityData(entity_id="test", entity_type="player")
        entity = GameEntity(data)
        
        combat = CombatComponent()
        entity.add_component(combat)
        
        assert entity.has_component("combat")
        assert entity.get_component("combat") is combat
    
    def test_remove_component(self):
        data = EntityData(entity_id="test", entity_type="player")
        entity = GameEntity(data)
        
        combat = CombatComponent()
        entity.add_component(combat)
        entity.remove_component("combat")
        
        assert not entity.has_component("combat")
    
    def test_health_death_event(self):
        data = EntityData(entity_id="test", entity_type="player", health=100.0, max_health=100.0)
        entity = GameEntity(data)
        
        entity.health = 0
        
        assert entity.is_alive is False
    
    def test_update_components(self):
        data = EntityData(entity_id="test", entity_type="enemy")
        entity = GameEntity(data)
        
        ai = AIComponent()
        ai.state = "patrol"
        ai.patrol_points = [(10.0, 10.0)]
        entity.add_component(ai)
        
        initial_x = entity.x
        entity.update(0.5)
        
        # AI should have moved the entity
        assert entity.x != initial_x or entity.y != 0.0
    
    def test_get_set_state(self):
        data = EntityData(entity_id="test", entity_type="player")
        entity = GameEntity(data)
        
        combat = CombatComponent()
        combat.damage = 50.0
        entity.add_component(combat)
        
        state = entity.get_state()
        assert state['entity_id'] == "test"
        assert 'components' in state
        assert 'combat' in state['components']


class TestEntityComponentsPlugin:
    """Test EntityComponentsPlugin."""
    
    def test_plugin_name(self):
        plugin = EntityComponentsPlugin()
        assert plugin.name == "entity_components"
    
    def test_init_registers_components(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        assert "combat" in plugin._component_registry
        assert "stats" in plugin._component_registry
        assert "ai" in plugin._component_registry
    
    def test_create_player(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        player = plugin.create_player("player_1", max_health=150.0)
        
        assert player.entity_id == "player_1"
        assert player.entity_type == "player"
        assert player.max_health == 150.0
        assert player.has_component("combat")
        assert player.has_component("stats")
    
    def test_create_enemy(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        enemy = plugin.create_enemy("enemy_1", enemy_type="basic", max_health=75.0)
        
        assert enemy.entity_id == "enemy_1"
        assert enemy.entity_type == "enemy"
        assert enemy.max_health == 75.0
        assert enemy.has_component("combat")
        assert enemy.has_component("ai")
    
    def test_create_boss(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        boss = plugin.create_boss("boss_1", boss_type="major", max_health=1000.0)
        
        assert boss.entity_id == "boss_1"
        assert boss.entity_type == "boss"
        assert boss.max_health == 1000.0
        assert boss.has_component("combat")
        assert boss.has_component("stats")
        assert boss.has_component("ai")
    
    def test_update_entities(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        enemy = plugin.create_enemy("enemy_1")
        ai = enemy.get_component("ai")
        ai.state = "patrol"
        ai.patrol_points = [(10.0, 10.0)]
        
        initial_x = enemy.x
        plugin.on_update(0.5)
        
        # Entity should have been updated
        assert enemy.x != initial_x or enemy.y != 0.0
    
    def test_shutdown_clears_entities(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        plugin.create_player("player_1")
        plugin.create_enemy("enemy_1")
        
        plugin.on_shutdown()
        
        assert len(plugin._entities) == 0
    
    def test_factory_property(self):
        plugin = EntityComponentsPlugin()
        assert plugin.factory is not None
        assert isinstance(plugin.factory, EntityFactory)


class TestEntityFactory:
    """Test EntityFactory."""
    
    def test_create_standard_player(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        player = plugin.factory.create_standard_player("hero_1")
        
        assert player.entity_id == "hero_1"
        assert player.entity_type == "player"
        assert player.max_health == 100.0
    
    def test_create_basic_enemy(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        enemy = plugin.factory.create_basic_enemy("mob_1")
        
        assert enemy.entity_id == "mob_1"
        assert enemy.entity_type == "enemy"
        assert enemy.max_health == 50.0
    
    def test_create_elite_enemy(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        elite = plugin.factory.create_elite_enemy("elite_1")
        
        assert elite.entity_id == "elite_1"
        assert elite.max_health == 150.0
        assert elite.has_component("combat")
        assert elite.has_component("ai")
        assert elite.has_component("stats")  # Elite has stats
    
    def test_create_boss(self):
        plugin = EntityComponentsPlugin()
        plugin.on_init()
        
        boss = plugin.factory.create_boss("big_boss", "Dragon Lord")
        
        assert boss.entity_type == "boss"
        assert boss.max_health == 1000.0
