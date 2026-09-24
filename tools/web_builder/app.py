"""
🎨 Effect Schema Item Builder — Flet 1.0 UI

Билдер предметов по схеме Effect -> Ops[] (docs/EFFECT_SCHEMA.md). Работает
поверх tools.effect_schema.ui_logic: тот же код, что и в тестах, поэтому
«Тест в тренировочной комнате» из UI идентичен прогону pytest.

Предмет = список эффектов. Слева - список эффектов предмета и редактор
выбранного (триггер, filter/cross, cooldown, threshold, amplify, ops с
fail-ветками и флагами), справа - digest + JSON, Lua и результаты.

Запуск:      python tools/web_builder/app.py            (desktop)
             python tools/web_builder/app.py --web      (web, порт 8550; нужен flet-web)
             ... --web --renderer canvaskit             (без доступа к CDN Flutter)
Без окна:    tools/web_builder/headless.py (тот же BuilderApp на подставной странице).

Flet 1.0 API: ft.run(main), ft.FilledButton, ft.Colors.*, Dropdown(on_select).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft  # noqa: E402

from tools import lua_bridge  # noqa: E402
from tools.effect_schema import itemcheck, ui_logic  # noqa: E402
from tools.effect_schema.catalog import CATALOG, bundle  # noqa: E402
from tools.effect_schema.digest import digest  # noqa: E402
from tools.effect_schema.sim import STEP_HELP  # noqa: E402
from tools.effect_schema.schema import (  # noqa: E402
    EVENTS, FLAGS, KNOWN_STATS, OP_KINDS, OPS, TARGETS, TRIGGER_KINDS,
)

# ---------------------------------------------------------------- enums → списки

KINDS = sorted(OP_KINDS)
TARGET_LIST = sorted(TARGETS)
OP_LIST = sorted(OPS)
TRIGGER_LIST = sorted(TRIGGER_KINDS)
EVENT_LIST = sorted(EVENTS)
STAT_LIST = sorted(KNOWN_STATS) + ["custom:<name>"]
FLAG_LIST = sorted(FLAGS)
ITEMS_DIR = ROOT / "lua_content" / "items"
DEFAULT_SCENARIO = "use; attack; attack; enemy_attack 50; hp 30; attack; tick 1 1"


def _opts(values):
    return [ft.dropdown.Option(key=v, text=v) for v in values]


def _s(x):
    """None/'' -> '', числа -> строка без '.0' для целых."""
    if x is None or x == "":
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def _field(label, width, value="", on_change=None):
    return ft.TextField(label=label, width=width, value=_s(value), on_change=on_change)


def _values(pairs) -> dict:
    """{ключ: значение поля} только для заполненных полей."""
    return {k: f.value for k, f in pairs if f.value}


# ---------------------------------------------------------------- op form card

class OpForm:
    """Карточка одной операции: все поля чек-листа схемы."""

    def __init__(self, app: "BuilderApp", data: dict | None = None,
                 title: str = "Op", top_level: bool = True):
        self.app = app
        d = data or {}
        t = self._touched
        self.kind = ft.Dropdown(label="kind *", width=160, value=d.get("kind", "mod"),
                                options=_opts(KINDS), on_select=t)
        self.target = ft.Dropdown(label="target", width=130, value=d.get("target", "self"),
                                  options=_opts(TARGET_LIST), on_select=t)
        self.stat = ft.Dropdown(label="stat", width=190, editable=True, value=d.get("stat") or None,
                                options=_opts(STAT_LIST), on_select=t)
        self.op = ft.Dropdown(label="op", width=120, value=d.get("op") or None,
                              options=_opts(OP_LIST), on_select=t)
        v = d.get("value") or {}
        self.v_flat = _field("value.flat", 130, v.get("flat"), t)
        self.v_pct = _field("value.pct", 130, v.get("pct"), t)
        self.v_of = _field("value.of", 170, v.get("of"), t)
        self.v_ref = _field("value.ref", 170, v.get("ref"), t)
        s = d.get("scale") or {}
        sv = s.get("value") or {}
        self.s_every = _field("scale.every", 140, s.get("every"), t)
        self.s_of = _field("scale.of", 170, s.get("of"), t)
        self.sv_flat = _field("scale.value.flat", 170, sv.get("flat"), t)
        self.sv_pct = _field("scale.value.pct", 170, sv.get("pct"), t)
        self.sv_of = _field("scale.value.of", 160, sv.get("of"), t)
        self.s_factor = _field("scale.factor", 140, s.get("factor"), t)
        self.s_cap = _field("scale.cap", 130, s.get("cap"), t)
        self.s_floor = _field("scale.floor", 140, s.get("floor"), t)
        self.when = _field("when (ctx.hp_pct < 40)", 300, d.get("when"), t)
        self.buff_id = _field("buff_id", 170, d.get("buff_id"), t)
        dur = d.get("duration") if isinstance(d.get("duration"), dict) else {}
        # длительность редактируется числом; ключ (flat/base) и scale сохраняются как были
        self._duration_key = "flat" if "flat" in dur else "base"
        self._duration_rest = {k: v for k, v in dur.items() if k not in ("base", "flat")}
        self.d_base = _field("duration", 120, dur.get("base", dur.get("flat")), t)
        cd = d.get("cooldown") if isinstance(d.get("cooldown"), dict) else {}
        self.cd_flat = _field("cooldown.flat", 160, cd.get("flat"), t)
        ext = d.get("extend") or {}
        self.ext_on = ft.Dropdown(label="extend.on", width=160, value=ext.get("on") or None,
                                  options=_opts(EVENT_LIST), on_select=t)
        self.ext_flat = _field("extend.flat", 150, ext.get("flat"), t)
        flags = set(d.get("flags") or [])
        self.flags = {f: ft.Checkbox(label=f, value=f in flags, on_change=t) for f in FLAG_LIST}
        self.remove_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400,
                                        tooltip="удалить операцию", on_click=self._remove)
        self.fail_switch = ft.Switch(label="fail-ветка", value=bool(d.get("fail")), on_change=self._toggle_fail)
        self.fail_list_col = ft.Column([], spacing=4, visible=bool(d.get("fail")))
        self.add_fail_btn = ft.TextButton("+ fail op", icon=ft.Icons.ADD, on_click=self._add_fail)
        self.fail_ops: list[OpForm] = []
        for f in d.get("fail") or []:
            self._make_fail(f)
        if not top_level:
            self.remove_btn.visible = False
            self.add_fail_btn.visible = False   # без рекурсии fail-in-fail

        self.title = ft.Text(title, weight=ft.FontWeight.BOLD, size=13)
        self.control = ft.Container(
            content=ft.Column([
                ft.Row([self.title, ft.Container(expand=True), self.remove_btn]),
                ft.Row([self.kind, self.target, self.stat, self.op], wrap=True),
                ft.Row([self.v_flat, self.v_pct, self.v_of, self.v_ref], wrap=True),
                ft.Row([self.s_every, self.s_of, self.sv_flat, self.sv_pct, self.sv_of,
                        self.s_factor, self.s_cap, self.s_floor], wrap=True),
                ft.Row([self.when, self.buff_id, self.d_base, self.cd_flat,
                        self.ext_on, self.ext_flat], wrap=True),
                ft.Row([ft.Text("flags:", size=12), *self.flags.values()], spacing=4),
                ft.Row([self.fail_switch, self.add_fail_btn]),
                self.fail_list_col,
            ], spacing=6),
            padding=10, border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)),
        )

    # -- handlers ---------------------------------------------------------
    def _touched(self, e=None):
        self.app.dirty()

    def _remove(self, e):
        self.app.remove_op(self)

    def _toggle_fail(self, e):
        self.fail_list_col.visible = bool(self.fail_switch.value)
        if not self.fail_list_col.visible:
            self.fail_ops.clear()
            self.fail_list_col.controls.clear()
        self.app.page.update()

    def _add_fail(self, e):
        self._make_fail({})
        self.fail_switch.value = True
        self.fail_list_col.visible = True
        self.app.page.update()

    def _make_fail(self, data):
        fo = OpForm(self.app, data, title="fail-op", top_level=False)
        self.fail_ops.append(fo)
        self.fail_list_col.controls.append(fo.control)

    # -- to form dict -----------------------------------------------------
    def to_form(self) -> dict:
        scale = _values((("every", self.s_every), ("of", self.s_of), ("factor", self.s_factor),
                         ("cap", self.s_cap), ("floor", self.s_floor)))
        sv = _values((("flat", self.sv_flat), ("pct", self.sv_pct), ("of", self.sv_of)))
        if sv:
            scale["value"] = sv
        out: dict = {"kind": self.kind.value or "mod",
                     "target": self.target.value or "self",
                     "stat": self.stat.value or "",
                     "op": self.op.value or "",
                     "value": _values((("flat", self.v_flat), ("pct", self.v_pct),
                                       ("of", self.v_of), ("ref", self.v_ref))),
                     "when": self.when.value or "",
                     "buff_id": self.buff_id.value or "",
                     "flags": [f for f, cb in self.flags.items() if cb.value]}
        if scale:
            out["scale"] = scale
        if self.d_base.value or self._duration_rest:
            dur = dict(self._duration_rest)
            if self.d_base.value:
                try:
                    dur[self._duration_key] = float(self.d_base.value)
                except ValueError:
                    dur[self._duration_key] = self.d_base.value
            out["duration"] = dur
        if self.cd_flat.value:
            out["cooldown"] = {"flat": self.cd_flat.value}
        ext = _values((("on", self.ext_on), ("flat", self.ext_flat)))
        if ext:
            out["extend"] = {**ext, "flat": float(ext["flat"])} if "flat" in ext else ext
        if self.fail_switch.value and self.fail_ops:
            out["fail"] = [f.to_form() for f in self.fail_ops]
        return out


# ---------------------------------------------------------------- effect editor

class EffectEditor:
    """Поля одного эффекта: id, теги, триггер, cooldown, threshold, amplify, ops."""

    def __init__(self, app: "BuilderApp"):
        self.app = app
        d = app.dirty
        self.ef_id = _field("effect.id *", 220, "my_effect", d)
        self.ef_tags = _field("tags (через запятую)", 220, "", d)
        self.ef_name = _field("meta.name", 200, "", d)
        self.tr_kind = ft.Dropdown(label="trigger.kind", width=150, value="passive",
                                   options=_opts(TRIGGER_LIST), on_select=d)
        self.tr_event = ft.Dropdown(label="trigger.event", width=190, options=_opts(EVENT_LIST), on_select=d)
        self.tr_when = _field("trigger.when (ctx.hp_pct < 40)", 320, "", d)
        self.tr_filter = _field("trigger.filter", 240, "", d)
        self.tr_owner = _field("trigger.owner_has", 200, "", d)
        self.tr_cross = _field("trigger.cross (hp_cross)", 240, "", d)
        self.cooldown = _field("effect.cooldown (с)", 200, "", d)
        self.threshold = _field("threshold (HP %, зона hp_cross)", 300, "", d)
        self.amp_when = _field("amplify.when (ctx.hp <= 1)", 260, "", d)
        self.amp_while = _field("amplify.while_buff", 200, "", d)
        self.amp_every = _field("amplify.every", 150, "", d)
        self.amp_of = _field("amplify.of", 190, "", d)
        self.amp_factor = _field("amplify.factor", 150, "", d)
        self.ops_col = ft.Column([], spacing=8)
        self.op_forms: list[OpForm] = []
        self._rest: dict = {}  # поля эффекта, которых нет в форме (duration, stacks, meta.*)
        self.control = ft.Column([
            ft.Row([self.ef_id, self.ef_tags, self.ef_name], wrap=True),
            ft.Row([self.tr_kind, self.tr_event, self.tr_when], wrap=True),
            ft.Row([self.tr_filter, self.tr_owner, self.tr_cross], wrap=True),
            ft.Row([self.cooldown, self.threshold], wrap=True),
            ft.Row([self.amp_when, self.amp_while, self.amp_every, self.amp_of, self.amp_factor], wrap=True),
            ft.Row([ft.Text("⚙️ Ops (операции)", size=16, weight=ft.FontWeight.BOLD),
                    ft.FilledButton("+ op", icon=ft.Icons.ADD, on_click=app.add_op)]),
            self.ops_col,
        ], spacing=8)

    def load(self, ef: dict):
        """Эффект (JSON схемы или форма билдера) -> поля."""
        tr = ef.get("trigger") or {}
        amp = ef.get("amplify") or {}
        meta = ef.get("meta") or {}
        cd = ef.get("cooldown")
        self.ef_id.value = ef.get("id", "")
        self.ef_tags.value = ", ".join(ef.get("tags") or [])
        self.ef_name.value = meta.get("name", "")
        self.tr_kind.value = tr.get("kind") or "passive"
        self.tr_event.value = tr.get("event") or None
        for fld, key in ((self.tr_when, "when"), (self.tr_filter, "filter"),
                         (self.tr_owner, "owner_has"), (self.tr_cross, "cross")):
            fld.value = _s(tr.get(key))
        self.cooldown.value = _s(cd.get("flat")) if isinstance(cd, dict) else ""
        self.threshold.value = _s(ef.get("threshold"))
        for fld, key in ((self.amp_when, "when"), (self.amp_while, "while_buff"), (self.amp_every, "every"),
                         (self.amp_of, "of"), (self.amp_factor, "factor")):
            fld.value = _s(amp.get(key))
        self._rest = {k: ef[k] for k in ("duration", "stacks") if ef.get(k)}
        self._rest["meta"] = {k: v for k, v in meta.items() if k != "name"}
        self.op_forms = [OpForm(self.app, o, title=f"ops[{i}]") for i, o in enumerate(ef.get("ops") or [])]
        self.rebuild_ops()

    def rebuild_ops(self):
        for i, f in enumerate(self.op_forms):
            f.title.value = f"ops[{i}]"
        self.ops_col.controls = [f.control for f in self.op_forms]

    def to_form(self) -> dict:
        meta = dict(self._rest.get("meta") or {})
        if self.ef_name.value:
            meta["name"] = self.ef_name.value
        form = {
            "_form": True,
            "id": (self.ef_id.value or "").strip() or "unnamed",
            "tags": [t.strip() for t in (self.ef_tags.value or "").split(",") if t.strip()],
            "trigger": {"kind": self.tr_kind.value or "passive", "event": self.tr_event.value or "",
                        "when": self.tr_when.value or "", "filter": self.tr_filter.value or "",
                        "owner_has": self.tr_owner.value or "", "cross": self.tr_cross.value or ""},
            "cooldown": {"flat": self.cooldown.value} if self.cooldown.value else None,
            "threshold": self.threshold.value or None,
            "amplify": _values((("when", self.amp_when), ("while_buff", self.amp_while), ("every", self.amp_every),
                                ("of", self.amp_of), ("factor", self.amp_factor))) or None,
            "meta": meta or None,
            "ops": [f.to_form() for f in self.op_forms],
        }
        form.update({k: v for k, v in self._rest.items() if k != "meta"})
        return form


# ---------------------------------------------------------------- main app

class BuilderApp:
    def __init__(self, page: ft.Page):
        self.page = page
        page.title = "Effect Schema Item Builder"
        page.theme_mode = ft.ThemeMode.DARK
        page.padding = 16

        self.item_name = ft.TextField(label="Название предмета", width=320, value="New Item")
        self.item_desc = ft.TextField(label="Описание", width=320, value="")
        self.lua_path = ft.TextField(label="файл .lua (lua_content/items/…)", width=420, value="")
        self.effects: list[dict] = []           # формы эффектов предмета
        self.current = 0                        # индекс редактируемого эффекта
        self.effects_col = ft.Column([], spacing=2)
        self.editor = EffectEditor(self)
        self.template_dd = ft.Dropdown(label="Шаблон из каталога", width=320,
                                       options=_opts(list(CATALOG)), on_select=self.load_template)
        self.scenario = ft.TextField(label="сценарий комнаты (шаги через ;)", width=520, value=DEFAULT_SCENARIO)
        self.hero_hp = ft.TextField(label="HP героя в начале", width=160, value="1000")
        self.base_damage = ft.TextField(label="урон удара (attack)", width=160, value="50")
        self.status = ft.Text("", selectable=True)
        # без GitHub-расширений Flet схлопывает ```-блоки в сплошной абзац
        md = dict(selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                  code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK)
        self.json_out = ft.Markdown("", **md)
        self.lua_out = ft.Markdown("", **md)
        self.room_out = ft.Markdown("", **md)
        self._last_item: dict | None = None
        self._pristine = True  # стартовый пустой эффект ещё не трогали

        left = ft.Column([
            ft.Text("🧱 Предмет", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([self.item_name, self.item_desc], wrap=True),
            ft.Row([self.lua_path,
                    ft.OutlinedButton("Открыть .lua", icon=ft.Icons.FOLDER_OPEN, on_click=self.open_lua),
                    ft.OutlinedButton("Сохранить .lua", icon=ft.Icons.SAVE, on_click=self.save_lua)], wrap=True),
            ft.Divider(),
            ft.Row([ft.Text("✨ Эффекты предмета", size=18, weight=ft.FontWeight.BOLD),
                    ft.FilledButton("+ эффект", icon=ft.Icons.ADD, on_click=self.add_effect),
                    ft.OutlinedButton("удалить эффект", icon=ft.Icons.DELETE_OUTLINE, on_click=self.remove_effect)],
                   wrap=True),
            ft.Row([self.template_dd, ft.Text("(добавляет шаблон с зависимостями)", size=12)], wrap=True),
            self.effects_col,
            ft.Divider(),
            self.editor.control,
            ft.Divider(),
            ft.Row([self.scenario, self.hero_hp, self.base_damage], wrap=True),
            ft.Text("шаги: " + STEP_HELP, size=11, selectable=True),
            ft.Row([
                ft.FilledButton("Валидировать", icon=ft.Icons.CHECK, on_click=self.validate),
                ft.FilledButton("Собрать Lua", icon=ft.Icons.CODE, on_click=self.build_lua),
                ft.FilledButton("Тест в тренировочной комнате", icon=ft.Icons.SCIENCE, on_click=self.test_room),
                ft.FilledButton("Проверить предмет (itemcheck)", icon=ft.Icons.FACT_CHECK, on_click=self.check_item),
            ], wrap=True),
            self.status,
        ], scroll=ft.ScrollMode.AUTO, expand=3, spacing=8)

        def _panel(md: ft.Markdown, flex: int) -> ft.Container:
            return ft.Container(ft.Column([md], scroll=ft.ScrollMode.AUTO, expand=True), expand=flex,
                                bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.BLACK), border_radius=8, padding=10)

        right = ft.Column([
            ft.Text("Предмет: digest + JSON", weight=ft.FontWeight.BOLD),
            _panel(self.json_out, 2),
            ft.Text("Lua", weight=ft.FontWeight.BOLD),
            _panel(self.lua_out, 2),
            ft.Text("Тренировочная комната / itemcheck", weight=ft.FontWeight.BOLD),
            _panel(self.room_out, 3),
        ], scroll=ft.ScrollMode.AUTO, expand=2, spacing=8)

        page.add(ft.Row([left, right], vertical_alignment=ft.CrossAxisAlignment.START, spacing=16, expand=True))
        self.add_effect(None, quiet=True)  # стартовый пустой эффект

    # -- helpers ------------------------------------------------------------
    def dirty(self, e=None):
        self._pristine = False
        self._last_item = None
        self.status.value = "● несохранённые изменения"
        self.status.color = ft.Colors.AMBER_400
        self.page.update()

    def _set_status(self, msg, color=ft.Colors.LIGHT_BLUE_400):
        self.status.value = msg
        self.status.color = color
        self.page.update()

    def _sync(self):
        """Сохранить редактор в список эффектов."""
        if self.effects:
            self.effects[self.current] = self.editor.to_form()

    def _refresh_effects(self):
        self.effects_col.controls = [
            ft.TextButton(f"{'▶ ' if i == self.current else ''}{i}: {ef.get('id')} "
                          f"({(ef.get('trigger') or {}).get('kind')})",
                          on_click=lambda e, i=i: self.select_effect(i))
            for i, ef in enumerate(self.effects)]

    # -- effects list ----------------------------------------------------------
    def add_effect(self, e=None, quiet: bool = False, effect: dict | None = None):
        self._sync()
        self.effects.append(effect or {"id": f"effect_{len(self.effects)}", "trigger": {"kind": "passive"},
                                       "ops": [{"kind": "mod", "target": "self"}]})
        self.select_effect(len(self.effects) - 1, sync=False, quiet=quiet)

    def select_effect(self, index: int, sync: bool = True, quiet: bool = False):
        if sync:
            self._sync()
        self.current = max(0, min(index, len(self.effects) - 1))
        if self.effects:
            self.editor.load(self.effects[self.current])
        self._refresh_effects()
        if not quiet:
            self.dirty()

    def remove_effect(self, e=None):
        if not self.effects:
            return
        self.effects.pop(self.current)
        if not self.effects:
            self.effects.append({"id": "effect_0", "trigger": {"kind": "passive"}, "ops": []})
        self.select_effect(min(self.current, len(self.effects) - 1), sync=False)

    def add_op(self, e=None):
        self.editor.op_forms.append(OpForm(self, {}, title=""))
        self.editor.rebuild_ops()
        self.dirty()

    def remove_op(self, opf: OpForm):
        if opf in self.editor.op_forms:
            self.editor.op_forms.remove(opf)
        self.editor.rebuild_ops()
        self.dirty()

    def load_template(self, e=None):
        """Шаблон каталога + то, на что он ссылается (owner_has, apply_effect)."""
        tid = self.template_dd.value
        if not tid:
            return
        self._sync()
        have = {ef.get("id") for ef in self.effects}
        added = [ef for ef in bundle(tid) if ef["id"] not in have]
        if self._pristine:  # нетронутый стартовый эффект заменяется шаблоном
            self.effects = []
        self.effects.extend(added)
        self.select_effect(len(self.effects) - len(added), sync=False, quiet=True)
        self._pristine = False
        self._set_status(f"Добавлен шаблон «{tid}» ({len(added)} эффект(ов))", ft.Colors.GREEN_400)

    # -- form -> state --------------------------------------------------------
    def collect_form(self) -> dict:
        self._sync()
        return {"name": self.item_name.value, "description": self.item_desc.value,
                "effects": list(self.effects)}

    def _item(self) -> dict:
        item = ui_logic.build_item_json(self.collect_form())
        self._last_item = item
        return item

    # -- actions ---------------------------------------------------------------
    def validate(self, e=None) -> list[str]:
        item = self._item()
        errs = ui_logic.validate(item)
        self.json_out.value = "```text\n" + "\n".join(digest(item)) + "\n```\n\n```json\n" + \
            json.dumps(item, ensure_ascii=False, indent=2) + "\n```"
        if errs:
            self._set_status(f"❌ ошибок: {len(errs)}", ft.Colors.RED_400)
            self.room_out.value = "**Ошибки валидации:**\n" + "\n".join(f"- `{x}`" for x in errs)
        else:
            self._set_status(f"✅ схема валидна ({len(item['effects'])} эффект(ов))", ft.Colors.GREEN_400)
        self.page.update()
        return errs

    def _valid_item(self) -> dict | None:
        if self.validate():
            return None
        return self._last_item

    def build_lua(self, e=None) -> str | None:
        item = self._valid_item()
        if item is None:
            return None
        lua = ui_logic.to_lua(item)
        try:
            ui_logic.lua_load(lua)
            self._set_status(f"Lua собран и исполнен ({', '.join(lua_bridge.available_backends())}) ✅",
                             ft.Colors.GREEN_400)
        except RuntimeError:
            self._set_status("Lua собран (нет ни rust_core, ни lupa)", ft.Colors.AMBER_400)
        except Exception as ex:  # noqa: BLE001 - показать ошибку Lua в UI
            self._set_status(f"Lua не исполнился: {ex}", ft.Colors.RED_400)
        self.lua_out.value = "```lua\n" + lua + "\n```"
        self.page.update()
        return lua

    def test_room(self, e=None) -> dict | None:
        item = self._valid_item()
        if item is None:
            return None
        events = ui_logic.parse_scenario(self.scenario.value or "")
        hero_hp = float(self.hero_hp.value) if self.hero_hp.value else None
        report = ui_logic.run_training_room(item, scenario={
            "hero_hp": hero_hp, "events": events, "base_damage": float(self.base_damage.value or 0)})
        lines = [f"### 🏋️ Тренировочная комната (hero hp={_s(hero_hp)}/1000)", ""]
        for st in report["steps"]:
            lines.append(f"- **{st['event']}** → hero hp={st['hero_hp']}, манекен hp={st['dummy_hp']}, "
                         f"kills={st['kills']}")
        s = report["summary"]
        lines += ["", f"**Итог:** HP {s['hp']}/{s['max_hp']} ({s['hp_pct']}%), kills={s['kills']}",
                  f"- моды: `{json.dumps(s['mods'], ensure_ascii=False)}`",
                  f"- баффы: `{json.dumps(s['buffs'], ensure_ascii=False)}`",
                  "", "**Лог эффектов:**", "", "```text", *report["log"][:60], "```"]
        self.room_out.value = "\n".join(lines)
        self._set_status("тренировочная комната прогнана ✅", ft.Colors.GREEN_400)
        self.page.update()
        return report

    def check_item(self, e=None) -> itemcheck.Report | None:
        item = self._valid_item()
        if item is None:
            return None
        report = itemcheck.check_item(item, pred_samples=100)
        self.room_out.value = "```text\n" + "\n".join(report.lines()) + "\n```"
        self._set_status("itemcheck: PASS ✅" if report.ok else "itemcheck: FAIL ❌",
                         ft.Colors.GREEN_400 if report.ok else ft.Colors.RED_400)
        return report

    # -- files -------------------------------------------------------------------
    def _path(self) -> Path:
        raw = (self.lua_path.value or "").strip()
        if not raw:
            slug = re.sub(r"[^a-z0-9]+", "_", (self.item_name.value or "item").lower()).strip("_") or "item"
            raw = str(ITEMS_DIR / f"{slug}.lua")
            self.lua_path.value = raw
        p = Path(raw)
        return p if p.is_absolute() else ROOT / p

    def open_lua(self, e=None):
        try:
            data = lua_bridge.load(self._path())
        except Exception as ex:  # noqa: BLE001
            self._set_status(f"не открылся: {ex}", ft.Colors.RED_400)
            return
        self.item_name.value = data.get("name", "")
        self.item_desc.value = data.get("description", "")
        self.effects = list(data.get("effects") or [])
        self.select_effect(0, sync=False, quiet=True)
        self._pristine = False
        self._set_status(f"открыт {self._path().name}: {len(self.effects)} эффект(ов)", ft.Colors.GREEN_400)

    def save_lua(self, e=None) -> Path | None:
        lua = self.build_lua()
        if lua is None:
            return None
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(lua, encoding="utf-8")
        self._set_status(f"сохранён {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}",
                         ft.Colors.GREEN_400)
        return path


# ---------------------------------------------------------------- entry point

def main(page: ft.Page):
    BuilderApp(page)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Effect Schema Item Builder")
    ap.add_argument("--web", action="store_true", help="serve the web UI (needs flet-web)")
    ap.add_argument("--port", type=int, default=8550)
    ap.add_argument("--renderer", choices=["auto", "canvaskit", "skwasm"], default="auto",
                    help="canvaskit ships inside flet-web: use it where the Flutter CDN is unreachable")
    args = ap.parse_args()
    if args.web:
        ft.run(main, view=ft.AppView.WEB_BROWSER, port=args.port, web_renderer=ft.WebRenderer(args.renderer))
    else:
        ft.run(main)
