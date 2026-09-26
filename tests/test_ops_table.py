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


# ---------------------------------------------------------------- pseudo-stats and the damage_taken host primitive

def test_hp_missing_below_is_one_family_for_values_and_predicates():
    """`hp_missing_below_<N>` = сколько % HP не хватает до порога N (0..N): ОДНО место (ops.derived_ctx) для значений
    (scale/amplify `of`) и для предикатов условий. Порог 35 (Gojo, cursed_relics.lua) раньше падал KeyError в симуляции."""
    from src.effects.runtime import compile_pred
    ctx = {"hp_pct": 20.0}
    assert ops.ctx_get(ctx, "hp_missing_below_40") == 20.0 and ops.ctx_get(ctx, "hp_missing_below_35") == 15.0
    assert ops.ctx_get({"hp_pct": 90.0}, "hp_missing_below_35") == 0.0            # выше порога - 0, не отрицательное
    assert ops.ctx_get({"hp_missing_below_35": 3.0, "hp_pct": 20.0}, "hp_missing_below_35") == 3.0   # готовое поле ctx главнее
    assert compile_pred("ctx.hp_missing_below_35 >= 15")(ctx) and not compile_pred("ctx.hp_missing_below_35 > 15")(ctx)
    with pytest.raises(KeyError, match="unknown ctx field"):
        ops.ctx_get(ctx, "hp_missing_above_35")                                  # семейство узкое: чужие имена по-прежнему ошибка
    from tools.effect_schema.validate import validate_op
    assert schema.is_stat("hp_missing_below_35") and schema.is_stat("enemy_hp_missing_below_35") and not schema.is_stat("hp_missing_above_35")
    assert validate_op({"kind": "mod", "stat": "strength", "op": "add", "value": {"flat": 1},
                        "scale": {"every": 10, "of": "hp_missing_below_35", "value": {"flat": 1}}}, "op") == []
    assert any("read-only" in e for e in validate_op({"kind": "mod", "stat": "hp_missing_below_35", "op": "add", "value": {"flat": 1}}, "op"))


def test_damage_taken_primitive_on_both_hosts():
    """`_damage_dealt_to` (порог damage_total адаптации Махораги) зовёт op_damage_taken - его обязаны иметь ОБА хозяина."""
    from src.effects.manager import HitInfo
    from src.effects.ops import OpCall
    mgr = EffectManager(world=World(), abilities={}, rng=random.Random(1))
    st = mgr.register(Fighter(), "hero")
    hits = [HitInfo("boss", "hero", 7.0), HitInfo("boss", "someone_else", 3.0), HitInfo("boss", "hero", 1.5)]
    assert mgr.op_damage_taken(OpCall(ctx={}, src="x", t=0.0, hits=hits), st) == 8.5      # только попадания ПО ЭТОЙ цели
    assert mgr.op_damage_taken(OpCall(ctx={}, src="x", t=0.0), st) == 0.0                 # hits=None: ничего не нанесено
    unit = Unit("hero", max_hp=1000.0)
    rt = EffectRuntime(unit, [], enemy=Unit("dummy"))
    assert rt.op_damage_taken(OpCall(ctx={"last_damage": 4.5}, src="x", t=0.0), unit) == 4.5


def test_adapt_op_runs_on_both_hosts():
    """adapt: подпись феномена -> колесо +1; путь через op_damage_taken/op_adaptation не падает ни в комнате, ни в игре."""
    op = {"kind": "adapt", "target": "self", "threshold": {"damage_total": 5}, "phenomenon": {"damage_type": "fire"}}
    unit = Unit("hero", max_hp=1000.0)
    rt = EffectRuntime(unit, [], enemy=Unit("dummy"))
    ctx = rt.context()
    ctx["last_damage"] = 9.0
    rt.run_ops([op], ctx, 1.0, "s#use", event="use")
    assert unit.external["mahoraga"]["wheel"] == 1
    mgr = EffectManager(world=World(), abilities={}, rng=random.Random(1))
    st = mgr.register(Fighter(), "hero")
    mgr.now = 1.0
    assert mgr.cast(st.entity, {"id": "s", "ops": [op]}).ok
    assert st.unit.external["mahoraga"]["wheel"] == 1


def test_every_op_note_has_a_training_room_log_line():
    """op_note(cx, "<что>", ...) в ops.py: у тренировочной комнаты на каждое <что> обязана быть строка лога (иначе KeyError на
    первой же такой операции - так падали adapt/use_learned_technique/колесо Махораги)."""
    import re
    used = set(re.findall(r'op_note\(cx, "([a-z_]+)"', inspect.getsource(ops)))
    from src.effects.runtime import _NOTES
    assert len(used) > 30 and sorted(used - set(_NOTES)) == []


def test_every_primitive_op_runs_on_the_game_manager():
    """Кузница (tools/effect_schema/forge.primitive_effects) держит по одной операции на каждый kind боевых примитивов и
    Махораги; в комнате их гоняет itemcheck (sim), здесь - тот же набор на менеджере игры (цель self: без мира)."""
    from tools.effect_schema.forge import primitive_effects
    hero = Fighter()
    mgr = EffectManager(world=World(), abilities={}, rng=random.Random(1))
    mgr.register(hero, "hero")
    mgr.now = 1.0
    kinds = set()
    for ef in primitive_effects():
        for o in ef["ops"]:
            kinds.add(o["kind"])
            assert mgr.cast(hero, {"id": f"{ef['id']}.{o['kind']}", "ops": [dict(o, target="self")]}).ok, o["kind"]
    classic = {"mod", "heal", "drain", "deal", "set", "buff", "extend", "remove_buff", "apply_effect", "kill", "summon", "move"}
    assert kinds == set(schema.OP_KINDS) - classic                      # новый kind схемы -> строка в primitive_effects


def test_mahoraga_spec_edges_that_used_to_crash():
    """Три края спецификации Махораги, на которых обработчики падали: литеральная id_formula (3 цели распаковки из 2 частей),
    purge со строковым фильтром (`str.get`) и threshold.custom (аргументы ctx_get были переставлены)."""
    from src.effects.ops import OpCall
    cx = OpCall(ctx={}, src="hero", t=0.0)
    spec = {"phenomenon": {"id_formula": "damage_type..':'..technique_id", "damage_type": "fire", "technique_id": "cleave"}}
    assert ops._phenomenon_signature(spec, cx) == "fire:cleave"
    assert ops._phenomenon_signature({"phenomenon": {"id_formula": "damage_type..':'..technique_id", "damage_type": "fire"}}, cx) == "fire:basic"
    assert ops._phenomenon_signature({"phenomenon": {"damage_type": "fire", "technique_id": "x", "source_flag": ["b", "a"]}}, cx) == "fire:x#a+b"

    unit = Unit("hero", max_hp=1000.0)
    rt = EffectRuntime(unit, [], enemy=Unit("dummy"))
    for filt in ("debuff", {"kind": "debuff"}):
        unit.buffs.update({"debuff_slow": {"until": 99.0}, "haste": {"until": 99.0}, "block:heal": {"until": 99.0}})
        rt.run_ops([{"kind": "purge", "target": "self", "filter": filt}], rt.context(), 1.0, "s#use", event="use")
        assert sorted(unit.buffs) == ["haste"], filt
        unit.buffs.clear()

    st = {"wheel": 2, "progress": {"fire:x": 1}}
    assert ops._threshold_ok({"custom": "ctx.wheel >= 2"}, "fire:x", 0.0, st, {})
    assert not ops._threshold_ok({"custom": "ctx.wheel >= 3"}, "fire:x", 0.0, st, {})
    assert not ops._threshold_ok({"hits": 2}, "fire:x", 0.0, st, {}) and ops._threshold_ok({"hits": 1, "wheel_min": 2}, "fire:x", 0.0, st, {})
    assert not ops._threshold_ok({"damage_total": 10}, "fire:x", 4.0, st, {}) and ops._threshold_ok({"damage_total": 10}, "fire:x", 10.0, st, {})
