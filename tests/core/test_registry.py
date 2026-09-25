"""Тесты Registry System — расширяемости движка без правки ядра."""

import pytest

from src.core.registry import (
    CORE_DOMAINS,
    DuplicateEntryError,
    FrozenRegistryError,
    Registry,
    RegistryError,
    RegistrySet,
    default_registries,
)


class TestRegistry:
    def test_register_get_roundtrip(self):
        reg = Registry("conditions")
        fn = lambda e, ctx: True
        reg.register("is_night", fn)
        assert reg.get("is_night") is fn
        assert "is_night" in reg and len(reg) == 1
        assert reg.names() == ["is_night"]

    def test_unknown_name_raises_with_hint(self):
        reg = Registry("statuses")
        with pytest.raises(RegistryError, match="not registered"):
            reg.get("burning")

    def test_get_or_default_never_raises(self):
        reg = Registry("selectors")
        assert reg.get_or_default("missing", "fallback") == "fallback"

    def test_duplicate_policies(self):
        r1 = Registry("effects", duplicate_policy="error")
        r1.register("e", 1)
        with pytest.raises(DuplicateEntryError):
            r1.register("e", 2)

        r2 = Registry("effects", duplicate_policy="skip")
        r2.register("e", 1)
        assert r2.register("e", 2) == 1 and r2.get("e") == 1

        r3 = Registry("effects", duplicate_policy="override")
        r3.register("e", 1)
        assert r3.register("e", 2) == 2 and r3.get("e") == 2

    def test_bad_name_rejected(self):
        reg = Registry("flags")
        with pytest.raises(RegistryError):
            reg.register("", 1)
        with pytest.raises(RegistryError):
            reg.register(None, 1)

    def test_freeze_blocks_writes_allows_reads(self):
        reg = Registry("abilities")
        reg.register("rasengan", {"dmg": 50})
        reg.freeze()
        assert reg.frozen
        with pytest.raises(FrozenRegistryError):
            reg.register("new_move", {})
        with pytest.raises(FrozenRegistryError):
            reg.unregister("rasengan")
        assert reg.get("rasengan") == {"dmg": 50}   # чтение доступно


class TestRegistrySet:
    def test_core_domains_present(self):
        rs = RegistrySet()
        for d in CORE_DOMAINS:
            assert d in rs
        assert set(rs.domains()) >= set(CORE_DOMAINS)

    def test_shorthand_register_get(self):
        rs = RegistrySet()
        fn = lambda: 42
        rs.register("scales", "per_stack", fn)
        assert rs.get("scales", "per_stack") is fn
        assert rs["scales"]["per_stack"] is fn

    def test_custom_domain_creation_idempotent(self):
        rs = RegistrySet()
        a = rs.create_domain("souls")
        b = rs.create_domain("souls")
        assert a is b

    def test_unknown_domain_raises(self):
        rs = RegistrySet()
        with pytest.raises(RegistryError, match="unknown registry domain"):
            rs.domain("nope")

    def test_freeze_all(self):
        rs = RegistrySet()
        rs.freeze_all()
        for name in rs.domains():
            assert rs[name].frozen


class TestDefaults:
    def test_layers_registered_with_priority(self):
        rs = default_registries()
        assert rs["layers"].get("effect")["priority"] < rs["layers"].get("rules")["priority"]
        assert rs["layers"].get("narrative")["priority"] == max(
            d["priority"] for _, d in rs["layers"].items())

    def test_damage_types_resist_flags(self):
        rs = default_registries()
        assert rs["damage_types"].get("physical")["resistible"] is True
        assert rs["damage_types"].get("true")["resistible"] is False
        assert rs["damage_types"].get("existential")["resistible"] is False

    def test_conditions_always_and_scales(self):
        rs = default_registries()
        assert rs["conditions"].get("always")() is True
        assert rs["scales"].get("flat")(3, factor=2) == 6
        assert rs["scales"].get("none")(999) == 0.0

    def test_bypass_flags_known(self):
        rs = default_registries()
        assert "bypass_infinity" in rs["flags"]
        assert "true_damage" in rs["flags"]

    def test_content_extends_without_core_edits(self):
        """Главное правило: персонаж добавляет записи, а не поля ядра."""
        rs = default_registries(duplicate_policy="override")
        rs["conditions"].register("hp_below_half",
                                  lambda ent, ctx: ent["hp"] < ent["max_hp"] * 0.5)
        cond = rs["conditions"].get("hp_below_half")
        assert cond({"hp": 30, "max_hp": 100}, {}) is True
        assert cond({"hp": 60, "max_hp": 100}, {}) is False
