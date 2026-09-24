"""Flet-билдер предметов без окна: настоящие обработчики UI через tools/web_builder/headless.py.

Поля находятся по подписи, кнопки - по тексту, как их видит человек.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("flet")

from tools import lua_bridge  # noqa: E402
from tools.effect_schema.catalog import CATALOG, bundle  # noqa: E402
from tools.web_builder.headless import UI  # noqa: E402

needs_lua = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")


def _norm(v):
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return [_norm(x) for x in v]


@pytest.mark.parametrize("tid", list(CATALOG))
def test_template_survives_the_editor_form(tid):
    """Шаблон -> поля редактора -> форма -> JSON схемы: ничего не теряется.
    Раньше терялись duration.scale (Rage Tonic) и scale.value.of (Blood Price:
    +0.5% от max_hp за шаг превращалось в +0.5% от текущего HP)."""
    ui = UI()
    ui.pick("Шаблон из каталога", tid)
    for i in range(len(ui.app.effects)):  # открыть каждый эффект в редакторе и уйти с него
        ui.app.select_effect(i)
    ui.click("Валидировать")
    assert "✅" in ui.status, ui.panel("room")
    assert _norm(ui.app._last_item["effects"]) == _norm(bundle(tid))


def test_template_brings_its_dependencies():
    ui = UI()
    ui.pick("Шаблон из каталога", "lost_my_self.attack")
    assert [e["id"] for e in ui.app.effects] == ["lost_my_self.attack", "lost_my_self"]
    ui.pick("Шаблон из каталога", "venom_bite")
    assert [e["id"] for e in ui.app.effects][-2:] == ["venom_bite", "poison_stack"]


@needs_lua
def test_new_item_built_through_the_form_passes_everything(tmp_path):
    """Предмет с нуля через поля билдера: стамина, флаги, amplify, filter, fail-ветка."""
    ui = UI()
    ui.fill("Название предмета", "Second Wind")
    ui.fill("effect.id *", "second_wind")
    ui.pick("trigger.kind", "event").pick("trigger.event", "take_damage")
    ui.fill("trigger.filter", "ctx.hp_pct < 50 and ctx.stamina >= 20")
    ui.fill("effect.cooldown (с)", "3")
    ui.pick("kind *", "drain").pick("stat", "stamina").fill("value.flat", "20")
    ui.check("fail-ветка", True)
    ui.click("+ fail op")
    ui.pick("kind *", "deal", nth=1).pick("stat", "hp", nth=1).fill("value.flat", "5", nth=1)
    ui.click("+ op")
    ui.pick("kind *", "heal", nth=2).pick("stat", "hp", nth=2)
    ui.fill("value.pct", "10", nth=2).fill("value.of", "max_hp", nth=2)
    ui.click("+ op")
    ui.pick("kind *", "buff", nth=3).fill("buff_id", "second_wind", nth=3)
    ui.fill("duration", "2", nth=3).check("iframe", True, nth=3)

    ui.click("+ эффект")
    ui.fill("effect.id *", "winded")
    ui.pick("trigger.kind", "condition").fill("trigger.when (ctx.hp_pct < 40)", "ctx.stamina < 30")
    ui.fill("amplify.when (ctx.hp <= 1)", "ctx.hp_pct < 20").fill("amplify.every", "10")
    ui.fill("amplify.of", "hp_missing_below_40").fill("amplify.factor", "2")
    ui.pick("kind *", "mod").pick("stat", "defense").pick("op", "add").fill("value.flat", "15")

    ui.click("Валидировать")
    assert "✅" in ui.status and "2 эффект" in ui.status, ui.panel("room")
    item = ui.app._last_item
    assert item["effects"][0]["ops"][0]["fail"][0]["kind"] == "deal"
    assert item["effects"][0]["ops"][2]["flags"] == ["iframe"]
    assert item["effects"][0]["cooldown"] == {"flat": 3.0}
    assert item["effects"][1]["amplify"] == {"every": 10.0, "of": "hp_missing_below_40", "factor": 2.0,
                                             "when": "ctx.hp_pct < 20"}
    assert "second_wind | event:take_damage" in ui.panel("json")  # digest над JSON

    ui.click("Собрать Lua")
    assert "✅" in ui.status
    assert _norm(lua_bridge.load(ui.panel("lua").strip("`\n").removeprefix("lua\n"))["effects"]) == \
        _norm(item["effects"])

    ui.fill("сценарий комнаты (шаги через ;)", "hp 40; enemy_attack 10; enemy_attack 10; tick 1 1; enemy_attack 10")
    ui.click("Тест в тренировочной комнате")
    room = ui.panel("room")
    assert "drain 20.00 -> stamina=80.0" in room and "ignores 10.0 damage (iframe second_wind)" in room

    ui.click("Проверить предмет (itemcheck)")
    assert ui.status == "itemcheck: PASS ✅", ui.panel("room")

    path = tmp_path / "second_wind.lua"
    ui.fill("файл .lua (lua_content/items/…)", str(path)).click("Сохранить .lua")
    reopened = UI()
    reopened.fill("файл .lua (lua_content/items/…)", str(path)).click("Открыть .lua")
    assert [e["id"] for e in reopened.app.effects] == ["second_wind", "winded"]
    reopened.click("Валидировать")
    assert _norm(reopened.app._last_item["effects"]) == _norm(item["effects"])


def test_switching_effects_keeps_edits_and_remove_works():
    ui = UI()
    ui.fill("effect.id *", "first")
    ui.click("+ эффект").fill("effect.id *", "second")
    ui.app.select_effect(0)
    assert ui.field("effect.id *").value == "first"
    ui.click("удалить эффект")
    assert [e["id"] for e in ui.app.effects] == ["second"]


def test_validation_errors_are_shown():
    ui = UI()
    ui.pick("kind *", "mod").pick("stat", "stamina").pick("op", "add").fill("value.flat", "5")
    ui.click("Валидировать")
    assert "❌" in ui.status and "resource 'stamina'" in ui.panel("room")
    json.loads(ui.panel("json").split("```json\n", 1)[1].rsplit("```", 1)[0])  # JSON панели валиден
