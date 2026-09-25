"""Юнит-тесты предметов и каталога (src/gameplay/items.py).

Покрывает: ItemDef (свойства equippable/usable/restores), парсинг из Lua-словаря
(from_lua), конструктор каталога (get/by_kind/len/contains) и взвешенный ролл
редкости 8/3/1/0.3 с фильтрами kinds/min_rarity/max_rarity.
"""
import random

import pytest

from src.gameplay.items import (
    EQUIP_SLOTS,
    ItemCatalog,
    ItemDef,
    RARITY_ORDER,
    _items_from,
)


def make_item(**kw):
    base = dict(id="i", name="Item")
    base.update(kw)
    return ItemDef(**base)


@pytest.fixture()
def catalog():
    items = {
        "sword": make_item(id="sword", name="Sword", kind="equipment", slot="weapon", rarity="common"),
        "ring_rare": make_item(id="ring_rare", name="Rare Ring", kind="equipment", slot="ring", rarity="rare"),
        "amulet_epic": make_item(id="amulet_epic", name="Epic Amulet", kind="equipment", slot="amulet", rarity="epic"),
        "legend_art": make_item(id="legend_art", name="Legend Artifact", kind="artifact", slot="trinket", rarity="legendary"),
        "potion": make_item(id="potion", name="Potion", kind="consumable", rarity="common"),
        "map1": make_item(id="map1", name="Map", kind="map", rarity="common"),
        "mat": make_item(id="mat", name="Ore", kind="material", rarity="common"),
    }
    return ItemCatalog(items)


class TestItemDefProperties:
    def test_defaults(self):
        it = make_item()
        assert it.kind == "equipment"
        assert it.rarity == "common"
        assert it.value == 10
        assert it.stats == {}
        assert it.effects == ()
        assert it.slot is None

    def test_equippable(self):
        assert make_item(kind="equipment", slot="weapon").equippable is True
        assert make_item(kind="artifact", slot="ring").equippable is True
        # артефакт без валидного слота не экипируется
        assert make_item(kind="artifact", slot=None).equippable is False
        assert make_item(kind="artifact", slot="bogus").equippable is False
        assert make_item(kind="consumable", slot="weapon").equippable is False
        assert make_item(kind="equipment", slot=None).equippable is False

    def test_usable(self):
        assert make_item(kind="consumable").usable is True
        assert make_item(kind="equipment").usable is False

    def test_restores_only_use_self_heals(self):
        potion = make_item(
            kind="consumable",
            effects=(
                {"trigger": {"event": "use"}, "ops": [
                    {"kind": "heal", "stat": "hp"},
                    {"kind": "heal", "target": "self", "stat": "mana"},
                    {"kind": "heal", "target": "ally", "stat": "stamina"},
                ]},
                {"trigger": {"event": "on_hit"}, "ops": [{"kind": "heal", "stat": "hp"}]},
            ),
        )
        # ally-цель и триггер не-use не учитываются; heal без stat -> hp
        assert potion.restores() == {"hp", "mana"}

    def test_restores_empty_for_plain_item(self):
        assert make_item().restores() == set()

    def test_frozen_dataclass(self):
        it = make_item()
        with pytest.raises(Exception):
            it.name = "changed"


class TestFromLua:
    def test_full_dict(self):
        raw = {
            "id": "doom_blade", "name": "Doom Blade", "kind": "equipment", "slot": "weapon",
            "rarity": "epic", "value": 250, "stats": {"attack_damage": 20, "aspd": 0.1},
            "effects": [{"trigger": {"event": "use"}}], "knowledge": {"maps": ["crypt"]},
            "description": "Cursed blade", "attack": "sword_swing",
        }
        it = ItemDef.from_lua(raw)
        assert it.id == "doom_blade"
        assert it.rarity == "epic"
        assert it.value == 250
        assert it.stats == {"attack_damage": 20.0, "aspd": 0.1}
        assert all(isinstance(v, float) for v in it.stats.values())
        assert it.effects == ({"trigger": {"event": "use"}},)
        assert it.knowledge == {"maps": ["crypt"]}
        assert it.attack == "sword_swing"

    def test_minimal_dict_id_falls_back_to_name(self):
        it = ItemDef.from_lua({"name": "Healing Potion"})
        assert it.id == "Healing Potion"
        assert it.name == "Healing Potion"

    def test_kind_inferred_from_effects(self):
        # эффекты/статы есть -> equipment; слот по умолчанию amulet
        it = ItemDef.from_lua({"id": "x", "stats": {"defense": 5}})
        assert it.kind == "equipment"
        assert it.slot == "amulet"

    def test_kind_material_when_no_stats(self):
        it = ItemDef.from_lua({"id": "ore", "name": "Ore"})
        assert it.kind == "material"
        assert it.slot is None

    def test_empty_knowledge_becomes_none(self):
        it = ItemDef.from_lua({"id": "a", "knowledge": {}})
        assert it.knowledge is None


class TestItemsFrom:
    def test_items_list_passthrough(self):
        data = {"items": [{"id": "a"}, {"id": "b"}]}
        assert _items_from(data) == [{"id": "a"}, {"id": "b"}]

    def test_single_item_gets_slug_id(self):
        data = {"name": "Sorrow of Berserk", "effects": [{}]}
        out = _items_from(data)
        assert len(out) == 1
        assert out[0]["id"] == "sorrow_of_berserk"

    def test_single_item_keeps_explicit_id(self):
        data = {"id": "explicit", "name": "X"}
        assert _items_from(data)[0]["id"] == "explicit"

    def test_garbage_returns_empty(self):
        assert _items_from([]) == []
        assert _items_from({}) == []
        assert _items_from({"unrelated": 1}) == []


class TestCatalogBasics:
    def test_len_and_contains(self, catalog):
        assert len(catalog) == 7
        assert "sword" in catalog
        assert "nonexistent" not in catalog

    def test_get(self, catalog):
        assert catalog.get("sword").name == "Sword"
        assert catalog.get("nonexistent") is None

    def test_by_kind(self, catalog):
        assert {it.id for it in catalog.by_kind("consumable")} == {"potion"}
        assert {it.id for it in catalog.by_kind("equipment", "artifact")} == {
            "sword", "ring_rare", "amulet_epic", "legend_art"
        }
        assert catalog.by_kind("nothing") == []


class TestCatalogRoll:
    def test_respects_kind_filter(self, catalog):
        rng = random.Random(42)
        for _ in range(50):
            it = catalog.roll(rng, kinds=("consumable",))
            assert it.id == "potion"

    def test_empty_pool_returns_none(self, catalog):
        assert catalog.roll(random.Random(0), kinds=("nonexistent_kind",)) is None

    def test_rarity_window_filters(self, catalog):
        rng = random.Random(1)
        for _ in range(50):
            it = catalog.roll(rng, min_rarity="rare", max_rarity="epic")
            assert it.id in {"ring_rare", "amulet_epic"}

    def test_unknown_rarity_treated_as_common(self):
        weird = ItemCatalog({"w": make_item(id="w", rarity="weird")})
        # неизвестная редкость => вес как у common, окно common..common её ловит
        assert weird.roll(random.Random(0), min_rarity="common", max_rarity="common").id == "w"

    def test_weighted_distribution_matches_8_3_1_03(self, catalog):
        # default kinds = (equipment, consumable, artifact, map) -> mat (material) НЕ в пуле;
        # пул: common(sword,potion,map1)=3 шт * 8, rare=3, epic=1, legendary=0.3
        rng = random.Random(7)
        counts = {"common": 0, "rare": 0, "epic": 0, "legendary": 0}
        n = 200000
        for _ in range(n):
            it = catalog.roll(rng)
            counts[it.rarity] += 1
        # ожидаемые доли: total weight = 3*8 + 3 + 1 + 0.3 = 28.3
        expected = {
            "common": 24 / 28.3,
            "rare": 3 / 28.3,
            "epic": 1 / 28.3,
            "legendary": 0.3 / 28.3,
        }
        for rarity, share in expected.items():
            actual = counts[rarity] / n
            assert abs(actual - share) < 0.01, f"{rarity}: {actual} vs {share}"

    def test_material_excluded_from_default_roll(self, catalog):
        rng = random.Random(11)
        ids = {catalog.roll(rng).id for _ in range(500)}
        assert "mat" not in ids and len(ids) == 6  # все кроме material

    def test_roll_is_deterministic_per_seed(self, catalog):
        a = [catalog.roll(random.Random(5)) for _ in range(1)]
        b = [catalog.roll(random.Random(5)) for _ in range(1)]
        assert a[0].id == b[0].id

    def test_rarity_order_constant(self):
        assert RARITY_ORDER == {"common": 0, "rare": 1, "epic": 2, "legendary": 3}
        assert EQUIP_SLOTS == ("weapon", "armor", "amulet", "ring", "trinket")
