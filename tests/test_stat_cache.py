"""Кэш итоговых статов: EntityState.refresh пересчитывает статы, только если изменился вход (dirty-флаг).

Правило: результат с кэшем ТОТ ЖЕ, бит-в-бит, что и без него (EntityState.stat_cache = False), на любой
последовательности изменений входов и времени; при каждом изменении входа кэш действительно сбрасывается;
временный слой (external) истекает в тот же кадр, что и раньше. Входы: поля сущности (прокачка, реген),
очки характеристик, надетое, временные моды, перки/эффекты, Unit.base / Unit.mods, правила статов.
"""
import math
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.effects import runtime  # noqa: E402
from src.effects.manager import EffectManager, EntityState  # noqa: E402
from src.effects.ops import Tracked  # noqa: E402
from src.effects.runtime import Unit  # noqa: E402

STAT_FIELDS = ("max_health", "max_mana", "max_stamina", "health_regen", "mana_regen", "stamina_regen", "physical_damage",
               "magical_damage", "defense", "attack_speed", "critical_chance", "critical_damage", "dodge_chance",
               "speed", "move_speed", "attack_range", "vision_range", "health", "mana", "stamina", "lifesteal")


class Fighter:
    def __init__(self, n, x=0.0, hp=300.0):
        self.entity_id = f"f{n}"
        self.x, self.y = x, 0.0
        self.health = self.max_health = hp
        self.mana = self.max_mana = 100.0
        self.stamina = self.max_stamina = 100.0
        self.health_regen, self.mana_regen, self.stamina_regen = 1.0, 0.5, 0.25
        self.physical_damage, self.magical_damage = 20.0, 30.0
        self.defense, self.attack_speed = 2.0, 1.0
        self.critical_chance, self.critical_damage, self.dodge_chance = 0.05, 1.5, 0.0
        self.speed = 5.0
        self.attributes = {"strength": 3.0, "agility": 1.0}

    def is_alive(self):
        return self.health > 0


class Item:
    slot = "armor"

    def __init__(self, stats, effects=()):
        self.stats, self.effects = stats, list(effects)


class World:
    def entities(self):
        return []

    def spawn_summon(self, *a):
        pass


DEBUFF = {"id": "dbf", "range": 30.0, "ops": [
    {"kind": "mod", "target": "enemy", "stat": "defense", "op": "add", "value": {"flat": -1.5}, "duration": {"flat": 2.0}}]}
PERK = {"id": "perk.t", "trigger": {"kind": "passive"},
        "ops": [{"kind": "mod", "target": "self", "stat": "strength", "op": "add", "value": {"flat": 3.0}}]}


def fields(e):
    return tuple(repr(getattr(e, f, None)) for f in STAT_FIELDS)


class Rig:
    """Одна и та же сцена дважды: с кэшем и без него (stat_cache = False на каждом состоянии)."""

    def __init__(self, cached):
        self.mgr = EffectManager(world=World(), abilities={"dbf": DEBUFF}, rng=random.Random(7))
        self.hero, self.enemy = Fighter(1), Fighter(2, x=1.0)
        self.states = [self.mgr.register(e, "hero" if e is self.hero else "monsters") for e in (self.hero, self.enemy)]
        for st in self.states:
            st.stat_cache = cached
        self.pulls = 0
        st0 = self.states[0]
        real = st0.pull

        def counting(now, base=None):
            self.pulls += 1
            return real(now, base)
        st0.pull = counting

    @property
    def st(self):
        return self.states[0]

    def snapshot(self):
        return fields(self.hero) + fields(self.enemy)


def twin(mutation, refresh_at=None):
    """Применить мутацию к обеим сценам и вернуть (с кэшем, без кэша)."""
    rigs = Rig(True), Rig(False)
    for rig in rigs:
        for _ in range(3):                   # прогрев: у кэшированной сцены кэш уже построен
            rig.mgr.update(0.5)
        rig.pulls = 0
        mutation(rig)
        rig.st.refresh(rig.mgr.now if refresh_at is None else refresh_at)
    return rigs


MUTATIONS = {
    "entity field (level up)": lambda r: setattr(r.hero, "physical_damage", r.hero.physical_damage + 7.0),
    "max_health": lambda r: setattr(r.hero, "max_health", r.hero.max_health + 50.0),
    "regen field": lambda r: setattr(r.hero, "mana_regen", 3.0),
    "attribute points": lambda r: r.hero.attributes.__setitem__("strength", 5.0),
    "new attribute point": lambda r: r.hero.attributes.__setitem__("wisdom", 4.0),
    "field appears (vision_range)": lambda r: setattr(r.hero, "vision_range", 33.0),
    "field appears (attack_range)": lambda r: setattr(r.hero, "attack_range", 4.5),
    "speed name switch": lambda r: (delattr(r.hero, "speed"), setattr(r.hero, "move_speed", 9.0)),
    "equipment": lambda r: r.mgr.equip(r.hero, [Item({"strength": 4, "defense": 1.0})]),
    "equipment removed": lambda r: (r.mgr.equip(r.hero, [Item({"strength": 4})]), r.mgr.equip(r.hero, [])),
    "temporary mod (external layer)": lambda r: r.st.external.__setitem__(("x", "dbf", 0), (r.mgr.now + 5.0, {"defense": 3.0})),
    "perk effect": lambda r: r.mgr.set_perks(r.hero, [PERK]),
    "debuff cast": lambda r: r.mgr.cast(r.enemy, "dbf", r.hero),
    "Unit.base write": lambda r: r.st.unit.base.__setitem__("strength", 99.0),
    "Unit.mods write": lambda r: r.st.unit.mods.__setitem__("defense", 5.0),
}


@pytest.mark.parametrize("name", list(MUTATIONS))
def test_every_input_change_invalidates_the_cache_and_matches_the_uncached_result(name):
    cached, plain = twin(MUTATIONS[name])
    assert cached.snapshot() == plain.snapshot(), name
    assert cached.pulls >= 1, f"{name}: stale cache (stats were not recomputed)"
    cached.mgr.update(0.5)
    plain.mgr.update(0.5)
    assert cached.snapshot() == plain.snapshot(), name


def test_unchanged_inputs_are_served_from_the_cache():
    rig = Rig(True)
    for _ in range(5):
        rig.mgr.update(0.5)
    rig.pulls = 0
    cache = rig.st._cache
    assert cache is not None
    before = rig.snapshot()
    for _ in range(20):
        rig.mgr.update(0.25)                 # реген меняет ресурсы, но не входы статов
    assert rig.pulls == 0 and rig.st._cache is cache
    assert fields(rig.hero)[:15] == before[:15]


def test_rules_reload_invalidates_the_cache():
    rig = Rig(True)
    rig.mgr.update(0.5)
    old = rig.st._cache
    runtime.rules.cache_clear()
    rig.pulls = 0
    rig.st.refresh(rig.mgr.now)
    assert rig.pulls == 1 and rig.st._cache is not old


def test_temporary_layer_expires_on_the_exact_boundary():
    """Время - вход кэша: слой действует, пока until > now. Прямой refresh (без update) вокруг границы."""
    cached, plain = Rig(True), Rig(False)
    for rig in (cached, plain):
        rig.mgr.update(0.5)
        assert rig.mgr.cast(rig.hero, "dbf", rig.enemy).ok           # until = 0.5 + 2.0
    until = cached.mgr.now + 2.0
    assert cached.enemy.defense == plain.enemy.defense == 0.5        # 2.0 - 1.5
    for now in (0.75, 1.5, until - 1e-9, until, until + 1e-9, until + 1.0):
        for rig in (cached, plain):
            rig.states[1].refresh(now)
        assert fields(cached.enemy) == fields(plain.enemy), now
        assert (cached.enemy.defense == 2.0) == (now >= until), now


def test_update_removes_the_layer_in_the_same_frame_as_without_the_cache():
    seen = []
    for cached in (True, False):
        rig = Rig(cached)
        assert rig.mgr.cast(rig.hero, "dbf", rig.enemy).ok           # now = 0: until = 2.0
        seen.append([(rig.mgr.update(0.5), rig.enemy.defense)[1] for _ in range(7)])
    assert seen[0] == seen[1] == [0.5, 0.5, 0.5, 2.0, 2.0, 2.0, 2.0]   # на now == until слоя уже нет


def test_stat_cache_is_bit_identical_on_random_change_sequences():
    hits = 0
    for seed in range(40):
        rng = random.Random(seed)
        rigs = Rig(True), Rig(False)
        script = [(rng.choice(list(MUTATIONS) + ["tick"] * 6), rng.uniform(0.05, 1.5)) for _ in range(30)]
        for name, dt in script:
            for rig in rigs:
                if name == "tick":
                    rig.mgr.update(dt)
                else:
                    try:
                        MUTATIONS[name](rig)
                    except AttributeError:      # мутация уже применена (поле удалено раньше)
                        pass
                    rig.mgr.update(0.0)
            assert rigs[0].snapshot() == rigs[1].snapshot(), (seed, name)
        hits += rigs[0].st._cache is not None
    assert hits > 0


# ---------------------------------------------------------------- Unit: dirty flag + memo of _eff

def test_tracked_dict_bumps_the_owner_version_on_every_mutator():
    class Owner:
        version = 0

        def touch(self):
            self.version += 1

    o = Owner()
    d = Tracked(o, {"a": 1.0})
    for op in (lambda: d.__setitem__("b", 2.0), lambda: d.__delitem__("b"), lambda: d.update(c=3.0), lambda: d.pop("c"),
               lambda: d.setdefault("z", 0.0), lambda: d.popitem(), lambda: d.__ior__({"q": 1.0}), lambda: d.clear()):
        before = o.version
        op()
        assert o.version > before
    before = o.version
    d.get("a"), list(d), len(d)
    assert o.version == before


def test_unit_eff_follows_every_write_and_equals_the_direct_formula():
    u = Unit("hero", derive=True)
    v0 = u.version
    assert u._eff("strength") == u._eff_calc("strength")
    u.base["strength"] = 100.0                       # прямая запись в базу (так делают тесты)
    assert u.version > v0 and u._eff("strength") == 100.0 == u._eff_calc("strength")
    assert u._eff("attack_damage") == u._eff_calc("attack_damage") == pytest.approx(60.0)   # сила -> урон
    u.mods["strength"] = 20.0
    assert u._eff("strength") == 120.0 and u._eff("attack_damage") == pytest.approx(72.0)
    u.mods = {"strength": -10.0}
    assert u._eff("strength") == 90.0
    u.base = {"strength": 1.0}                       # база заменена целиком, моды остались
    assert u._eff("strength") == -9.0
    u.mods.clear()
    assert u._eff("strength") == 1.0


def test_unit_mods_assignment_with_same_content_keeps_the_cache_but_zero_sign_does_not():
    u = Unit("hero")
    u.mods = {"strength": 5.0}
    v = u.version
    u.mods = {"strength": 5.0}
    assert u.version == v                             # то же содержимое: входы не менялись
    u.mods = {"strength": 0.0}
    v = u.version
    u.mods = {"strength": -0.0}
    assert u.version > v and math.copysign(1.0, u.mods["strength"]) == -1.0   # знак нуля - тоже изменение


def test_unit_eff_memo_is_bit_identical_to_the_direct_formula():
    rng = random.Random(3)
    u = Unit("hero", derive=True)
    stats = ["strength", "agility", "vitality", "max_hp", "crit_chance", "aspd", "attack_damage", "dodge", "move_speed"]
    for _ in range(300):
        stat = rng.choice(stats)
        target = rng.choice([u.base, u.mods])
        target[stat] = rng.uniform(-50, 200)
        for key in stats:
            assert repr(u._eff(key)) == repr(u._eff_calc(key))
    assert u.stat("hp_pct") == pytest.approx(u.current_hp / u._eff("max_hp") * 100.0)


def test_entity_state_is_a_plain_python_class_with_a_version():
    st = EntityState(Fighter(9), "hero")
    v = st.version
    st.equipment_stats["strength"] = 1.0
    st.external[("a", "b", 0)] = (1.0, {"defense": 1.0})
    assert st.version == v + 2
    st.external = {}                                   # присваивание словаря - тоже изменение входа
    assert st.version == v + 3 and isinstance(st.external, Tracked)
