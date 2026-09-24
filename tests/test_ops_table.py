"""Один интерпретатор операций схемы (src/effects/ops.py): таблица обработчиков и её два хозяина.

* таблица OP_HANDLERS покрывает каждый вид операции схемы (schema.OP_KINDS), MOD_MATH - каждый mod-оператор (schema.OPS);
* EffectRuntime.run_op и EffectManager._run_op - тонкие вызовы общего apply_op (вторых интерпретаторов нет);
* и Unit тренировочной комнаты, и сущность игры (EntityState) реализуют весь интерфейс OpHost;
* Unit и EntityState дают одинаковые ресурсы и баффы на одних и тех же случайных последовательностях операций.
"""
import inspect
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.effects import ops, schema  # noqa: E402
from src.effects.manager import EffectManager  # noqa: E402
from src.effects.runtime import EffectRuntime, Unit  # noqa: E402


def test_every_schema_op_kind_has_exactly_one_handler():
    assert set(ops.OP_HANDLERS) == set(schema.OP_KINDS)
    assert all(callable(fn) for fn in ops.OP_HANDLERS.values())
    assert len({fn for fn in ops.OP_HANDLERS.values()}) == len(ops.OP_HANDLERS)   # по одному на вид


def test_every_mod_operator_has_math():
    assert set(ops.MOD_MATH) == set(schema.OPS)
    dst: dict = {}
    ops.apply_mod_math(dst, 10.0, "strength", "mul", 1.5)
    assert dst == {"strength": 10.0 * 1.5 - 10.0}                       # base + вклад = 15
    ops.apply_mod_math(dst, 10.0, "strength", "nonsense", 3.0)          # неизвестный оператор - ничего не пишет
    assert dst == {"strength": 5.0}


@pytest.mark.parametrize("host", [EffectRuntime, EffectManager])
def test_both_hosts_implement_the_whole_op_host_interface(host):
    wanted = [n for n in vars(ops.OpHost) if n.startswith("op_")]
    assert len(wanted) >= 15
    assert [n for n in wanted if not callable(getattr(host, n, None))] == []


def test_hosts_have_no_op_interpreter_of_their_own():
    for fn in (EffectRuntime.run_op, EffectManager._run_op):
        src = inspect.getsource(fn)
        assert "apply_op" in src and 'kind == "' not in src


def test_handlers_are_small():
    """Один маленький обработчик на вид: ни один не длиннее 25 строк (было ~140 строк if/elif в двух копиях)."""
    for name, fn in ops.OP_HANDLERS.items():
        assert len(inspect.getsource(fn).splitlines()) <= 25, name


# ---------------------------------------------------------------- Unit vs EntityState on random op sequences

class Fighter:
    def __init__(self, hp=1000.0):
        self.entity_id = "hero"
        self.x = self.y = 0.0
        self.health = self.max_health = hp
        self.mana = self.max_mana = 100.0
        self.stamina = self.max_stamina = 100.0
        self.health_regen = self.mana_regen = self.stamina_regen = 0.0
        self.physical_damage, self.magical_damage = 20.0, 30.0
        self.defense, self.attack_speed = 0.0, 1.0
        self.critical_chance, self.critical_damage, self.dodge_chance = 0.0, 1.5, 0.0
        self.speed = 5.0

    def is_alive(self):
        return self.health > 0


class World:
    def entities(self):
        return []

    def spawn_summon(self, *a):
        pass


def _flat(v):
    return {"flat": round(v, 2)}


def random_ops(rng):
    """Операции, которые обе стороны понимают одинаково (цель - сам, значения flat; урон точный)."""
    ops_out = []
    for _ in range(rng.randint(1, 4)):
        kind = rng.choice(["heal", "deal", "drain", "set", "buff", "remove_buff", "extend", "deal", "heal"])
        o: dict = {"kind": kind, "target": "self"}
        if kind in ("heal", "deal", "drain", "set"):
            o["stat"] = rng.choice(["hp", "mana", "stamina"])
            o["value"] = _flat(rng.uniform(0, 300) if kind != "set" else rng.uniform(0, 1100))
        if kind == "deal":
            o["flags"] = ["true_damage", "no_crit", "unavoidable"]
        if kind == "drain" and rng.random() < 0.6:
            o["fail"] = [{"kind": "heal", "target": "self", "stat": "hp", "value": _flat(rng.uniform(1, 50))}]
        if kind in ("buff", "remove_buff", "extend"):
            o["buff_id"] = rng.choice(["b1", "b2"])
        if kind == "buff":
            o["duration"] = _flat(rng.choice([1.0, 2.5, 5.0]))
            if rng.random() < 0.4:
                o["cooldown"] = _flat(rng.choice([2.0, 6.0]))
        if kind == "extend":
            o["extend"] = {"flat": rng.choice([1.0, 3.0])}
        ops_out.append(o)
    return ops_out


@pytest.mark.parametrize("seed", range(40))
def test_unit_and_entity_state_agree_on_random_op_sequences(seed):
    rng = random.Random(seed)
    unit = Unit("hero", max_hp=1000.0)
    rt = EffectRuntime(unit, [], enemy=Unit("dummy"))
    hero = Fighter()
    mgr = EffectManager(world=World(), abilities={}, rng=random.Random(seed))
    st = mgr.register(hero, "hero")
    t = 0.0
    for step in range(rng.randint(5, 12)):
        if hero.health <= 0:
            break                       # мёртвый заклинатель в игре не кастует (в комнате ops идут дальше): сравнение до смерти
        t += rng.choice([0.0, 0.4, 1.0, 3.0])
        batch = random_ops(rng)
        rt.run_ops(batch, rt.context(), t, f"s{step}#use", event="use")
        mgr.now = t
        assert mgr.cast(hero, {"id": f"s{step}", "ops": batch}).ok
        # обе стороны снимают истёкшие баффы одинаково: сравниваем только живые
        live_unit = {b: d for b, d in unit.buffs.items() if d["until"] > t}
        live_ent = {b: d for b, d in st.unit.buffs.items() if d["until"] > t}
        assert (round(unit.current_hp, 9), round(unit.pools["mana"], 9), round(unit.pools["stamina"], 9)) == \
               (round(hero.health, 9), round(hero.mana, 9), round(hero.stamina, 9)), (seed, step, batch)
        assert {b: round(d["until"], 9) for b, d in live_unit.items()} == \
               {b: round(d["until"], 9) for b, d in live_ent.items()}, (seed, step, batch)
        assert unit.alive == (hero.health > 0)
