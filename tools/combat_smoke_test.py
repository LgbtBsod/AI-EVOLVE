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
from src.systems.effects.effect_system import EffectSystem, apply_tick_to_entity  # noqa: E402
from src.entities.character import Character  # noqa: E402
from src.entities.enemy import EnhancedEnemy  # noqa: E402
from src.scenes.main_game_scene import EnhancedGameScene  # noqa: E402

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


def make_game(rng=None, with_effects=False):
    effect_system = None
    if with_effects:
        # initialize() only reaches READY - BaseComponent.update() is a
        # no-op unless the state is RUNNING, so start() is required too or
        # effect ticking/expiration silently never happens (see main.py).
        effect_system = EffectSystem()
        effect_system.initialize()
        effect_system.start()
    game = SimpleNamespace(
        render=NodePath("fake_render"),
        showbase=SimpleNamespace(taskMgr=FakeTaskMgr()),
        combat_system=CombatSystem(rng=rng if rng is not None else get_default_rng(), effect_system=effect_system),
        effect_system=effect_system,
    )
    return game


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
    player = make_player(game, physical_damage=20, defense=0, critical_chance=1.0, critical_damage=2.0)
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
    enemy2.dodge_chance = 0.5  # -> 0.5 fraction; FakeRNG's 0.0 < 0.5 -> dodge
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


# ---------------------------------------------------------------------------
# Leveling (Character.add_experience / EnhancedEnemy.apply_level_bonus)
# ---------------------------------------------------------------------------

def test_character_levels_up_from_experience():
    game = make_game()
    player = make_player(game)
    check("starts at level 1 with 0 XP", player.level == 1 and player.experience == 0)

    threshold = player.experience_to_next_level
    max_hp_before = player.max_health
    levels_gained = player.add_experience(threshold)
    check("add_experience() crossing the threshold returns 1 level gained", levels_gained == 1)
    check("level actually incremented", player.level == 2)
    check("leftover experience is 0, not silently dropped or duplicated",
          player.experience == 0)
    check("stats actually grow on level up (max_health increased)", player.max_health > max_hp_before)
    check("health is topped up to the new max on level up", player.health == player.max_health)

    # Enough XP to cross two thresholds in one call - while loop, not a single if.
    player2 = make_player(game)
    t1 = player2.experience_to_next_level
    levels_gained2 = player2.add_experience(t1 * 3)
    check("a big XP dump can cross multiple level thresholds in one call", levels_gained2 >= 2)


def test_enemy_level_bonus_scales_stats():
    game = make_game()
    enemy = make_enemy(game, x=1.0, enemy_type="basic")
    base_level, base_hp, base_dmg, base_reward = enemy.level, enemy.max_health, enemy.physical_damage, enemy.experience_reward

    enemy.apply_level_bonus(0)
    check("apply_level_bonus(0) is a no-op", enemy.level == base_level and enemy.max_health == base_hp)

    enemy.apply_level_bonus(3)
    check("apply_level_bonus() raises level", enemy.level == base_level + 3)
    check("apply_level_bonus() raises max_health", enemy.max_health > base_hp)
    check("apply_level_bonus() heals to the new (higher) max_health", enemy.health == enemy.max_health)
    check("apply_level_bonus() raises physical_damage", enemy.physical_damage > base_dmg)
    check("apply_level_bonus() raises the XP a kill is worth", enemy.experience_reward > base_reward)


# ---------------------------------------------------------------------------
# Effect system <-> combat system integration
# ---------------------------------------------------------------------------

def test_buff_modifies_combat_stats():
    game = make_game(with_effects=True)
    player = make_player(game, physical_damage=20)
    base_damage = player.get_combat_stats().physical_damage
    check("no active effects -> get_combat_stats() returns the raw stat", base_damage == 20)

    applied = game.effect_system.apply_effect(player.entity_id, "strength_buff", source="test")
    check("apply_effect() for a known template succeeds", applied is not None)

    buffed_damage = player.get_combat_stats().physical_damage
    check("strength_buff (physical_damage x1.2) is reflected in get_combat_stats()",
          abs(buffed_damage - 24.0) < 0.01)


def test_effect_tick_damage_respects_death_latch():
    # apply_tick_to_entity() must go through take_damage(), not a raw
    # entity.health -= value - otherwise it's the exact same class of bug as
    # the regen-oscillation death bug fixed earlier in this project's history
    # (a mutation that bypasses is_defeated/state="dead").
    game = make_game()
    enemy = make_enemy(game, x=1.0, enemy_type="basic")
    enemy.defense = 0
    enemy.health = 3  # about to die from a single -5 poison tick

    effect_system = EffectSystem()
    effect_system.initialize()
    poison_id = effect_system.apply_effect(enemy.entity_id, "poison_debuff", source="test")
    check("poison_debuff applies successfully", poison_id is not None)
    active = effect_system.get_entity_effects(enemy.entity_id)[0]

    apply_tick_to_entity(enemy, active)
    check("a lethal poison tick actually kills (via take_damage's own death handling)",
          enemy.health == 0 and not enemy.is_alive())

    enemy.health = enemy.max_health  # simulate a stray unrelated heal/regen after death
    check("enemy stays dead after an external health change post-mortem (state latch holds)",
          not enemy.is_alive())


def test_effect_tick_heal_clamps_to_max_health():
    game = make_game()
    player = make_player(game)
    player.health = player.max_health - 2

    effect_system = EffectSystem()
    effect_system.initialize()
    effect_system.apply_effect(player.entity_id, "heal_over_time", source="test")
    active = effect_system.get_entity_effects(player.entity_id)[0]

    apply_tick_to_entity(player, active)  # heal_over_time is +3/tick, only 2 missing
    check("a heal tick clamps at max_health instead of overshooting", player.health == player.max_health)


def test_hero_hp_never_exceeds_max_after_hits():
    """Регрессия: HealthComponent героя создавался до того, как класс
    выставлял max_health (warrior 120), и первый удар ставил HP 149/120;
    реген/лечение компонент не видел и следующий удар откатывал HP назад."""
    game = make_game()
    player = make_player(game)
    player.take_damage(1.0)
    check("first hit keeps hero HP <= max_health", player.health <= player.max_health)
    player.health = player.max_health - 30  # как будто реген/лечение изменили HP в обход компонента
    before = player.health
    player.take_damage(10.0)
    check("next hit starts from the current HP, not the component's stale value",
          before - 10.0 <= player.health < before)
    player.add_experience(player.experience_to_next_level)  # level-up: max_health +15, полное лечение
    player.take_damage(1.0)
    check("after level-up a hit lands on the new max_health", player.max_health - 1.0 <= player.health < player.max_health)


def test_stealth_attack_applies_poison_via_combat_system():
    # Previously _stealth_attack computed damage by hand and called
    # target.take_damage() directly, bypassing CombatSystem entirely (no
    # crit/dodge, and no way to hook an effect on hit). FakeRNG([1.0, 1.0])
    # forces no-crit/no-dodge so the x1.5 multiplier is checked exactly.
    game = make_game(rng=FakeRNG([1.0, 1.0]), with_effects=True)
    player = make_player(game, character_class="rogue", physical_damage=20, defense=0, stamina=100)
    enemy = make_enemy(game, x=1.0, enemy_type="basic")
    enemy.defense = 0
    hp_before = enemy.health

    player._stealth_attack(enemy)
    check("stealth attack applies the x1.5 damage_multiplier via CombatSystem",
          enemy.health == hp_before - 20 * 1.5)
    check("stealth attack applies poison_debuff to the target on hit",
          game.effect_system.has_effect(enemy.entity_id, "poison_debuff"))


def test_time_based_enemy_scaling_applies_on_spawn():
    # EnhancedGameScene.__init__/_spawn_enemies never touch Panda3D beyond
    # attachNewNode() on a bare NodePath (confirmed by reading the file - no
    # camera/window dependency), so the wiring between "time elapsed" and
    # "newly spawned enemies get apply_level_bonus()" can be checked exactly,
    # deterministically, instead of hoping a real dev_probe.py run happens to
    # spawn a replacement enemy after the right number of real seconds.
    game = make_game()
    scene = EnhancedGameScene(game, dev_mode=True)
    check("no bonus at t=0", scene._current_enemy_level_bonus() == 0)

    scene.world_start_time -= scene.enemy_level_up_interval * 2.3  # simulate 2.3 intervals elapsed
    check("bonus grows with elapsed time (floor division by the interval)",
          scene._current_enemy_level_bonus() == 2)

    scene.max_enemies = 10
    scene.last_enemy_spawn = 0
    scene._spawn_enemies(dt=0.1)
    check("a newly spawned enemy actually exists after _spawn_enemies()", len(scene.enemies) == 1)
    spawned = scene.enemies[0]
    check("a newly spawned enemy is scaled to the current time-based bonus level",
          spawned.level >= 1 + 2)  # base level (>=1) + the 2 bonus levels just simulated


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
    test_character_levels_up_from_experience,
    test_enemy_level_bonus_scales_stats,
    test_buff_modifies_combat_stats,
    test_effect_tick_damage_respects_death_latch,
    test_effect_tick_heal_clamps_to_max_health,
    test_hero_hp_never_exceeds_max_after_hits,
    test_stealth_attack_applies_poison_via_combat_system,
    test_time_based_enemy_scaling_applies_on_spawn,
]

for test_fn in TESTS:
    print(f"-- {test_fn.__name__} --")
    test_fn()

print(f"\n{passed} passed, {len(failed)} failed" + (f": {failed}" if failed else ""))
print(f"Status: {'OK' if not failed else 'FAILED'}")
sys.exit(1 if failed else 0)
