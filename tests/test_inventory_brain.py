"""Юнит-тесты Inventory / InventoryBrain / item_power (src/gameplay/inventory.py)."""
import pytest

from src.gameplay.inventory import (
    EFFECT_VALUE,
    STAT_WEIGHTS,
    Inventory,
    InventoryBrain,
    item_power,
)
from src.gameplay.items import ItemDef


# ------------------------------------------------------------------ фикстуры
def make_potion(pid="hp1", rarity="common", stat="hp"):
    return ItemDef(
        id=pid, name=f"Potion {pid}", kind="consumable", rarity=rarity,
        effects=({"trigger": {"event": "use"}, "ops": [{"kind": "heal", "target": "self", "stat": stat}]},),
    )


def make_sword(pid="sword", rarity="rare", ad=10.0):
    return ItemDef(id=pid, name=f"Sword {pid}", kind="equipment", slot="weapon",
                   rarity=rarity, stats={"attack_damage": ad})


class Owner:
    def __init__(self, health=30, max_health=100, mana=None, max_mana=None,
                 stamina=None, max_stamina=None):
        self.health = health
        self.max_health = max_health
        if mana is not None:
            self.mana = mana
        if max_mana is not None:
            self.max_mana = max_mana
        if stamina is not None:
            self.stamina = stamina
        if max_stamina is not None:
            self.max_stamina = max_stamina


@pytest.fixture
def inv():
    return Inventory(owner=Owner())


# ------------------------------------------------------------------ item_power
class TestItemPower:
    def test_none_is_zero(self):
        assert item_power(None) == 0.0

    def test_stats_by_role_weights(self):
        sword = make_sword()
        assert item_power(sword, "warrior") == pytest.approx(3.0 * 10)
        # роль без веса для стата -> дефолтный вес 0.5
        assert item_power(sword, "mage") == pytest.approx(0.5 * 10)
        # неизвестная роль -> warrior
        assert item_power(sword, "paladin") == item_power(sword, "warrior")

    def test_effects_bonus_capped_at_three(self):
        ef = {"trigger": {"event": "on_hit"}, "ops": []}
        it = ItemDef(id="x", name="X", rarity="epic", effects=(ef,) * 5)
        assert item_power(it, "warrior") == pytest.approx(EFFECT_VALUE["epic"] * 3)

    def test_unknown_rarity_effect_value_defaults_to_common(self):
        it = ItemDef(id="x", name="X", rarity="mythic", effects=({"ops": []},))
        assert item_power(it) == pytest.approx(6.0)

    def test_knowledge_bonus(self):
        map_item = ItemDef(id="m", name="Map", kind="map", knowledge={"area": "north"})
        assert item_power(map_item) == pytest.approx(10.0)

    def test_stat_weights_roles_present(self):
        for role in ("warrior", "mage", "rogue", "monster"):
            assert role in STAT_WEIGHTS and STAT_WEIGHTS[role]


# ------------------------------------------------------------------ Inventory
class TestInventoryBasics:
    def test_defaults(self, inv):
        assert inv.capacity == 16 and inv.gold == 0
        assert inv.bag == [] and inv.equipped == {} and inv.log == []

    def test_add_and_count(self, inv):
        p = make_potion()
        assert inv.add(p) is True
        assert inv.count("hp1") == 1
        assert inv.count("nope") == 0

    def test_capacity_blocks_add(self):
        inv = Inventory(owner=Owner(), capacity=2)
        assert inv.add(make_potion("a")) and inv.add(make_potion("b"))
        assert inv.add(make_potion("c")) is False

    def test_remove(self, inv):
        p = make_potion()
        inv.add(p)
        assert inv.remove(p) is True
        assert inv.remove(p) is False

    def test_equip_requires_in_bag_and_equippable(self, inv):
        sword = make_sword()
        assert inv.equip(sword) is None  # не в сумке
        inv.add(sword)
        potion = make_potion()
        inv.add(potion)
        assert inv.equip(potion) is None  # не экипируется
        assert inv.equip(sword) is None   # снятого нет -> None как old
        assert inv.equipped["weapon"] is sword
        assert sword not in inv.bag

    def test_equip_swaps_old_into_bag(self, inv):
        s1, s2 = make_sword("s1"), make_sword("s2")
        inv.add(s1); inv.add(s2)
        old = inv.equip(s1)
        assert old is None
        old = inv.equip(s2)
        assert old is s1
        assert s1 in inv.bag and inv.equipped["weapon"] is s2
        assert any("вместо" in line for line in inv.log)

    def test_unequip(self, inv):
        s = make_sword()
        inv.add(s); inv.equip(s)
        out = inv.unequip("weapon")
        assert out is s and s in inv.bag and "weapon" not in inv.equipped
        assert inv.unequip("weapon") is None

    def test_drop_all_clears_everything(self, inv):
        s, p = make_sword(), make_potion()
        inv.add(s); inv.equip(s); inv.add(p)
        dropped = inv.drop_all()
        assert {it.id for it in dropped} == {"sword", "hp1"}  # ItemDef не хешируется (dict-поля)
        assert inv.bag == [] and inv.equipped == {}

    def test_all_items_includes_equipped(self, inv):
        s, p = make_sword(), make_potion()
        inv.add(s); inv.equip(s); inv.add(p)
        assert inv.all_items() == [s, p]

    def test_on_change_callback_fires(self, inv):
        calls = []
        inv.on_change = lambda i: calls.append(i)
        s = make_sword()
        inv.add(s); inv.equip(s)
        assert calls == [inv]
        inv.unequip("weapon")
        assert len(calls) == 2

    def test_summary(self, inv):
        inv.gold = 99
        s = make_sword()
        inv.add(s); inv.equip(s)
        summ = inv.summary()
        assert summ["gold"] == 99
        assert summ["equipped"] == {"weapon": "Sword sword"}
        assert summ["bag"] == []


# ------------------------------------------------------------------ InventoryBrain
class TestInventoryBrainPotions:
    def test_drinks_hp_potion_below_threshold(self, inv):
        potion = make_potion()
        inv.add(potion)
        used = []
        brain = InventoryBrain(inv, heal_at=0.35)
        assert brain.update(0.1, lambda it: used.append(it) or True) == "potion:hp"
        assert used == [potion]
        assert potion not in inv.bag
        assert any("выпил" in line for line in inv.log)

    def test_no_potion_when_hp_above_threshold(self, inv):
        inv.owner.health = 80
        inv.add(make_potion())
        brain = InventoryBrain(inv, heal_at=0.35)
        assert brain.update(0.1, lambda it: True) != "potion:hp"

    def test_potion_cooldown_blocks_next_drink(self, inv):
        inv.add(make_potion("weak")); inv.add(make_potion("strong", rarity="epic"))
        brain = InventoryBrain(inv, potion_cooldown=3.0)
        assert brain.update(0.1, lambda it: True) == "potion:hp"
        # сразу после зелья - пить нельзя (таймер кулдауна активен)
        assert brain.update(0.1, lambda it: True) is None or \
            not brain.update(0.1, lambda it: True).startswith("potion")

    def test_prefers_weakest_potion(self, inv):
        strong = make_potion("big", rarity="legendary")
        weak = make_potion("small", rarity="common")
        inv.add(strong); inv.add(weak)
        used = []
        brain = InventoryBrain(inv)
        brain.update(0.1, lambda it: used.append(it) or True)
        assert used == [weak]  # большое зелье - на чёрный день

    def test_use_item_failure_keeps_potion(self, inv):
        potion = make_potion()
        inv.add(potion)
        brain = InventoryBrain(inv)
        assert brain.update(0.1, lambda it: False) is None
        assert potion in inv.bag

    def test_mana_potion_when_mana_low(self, inv):
        inv.owner = Owner(health=100, max_health=100, mana=5, max_mana=50)
        mp = make_potion("mp", stat="mana")
        inv.add(mp)
        brain = InventoryBrain(inv, resource_at=0.2)
        assert brain.update(0.1, lambda it: True) == "potion:mana"

    def test_stamina_potion(self, inv):
        inv.owner = Owner(health=100, max_health=100, stamina=1, max_stamina=40)
        sp = make_potion("sp", stat="stamina")
        inv.add(sp)
        brain = InventoryBrain(inv, resource_at=0.2)
        assert brain.update(0.1, lambda it: True) == "potion:stamina"

    def test_smoke_bomb_when_no_potions(self, inv):
        inv.owner.health = 10  # ниже порога, но зелий нет
        bomb = ItemDef(id="bomb", name="Smoke", kind="consumable",
                       effects=({"trigger": {"event": "use"},
                                 "ops": [{"kind": "mod", "toward": "source"}]},))
        inv.add(bomb)
        used = []
        brain = InventoryBrain(inv)
        assert brain.update(0.1, lambda it: used.append(it) or True) == "stealth"
        assert used == [bomb]


class TestInventoryBrainMapsAndEquips:
    def test_reads_map_and_calls_learn(self, inv):
        inv.owner.health = 100  # не мешают зелья
        m = ItemDef(id="map1", name="Map of North", kind="map", knowledge={"area": "north"})
        inv.add(m)
        learned = []
        brain = InventoryBrain(inv)
        assert brain.update(0.1, lambda it: True, learn=learned.append) == "read:map1"
        assert learned == [m] and m not in inv.bag
        assert any("прочитал" in line for line in inv.log)

    def test_equip_upgrade_after_interval(self, inv):
        inv.owner.health = 100
        sword = make_sword()
        inv.add(sword)
        brain = InventoryBrain(inv, equip_interval=2.0)
        # первый вызов: таймер стартует с 0 -> апгрейд возможен сразу
        assert brain.update(0.1, lambda it: True) == "equip:sword"
        assert inv.equipped.get("weapon") is sword

    def test_equip_respects_gain_threshold(self, inv):
        inv.owner.health = 100
        tiny = make_sword("tiny", ad=0.1)  # power 0.3 < gain threshold 0.5
        inv.add(tiny)
        brain = InventoryBrain(inv)
        assert brain.update(0.1, lambda it: True) is None
        assert inv.equipped == {}

    def test_no_double_equip_of_worse_item(self, inv):
        inv.owner.health = 100
        good = make_sword("good", ad=10)
        bad = make_sword("bad", ad=1)
        inv.add(good); inv.add(bad)
        brain = InventoryBrain(inv, equip_interval=0.0)
        first = brain.update(0.0, lambda it: True)
        second = brain.update(0.0, lambda it: True)
        assert first == "equip:good"
        assert second is None  # bad слабее good + порога 0.5

    def test_artifact_triggers_learn_on_equip(self, inv):
        inv.owner.health = 100
        art = ItemDef(id="art", name="Artifact", kind="artifact", slot="amulet",
                      rarity="legendary", stats={"attack_damage": 20}, knowledge={"lore": "old"})
        inv.add(art)
        learned = []
        brain = InventoryBrain(inv)
        assert brain.update(0.1, lambda it: True, learn=learned.append) == "equip:art"
        assert learned == [art]

    def test_best_upgrade_skips_non_equip_slots(self, inv):
        odd = ItemDef(id="odd", name="Odd", kind="equipment", slot="boots",
                      stats={"attack_damage": 50})
        inv.add(odd)
        brain = InventoryBrain(inv)
        assert brain.best_upgrade() is None
