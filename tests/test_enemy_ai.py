"""Враги учатся (бандит rust_core + Python-двойник), мозг врага, обзор и стелс,
дальность атаки из оружия, френдли фаер в решениях ИИ."""
import math
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content import lua_bridge  # noqa: E402

pytestmark = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")

from src.effects.abilities import load_abilities, load_bosses  # noqa: E402
from src.effects.manager import EffectManager, Telegraph  # noqa: E402
from src.gameplay import tactics as tac  # noqa: E402
from src.gameplay.enemy_ai import EnemyBrain  # noqa: E402
from src.gameplay.items import catalog  # noqa: E402
from tests.test_effect_manager import FakeRng, Fighter, World  # noqa: E402


class Mob(Fighter):
    """Враг для мозга: ходит к точке со своей скоростью."""

    def __init__(self, x=0.0, y=0.0, shape="humanoid", skills=(), tactics_pool=(), ranged=False, role=None,
                 rooted=False, **kw):
        super().__init__(x=x, y=y, **kw)
        self.shape, self.skills, self.tactics_pool = shape, list(skills), list(tactics_pool)
        self.ranged, self.role, self.rooted = ranged, role, rooted
        self.vision_range, self.attack_range = 20.0, 2.0
        self.state = "idle"

    def move_towards(self, x, y, dt):
        dx, dy = x - self.x, y - self.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            step = min(d, self.speed * dt)
            self.x += dx / d * step
            self.y += dy / d * step

    def _wander(self, dt):
        pass


def arena(rng=0.99):
    mgr = EffectManager(world=World(), abilities=load_abilities(), rng=FakeRng(rng))
    hero = Fighter(hp=500.0, atk=5.0)
    mgr.register(hero, "hero")
    return mgr, hero


def run(mgr, brain, hero, seconds, dt=0.05):
    for _ in range(int(seconds / dt)):
        mgr.update(dt)
        brain.update(hero, dt)


# ---------------------------------------------------------------- learning

def test_rust_bandit_matches_python_twin_bit_for_bit():
    if tac._RustBandit is None:
        pytest.skip("rust_core not built")
    rust, py = tac.new_bandit("rust"), tac.new_bandit("python")
    rng = random.Random(3)
    for _ in range(400):
        ctx = rng.randrange(len(tac.CONTEXTS))
        mask = [rng.random() < 0.8 for _ in tac.TACTICS]
        a, b = rust.select(ctx, mask), py.select(ctx, mask)
        assert a == b
        reward = rng.random() * 1.5
        rust.update(ctx, a, reward)
        py.update(ctx, b, reward)
    for ctx in range(len(tac.CONTEXTS)):
        assert rust.means(ctx) == pytest.approx(py.means(ctx), abs=1e-12)
    counts, sums = rust.state()
    py2 = tac.new_bandit("python")
    py2.load_state(counts, sums)
    assert py2.means(0) == pytest.approx(rust.means(0), abs=1e-12)


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_memory_learns_what_works_and_survives_restart(backend, tmp_path):
    if backend == "rust" and tac._RustBandit is None:
        pytest.skip("rust_core not built")
    path = tmp_path / "tactics.json"
    memory = tac.TacticsMemory(path, backend=backend)
    wolf = Mob(shape="beast", tactics_pool=("flank", "pack"))
    payoff = {"flank": (40.0, 5.0), "pack": (10.0, 30.0), "rush": (5.0, 40.0)}
    for _ in range(60):
        t = memory.choose(wolf)
        assert t in ("flank", "pack", "rush")          # только то, что волк умеет (+ натиск)
        dealt, taken = payoff[t]
        memory.report(wolf, t, dealt, taken, hero_died=False)
    assert memory.best("beast") == "flank"
    memory.save()
    again = tac.TacticsMemory(path, backend=backend)
    assert again.summary() == memory.summary() and again.outcomes == 60


def test_memory_path_can_be_switched_off(monkeypatch):
    monkeypatch.setenv(tac.MEMORY_ENV, "off")
    assert tac.memory_path() is None
    monkeypatch.delenv(tac.MEMORY_ENV)
    assert tac.memory_path().name == "tactics_memory.json"


def test_brain_reports_fight_outcome_to_memory():
    mgr, hero = arena()
    memory = tac.TacticsMemory(None, backend="python")
    mob = Mob(x=1.5, atk=30.0)
    mgr.register(mob, "monsters")
    brain = EnemyBrain(mob, mgr, memory)
    mgr.register_event_handler(lambda info: brain.note_hit(info, hero.entity_id))
    run(mgr, brain, hero, 3.0)
    assert brain.dealt > 0 and brain.engaged_at is not None
    tactic = brain.tactic
    reward = brain.finish(hero_died=True)
    assert reward is not None and reward > 0.5 and memory.outcomes == 1
    assert memory.summary()["humanoid"][tactic] == pytest.approx(reward, abs=0.01)


# ---------------------------------------------------------------- tactics

def test_kite_keeps_distance_and_shoots():
    mgr, hero = arena()
    spitter = Mob(x=12.0, skills=("venom_spit",), ranged=True, tactics_pool=("kite",))
    mgr.register(spitter, "monsters")
    brain = EnemyBrain(spitter, mgr)
    brain.tactic = "kite"
    run(mgr, brain, hero, 6.0)
    d = math.dist((spitter.x, spitter.y), (hero.x, hero.y))
    assert 4.5 <= d <= 7.5 and hero.health < 500


def test_ambush_waits_until_hero_comes_close():
    mgr, hero = arena()
    lurker = Mob(x=15.0, tactics_pool=("ambush",))
    mgr.register(lurker, "monsters")
    brain = EnemyBrain(lurker, mgr)
    brain.tactic = "ambush"
    run(mgr, brain, hero, 2.0)
    assert lurker.x == pytest.approx(15.0) and lurker.state == "ambush"   # видит, но ждёт
    hero.x = 7.0
    run(mgr, brain, hero, 1.0)
    assert lurker.x < 15.0


def test_everyone_steps_out_of_a_telegraphed_circle():
    mgr, hero = arena()
    mob = Mob(x=3.0)
    mgr.register(mob, "monsters")
    brain = EnemyBrain(mob, mgr)
    mgr.telegraphs.append(Telegraph(hero, {"id": "slam", "ops": []}, mob, 3.0, 0.0, 3.0, mgr.now + 5.0))
    run(mgr, brain, hero, 0.1)
    assert mob.state == "evading"                                    # круг важнее героя рядом
    run(mgr, brain, hero, 1.5)
    assert math.dist((mob.x, mob.y), (3.0, 0.0)) > 3.0


def test_boss_brain_uses_its_kit():
    mgr, hero = arena()
    kit = load_bosses()["forest_warden"]["skills"]
    boss = Mob(x=6.0, skills=kit, role="boss", hp=5000.0, atk=20.0)
    mgr.register(boss, "monsters")
    brain = EnemyBrain(boss, mgr)
    run(mgr, brain, hero, 8.0)
    used = {k for k in mgr.state(boss).cooldowns if k in kit}
    assert len(used) >= 2 and hero.health < 500


def test_rooted_boss_never_moves():
    mgr, hero = arena()
    lucifer = Mob(x=8.0, skills=load_bosses()["lucifer"]["skills"], role="final", rooted=True, hp=9000.0)
    mgr.register(lucifer, "monsters")
    brain = EnemyBrain(lucifer, mgr)
    run(mgr, brain, hero, 5.0)
    assert (lucifer.x, lucifer.y) == (8.0, 0.0)


# ---------------------------------------------------------------- range, vision, stealth

def test_attack_range_comes_from_the_weapon():
    mgr, hero = arena()
    target = Fighter(x=8.0, hp=100.0)
    mgr.register(target, "monsters")
    assert mgr.cast(hero, "weapon_attack", target).reason == "out of range"
    mgr.equip(hero, [catalog().get("hunting_bow")])
    assert mgr.range_of(hero, "weapon_attack") == pytest.approx(9.0)  # 2 + лук 7
    assert mgr.cast(hero, "weapon_attack", target).ok and target.health < 100
    assert mgr.range_of(hero, "power_strike") == pytest.approx(9.9)  # навык: 110% дальности оружия


def test_stealth_circle_hides_only_the_caster_from_those_inside():
    mgr, rogue = arena()
    rogue.health = 200.0                                             # < 60%: навык готов
    friend = Fighter(x=-10.0)
    near, far = Mob(x=10.0), Mob(x=16.0)
    for e, f in ((friend, "hero"), (near, "monsters"), (far, "monsters")):
        mgr.register(e, f)
    near.vision_range = far.vision_range = 20.0
    assert mgr.can_see(near, rogue) and mgr.can_see(far, rogue)
    assert mgr.cast(rogue, "shadow_veil").ok
    assert not mgr.can_see(near, rogue)                              # в круге 14: обзор на вора 20 -> 5
    assert mgr.can_see(near, friend) and mgr.vision_toward(near, friend) == pytest.approx(20.0)
    assert mgr.can_see(far, rogue)                                   # вне круга - видит как прежде
    for _ in range(14):
        mgr.update(0.5)
    assert mgr.can_see(near, rogue)                                  # через 6 с покров спал


def test_enemy_loses_a_stealthed_hero_and_gives_up():
    mgr, hero = arena()
    mob = Mob(x=10.0)
    mgr.register(mob, "monsters")
    brain = EnemyBrain(mob, mgr)
    brain.tactic = "rush"
    run(mgr, brain, hero, 0.2)
    assert brain.engaged_at is not None
    hero.health = 200.0
    mgr.cast(hero, "shadow_veil")
    hero.x, hero.y = 0.0, 6.0                                        # отошёл в сторону под покровом
    run(mgr, brain, hero, 5.0)
    assert brain.engaged_at is None and mob.state == "idle"


def test_smoke_bomb_is_thrown_when_no_potions_left():
    from src.gameplay.inventory import Inventory, InventoryBrain
    mgr, hero = arena()
    watcher = Mob(x=6.0)
    mgr.register(watcher, "monsters")
    inv = Inventory(hero)
    inv.add(catalog().get("smoke_bomb"))
    hero.health = 100.0
    assert InventoryBrain(inv).update(0.1, lambda it: mgr.use_item(hero, it)) == "stealth"
    assert not mgr.can_see(watcher, hero) and inv.count("smoke_bomb") == 0


def test_hero_ai_does_not_fireball_itself():
    from src.entities.character import Character

    class Game:
        render = None
    mgr = EffectManager(world=World(), abilities=load_abilities(), rng=FakeRng(0.99))
    mage = Character("m", Game(), 0, 0, 0.5, "mage", (0, 0, 1, 1), is_player=True)
    mgr.register(mage, "hero")
    Game.effect_manager = mgr
    close = Fighter(x=1.5, hp=300.0)
    mgr.register(close, "monsters")
    assert mage.game.effect_manager is mgr
    mage._use_skills_via_manager(mgr, [close])
    cds = mgr.state(mage).cooldowns
    assert "fireball" not in cds and "magic_bolt" in cds             # шар задел бы себя - стрела
    close.x = 6.0
    mgr.update(2.0)
    mage._use_skills_via_manager(mgr, [close])
    assert "fireball" in mgr.state(mage).cooldowns


# ---------------------------------------------------------------- weapon shapes

def test_sword_swings_an_arc_bow_hits_one_staff_blasts_a_circle():
    mgr, hero = arena()
    hero.physical_damage = 20.0
    front = Fighter(x=1.5, hp=100.0)
    side = Fighter(x=1.0, y=1.0, hp=100.0)             # 45 градусов - внутри дуги 110
    behind = Fighter(x=-1.5, hp=100.0)                 # сзади - вне дуги
    friend = Fighter(x=1.2, y=-0.8, hp=100.0)          # свой перед мечом - получит (френдли фаер)
    for e, f in ((front, "monsters"), (side, "monsters"), (behind, "monsters"), (friend, "hero")):
        mgr.register(e, f)
    mgr.equip(hero, [catalog().get("rusty_sword")])
    assert mgr.resolve(hero, "weapon_attack") == "sword_swing"
    assert mgr.cast(hero, "weapon_attack", front).ok
    assert front.health < 100 and side.health < 100 and friend.health < 100
    assert behind.health == 100 and hero.health == 500

    mgr2, archer = arena()
    a, b = Fighter(x=6.0, hp=100.0), Fighter(x=6.5, hp=100.0)
    mgr2.register(a, "monsters")
    mgr2.register(b, "monsters")
    mgr2.equip(archer, [catalog().get("hunting_bow")])
    assert mgr2.cast(archer, "weapon_attack", a).ok and a.health < 100 and b.health == 100

    mgr3, mage = arena()
    c, d = Fighter(x=4.0, hp=100.0), Fighter(x=5.0, hp=100.0)
    mgr3.register(c, "monsters")
    mgr3.register(d, "monsters")
    mgr3.equip(mage, [catalog().get("apprentice_staff")])
    assert mgr3.cast(mage, "weapon_attack", c).ok and c.health < 100 and d.health < 100
