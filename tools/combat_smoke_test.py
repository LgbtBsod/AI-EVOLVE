#!/usr/bin/env python3
"""Windowless smoke test for combat/entity/AI-targeting logic - no Panda3D
window, no screenshots, sub-second.

tools/dev_probe.py boots the whole game and watches it run for real seconds
to answer questions like "does crit damage still compute right" or "is the
historical death-oscillation bug (d69c002, Character.is_defeated) still
fixed" - real token cost (every stdout line, every screenshot an agent opens)
and real wall-clock cost, for a question that's actually a handful of pure
Python function calls. Character/EnhancedEnemy's constructors and their
attack()/take_damage()/is_alive()/update_ai() methods never touch Panda3D
unless self.node is set (create_character()/create_enemy() are what attaches
the render tree - this script never calls them), so all of that logic can be
exercised directly against a fake game/entity stand-ins.

Reach for this FIRST for logic-only changes confined to src/entities/ or
src/systems/combat/ (damage formulas, the is_alive()/is_defeated latch, AI
targeting/movement math). Fall back to tools/dev_probe.py only when the
change needs visual/rendering/scene-wiring/real-time verification - this
script proves the math is right, not that it renders or gets called at all
from the actual game loop.

Usage:
    .venv/Scripts/python.exe tools/combat_smoke_test.py
"""
import random as python_random
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from panda3d.core import NodePath  # noqa: E402

from src.core.rng_manager import get_default_rng  # noqa: E402
from src.systems.combat.combat_system import CombatSystem  # noqa: E402
from src.entities.character import Character  # noqa: E402
from src.entities.enemy import EnhancedEnemy  # noqa: E402

passed = 0
failed = []


def check(name, condition):
    global passed
    if condition:
        passed += 1
    else:
        failed.append(name)
    print(f"{'OK  ' if condition else 'FAIL'} {name}")


class FakeRNG:
    """Deterministic stand-in for RNGManager: feeds a fixed sequence of
    .random() results so crit/dodge branches can be exercised on demand,
    instead of only ever getting False (rng=None) or a real RNGManager whose
    run-to-run variance is exactly what dev_probe.py's --seed docstring
    already documents as unresolved."""

    def __init__(self, values):
        self._values = list(values)

    def random(self):
        return self._values.pop(0)


class FakeTaskMgr:
    def add(self, *a, **k):
        pass

    def doMethodLater(self, *a, **k):
        pass


def make_game(rng=None):
    return SimpleNamespace(
        render=NodePath("fake_render"),
        showbase=SimpleNamespace(taskMgr=FakeTaskMgr()),
        combat_system=CombatSystem(rng=rng if rng is not None else get_default_rng()),
    )


def make_player(game, **kwargs):
    p = Character("p", game, 0, 0, 0.5, kwargs.pop("character_class", "warrior"), (0, 0, 1, 1), is_player=True)
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def make_enemy(game, x=1.0, y=0.0, enemy_type="basic", **kwargs):
    e = EnhancedEnemy(game, x, y, 0.5, enemy_type)
    for k, v in kwargs.items():
        setattr(e, k, v)
    return e


class StubUnit:
    """Bare-minimum stand-in for an enemy/entity in AI-targeting tests -
    Character.get_distance_to()/_find_nearest_enemy() only need .x/.y/
    .is_alive(), confirmed by reading character.py directly."""

    def __init__(self, x, y, alive=True):
        self.x, self.y = x, y
        self._alive = alive

    def is_alive(self):
        return self._alive


# ---------------------------------------------------------------------------
# Combat + death-latch regression
# ---------------------------------------------------------------------------

def test_combat_and_death_latch():
    game = make_game()
    player = make_player(game)
    enemy = make_enemy(game, x=1.0, enemy_type="strong")

    check("player.is_alive() true at full HP", player.is_alive())
    check("enemy.is_alive() true at full HP", enemy.is_alive())

    player.attack_cooldown = 0
    hit = player.attack(enemy)
    check("player.attack() returns a bool, not a silent no-op", isinstance(hit, bool))

    n = 0
    while enemy.is_alive() and n < 100:
        player.attack_cooldown = 0
        player.attack(enemy)
        n += 1
    check("enemy actually dies within a bounded number of hits", not enemy.is_alive())
    check("dead enemy health is clamped at 0, not negative", enemy.health == 0)

    # Regression guard for the death-oscillation bug fixed in d69c002:
    # main_game_scene.update() used to regen health unconditionally every
    # frame, which flipped is_alive() back to True the instant health ticked
    # above 0 again. The fix was a sticky Character.is_defeated flag - this
    # simulates exactly what an unconditional regen tick would do and asserts
    # the latch holds anyway.
    enemy2 = make_enemy(game, x=1.0, enemy_type="basic")
    while enemy2.health > 0:
        player.attack_cooldown = 0
        player.attack(enemy2)
    check("EnhancedEnemy latches dead via self.state", not enemy2.is_alive())
    enemy2.health = enemy2.max_health  # simulate a stray/unconditional regen tick
    check("EnhancedEnemy stays dead even if health is externally restored (state latch)", not enemy2.is_alive())

    dying_player = make_player(game)
    while dying_player.health > 0:
        enemy2.attack_cooldown = 0
        enemy2.last_attack_time = 0
        enemy2 = make_enemy(game, x=1.0, enemy_type="elite")
        enemy2.attack(dying_player)
    check("Character.is_defeated latches false", not dying_player.is_alive())
    dying_player.health = dying_player.max_health  # simulate the exact regen bug this was fixed for
    check("Character stays dead even if health is externally restored (is_defeated latch)",
          not dying_player.is_alive())


def test_damage_floor():
    game = make_game(rng=FakeRNG([1.0] * 20))  # 1.0 never < any chance -> no crit, no dodge, ever
    player = make_player(game, physical_damage=20, defense=0)
    enemy = make_enemy(game, x=1.0, enemy_type="basic")
    enemy.defense = 1000  # absurdly high on purpose

    player.attack_cooldown = 0
    hp_before = enemy.health
    player.attack(enemy)
    check("take_damage() floors at 1 even against huge defense (max(1, damage-defense))",
          enemy.health == hp_before - 1)


def test_crit_and_dodge_via_combat_system():
    # execute_attack() calls rng.random() exactly twice per attack, in order:
    # crit check then dodge check (verified by reading combat_system.py).
    game = make_game(rng=FakeRNG([0.0, 1.0]))  # 0.0 -> crit; 1.0 -> not dodged
    player = make_player(game, physical_damage=20, defense=0, critical_chance=100.0, critical_damage=200.0)
    enemy = make_enemy(game, x=1.0, enemy_type="basic")
    enemy.defense = 0
    enemy.dodge_chance = 0.0

    hp_before = enemy.health
    info = game.combat_system.execute_attack(player, enemy)
    expected = max(1, 20 * 2.0)  # critical_damage=200% -> x2, then take_damage's own defense floor
    check("forced crit (FakeRNG) applies the critical_damage multiplier",
          info.is_critical and enemy.health == hp_before - expected)

    game2 = make_game(rng=FakeRNG([1.0, 0.0]))  # 1.0 -> not crit; 0.0 -> dodged (needs dodge_chance>0)
    player2 = make_player(game2, physical_damage=20, defense=0)
    enemy2 = make_enemy(game2, x=1.0, enemy_type="basic")
    enemy2.dodge_chance = 50.0  # -> 0.5 fraction; FakeRNG's 0.0 < 0.5 -> dodge
    hp_before2 = enemy2.health
    info2 = game2.combat_system.execute_attack(player2, enemy2)
    check("forced dodge (FakeRNG) deals zero damage and leaves HP untouched",
          info2.is_dodged and info2.damage == 0 and enemy2.health == hp_before2)


def test_enemy_takes_no_dodge_by_default():
    # Every current enemy type sets dodge_chance=0 (_setup_enemy_type) - this
    # just pins that fact so a future change adding nonzero dodge to some
    # enemy type is a visible, deliberate diff against this assertion.
    game = make_game()
    for enemy_type in ("basic", "strong", "elite", "boss"):
        e = make_enemy(game, x=1.0, enemy_type=enemy_type)
        check(f"enemy_type={enemy_type!r} has dodge_chance == 0 by default", e.dodge_chance == 0.0)


def test_enemy_take_damage_has_its_own_independent_dodge_roll():
    # KNOWN LANDMINE, pinned as a named regression check rather than left
    # invisible: CombatSystem.execute_attack() already resolves dodge via
    # target.get_combat_stats().dodge_chance BEFORE ever calling
    # target.take_damage() - but EnhancedEnemy.take_damage() (enemy.py) rolls
    # its OWN independent dodge check via the global random module whenever
    # damage_type=="physical" and self.dodge_chance>0. Today this is dead
    # code (every enemy type ships dodge_chance=0, see the test above), but
    # the moment any enemy type gets nonzero dodge, an attack that survives
    # CombatSystem's own dodge roll gets a SECOND, independently-seeded
    # chance to dodge the exact same hit - a real double-roll that a windowed
    # dev_probe run could only notice via statistical hit-rate drift over a
    # long --seed'd session, not a single deterministic assertion.
    #
    # This test forces dodge_chance=100 (always dodges, regardless of the
    # actual random draw) to deterministically prove take_damage()'s
    # internal branch exists and fires - without needing to seed the global
    # random module to hit a probabilistic 50/50 branch.
    game = make_game()
    enemy = make_enemy(game, x=1.0, enemy_type="basic")
    enemy.dodge_chance = 100.0
    hp_before = enemy.health
    python_random.seed(1)  # determinism isn't the point here (100% always dodges) - just avoids polluting global state
    result = enemy.take_damage(50, "physical")
    check("EnhancedEnemy.take_damage() has its own independent dodge branch "
          "(100% dodge_chance dodges even called directly, bypassing CombatSystem entirely)",
          result is False and enemy.health == hp_before)


def test_entity_ids_unique():
    game = make_game()
    ids = {make_enemy(game, x=0, enemy_type="basic").entity_id for _ in range(20)}
    check("20 enemies constructed in a row get 20 distinct entity_ids", len(ids) == 20)
    ids2 = {make_player(game).entity_id for _ in range(20)}
    check("20 players constructed in a row get 20 distinct entity_ids", len(ids2) == 20)


# ---------------------------------------------------------------------------
# AI targeting / movement (pure math, gated behind `if self.node:` for every
# Panda3D call - confirmed by reading move_towards()/update_ai() directly)
# ---------------------------------------------------------------------------

def test_find_nearest_enemy():
    game = make_game()
    player = make_player(game)
    near = StubUnit(3, 0)
    far = StubUnit(50, 0)
    dead_but_closer = StubUnit(1, 0, alive=False)
    nearest = player._find_nearest_enemy([far, near, dead_but_closer])
    check("_find_nearest_enemy() picks the closest ALIVE candidate, skipping dead ones", nearest is near)


def test_retreat_at_low_hp():
    game = make_game()
    player = make_player(game)
    player.health = player.max_health * 0.2  # below the 0.3 retreat threshold in update_ai()
    player.last_ai_update = 0  # avoid the ai_update_interval throttle on a fresh call
    enemy = StubUnit(2, 0)  # within the 12-unit retreat trigger radius

    x_before, y_before = player.x, player.y
    player.update_ai(enemies=[enemy], items=[], dt=0.1)
    check("update_ai() sets ai_state to 'retreating' below 30% HP with an enemy nearby",
          player.ai_state == "retreating")
    moved_away = (player.x - enemy.x) ** 2 + (player.y - enemy.y) ** 2 > (x_before - enemy.x) ** 2 + (y_before - enemy.y) ** 2
    check("retreating actually increases distance to the enemy, not just labels the state", moved_away)


def test_exit_and_hint_target_prefer_nearest():
    game = make_game()
    player = make_player(game)
    target = player._select_best_exit_target(known_exit_positions=[(50, 50), (2, 0), (30, -10)])
    check("_select_best_exit_target() picks the nearest of several known exits", target == (2, 0))

    hint = player._select_best_hint_target(hint_positions=[(40, 0), (1, 1), (20, 20)])
    check("_select_best_hint_target() picks the nearest of several hints", hint == (1, 1))


TESTS = [
    test_combat_and_death_latch,
    test_damage_floor,
    test_crit_and_dodge_via_combat_system,
    test_enemy_takes_no_dodge_by_default,
    test_enemy_take_damage_has_its_own_independent_dodge_roll,
    test_entity_ids_unique,
    test_find_nearest_enemy,
    test_retreat_at_low_hp,
    test_exit_and_hint_target_prefer_nearest,
]

for test_fn in TESTS:
    print(f"-- {test_fn.__name__} --")
    test_fn()

print(f"\n{passed} passed, {len(failed)} failed" + (f": {failed}" if failed else ""))
print(f"Status: {'OK' if not failed else 'FAILED'}")
sys.exit(1 if failed else 0)
