"""Модульные тесты для src/entities/base_entity.py - базовая игровая сущность."""
from enum import Enum

import pytest

from src.entities.base_entity import BaseEntity, EntityState


class EntityType(Enum):
    HERO = "hero"
    ENEMY = "enemy"


@pytest.fixture()
def entity():
    e = BaseEntity("e1", EntityType.HERO, name="Герой")
    e.initialize()
    return e


class TestConstruction:
    def test_defaults(self):
        e = BaseEntity("x1", EntityType.ENEMY)
        assert e.entity_id == "x1"
        assert e.name == "x1"          # имя по умолчанию = id
        assert e.state == EntityState.INACTIVE
        assert e.position == [0.0, 0.0, 0.0]
        assert e.health == e.max_health == 100.0
        assert e.components == {}

    def test_explicit_name_kept(self, entity):
        assert entity.name == "Герой"


class TestLifecycle:
    def test_initialize_sets_alive(self):
        e = BaseEntity("x2", EntityType.ENEMY)
        assert e.initialize() is True
        assert e.state == EntityState.ALIVE
        assert e.is_alive is True

    def test_update_noop_when_not_alive(self):
        e = BaseEntity("x3", EntityType.ENEMY)  # INACTIVE
        e.update(0.1)  # не должна упасть
        assert e.state == EntityState.INACTIVE

    def test_die(self, entity):
        entity.die()
        assert entity.state == EntityState.DEAD
        assert entity.is_alive is False

    def test_respawn_restores_full_hp_and_position(self, entity):
        entity.take_damage(80)
        assert entity.respawn(1.0, 2.0, 3.0) is True
        assert entity.position == [1.0, 2.0, 3.0]
        assert entity.health == entity.max_health
        assert entity.state == EntityState.ALIVE
        assert entity.is_alive is True

    def test_destroy_clears_components(self, entity):
        entity.add_component("ai", {"mode": "hunt"})
        assert entity.destroy() is True
        assert entity.components == {}
        assert entity.state == EntityState.INACTIVE


class TestCombatMath:
    def test_take_damage_returns_actual_and_applies(self, entity):
        assert entity.take_damage(30) == 30
        assert entity.health == 70.0

    def test_negative_damage_clamped_to_zero(self, entity):
        assert entity.take_damage(-50) == 0
        assert entity.health == 100.0

    def test_lethal_damage_kills(self, entity):
        entity.take_damage(1000)
        assert entity.health == 0
        assert entity.state == EntityState.DEAD
        assert entity.is_alive is False

    def test_damage_on_dead_ignored(self, entity):
        entity.die()
        assert entity.take_damage(10) == 0.0

    def test_heal_capped_at_max(self, entity):
        entity.take_damage(40)
        assert entity.heal(200) == 40.0   # фактическое лечение ограничено потолком
        assert entity.health == 100.0

    def test_heal_on_dead_ignored(self, entity):
        entity.die()
        assert entity.heal(50) == 0.0


class TestComponents:
    def test_add_get_remove(self, entity):
        comp = {"hp": 10}
        assert entity.add_component("stats", comp) is True
        assert entity.get_component("stats") is comp
        assert entity.remove_component("stats") is True
        assert entity.get_component("stats") is None

    def test_remove_missing_returns_false(self, entity):
        assert entity.remove_component("nope") is False


class TestSerialization:
    def test_to_dict_fields(self, entity):
        entity.position[0] = 5.0
        d = entity.to_dict()
        assert d["entity_id"] == "e1"
        assert d["entity_type"] == "hero"           # .value у Enum
        assert d["state"] == "alive"
        assert d["health"] == 100.0
        assert d["components"] == []
        # копия позиции: изменение словаря не трогает сущность
        d["position"][0] = 99.0
        assert entity.position[0] == 5.0

    def test_roundtrip(self, entity):
        entity.take_damage(25)
        entity.position = [7.0, 8.0, 9.0]
        data = entity.to_dict()
        restored = BaseEntity.from_dict(data)
        assert restored.entity_id == entity.entity_id
        assert restored.health == entity.health == 75.0
        assert restored.position == [7.0, 8.0, 9.0]
        assert restored.state == entity.state
        assert restored.is_alive is True

    def test_from_dict_defaults_for_missing_keys(self):
        e = BaseEntity.from_dict({"entity_id": "z", "entity_type": "enemy"})
        assert e.health == 100.0
        assert e.state == EntityState.INACTIVE  # default 'inactive'

    def test_to_dict_with_plain_string_type(self):
        e = BaseEntity("s1", "plain_type")
        assert e.to_dict()["entity_type"] == "plain_type"


class TestRepr:
    def test_str_contains_id_and_hp(self, entity):
        s = str(entity)
        assert "e1" in s and "100.0/100.0" in s
        assert repr(entity) == s
