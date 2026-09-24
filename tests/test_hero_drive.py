"""Эмоция и подсказки игрока сдвигают интерес героя, но не приказывают."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.gameplay.hero_drive import HeroDrive, Option, player_keys  # noqa: E402

HERE = (0.0, 0.0)


def opts(enemy_d=6.0):
    return [Option("fight", (enemy_d, 0.0), max(0.2, 1.0 - enemy_d / 15.0)),
            Option("loot", (0.0, 12.0), 0.3 + 0.7 * (1 - 12 / 30)),
            Option("exit", (-20.0, 0.0), 1.0),
            Option("explore", None, 1.0)]


def test_emotion_shifts_the_choice():
    d = HeroDrive()
    assert d.choose(opts(), HERE, 0.0).goal == "fight"
    d = HeroDrive("fear")
    assert d.choose(opts(), HERE, 0.0).goal == "exit" and d.retreat_hp > HeroDrive().retreat_hp
    d = HeroDrive("greed")
    assert d.choose(opts(enemy_d=11.0), HERE, 0.0).goal == "loot"
    assert HeroDrive("rage").press_bias > 0 and HeroDrive("rage").heal_at < HeroDrive().heal_at


def test_directive_is_interest_not_an_order_and_fades():
    d = HeroDrive()
    d.set_directive("north", 0.0)
    assert d.choose(opts(enemy_d=2.0), HERE, 0.0).goal == "fight"          # враг вплотную важнее
    north = [Option("hint", (0.0, 12.0), 1.0), Option("exit", (0.0, -20.0), 1.0), Option("explore", None, 1.0)]
    assert HeroDrive().choose(north, HERE, 0.0).goal == "exit"             # без подсказки - к выходу
    assert d.choose(north, HERE, 0.0).goal == "hint"                        # подсказка на севере тянет
    d.goal = None
    assert d.choose(north, HERE, 29.0).goal == "exit"                       # интерес почти угас
    assert d.interest(31.0) == 0 and d.directive is None


def test_goal_directive_and_directed_exploration():
    import random
    d = HeroDrive()
    d.set_directive("chest", 0.0)
    no_chest = [Option("hint", (5.0, 5.0), 1.0), Option("explore", None, 1.0)]
    assert d.choose(no_chest, HERE, 0.0).goal == "explore"                  # сундука не видно - ищет
    d.set_directive("east", 0.0)
    x, _y = d.explore_target(HERE, random.Random(1))
    assert x > 5.0


def test_stickiness_stops_flip_flopping():
    d = HeroDrive()
    a = [Option("exit", (10.0, 0.0), 1.0), Option("hint", (0.0, 10.0), 1.0 * 0.7 / 0.5)]
    first = d.choose(a, HERE, 0.0).goal
    a[0].base, a[1].base = 1.0, 1.0 * 0.7 / 0.5 * 1.05                      # чуть-чуть перевесило другое
    assert d.choose(a, HERE, 0.1).goal == first


def test_keys_come_from_lua_and_unknown_names_are_rejected():
    keys = player_keys()
    assert keys["f2"] == ("emotion", "rage") and keys["arrow_up"] == ("directive", "north")
    d = HeroDrive()
    assert not d.set_emotion("boredom") and not d.set_directive("upstairs", 0.0)
    assert "Ярость" in (d.set_emotion("rage") and d.thought("fight"))
