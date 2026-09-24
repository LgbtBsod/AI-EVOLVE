#!/usr/bin/env python3
"""
Training-room test for Effect Schema v1 (Effect -> Ops[]).

Создаёт манекены (sim.Unit), экипирует предметами из catalog
(tools.effect_schema.catalog), прогоняет атаку / исцеление / смертельный
дрэйн через sim.EffectRuntime и сравнивает результат с аналитическими
значениями, посчитанными вручную по формулам схемы:

    value = flat | pct/100 * ctx[of or stat]
    total = value + floor(ctx[scale.of]/scale.every) * scale.value * factor

Дополнительно проверяется полный цикл UI-логики (tools.effect_schema.ui_logic):
    форма -> build_item_json -> validate -> render Lua -> lupa load
          -> round-trip парсер -> sim (тренировочная комната).

Запуск:  pytest tests/test_training_room_effectschema.py -v
      или python tests/test_training_room_effectschema.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.effect_schema.catalog import CATALOG, get_template, template_names  # noqa: E402
from tools.effect_schema.lua_gen import render_item  # noqa: E402
from tools.effect_schema.lua_parse import parse_lua  # noqa: E402
from tools.effect_schema import sim, ui_logic  # noqa: E402
from tools.effect_schema.sim import EffectRuntime, Unit  # noqa: E402
from tools.effect_schema.validate import validate_item  # noqa: E402

TOL = 1e-6


def equip(*effect_ids) -> tuple[Unit, Unit, EffectRuntime]:
    """Герой + манекен, герой «экипирован» предметом из каталога."""
    hero = Unit("hero", max_hp=1000.0)
    dummy = Unit("mannequin", max_hp=5000.0)
    effects = [get_template(t).to_json() for t in effect_ids]
    rt = EffectRuntime(hero, effects, enemy=dummy)
    rt.refresh_passives()
    return hero, dummy, rt


class TestSchemaValidation(unittest.TestCase):
    """Все шаблоны каталога проходят валидатор."""

    def test_catalog_templates_validate(self):
        for tid in CATALOG:
            ef = get_template(tid).to_json()
            errs = validate_item({"effects": [ef]})
            self.assertEqual(errs, [], f"{tid}: {errs}")


class TestHealthPotionRoom(unittest.TestCase):
    """Банка хила: +40 HP разово на событии use (тренировочная комната)."""

    def test_heal_on_use(self):
        hero, dummy, rt = equip("health_potion")
        hero.current_hp = 500.0                      # потренировали урон
        expected = min(1000.0, 500.0 + 40.0)         # аналитика: flat=40
        rt.fire_event("use")
        self.assertAlmostEqual(hero.current_hp, expected, delta=TOL)

    def test_heal_caps_at_max(self):
        hero, dummy, rt = equip("health_potion")
        hero.current_hp = 990.0
        rt.fire_event("use")
        self.assertAlmostEqual(hero.current_hp, 1000.0, delta=TOL)

    def test_no_heal_without_use(self):
        hero, dummy, rt = equip("health_potion")
        hero.current_hp = 500.0
        rt.fire_event("attack")                      # не то событие
        self.assertAlmostEqual(hero.current_hp, 500.0, delta=TOL)


class TestBerserkPassiveRoom(unittest.TestCase):
    """Lost My Self: condition-моды при hp_pct < 40 со скейлом от hp_missing_below_40."""

    def test_inactive_above_threshold(self):
        hero, dummy, rt = equip("lost_my_self")
        hero.base["strength"] = 100.0
        hero.current_hp = 500.0                      # 50% >= 40 -> выключено
        rt.refresh_passives()
        self.assertAlmostEqual(hero._eff("strength"), 100.0, delta=1e-4)
        self.assertEqual(hero.mods.get("crit_chance", 0.0), 0.0)

    def test_boundary_40pct_inactive(self):
        # условие строго `< 40`, ровно 40% — выключено
        hero, dummy, rt = equip("lost_my_self")
        hero.base["strength"] = 100.0
        hero.current_hp = 400.0
        rt.refresh_passives()
        self.assertAlmostEqual(hero._eff("strength"), 100.0, delta=1e-4)

    def test_just_below_40_steps_zero(self):
        # hp=390: hp_pct=39 -> активно; missing_below_40=1 -> steps=floor(1/10)=0
        hero, dummy, rt = equip("lost_my_self")
        hero.base["strength"] = 100.0
        hero.base["crit_chance"] = 100.0
        hero.current_hp = 390.0
        rt.refresh_passives()
        ctx = hero.ctx()
        self.assertAlmostEqual(ctx["hp_missing_below_40"], 1.0, delta=TOL)
        # только базовые проценты, скейл-шагов нет
        self.assertAlmostEqual(hero._eff("strength"), 120.0, delta=1e-4)     # +20% of strength
        self.assertAlmostEqual(hero._eff("crit_chance"), 105.0, delta=1e-4)  # +5% of crit
        self.assertAlmostEqual(hero._eff("hp_regen"), 0.0, delta=1e-4)       # flat0 + 0*20

    def test_scaling_at_10pct_hp(self):
        # hp=100: hp_pct=10 -> missing_below_40 = 30 -> steps = 3
        hero, dummy, rt = equip("lost_my_self")
        hero.base.update({"strength": 100.0, "stamina": 100.0,
                          "crit_chance": 100.0, "aspd": 1.0})
        hero.current_hp = 100.0
        rt.refresh_passives()
        ctx = hero.ctx()
        steps = int(30 // 10)                        # аналитика шагов
        self.assertAlmostEqual(ctx["hp_missing_below_40"], 30.0, delta=TOL)
        self.assertEqual(steps, 3)
        self.assertAlmostEqual(hero._eff("strength"),
                               100.0 + 0.20 * 100.0, delta=1e-4)
        self.assertAlmostEqual(hero._eff("stamina"),
                               100.0 + 0.10 * 100.0, delta=1e-4)
        # crit_chance: add pct=5 + scale every=10 val pct=5
        self.assertAlmostEqual(hero._eff("crit_chance"),
                               100.0 + 0.05 * 100.0 + steps * 0.05 * 100.0,
                               delta=1e-4)
        # aspd: add pct=5 + scale every=10 val pct=10
        self.assertAlmostEqual(hero._eff("aspd"),
                               1.0 + 0.05 * 1.0 + steps * 0.10 * 1.0,
                               delta=1e-4)
        # hp_regen: flat 0 + steps * flat 20
        self.assertAlmostEqual(hero._eff("hp_regen"), steps * 20.0, delta=1e-4)


class TestBloodPriceAttackRoom(unittest.TestCase):
    """lost_my_self.attack: drain 0.5% max_hp (+0.5%/шаг) и deal 1.5% (+1.5%/шаг)."""

    def test_attack_drain_and_deal_at_full_parent_off(self):
        # родитель (condition) неактивен на полном HP -> sub-effect не стреляет
        hero, dummy, rt = equip("lost_my_self", "lost_my_self.attack")
        before_e = dummy.current_hp
        rt.fire_event("attack")
        self.assertAlmostEqual(hero.current_hp, 1000.0, delta=TOL)
        self.assertAlmostEqual(dummy.current_hp, before_e, delta=TOL)

    def test_attack_at_10pct_hp(self):
        hero, dummy, rt = equip("lost_my_self", "lost_my_self.attack")
        hero.current_hp = 100.0                      # steps = 3
        rt.refresh_passives()
        steps = int(max(0.0, 40.0 - 10.0) // 10)     # аналитика: 3
        drain = (0.5 + 0.5 * steps) / 100.0 * 1000.0  # = 20.0
        dmg = (1.5 + 1.5 * steps) / 100.0 * 1000.0    # = 60.0
        rt.fire_event("attack")
        self.assertAlmostEqual(hero.current_hp, 100.0 - drain, delta=TOL)
        self.assertAlmostEqual(dummy.current_hp, 5000.0 - dmg, delta=TOL)

    def test_lethal_drain_triggers_fail_branch(self):
        """Смертельный дрэйн: cost > current_hp -> set hp=1 + buff last_will."""
        hero, dummy, rt = equip("lost_my_self", "lost_my_self.attack")
        hero.current_hp = 5.0                        # steps=3, drain=20 > 5
        rt.refresh_passives()
        rt.fire_event("attack")
        self.assertTrue(hero.alive)
        self.assertAlmostEqual(hero.current_hp, 1.0, delta=TOL)
        self.assertIn("last_will", hero.buffs)
        # duration base=5, scale every=10 of hp_missing_below_40 value flat=5 factor=2
        # аналитика: 5 + floor(30/10) * 5 * 2 = 35
        steps = int(max(0.0, 40.0 - hero.stat("hp_pct")) // 10)
        expected_until = 5.0 + steps * 5.0 * 2.0
        self.assertEqual(steps, 3)
        self.assertAlmostEqual(hero.buffs["last_will"]["until"],
                               expected_until, delta=TOL)
        self.assertAlmostEqual(hero.buffs["last_will"]["cooldown"], 30.0, delta=TOL)
        # deal-оп идёт ПОСЛЕ fail-ветки: hp уже 1, но deal бьёт по врагу
        dmg = (1.5 + 1.5 * 3) / 100.0 * 1000.0
        self.assertAlmostEqual(dummy.current_hp, 5000.0 - dmg, delta=TOL)

    def test_last_will_cooldown_blocks_reapply(self):
        """Повторный щит раньше cooldown=30с не ставится."""
        hero, dummy, rt = equip("lost_my_self", "lost_my_self.attack")
        hero.current_hp = 5.0
        rt.refresh_passives()
        rt.fire_event("attack")
        first_until = hero.buffs["last_will"]["until"]
        hero.current_hp = 5.0
        rt.fire_event("attack", t=10.0)              # 10 - 0 < 30 -> кулдаун
        self.assertAlmostEqual(hero.buffs["last_will"]["until"],
                               first_until, delta=TOL)
        self.assertTrue(any("ON COOLDOWN" in l for l in rt.log))

    def test_last_will_extend_on_kill(self):
        hero, dummy, rt = equip("lost_my_self", "lost_my_self.attack")
        hero.current_hp = 5.0
        rt.refresh_passives()
        rt.fire_event("attack")                      # fail -> last_will until=35
        b = hero.buffs["last_will"]
        # extend-правило висит на баффе ({on:"kill", flat:5}); движок вызывает
        # ops extend на событии kill — продление на 5с:
        ext_op = {"kind": "extend", "target": "self", "buff_id": "last_will",
                  "extend": {"on": "kill", "flat": 5}}
        until0 = b["until"]
        rt.run_ops([ext_op], hero.ctx(), t=until0 - 1.0, src="test#kill")
        self.assertAlmostEqual(hero.buffs["last_will"]["until"],
                               until0 + 5.0, delta=TOL)
        # и НЕ продлевается на нерелевантном событии (on=kill mismatch)
        rt.run_ops([ext_op], hero.ctx(), t=until0 - 1.0, src="test#attack")
        self.assertAlmostEqual(hero.buffs["last_will"]["until"],
                               until0 + 5.0, delta=TOL)

    def test_buff_expiry_via_tick(self):
        hero, dummy, rt = equip("lost_my_self", "lost_my_self.attack")
        hero.current_hp = 5.0
        rt.refresh_passives()
        rt.fire_event("attack")
        self.assertIn("last_will", hero.buffs)
        until = hero.buffs["last_will"]["until"]     # 35 по аналитике
        self.assertAlmostEqual(until, 35.0, delta=TOL)
        rt.tick(t=until + 1.0, dt=0.0)               # past until
        self.assertNotIn("last_will", hero.buffs)


class TestLuaPipelineRoom(unittest.TestCase):
    """Полный цикл: catalog -> render_item(Lua) -> lupa load -> sim-прогон."""

    @classmethod
    def setUpClass(cls):
        try:
            import lupa
            cls.lupa = lupa
        except ImportError:
            cls.lupa = None

    def _load_lua_effects(self, lua_text: str) -> list[dict]:
        data = parse_lua(lua_text)                   # собственный парсер round-trip
        self.assertIsInstance(data, dict)
        return data["effects"]

    def test_render_parses_back_to_same_json(self):
        for tid in ("health_potion", "lost_my_self", "lost_my_self.attack"):
            ef = get_template(tid).to_json()
            lua = render_item({"name": tid}, [ef])
            back = self._load_lua_effects(lua)[0]
            self.assertEqual(back.get("id"), ef["id"], tid)
            self.assertEqual(len(back.get("ops", [])), len(ef["ops"]), tid)
            # значения ops должны совпасть после round-trip (числовые поля)
            for a, b in zip(ef["ops"], back["ops"]):
                self.assertEqual(a["kind"], b["kind"], tid)
                for k in ("target", "stat", "op", "buff_id"):
                    if k in a:
                        self.assertEqual(b.get(k), a[k], f"{tid}:{k}")
                if isinstance(a.get("value"), dict):
                    self.assertEqual(b.get("value"), a["value"], f"{tid}:value")
                if isinstance(a.get("scale"), dict):
                    self.assertEqual(b.get("scale"), a["scale"], f"{tid}:scale")
                if a.get("fail"):
                    self.assertEqual(b.get("fail"), a["fail"], f"{tid}:fail")
                if a.get("duration"):
                    self.assertEqual(b.get("duration"), a["duration"], tid)
                if a.get("extend"):
                    self.assertEqual(b.get("extend"), a["extend"], tid)

    def test_lupa_load_validates_syntax(self):
        if self.lupa is None:
            self.skipTest("lupa not installed")
        item = {"name": "Sorrow of Berserk", "slot": "amulet"}
        effs = [get_template("lost_my_self"), get_template("lost_my_self.attack")]
        lua = render_item(item, effs)
        rt = self.lupa.LuaRuntime()
        tbl = rt.execute(lua)                        # синтаксис Lua 5.x валиден
        py = ui_logic._lua_to_py(rt, tbl)
        self.assertEqual(py["name"], "Sorrow of Berserk")
        self.assertEqual(len(py["effects"]), 2)
        self.assertEqual(py["effects"][0]["id"], "lost_my_self")
        self.assertEqual(len(py["effects"][1]["ops"]), 2)
        # предикат из Lua: строка вида "ctx.hp_pct < 40" (round-trip) или
        # callable, если lupa-таблица была materialized с функцией
        when = parse_lua(lua)["effects"][0]["trigger"]["when"]
        self.assertTrue(callable(when) or isinstance(when, str))
        if isinstance(when, str):
            self.assertTrue(sim.eval_pred(when, {"hp_pct": 50.0}) is False)
            self.assertTrue(sim.eval_pred(when, {"hp_pct": 39.0}))
        else:
            self.assertFalse(when({"hp_pct": 50.0}))
            self.assertTrue(when({"hp_pct": 39.0}))

    def test_sim_runs_on_roundtripped_lua_effects(self):
        """Манекены вооружаем эффектами, загруженными ИЗ Lua, а не из Python-JSON."""
        item = {"name": "berserk set"}
        lua = render_item(item, [get_template("lost_my_self"),
                                 get_template("lost_my_self.attack")])
        effects = self._load_lua_effects(lua)
        hero = Unit("hero", max_hp=1000.0)
        dummy = Unit("dummy", max_hp=5000.0)
        rt = EffectRuntime(hero, effects, enemy=dummy)
        hero.current_hp = 100.0
        rt.refresh_passives()
        rt.fire_event("attack")
        drain = (0.5 + 0.5 * 3) / 100.0 * 1000.0
        dmg = (1.5 + 1.5 * 3) / 100.0 * 1000.0
        self.assertAlmostEqual(hero.current_hp, 100.0 - drain, delta=TOL)
        self.assertAlmostEqual(dummy.current_hp, 5000.0 - dmg, delta=TOL)


class TestUiLogicFullCycle(unittest.TestCase):
    """Цикл UI-логики: форма -> JSON -> validate -> Lua -> lupa -> sim."""

    def _form_from_template(self, tid: str) -> dict:
        """Форма билдера из шаблона каталога (как если бы юзер всё набрал руками)."""
        ef = get_template(tid).to_json()

        def op_form(o):
            # форма: пустые строки/отсутствующие поля -> None в ui_logic
            f = {"kind": o["kind"], "target": o.get("target", "self"),
                 "stat": o.get("stat", ""), "op": o.get("op", ""),
                 "value": o.get("value") or {}, "when": o.get("when", ""),
                 "buff_id": o.get("buff_id", ""), "flags": o.get("flags", [])}
            if o.get("scale"):
                s = dict(o["scale"])
                s["value"] = s.get("value") or {}
                f["scale"] = s
            if o.get("fail"):
                f["fail"] = [op_form(x) for x in o["fail"]]
            if o.get("duration"):
                f["duration"] = o["duration"]
            if o.get("cooldown"):
                f["cooldown"] = o["cooldown"]
            if o.get("extend"):
                f["extend"] = o["extend"]
            return f

        tr = ef.get("trigger", {})
        when = tr.get("when", "")
        return {"id": ef["id"], "tags": ef.get("tags", []),
                "trigger": {"kind": tr.get("kind", "passive"),
                            "event": tr.get("event", ""),
                            "when": when if isinstance(when, str) else "",
                            "owner_has": tr.get("owner_has", "")},
                "ops": [op_form(o) for o in ef["ops"]]}

    def test_health_potion_full_cycle(self):
        form = {"name": "Health Potion", "description": "+40 HP",
                "effects": [self._form_from_template("health_potion")]}
        out = ui_logic.full_cycle(form, scenario={"hero_hp": 500.0,
                                                  "events": ["use"]})
        self.assertEqual(out["errors"], [])
        self.assertTrue(out.get("lupa_ok") in (True, None))
        step = out["room"]["steps"][0]
        self.assertAlmostEqual(step["hero_hp"], 540.0, delta=TOL)

    def test_berserk_set_full_cycle_matches_analytics(self):
        form = {"name": "Sorrow of Berserk",
                "effects": [self._form_from_template("lost_my_self"),
                            self._form_from_template("lost_my_self.attack")]}
        out = ui_logic.full_cycle(form, scenario={
            "hero_hp": 100.0, "base_stats": {"strength": 100.0},
            "events": ["attack"]})
        self.assertEqual(out["errors"], [])
        self.assertTrue(out.get("lupa_ok") in (True, None))
        # аналитика: drain 20, deal 60
        self.assertAlmostEqual(out["room"]["steps"][0]["hero_hp"], 80.0, delta=TOL)
        self.assertAlmostEqual(out["room"]["steps"][0]["dummy_hp"], 4940.0, delta=TOL)
        # пассивные моды из формы: strength +20%
        self.assertAlmostEqual(out["room"]["summary"]["mods"]["strength"],
                               20.0, delta=1e-4)

    def test_invalid_form_reports_errors(self):
        form = {"name": "Broken", "effects": [{
            "id": "bad", "trigger": {"kind": "event", "event": "nope"},
            "ops": [{"kind": "zzz"}]}]}
        out = ui_logic.full_cycle(form)
        self.assertTrue(out["errors"])
        self.assertNotIn("lua", out)

    def test_all_catalog_templates_full_cycle(self):
        """Каждый шаблон каталога проходит весь цикл UI-логики без ошибок."""
        for tid in CATALOG:
            with self.subTest(tid=tid):
                form = {"name": template_names()[tid],
                        "effects": [self._form_from_template(tid)]}
                out = ui_logic.full_cycle(form,
                                          scenario={"events": ["use", "attack"]})
                self.assertEqual(out["errors"], [], tid)
                self.assertTrue(out.get("lupa_ok") in (True, None), tid)
                self.assertIn("room", out)

    # -- новые предметы каталога: полный цикл + аналитика -------------------

    def _full_cycle_item(self, tid, scenario):
        form = {"name": template_names()[tid],
                "description": "test",
                "effects": [get_template(tid).to_json()]}
        out = ui_logic.full_cycle(form, scenario=scenario)
        self.assertEqual(out["errors"], [], f"{tid}: {out['errors']}")
        self.assertTrue(out.get("lupa_ok") in (True, None), tid)
        return out

    def test_vampires_fang_full_cycle(self):
        """Лifesteal 8% от урона + strength-скалинг по kills (scale.of='kills')."""
        out = self._full_cycle_item(
            "vampires_fang",
            {"hero_hp": 500.0, "base_stats": {"strength": 100.0},
             "dummy_max_hp": 200.0,
             "events": ["attack 100", "kill", "attack 100"]})
        steps = out["room"]["steps"]
        # атака 1: враг 200->100, heal 8 => 508; килла нет
        self.assertAlmostEqual(steps[0]["hero_hp"], 508.0, delta=TOL)
        self.assertEqual(steps[0]["kills"], 0)
        # kill-событие: манекен умирает/возрождается, kills+1
        self.assertEqual(steps[1]["kills"], 1)
        self.assertAlmostEqual(steps[1]["dummy_hp"], 200.0, delta=TOL)
        # атака 2: strength 100+5*1=105 (mod не влияет на прямой урон),
        # heal 8 => 516
        self.assertAlmostEqual(steps[2]["hero_hp"], 516.0, delta=TOL)
        mods = out["room"]["summary"]["mods"]
        self.assertAlmostEqual(mods.get("strength", 0.0), 5.0, delta=TOL)

    def test_mantle_of_thorns_full_cycle(self):
        """Реталиация: 20% от ТЕКУЩЕГО hp героя уроном по атакующему."""
        out = self._full_cycle_item(
            "mantle_of_thorns",
            {"hero_hp": 800.0, "events": ["enemy_attack 100"]})
        st = out["room"]["steps"][0]
        self.assertAlmostEqual(st["hero_hp"], 700.0, delta=TOL)   # 800-100
        self.assertAlmostEqual(st["dummy_hp"], 5000.0 - 140.0, delta=TOL)

    def test_rage_tonic_full_cycle(self):
        """Бафф enraged 8с (+1с за каждые 10% ниже 40 HP) + drain 10% hp."""
        out = self._full_cycle_item(
            "rage_tonic", {"hero_hp": 300.0, "events": ["use"]})
        st = out["room"]["steps"][0]
        self.assertAlmostEqual(st["hero_hp"], 270.0, delta=TOL)   # 300 - 10%
        buffs = out["room"]["summary"]["buffs"]
        self.assertIn("enraged", buffs)
        # hp_pct=30 -> below40=10 -> +1с => until 9.0
        self.assertAlmostEqual(buffs["enraged"], 9.0, delta=1e-3)

    def test_judgement_full_cycle_execute_and_noexecute(self):
        """Execute: убивает цель <15% HP и НЕ трогает цель выше порога."""
        out = self._full_cycle_item(
            "judgement",
            {"dummy_max_hp": 5000.0,   # set_dummy 700 => 14% — ниже порога;
                                       # set_dummy 1000 => 20% — выше порога
             "events": ["set_dummy 1000", "attack 300", "set_dummy 700",
                        "attack"]})
        steps = out["room"]["steps"]
        # шаг 2: dummy 1000/5000 = 20% -> execute НЕ срабатывает, базовый
        # урон 300 -> 700 (не смерть)
        self.assertEqual(steps[1]["kills"], 0)
        self.assertAlmostEqual(steps[1]["dummy_hp"], 700.0, delta=TOL)
        # шаг 4: dummy 700 = 14% < 15% -> execute убивает ДО базового урона;
        # kills ровно 1 (без двойного подсчёта), манекен возрождён полным
        self.assertEqual(steps[3]["kills"], 1)
        self.assertAlmostEqual(steps[3]["dummy_hp"], 5000.0, delta=TOL)

    def test_phoenix_feather_full_cycle_revive(self):
        """Воскрешение при смерти: set hp=30% max, remove_buff enraged."""
        item = ui_logic.build_item_json(
            {"name": "combo", "effects": [
                get_template("rage_tonic").to_json(),
                get_template("phoenix_feather").to_json()]})
        self.assertEqual(validate_item(item), [])
        hero = Unit("hero", max_hp=1000.0)
        dummy = Unit("mannequin", max_hp=5000.0)
        rt = EffectRuntime(hero, item["effects"], enemy=dummy)
        hero.current_hp = 50.0
        rt.refresh_passives()
        rt.fire_event("use", t=0.0)          # rage: drain 10% -> 45, buff enraged
        self.assertIn("enraged", hero.buffs)
        rt.receive_damage(100.0, t=1.0)      # смертельно -> die -> revive 300
        self.assertTrue(hero.alive)
        self.assertAlmostEqual(hero.current_hp, 300.0, delta=TOL)
        self.assertNotIn("enraged", hero.buffs)   # remove_buff от феникса


class TestTrainingRoomCombatLoop(unittest.TestCase):
    """Общий игровой цикл комнаты: attack/receive_damage/kill/die каскады."""

    def test_attack_chain_events(self):
        fired = []
        hero = Unit("hero", max_hp=1000.0)
        dummy = Unit("dummy", max_hp=100.0)
        effects = [{"id": "watch", "trigger": {"kind": "event", "event": "x"},
                    "ops": []}]
        rt = EffectRuntime(hero, effects, enemy=dummy)
        orig = rt.fire_event
        def spy(ev, t=0.0, extra=None):
            fired.append(ev)
            return orig(ev, t, extra)
        rt.fire_event = spy
        rt.attack(t=0.0, base_damage=150.0)  # one-shot dummy
        self.assertEqual(fired, ["attack", "attack_hit", "kill"])
        self.assertEqual(hero.kills, 1)

    def test_receive_damage_death_triggers_die(self):
        hero = Unit("hero", max_hp=100.0)
        dummy = Unit("dummy", max_hp=1000.0)
        item = ui_logic.build_item_json(
            {"name": "t", "effects": [get_template("phoenix_feather").to_json()]})
        rt = EffectRuntime(hero, item["effects"], enemy=dummy)
        rt.receive_damage(999.0)
        self.assertTrue(hero.alive)
        self.assertAlmostEqual(hero.current_hp, 30.0, delta=TOL)

    def test_kill_op_does_not_double_count(self):
        """Повторный kill по уже мёртвой цели не добавляет стаков kills."""
        hero = Unit("hero", max_hp=1000.0)
        dummy = Unit("dummy", max_hp=100.0)
        item = ui_logic.build_item_json(
            {"name": "t", "effects": [get_template("judgement").to_json()]})
        rt = EffectRuntime(hero, item["effects"], enemy=dummy)
        dummy.deal_damage(100.0)             # уже мёртв
        ctx = {**hero.ctx(), **rt.target_ctx("enemy", dummy)}
        rt.run_ops([{"kind": "kill", "target": "enemy"}], ctx, 0.0, "test")
        self.assertEqual(hero.kills, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
