"""Юнит-тесты roll_loot (src/gameplay/loot.py) на синтетических таблицах."""
import random

from src.gameplay.inventory import Inventory
from src.gameplay.items import ItemCatalog, ItemDef
from src.gameplay.loot import enemy_drop, outfit, roll_loot


SWORD = ItemDef(id="sword", name="Sword", kind="equipment", slot="weapon",
                rarity="rare", stats={"attack_damage": 10})
POTION = ItemDef(id="hp1", name="Potion", kind="consumable")
CAT = ItemCatalog({"sword": SWORD, "hp1": POTION})


class Owner:
    pass


# ------------------------------------------------------------------ roll_loot
class TestRollLoot:
    def test_gold_within_bounds(self):
        rng = random.Random(42)
        gold, _ = roll_loot({"gold": [10, 20]}, rng, CAT)
        assert 10 <= gold <= 20

    def test_gold_deterministic_for_seed(self):
        t = {"gold": [10, 20], "rolls": 3, "drop_chance": 1.0, "kinds": ("equipment",)}
        g1, i1 = roll_loot(t, random.Random(7), CAT)
        g2, i2 = roll_loot(t, random.Random(7), CAT)
        assert g1 == g2 and [x.id for x in i1] == [x.id for x in i2]

    def test_empty_table_yields_nothing(self):
        gold, items = roll_loot({}, random.Random(1), CAT)
        assert gold == 0 and items == []

    def test_zero_drop_chance_no_items(self):
        gold, items = roll_loot({"gold": [5, 5], "rolls": 5, "drop_chance": 0.0},
                                random.Random(1), CAT)
        assert gold == 5 and items == []

    def test_full_drop_chance_rolls_all(self):
        _, items = roll_loot({"rolls": 4, "drop_chance": 1.0, "kinds": ("equipment",)},
                             random.Random(1), CAT)
        assert len(items) == 4 and all(it.kind == "equipment" for it in items)

    def test_default_kind_is_consumable(self):
        # kinds не задан -> каталог роллит только consumable
        _, items = roll_loot({"rolls": 3}, random.Random(1), CAT)
        assert [it.id for it in items] == ["hp1"] * 3

    def test_max_rarity_filters_pool(self):
        legendary = ItemDef(id="legend", name="L", kind="equipment", slot="weapon",
                            rarity="legendary")
        cat = ItemCatalog({"common_s": ItemDef(id="common_s", name="C", kind="equipment",
                                               slot="weapon", rarity="common"),
                           "legend": legendary})
        _, items = roll_loot({"rolls": 10, "kinds": ("equipment",), "max_rarity": "rare"},
                             random.Random(3), cat)
        assert items and all(it.rarity in ("common", "rare") for it in items)

    def test_zero_gold_range_skips_roll(self):
        # hi == 0 -> золото не катается вообще (даже если lo отрицательное)
        gold, _ = roll_loot({"gold": [-5, 0]}, random.Random(1), CAT)
        assert gold == 0

    def test_missing_pool_returns_no_items(self):
        empty_cat = ItemCatalog({})
        _, items = roll_loot({"rolls": 3, "kinds": ("equipment",)}, random.Random(1), empty_cat)
        assert items == []

    def test_none_golds_falsy_handled(self):
        gold, _ = roll_loot({"gold": None, "rolls": None}, random.Random(1), CAT)
        assert gold == 0


# ------------------------------------------------------------------ outfit / enemy_drop
class TestOutfitAndDrop:
    def test_outfit_carries_and_equips(self, monkeypatch):
        import src.gameplay.loot as loot_mod
        table = {"goblin": {
            "carries": ["hp1", "missing_item"],
            "equip": {"weapon": ["nope", "sword"]},
        }}
        monkeypatch.setattr(loot_mod, "loot_tables", lambda: {"enemies": table})
        inv = Inventory(owner=Owner())
        outfit(inv, "goblin", random.Random(1), CAT)
        assert inv.count("hp1") == 1          # unknown id пропущен
        assert inv.equipped.get("weapon") is SWORD

    def test_outfit_unknown_enemy_noop(self, monkeypatch):
        import src.gameplay.loot as loot_mod
        monkeypatch.setattr(loot_mod, "loot_tables", lambda: {"enemies": {}})
        inv = Inventory(owner=Owner())
        outfit(inv, "nobody", random.Random(1), CAT)
        assert inv.bag == [] and inv.equipped == {}

    def test_enemy_drop_adds_inventory_contents(self, monkeypatch):
        import src.gameplay.loot as loot_mod
        table = {"goblin": {"gold": [5, 5], "rolls": 0}}
        monkeypatch.setattr(loot_mod, "loot_tables", lambda: {"enemies": table})
        inv = Inventory(owner=Owner(), gold=100)
        sword2 = ItemDef(id="sword", name="Sword", kind="equipment", slot="weapon",
                         rarity="rare", stats={"attack_damage": 10})
        inv.add(sword2)
        gold, items = enemy_drop(inv, "goblin", random.Random(1))
        assert gold == 105
        assert [it.id for it in items] == ["sword"]
        assert inv.bag == []  # всё выпало

    def test_enemy_drop_unknown_type_only_loots_bag(self, monkeypatch):
        import src.gameplay.loot as loot_mod
        monkeypatch.setattr(loot_mod, "loot_tables", lambda: {})
        inv = Inventory(owner=Owner(), gold=7)
        gold, items = enemy_drop(inv, "ghost", random.Random(1))
        assert gold == 7 and items == []
