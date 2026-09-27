"""World population within a level (main_game_scene.py):

1) 2-3 bosses active at once (boss_queue drains up front, not one-at-a-time).
2) each active boss summons a mob batch roughly every population.boss_summon_
   interval_minutes of *virtual* game time (scene.game_time, driven by dt -
   never time.time()).
3) summoned mobs wander further from their spawn point the longer they have
   lived (EnhancedEnemy.age, also dt-driven).

Numbers live in lua_content/world.lua -> population; defaults mirrored in
src/gameplay/progression.DEFAULT_POPULATION are asserted against directly so
the test stays meaningful if the content file changes.
"""
from types import SimpleNamespace

from panda3d.core import NodePath

from src.entities.enemy import EnhancedEnemy
from src.gameplay.progression import population
from src.scenes.main_game_scene import EnhancedGameScene


def make_game():
    return SimpleNamespace(render=NodePath("fake_render"), showbase=None, effect_manager=None)


def make_scene():
    scene = EnhancedGameScene(make_game(), dev_mode=True)
    return scene


def test_fill_active_bosses_caps_at_population_max():
    scene = make_scene()
    pop = population()
    max_active = int(pop["max_active_bosses"])
    assert max_active >= 2, "task requires 2-3 active bosses; population.max_active_bosses regressed"

    scene.boss_queue = ["forest_warden", "frost_jarl", "forge_golem", "bog_hydra"]
    scene._fill_active_bosses()

    assert len(scene.active_bosses) == max_active
    assert len(scene.boss_queue) == 4 - max_active
    for boss in scene.active_bosses:
        assert boss.is_boss is True
        assert boss.next_summon_at == scene.game_time + pop["boss_summon_interval_minutes"] * 60.0


def test_on_boss_death_refills_up_to_max_active_instead_of_one_at_a_time():
    scene = make_scene()
    scene.boss_queue = ["forest_warden", "frost_jarl", "forge_golem", "bog_hydra"]
    scene._fill_active_bosses()
    max_active = len(scene.active_bosses)
    dying = scene.active_bosses[0]

    scene._on_boss_death(dying)

    assert len(scene.active_bosses) == max_active, "a death should top back up to max_active, not spawn only one"
    assert dying not in scene.active_bosses


def test_on_boss_death_with_empty_queue_and_survivors_does_not_finish_level():
    scene = make_scene()
    scene.boss_queue = ["forest_warden", "frost_jarl"]
    scene._fill_active_bosses()
    assert len(scene.active_bosses) == 2
    dying = scene.active_bosses[0]

    scene._on_boss_death(dying)

    # queue is empty but one boss is still alive: level not "cleared" yet
    assert len(scene.active_bosses) == 1
    assert not scene.boss_queue


def test_boss_summon_timer_uses_virtual_game_time_not_wallclock():
    scene = make_scene()
    scene.boss_queue = ["forest_warden"]
    scene._fill_active_bosses()
    boss = scene.active_bosses[0]
    interval = population()["boss_summon_interval_minutes"] * 60.0
    before = len(scene.enemies)

    # just under the interval: no summon yet, no matter how much real
    # wall-clock time this test itself takes to run
    scene.game_time = interval - 1.0
    scene._update_boss_summons()
    assert len(scene.enemies) == before

    # crossing the interval on the virtual clock: a mob batch appears
    scene.game_time = interval
    scene._update_boss_summons()
    assert len(scene.enemies) > before
    assert boss.next_summon_at == interval + interval


def test_wander_radius_grows_after_population_grow_after_minutes():
    game = make_game()
    pop = population()
    enemy = EnhancedEnemy(game, x=0.0, y=0.0, z=0.5, enemy_type="slime")
    enemy.move_speed = 1000.0  # force the proposed step far outside any radius

    import random as random_module
    random_module.seed(0)

    # young enemy: clamped to the base radius
    enemy.age = 0.0
    for _ in range(200):
        enemy._wander(dt=1.0)
    base = float(pop["wander_base_radius"])
    assert abs(enemy.x - enemy.spawn_x) <= base + 1e-6
    assert abs(enemy.y - enemy.spawn_y) <= base + 1e-6

    # old enemy (well past wander_grow_after_minutes): radius grew, capped at wander_max_radius
    enemy.x, enemy.y = enemy.spawn_x, enemy.spawn_y
    enemy.age = pop["wander_grow_after_minutes"] * 60.0 + 999999.0
    reached = 0.0
    for _ in range(200):
        enemy._wander(dt=1.0)
        reached = max(reached, abs(enemy.x - enemy.spawn_x), abs(enemy.y - enemy.spawn_y))
    assert reached > base
    assert reached <= float(pop["wander_max_radius"]) + 1e-6


def test_enemy_age_accumulates_from_dt_not_wallclock():
    game = make_game()
    enemy = EnhancedEnemy(game, x=0.0, y=0.0, z=0.5, enemy_type="slime")
    assert enemy.age == 0.0
    enemy.update_ai(player=None, dt=0.5)
    enemy.update_ai(player=None, dt=0.25)
    assert enemy.age == 0.75
