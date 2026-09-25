"""Юнит-тесты WorldPlan (src/gameplay/world.py) на синтетическом плане мира без Lua."""
import random

import pytest

from src.gameplay.world import DEFAULT_ACT, WorldPlan


ACT1 = {"id": "ash", "name": "Пепел", "levels": [1, 10], "biome": "ashlands",
        "enemies": ["imp", "wraith"], "elites": ["elite_imp"],
        "miniboss": "mini_boss", "boss": "act1_boss",
        "weather": ["clear", "rain"], "towns": [2, 6], "lore": ["line one", "line two"],
        "circles": {5: "Круг Тлена"}}
ACT2 = {"id": "frost", "name": "Мороз", "levels": [11, 20], "biome": "ice",
        "enemies": ["yeti"], "boss": "final_boss",
        "final_sequence": ["lucifer", "final_boss"]}
WORLD = {"max_level": 20, "acts": [ACT1, ACT2]}
BESTIARY = {"enemies": {"imp": {"loot": "basic"}, "elite_imp": {"loot": "elite"}},
            "attribute_weights": {}}
BOSSES = {"act1_boss": {"role": "boss"}, "mini_boss": {"role": "miniboss"},
          "final_boss": {"role": "final"}}


@pytest.fixture
def plan():
    return WorldPlan(WORLD, BESTIARY, BOSSES)


# ------------------------------------------------------------------ acts / info
class TestActsAndInfo:
    def test_act_for_ranges(self, plan):
        assert plan.act_for(1) is ACT1
        assert plan.act_for(10) is ACT1
        assert plan.act_for(11) is ACT2
        assert plan.act_for(20) is ACT2

    def test_act_for_gap_falls_back(self, plan):
        # уровень вне всех диапазонов: ниже первого -> acts[0], выше -> acts[-1]
        p = WorldPlan({"max_level": 30, "acts": [ACT1, ACT2]}, BESTIARY, BOSSES)
        assert p.act_for(15) is ACT2  # попадает в ACT2 по диапазону
        solo = WorldPlan({"max_level": 80, "acts": [{"id": "a", "name": "A", "levels": [10, 20]}]},
                         BESTIARY, {})
        assert solo.act_for(5)["id"] == "a"   # level<=1 fallback не срабатывает для >1? level=5 -> acts[0]
        assert solo.act_for(99)["id"] == "a"  # above -> acts[-1]

    def test_default_single_act_when_missing(self):
        p = WorldPlan({}, {}, {})
        assert p.max_level == 80
        assert p.acts == [DEFAULT_ACT]
        assert p.act_for(42) is DEFAULT_ACT

    def test_info_clamps_level(self, plan):
        assert plan.info(0).level == 1
        assert plan.info(999).level == 20

    def test_level_names_and_circles(self, plan):
        i1 = plan.info(1)
        assert i1.name == "Пепел, уровень 1"
        assert i1.biome == "ashlands"
        i5 = plan.info(5)
        assert i5.name.endswith("Круг Тлена")

    def test_towns_offsets(self, plan):
        # towns - смещения внутри акта: [2,6] -> уровни 2 и 6 (lo=1)
        assert plan.info(2).has_town and plan.info(6).has_town
        assert not plan.info(3).has_town

    def test_boss_on_last_level(self, plan):
        i10 = plan.info(10)
        assert i10.boss == "act1_boss" and i10.boss_role == "boss"

    def test_miniboss_at_lo_plus_4(self, plan):
        i5 = plan.info(5)
        assert i5.boss == "mini_boss" and i5.boss_role == "miniboss"

    def test_final_flags(self, plan):
        i20 = plan.info(20)
        assert i20.is_final and i20.boss == "final_boss" and i20.boss_role == "final"
        assert not plan.info(19).is_final


# ------------------------------------------------------------------ final_sequence
class TestFinalSequence:
    def test_non_final_returns_single_boss(self, plan):
        assert plan.final_sequence(10) == ["act1_boss"]

    def test_non_final_without_boss_empty(self, plan):
        assert plan.final_sequence(7) == []

    def test_final_uses_act_sequence(self, plan):
        assert plan.final_sequence(20) == ["lucifer", "final_boss"]


# ------------------------------------------------------------------ rank
class TestRank:
    def test_boss_roles(self, plan):
        assert plan.rank("act1_boss") == "boss"
        assert plan.rank("mini_boss") == "miniboss"

    def test_elite_by_loot_class(self, plan):
        assert plan.rank("elite_imp") == "elite"
        assert plan.rank("imp") == "normal"

    def test_unknown_is_normal(self, plan):
        assert plan.rank("nope") == "normal"


# ------------------------------------------------------------------ elite_chance / pick_enemy
class TestEnemyPick:
    def test_elite_chance_formula(self, plan):
        assert WorldPlan.elite_chance(1) == pytest.approx(0.02)
        assert WorldPlan.elite_chance(10) == pytest.approx(0.11)
        assert WorldPlan.elite_chance(29) == pytest.approx(0.30)
        assert WorldPlan.elite_chance(100) == pytest.approx(0.30)  # cap
        assert WorldPlan.elite_chance(0) == pytest.approx(0.02)    # max(0, ...)

    def test_pick_enemy_respects_force_chances(self, plan):
        assert plan.pick_enemy(1, random.Random(1), elite_chance=0.0) in ("imp", "wraith")
        assert plan.pick_enemy(1, random.Random(1), elite_chance=1.0) == "elite_imp"

    def test_no_elites_pool_falls_to_regular(self, plan):
        # ACT2 без elites: даже при шансе 1.0 роллятся обычные
        assert plan.pick_enemy(15, random.Random(1), elite_chance=1.0) == "yeti"

    def test_pick_enemy_deterministic(self, plan):
        a = plan.pick_enemy(3, random.Random(99))
        b = plan.pick_enemy(3, random.Random(99))
        assert a == b

    def test_empty_pools_default_basic(self):
        p = WorldPlan({"acts": [{"id": "x", "name": "X", "levels": [1, 5]}]}, {}, {})
        assert p.pick_enemy(1, random.Random(1), elite_chance=0.0) == "basic"


# ------------------------------------------------------------------ weather / lore / spec
class TestFlavor:
    def test_weather_choice_in_pool(self, plan):
        rng = random.Random(5)
        assert all(plan.weather_for(2, rng) in ("clear", "rain") for _ in range(20))

    def test_weather_defaults_clear(self):
        p = WorldPlan({"acts": [{"id": "x", "name": "X", "levels": [1, 5]}]}, {}, {})
        assert p.weather_for(1, random.Random(1)) == "clear"

    def test_lore_line(self, plan):
        rng = random.Random(5)
        assert plan.lore_line(2, rng) in ("line one", "line two")
        # акт без lore -> пустая строка
        assert plan.lore_line(15, rng) == ""

    def test_spec_lookups(self, plan):
        assert plan.spec("imp")["loot"] == "basic"
        assert plan.spec("act1_boss")["role"] == "boss"
        assert plan.spec("nobody") is None
