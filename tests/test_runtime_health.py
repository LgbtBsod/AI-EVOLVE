"""Базовые smoke-тесты на синтаксическое и импортное здоровье проекта."""


def test_launcher_importable() -> None:
    import launcher  # noqa: F401


def test_test_system_constructible() -> None:
    from src.systems.testing.test_system import TestSystem

    system = TestSystem()
    assert system.component_id == "test_system"


def test_scene_hybrid_input_routes_actions_without_direct_movement() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyPlayer:
        pass

    scene = EnhancedGameScene(game=None)
    scene.player = DummyPlayer()

    calls = {"attack": 0, "create": 0}
    scene._attack_nearest_enemy = lambda: calls.__setitem__("attack", calls["attack"] + 1)
    scene._create_object_at_player = lambda: calls.__setitem__("create", calls["create"] + 1)

    # Нажатие E пробрасывается в player.keys для интеракций
    scene.handle_input({"e": True})
    assert scene.player.keys["e"] is True

    # Одноразовые действия по фронту нажатия
    scene.handle_input({"1": True})
    scene.handle_input({"1": True})  # удержание не должно дублировать
    scene.handle_input({"1": False})
    scene.handle_input({"1": True})  # повторное нажатие

    # Атака с клавиатуры/мыши
    scene.handle_input({"space": True})
    scene.handle_input({"space": False})
    scene.handle_input({"mouse1": True})

    assert calls["create"] == 2
    assert calls["attack"] == 2


def test_scene_camera_setup_safe_when_camera_missing() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyGame:
        cam = None
        render_system = None

    scene = EnhancedGameScene(game=DummyGame())
    scene.player = None
    scene._setup_camera()  # should not raise


def test_chest_auto_interaction_opens_without_e_key() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyTaskMgr:
        def __init__(self):
            self.cb = None

        def add(self, cb, _name):
            self.cb = cb

    class DummyShowbase:
        def __init__(self):
            self.taskMgr = DummyTaskMgr()

    class DummyGame:
        def __init__(self):
            self.showbase = DummyShowbase()

    class DummyPlayer:
        x = 1.0
        y = 1.0

    scene = EnhancedGameScene(game=DummyGame())
    scene.player = DummyPlayer()

    opened = {"value": False}
    scene._open_chest = lambda chest, x, y, z: opened.__setitem__("value", True)

    scene._add_chest_logic(chest=object(), x=1.5, y=1.5, z=0.0)

    class DummyTask:
        cont = "cont"
        done = "done"

    result = scene.game.showbase.taskMgr.cb(DummyTask())

    assert opened["value"] is True
    assert result == DummyTask.done


def test_character_ai_moves_towards_loot_item_when_no_enemies() -> None:
    from src.entities.character import Character

    class DummyItem:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    character = Character("test_ai", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    character.ai_update_interval = 0.0
    character.last_ai_update = 0.0

    before_x, before_y = character.x, character.y
    loot = DummyItem(5.0, 0.0)

    character.update_ai(enemies=[], items=[loot], dt=0.5)

    assert character.ai_state == "looting"
    assert character.x > before_x
    assert character.y == before_y


def test_character_ai_prefers_exit_when_loot_too_far() -> None:
    from src.entities.character import Character

    class DummyItem:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    character = Character("test_ai2", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    character.ai_update_interval = 0.0
    character.last_ai_update = 0.0

    far_loot = DummyItem(999.0, 999.0)
    character.update_ai(
        enemies=[],
        items=[far_loot],
        dt=0.2,
        exit_position=(5.0, 0.0, 0.0),
        vision_range=100.0,
        known_exit_positions=[(5.0, 0.0)],
    )

    assert character.ai_state == "seeking_exit"


def test_scene_passes_known_exit_positions_directly() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyPlayer:
        attack_cooldown = 0
        max_health = 100
        health = 100
        health_regen = 0
        max_mana = 100
        mana = 100
        mana_regen = 0
        max_stamina = 100
        stamina = 100
        stamina_regen = 0

        def update_ai(self, enemies, items, dt, **kwargs):
            self.kwargs = kwargs

        def use_skill_automatically(self, enemies, dt):
            pass

        def is_alive(self):
            return True

    scene = EnhancedGameScene(game=type('G', (), {})())
    scene.player = DummyPlayer()
    scene.enemies = []
    scene.hud = None
    scene.known_exit_positions = [(1.0, 2.0)]
    scene.exit_beacon_position = (1.0, 2.0, 0.0)
    scene._spawn_enemies = lambda dt: None
    scene._update_exit_hints = lambda dt: None

    scene.update(0.016)

    assert scene.player.kwargs["known_exit_positions"] == [(1.0, 2.0)]


def test_character_ai_selects_nearest_known_exit_target() -> None:
    from src.entities.character import Character

    character = Character("test_ai3", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    character.ai_update_interval = 0.0
    character.last_ai_update = 0.0

    character.update_ai(
        enemies=[],
        items=[],
        dt=0.1,
        exit_position=(100.0, 0.0, 0.0),
        vision_range=200.0,
        known_exit_positions=[(30.0, 0.0), (5.0, 0.0), (20.0, 0.0)],
    )

    assert character.ai_state == "seeking_exit"
    assert character.x > 0.0  # сдвинулся в сторону ближайшей цели (5, 0)


def test_character_ai_retreats_on_low_health_when_enemy_near() -> None:
    from src.entities.character import Character

    class DummyEnemy:
        def __init__(self, x, y):
            self.x = x
            self.y = y

        def is_alive(self):
            return True

    character = Character("test_ai4", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    character.ai_update_interval = 0.0
    character.last_ai_update = 0.0
    character.max_health = 100
    character.health = 20  # ниже 30%

    enemy = DummyEnemy(1.0, 0.0)
    before_distance = character.get_distance_to(enemy)

    character.update_ai(enemies=[enemy], items=[], dt=0.5)

    after_distance = character.get_distance_to(enemy)
    assert character.ai_state == "retreating"
    assert after_distance > before_distance


def test_mage_uses_self_heal_when_low_health() -> None:
    from src.entities.character import Character

    mage = Character("mage_ai", game=None, x=0.0, y=0.0, z=0.0, character_class="mage", is_player=True)
    mage.health = 20
    mage.max_health = 80
    mage.mana = 50

    mage.use_skill_automatically(enemies=[], dt=0.1)

    assert mage.health > 20
    assert mage.mana == 35


def test_warrior_uses_second_wind_when_low_health() -> None:
    from src.entities.character import Character

    warrior = Character("warrior_ai", game=None, x=0.0, y=0.0, z=0.0, character_class="warrior", is_player=True)
    warrior.health = 20
    warrior.max_health = 120
    warrior.stamina = 60

    warrior.use_skill_automatically(enemies=[], dt=0.1)

    assert warrior.health > 20
    assert warrior.stamina == 35


def test_character_ai_ignores_malformed_exit_hints() -> None:
    from src.entities.character import Character

    character = Character("test_ai5", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    character.ai_update_interval = 0.0
    character.last_ai_update = 0.0

    # Невалидные подсказки не должны приводить к исключениям
    character.update_ai(
        enemies=[],
        items=[],
        dt=0.1,
        exit_position=("bad", None, 0.0),
        vision_range=200.0,
        known_exit_positions=[("x", "y"), (None, 1), "bad-obj", (3.0, 0.0)],
    )

    # Валидная подсказка (3,0) должна быть использована
    assert character.ai_state == "seeking_exit"
    assert character.x > 0.0


def test_character_extract_item_position_from_tuple_getpos() -> None:
    from src.entities.character import Character

    class TuplePosItem:
        def getPos(self):
            return (2.5, -1.0, 0.0)

    character = Character("test_ai6", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    x, y = character._extract_item_position(TuplePosItem())

    assert x == 2.5
    assert y == -1.0


def test_defensive_skill_respects_cooldown() -> None:
    from src.entities.character import Character

    mage = Character("mage_ai_cd", game=None, x=0.0, y=0.0, z=0.0, character_class="mage", is_player=True)
    mage.max_health = 80
    mage.health = 20
    mage.mana = 60
    mage.defensive_skill_cooldown = 9999.0
    import time
    mage.last_defensive_skill_time = time.time()  # гарантированно в кулдауне

    mana_before = mage.mana
    health_before = mage.health
    mage.use_skill_automatically(enemies=[], dt=0.1)

    assert mage.mana == mana_before
    assert mage.health == health_before


def test_defensive_skill_returns_bool_contract() -> None:
    from src.entities.character import Character

    rogue = Character("rogue_ai_bool", game=None, x=0.0, y=0.0, z=0.0, character_class="rogue", is_player=True)
    rogue.max_health = 90
    rogue.health = rogue.max_health
    rogue.stamina = 100

    used = rogue._use_second_wind()
    assert used is False


def test_character_exploration_sets_target_and_moves() -> None:
    from src.entities.character import Character

    character = Character("explore_ai", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    character.ai_update_interval = 0.0
    character.last_ai_update = 0.0

    before_x, before_y = character.x, character.y
    character.update_ai(enemies=[], items=[], dt=0.5, exit_position=None, vision_range=0.0, known_exit_positions=[])

    assert character.ai_state == "exploring"
    # Точка может быть сброшена в текущем тике, если персонаж сразу достиг цели.
    assert (character.x != before_x) or (character.y != before_y)


def test_character_exploration_retargets_after_reach() -> None:
    from src.entities.character import Character

    character = Character("explore_ai2", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    character.exploration_target = (0.0, 0.0)
    import time
    character.last_exploration_target_time = time.time()
    character.exploration_retarget_interval = 9999.0

    character._explore_area(0.5)

    # После достижения близкой цели она сбрасывается для следующего выбора.
    assert character.exploration_target is None


def test_install_requirements_skips_when_hash_unchanged(tmp_path, monkeypatch) -> None:
    import launcher

    req = tmp_path / "requirements.txt"
    req.write_text("numpy>=1.0\n", encoding="utf-8")

    marker = tmp_path / ".requirements_installed.sha256"
    marker.write_text(launcher._requirements_hash(req), encoding="utf-8")

    monkeypatch.setattr(launcher, "ROOT_DIR", tmp_path)

    called = {"value": False}

    def fake_check_call(_cmd):
        called["value"] = True

    monkeypatch.setattr(launcher.subprocess, "check_call", fake_check_call)

    ok = launcher.install_requirements_file(req)

    assert ok is True
    assert called["value"] is False


def test_scene_advances_level_when_player_reaches_exit() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyPlayer:
        x = 1.0
        y = 1.0
        z = 0.0
        attack_cooldown = 0
        max_health = 100
        health = 100
        health_regen = 0
        max_mana = 100
        mana = 100
        mana_regen = 0
        max_stamina = 100
        stamina = 100
        stamina_regen = 0

        def update_ai(self, enemies, items, dt, **kwargs):
            pass

        def use_skill_automatically(self, enemies, dt):
            pass

        def is_alive(self):
            return True

    scene = EnhancedGameScene(game=type('G', (), {})())
    scene.player = DummyPlayer()
    scene.enemies = []
    scene.hud = None
    scene.exit_beacon_position = (1.0, 1.0, 0.0)
    scene._spawn_enemies = lambda dt: None
    scene._update_exit_hints = lambda dt: None

    calls = {"advance": 0}
    scene._advance_to_next_level = lambda: calls.__setitem__("advance", calls["advance"] + 1)

    scene.update(0.016)

    assert calls["advance"] == 1


def test_scene_advance_clears_hints_and_rebuilds_exit(monkeypatch) -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyNode:
        def __init__(self):
            self.removed = False

        def removeNode(self):
            self.removed = True

    scene = EnhancedGameScene(game=type('G', (), {})())
    scene.map_hint_items = [{"node": DummyNode(), "used": False}]
    scene.npc_hints = [{"node": DummyNode(), "used": False, "knows_exit": True}]
    scene.enemies = []
    scene.player_created_objects = []

    flags = {"beacon": 0, "maps": 0, "npcs": 0}
    scene._create_exit_beacon = lambda: flags.__setitem__("beacon", flags["beacon"] + 1)
    scene._spawn_exit_hint_maps = lambda: flags.__setitem__("maps", flags["maps"] + 1)
    scene._spawn_exit_hint_npcs = lambda: flags.__setitem__("npcs", flags["npcs"] + 1)

    before_level = scene.current_level
    before_max_enemies = scene.max_enemies
    before_spawn_interval = scene.enemy_spawn_interval
    scene._advance_to_next_level()

    assert scene.current_level == before_level + 1
    assert scene.max_enemies >= before_max_enemies
    assert scene.enemy_spawn_interval <= before_spawn_interval
    assert scene.map_hint_items == []
    assert scene.npc_hints == []
    assert flags == {"beacon": 1, "maps": 1, "npcs": 1}


def test_scene_non_exact_npc_hint_builds_echo_points() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyPlayer:
        x = 0.0
        y = 0.0
        z = 0.0

    scene = EnhancedGameScene(game=type('G', (), {'render': None})())
    scene.player = DummyPlayer()
    scene.exit_beacon_position = (10.0, 0.0, 0.0)

    scene._register_exit_knowledge(precise=False)

    assert scene.known_exit_positions == []
    assert len(scene.echo_trail_points) == 4
    assert scene.echo_trail_points[0][0] > 0.0


def test_scene_update_passes_echo_points_to_ai() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyPlayer:
        x = 0.0
        y = 0.0
        z = 0.0
        attack_cooldown = 0
        max_health = 100
        health = 100
        health_regen = 0
        max_mana = 100
        mana = 100
        mana_regen = 0
        max_stamina = 100
        stamina = 100
        stamina_regen = 0

        def update_ai(self, enemies, items, dt, **kwargs):
            self.kwargs = kwargs

        def use_skill_automatically(self, enemies, dt):
            pass

        def is_alive(self):
            return True

    scene = EnhancedGameScene(game=type('G', (), {})())
    scene.player = DummyPlayer()
    scene.enemies = []
    scene.hud = None
    scene._spawn_enemies = lambda dt: None
    scene._update_exit_hints = lambda dt: None
    scene._check_exit_beacon_reached = lambda: None
    scene.known_exit_positions = [(1.0, 2.0)]
    scene.echo_trail_points = [(3.0, 4.0)]

    scene.update(0.016)

    assert scene.player.kwargs['known_exit_positions'] == [(1.0, 2.0), (3.0, 4.0)]


def test_character_ai_seeks_hint_when_exit_unknown() -> None:
    from src.entities.character import Character

    character = Character("hint_ai", game=None, x=0.0, y=0.0, z=0.0, is_player=True)
    character.ai_update_interval = 0.0
    character.last_ai_update = 0.0

    before_x, before_y = character.x, character.y
    character.update_ai(
        enemies=[],
        items=[],
        dt=0.4,
        exit_position=None,
        vision_range=0.0,
        known_exit_positions=[],
        hint_positions=[(6.0, 0.0)],
    )

    assert character.ai_state == "seeking_hint"
    assert character.x > before_x
    assert character.y == before_y


def test_scene_update_passes_hint_positions_to_ai() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyPosNode:
        def __init__(self, x, y):
            self.x = x
            self.y = y

        def getPos(self):
            return (self.x, self.y, 0.0)

    class DummyPlayer:
        x = 0.0
        y = 0.0
        z = 0.0
        attack_cooldown = 0
        max_health = 100
        health = 100
        health_regen = 0
        max_mana = 100
        mana = 100
        mana_regen = 0
        max_stamina = 100
        stamina = 100
        stamina_regen = 0

        def update_ai(self, enemies, items, dt, **kwargs):
            self.kwargs = kwargs

        def use_skill_automatically(self, enemies, dt):
            pass

        def is_alive(self):
            return True

    scene = EnhancedGameScene(game=type('G', (), {})())
    scene.player = DummyPlayer()
    scene.enemies = []
    scene.hud = None
    scene._spawn_enemies = lambda dt: None
    scene._update_exit_hints = lambda dt: None
    scene._check_exit_beacon_reached = lambda: None
    scene.map_hint_items = [{"node": DummyPosNode(10.0, 0.0), "used": False}]
    scene.npc_hints = [{"node": DummyPosNode(20.0, 0.0), "used": False, "knows_exit": False}]

    scene.update(0.016)

    assert scene.player.kwargs["hint_positions"] == [(10.0, 0.0), (20.0, 0.0)]


def test_scene_refreshes_echo_trail_when_player_moves(monkeypatch) -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyPlayer:
        x = 5.0
        y = 3.0
        z = 0.0

    scene = EnhancedGameScene(game=type('G', (), {'render': None})())
    scene.player = DummyPlayer()
    scene.exit_beacon_position = (20.0, 0.0, 0.0)
    scene.echo_trail_points = [(1.0, 1.0)]
    scene.known_exit_positions = []
    scene.echo_refresh_interval = 0.0

    calls = {"rebuild": 0}
    scene._rebuild_echo_trail = lambda ex, ey: calls.__setitem__("rebuild", calls["rebuild"] + 1)

    scene._refresh_echo_trail_guidance()

    assert calls["rebuild"] == 1


def test_scene_does_not_refresh_echo_when_exact_exit_known() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyPlayer:
        x = 0.0
        y = 0.0
        z = 0.0

    scene = EnhancedGameScene(game=type('G', (), {'render': None})())
    scene.player = DummyPlayer()
    scene.exit_beacon_position = (10.0, 0.0, 0.0)
    scene.echo_trail_points = [(1.0, 1.0)]
    scene.known_exit_positions = [(10.0, 0.0)]
    scene.echo_refresh_interval = 0.0

    calls = {"rebuild": 0}
    scene._rebuild_echo_trail = lambda ex, ey: calls.__setitem__("rebuild", calls["rebuild"] + 1)

    scene._refresh_echo_trail_guidance()

    assert calls["rebuild"] == 0


def test_scene_remove_runtime_tasks_ignores_missing_task_manager() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    scene = EnhancedGameScene(game=type('G', (), {})())
    scene._runtime_task_names = {"a", "b"}

    scene._remove_runtime_tasks()

    assert scene._runtime_task_names == set()


def test_scene_remove_runtime_tasks_calls_taskmgr_remove() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyTaskMgr:
        def __init__(self):
            self.removed = []

        def remove(self, name):
            self.removed.append(name)

    class DummyShowbase:
        def __init__(self):
            self.taskMgr = DummyTaskMgr()

    class DummyGame:
        def __init__(self):
            self.showbase = DummyShowbase()

    scene = EnhancedGameScene(game=DummyGame())
    scene._runtime_task_names = {"task_1", "task_2"}

    scene._remove_runtime_tasks()

    assert set(scene.game.showbase.taskMgr.removed) == {"task_1", "task_2"}
    assert scene._runtime_task_names == set()


def test_scene_advance_restarts_camera_follow_after_task_cleanup() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyTaskMgr:
        def remove(self, _name):
            pass

    class DummyShowbase:
        def __init__(self):
            self.taskMgr = DummyTaskMgr()

    class DummyPlayer:
        x = 0.0
        y = 0.0
        z = 0.0

    class DummyGame:
        def __init__(self):
            self.render = object()
            self.showbase = DummyShowbase()
            self.cam = object()

    scene = EnhancedGameScene(game=DummyGame())
    scene.player = DummyPlayer()
    scene.enemies = []
    scene.player_created_objects = []

    calls = {"camera": 0}
    scene._spawn_initial_enemies = lambda: None
    scene._start_camera_follow = lambda: calls.__setitem__("camera", calls["camera"] + 1)
    scene._create_exit_beacon = lambda: None
    scene._spawn_exit_hint_maps = lambda: None
    scene._spawn_exit_hint_npcs = lambda: None

    scene._advance_to_next_level()

    assert calls["camera"] == 1


def test_complete_runtime_task_discards_name() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    scene = EnhancedGameScene(game=type('G', (), {})())
    scene._runtime_task_names = {"a", "b"}

    scene._complete_runtime_task("a")

    assert scene._runtime_task_names == {"b"}


def test_chest_task_removed_from_registry_on_open() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyTaskMgr:
        def __init__(self):
            self.cb = None

        def add(self, cb, _name):
            self.cb = cb

        def doMethodLater(self, _delay, cb, _name):
            self.later_cb = cb

    class DummyShowbase:
        def __init__(self):
            self.taskMgr = DummyTaskMgr()

    class DummyRender:
        def attachNewNode(self, _name):
            class Node:
                def removeNode(self):
                    pass
                def setHpr(self, *_args):
                    pass
            return Node()

    class DummyGame:
        def __init__(self):
            self.showbase = DummyShowbase()
            self.render = DummyRender()

    class DummyPlayer:
        x = 0.0
        y = 0.0
        z = 0.0
        experience = 0
        health = 100
        max_health = 100

    class DummyTask:
        cont = "cont"
        done = "done"

    class DummyChest:
        def removeNode(self):
            pass
        def setHpr(self, *_args):
            pass

    scene = EnhancedGameScene(game=DummyGame())
    scene.player = DummyPlayer()
    chest = DummyChest()
    scene.world_objects.append(chest)
    scene.player_created_objects.append(chest)

    scene._add_chest_logic(chest, 0.0, 0.0, 0.0)
    task_name = next(name for name in scene._runtime_task_names if name.startswith("chest_"))

    result = scene.game.showbase.taskMgr.cb(DummyTask())

    assert result == DummyTask.done
    assert task_name not in scene._runtime_task_names


def test_dead_enemy_removed_from_player_created_objects_on_update() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyEnemy:
        def __init__(self):
            self.destroy_calls = 0

        def is_alive(self):
            return False

        def destroy(self):
            self.destroy_calls += 1

    class DummyPlayer:
        x = 0.0
        y = 0.0
        z = 0.0
        attack_cooldown = 0
        max_health = 100
        health = 100
        health_regen = 0
        max_mana = 100
        mana = 100
        mana_regen = 0
        max_stamina = 100
        stamina = 100
        stamina_regen = 0

        def update_ai(self, enemies, items, dt, **kwargs):
            pass

        def use_skill_automatically(self, enemies, dt):
            pass

        def is_alive(self):
            return True

    scene = EnhancedGameScene(game=type('G', (), {})())
    scene.player = DummyPlayer()
    scene.hud = None
    scene._spawn_enemies = lambda dt: None
    scene._update_exit_hints = lambda dt: None
    scene._check_exit_beacon_reached = lambda: None

    dead_enemy = DummyEnemy()
    scene.enemies = [dead_enemy]
    scene.player_created_objects = [dead_enemy]

    scene.update(0.016)

    assert dead_enemy.destroy_calls == 1
    assert dead_enemy not in scene.enemies
    assert dead_enemy not in scene.player_created_objects


def test_open_chest_does_not_double_reward_same_chest() -> None:
    from src.scenes.main_game_scene import EnhancedGameScene

    class DummyTaskMgr:
        def doMethodLater(self, _delay, _cb, _name):
            pass

    class DummyShowbase:
        def __init__(self):
            self.taskMgr = DummyTaskMgr()

    class DummyGame:
        def __init__(self):
            self.showbase = DummyShowbase()

    class DummyChest:
        def setHpr(self, *_args):
            pass

    class DummyPlayer:
        experience = 0
        health = 50
        max_health = 100

    scene = EnhancedGameScene(game=DummyGame())
    scene.player = DummyPlayer()

    chest = DummyChest()
    scene._open_chest(chest, 0.0, 0.0, 0.0)
    exp_after_first = scene.player.experience
    hp_after_first = scene.player.health

    scene._open_chest(chest, 0.0, 0.0, 0.0)

    assert scene.player.experience == exp_after_first
    assert scene.player.health == hp_after_first
