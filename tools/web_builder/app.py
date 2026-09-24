"""
🎨 Effect Schema Item Builder — Flet 1.0 UI

Билдер предметов с эффектами по схеме Effect -> Ops[] (Effect Schema v1).
Работает поверх tools.effect_schema.ui_logic: тот же код, что и в тестах
(tests/test_training_room_effectschema.py), поэтому «Тест в тренировочной
комнате» из UI идентичен прогону pytest.

Запуск:      python tools/web_builder/app.py            (desktop)
             python tools/web_builder/app.py --web      (web, порт 8550)

Flet 1.0 API: ft.run(main), ft.FilledButton, ft.Colors.*, Dropdown(on_select).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft  # noqa: E402

from tools.effect_schema.catalog import CATALOG, get_template  # noqa: E402
from tools.effect_schema.schema import (  # noqa: E402
    OP_KINDS, TARGETS, OPS, TRIGGER_KINDS, EVENTS, KNOWN_STATS,
)
from tools.effect_schema import ui_logic  # noqa: E402

# ---------------------------------------------------------------- enums → списки

KINDS = sorted(OP_KINDS)
TARGET_LIST = sorted(TARGETS)
OP_LIST = sorted(OPS)
TRIGGER_LIST = sorted(TRIGGER_KINDS)
EVENT_LIST = sorted(EVENTS)
STAT_LIST = sorted(KNOWN_STATS) + ["custom:<name>"]
FLAG_LIST = ["no_crit", "true_damage", "silent"]


def _opts(values):
    return [ft.dropdown.Option(key=v, text=v) for v in values]


def _s(x):
    """None/'' -> '', числа -> строка без '.0' для целых."""
    if x is None or x == "":
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


# ---------------------------------------------------------------- op form card

class OpForm:
    """Карточка одной операции: все поля чек-листа схемы."""

    def __init__(self, app: "BuilderApp", data: dict | None = None,
                 title: str = "Op", top_level: bool = True):
        self.app = app
        d = data or {}
        self.kind = ft.Dropdown(label="kind *", width=160, value=d.get("kind", "mod"),
                                options=_opts(KINDS), on_select=self._touched)
        self.target = ft.Dropdown(label="target", width=130,
                                  value=d.get("target", "self"),
                                  options=_opts(TARGET_LIST), on_select=self._touched)
        self.stat = ft.Dropdown(label="stat", width=190, editable=True,
                                value=d.get("stat") or None,
                                options=_opts(STAT_LIST), on_select=self._touched)
        self.op = ft.Dropdown(label="op", width=120,
                              value=d.get("op") or None,
                              options=_opts(OP_LIST), on_select=self._touched)
        v = d.get("value") or {}
        self.v_flat = ft.TextField(label="value.flat", width=110,
                                   value=_s(v.get("flat")), on_change=self._touched)
        self.v_pct = ft.TextField(label="value.pct", width=110,
                                  value=_s(v.get("pct")), on_change=self._touched)
        self.v_of = ft.TextField(label="value.of", width=170,
                                 value=_s(v.get("of")), on_change=self._touched)
        self.v_ref = ft.TextField(label="value.ref", width=170,
                                  value=_s(v.get("ref")), on_change=self._touched)
        s = d.get("scale") or {}
        self.s_every = ft.TextField(label="scale.every", width=120,
                                    value=_s(s.get("every")), on_change=self._touched)
        self.s_of = ft.TextField(label="scale.of", width=170,
                                 value=_s(s.get("of")), on_change=self._touched)
        sv = s.get("value") or {}
        self.sv_flat = ft.TextField(label="scale.value.flat", width=140,
                                    value=_s(sv.get("flat")), on_change=self._touched)
        self.sv_pct = ft.TextField(label="scale.value.pct", width=140,
                                   value=_s(sv.get("pct")), on_change=self._touched)
        self.s_factor = ft.TextField(label="scale.factor", width=120,
                                     value=_s(s.get("factor")), on_change=self._touched)
        self.s_cap = ft.TextField(label="scale.cap", width=110,
                                  value=_s(s.get("cap")), on_change=self._touched)
        self.when = ft.TextField(label="when (ctx.hp_pct < 40)",
                                 width=300, value=_s(d.get("when")),
                                 on_change=self._touched)
        self.buff_id = ft.TextField(label="buff_id", width=170,
                                    value=_s(d.get("buff_id")), on_change=self._touched)
        raw_dur = d.get("duration")
        dur = raw_dur if isinstance(raw_dur, dict) else {}
        base = dur.get("base", dur.get("flat"))
        self.d_base = ft.TextField(label="duration.base", width=140,
                                   value=_s(base), on_change=self._touched)
        cd = d.get("cooldown") if isinstance(d.get("cooldown"), dict) else {}
        self.cd_flat = ft.TextField(label="cooldown.flat", width=140,
                                    value=_s(cd.get("flat")), on_change=self._touched)
        ext = d.get("extend") or {}
        self.ext_on = ft.TextField(label="extend.on", width=140,
                                   value=_s(ext.get("on")), on_change=self._touched)
        self.ext_flat = ft.TextField(label="extend.flat", width=140,
                                     value=_s(ext.get("flat")), on_change=self._touched)
        self.flags = ft.Dropdown(label="flags", width=160,
                                 value=(d.get("flags") or [None])[0],
                                 options=_opts(FLAG_LIST), on_select=self._touched)
        self.remove_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE,
                                        icon_color=ft.Colors.RED_400,
                                        tooltip="удалить операцию",
                                        on_click=self._remove)
        self.fail_switch = ft.Switch(label="fail-ветка",
                                     value=bool(d.get("fail")),
                                     on_change=self._toggle_fail)
        self.fail_list_col = ft.Column([], spacing=4,
                                       visible=bool(d.get("fail")))
        self.add_fail_btn = ft.TextButton("+ fail op", icon=ft.Icons.ADD,
                                          on_click=self._add_fail)
        self.fail_ops: list[OpForm] = []
        for f in d.get("fail") or []:
            self._make_fail(f)
        if not top_level:
            self.remove_btn.visible = False
            self.add_fail_btn.visible = False   # без рекурсии fail-in-fail

        self.control = ft.Container(
            content=ft.Column([
                ft.Row([ft.Text(title, weight=ft.FontWeight.BOLD, size=13),
                        ft.Container(expand=True), self.remove_btn]),
                ft.Row([self.kind, self.target, self.stat, self.op], wrap=True),
                ft.Row([self.v_flat, self.v_pct, self.v_of, self.v_ref], wrap=True),
                ft.Row([self.s_every, self.s_of, self.sv_flat, self.sv_pct,
                        self.s_factor, self.s_cap], wrap=True),
                ft.Row([self.when, self.buff_id, self.d_base, self.cd_flat,
                        self.ext_on, self.ext_flat, self.flags], wrap=True),
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
        value = {k: v.value for k, v in
                 (("flat", self.v_flat), ("pct", self.v_pct),
                  ("of", self.v_of), ("ref", self.v_ref)) if v.value}
        scale = {k: v.value for k, v in
                 (("every", self.s_every), ("of", self.s_of),
                  ("factor", self.s_factor), ("cap", self.s_cap)) if v.value}
        sv = {k: v.value for k, v in
              (("flat", self.sv_flat), ("pct", self.sv_pct)) if v.value}
        if sv:
            scale["value"] = sv
        out: dict = {"kind": self.kind.value or "mod",
                     "target": self.target.value or "self",
                     "stat": self.stat.value or "",
                     "op": self.op.value or "",
                     "value": value, "when": self.when.value or "",
                     "buff_id": self.buff_id.value or "",
                     "flags": [self.flags.value] if self.flags.value else []}
        if scale:
            out["scale"] = scale
        if self.d_base.value:
            try:
                out["duration"] = {"base": float(self.d_base.value)}
            except ValueError:
                out["duration"] = {"base": self.d_base.value}
        if self.cd_flat.value:
            out["cooldown"] = {"flat": self.cd_flat.value}
        ext = {k: v.value for k, v in
               (("on", self.ext_on), ("flat", self.ext_flat)) if v.value}
        if ext:
            out["extend"] = ext
        if self.fail_switch.value and self.fail_ops:
            out["fail"] = [f.to_form() for f in self.fail_ops]
        return out


# ---------------------------------------------------------------- main app

class BuilderApp:
    def __init__(self, page: ft.Page):
        self.page = page
        page.title = "Effect Schema Item Builder"
        page.theme_mode = ft.ThemeMode.DARK
        page.padding = 16

        self.item_name = ft.TextField(label="Название предмета", width=320,
                                      value="Sorrow of Berserk")
        self.item_desc = ft.TextField(label="Описание", width=320, value="")
        self.ef_id = ft.TextField(label="effect.id *", width=220,
                                  value="my_effect", on_change=self.dirty)
        self.ef_tags = ft.TextField(label="tags (через запятую)", width=220,
                                    on_change=self.dirty)
        self.tr_kind = ft.Dropdown(label="trigger.kind", width=150, value="passive",
                                   options=_opts(TRIGGER_LIST),
                                   on_select=self.dirty)
        self.tr_event = ft.Dropdown(label="trigger.event", width=170,
                                    options=_opts(EVENT_LIST),
                                    on_select=self.dirty)
        self.tr_when = ft.TextField(label="trigger.when (ctx.hp_pct < 40)",
                                    width=280, on_change=self.dirty)
        self.tr_owner = ft.TextField(label="trigger.owner_has", width=200,
                                     on_change=self.dirty)

        self.ops_col = ft.Column([], spacing=8)
        self.op_forms: list[OpForm] = []
        self.template_dd = ft.Dropdown(label="Шаблон из каталога", width=320,
                                       options=_opts(list(CATALOG)),
                                       on_select=self.load_template)
        self.status = ft.Text("", selectable=True)
        self.json_out = ft.Markdown("", selectable=True)
        self.lua_out = ft.Markdown("", selectable=True)
        self.room_out = ft.Markdown("", selectable=True)
        self._last_item: dict | None = None

        left = ft.Column([
            ft.Text("🧱 Предмет", size=18, weight=ft.FontWeight.BOLD),
            self.item_name, self.item_desc,
            ft.Divider(),
            ft.Text("✨ Effect (контейнер)", size=18, weight=ft.FontWeight.BOLD),
            self.template_dd,
            ft.Row([self.ef_id, self.ef_tags], wrap=True),
            ft.Row([self.tr_kind, self.tr_event, self.tr_when, self.tr_owner],
                   wrap=True),
            ft.Text("⚙️ Ops (операции)", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([ft.FilledButton("+ op", icon=ft.Icons.ADD,
                                    on_click=self.add_op)]),
            self.ops_col,
            ft.Divider(),
            ft.Row([
                ft.FilledButton("Валидировать", icon=ft.Icons.CHECK,
                                on_click=self.validate),
                ft.FilledButton("Собрать Lua", icon=ft.Icons.CODE,
                                on_click=self.build_lua),
                ft.FilledButton("Тест в тренировочной комнате",
                                icon=ft.Icons.SCIENCE, on_click=self.test_room),
            ], wrap=True),
            self.status,
        ], scroll=ft.ScrollMode.AUTO, expand=3, spacing=8)

        def _panel(md: ft.Markdown, flex: int) -> ft.Container:
            return ft.Container(
                ft.Column([md], scroll=ft.ScrollMode.AUTO, expand=True),
                expand=flex,
                bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.BLACK),
                border_radius=8, padding=10)

        right = ft.Column([
            ft.Text("JSON предмета", weight=ft.FontWeight.BOLD),
            _panel(self.json_out, 2),
            ft.Text("Lua", weight=ft.FontWeight.BOLD),
            _panel(self.lua_out, 2),
            ft.Text("Тренировочная комната", weight=ft.FontWeight.BOLD),
            _panel(self.room_out, 3),
        ], scroll=ft.ScrollMode.AUTO, expand=2, spacing=8)

        page.add(ft.Row([left, right],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=16, expand=True))
        self.add_op(None, quiet=True)  # стартовая пустая op

    # -- helpers ------------------------------------------------------------
    def dirty(self, e=None):
        self.status.value = "● несохранённые изменения"
        self.status.color = ft.Colors.AMBER_400
        self.page.update()

    def add_op(self, e=None, quiet: bool = False):
        self.op_forms.append(OpForm(self, {}, title=f"ops[{len(self.op_forms)}]"))
        self.rebuild_ops(quiet=quiet)

    def remove_op(self, opf: OpForm):
        if opf in self.op_forms:
            self.op_forms.remove(opf)
        self.rebuild_ops()

    def rebuild_ops(self, quiet: bool = False):
        for i, f in enumerate(self.op_forms):
            f.control.content.controls[0].controls[0].value = f"ops[{i}]"
        self.ops_col.controls = [f.control for f in self.op_forms]
        if not quiet:
            self.dirty()

    def load_template(self, e):
        tid = self.template_dd.value
        if not tid:
            return
        ef = get_template(tid).to_json()
        self.ef_id.value = ef["id"]
        self.ef_tags.value = ", ".join(ef.get("tags", []))
        tr = ef.get("trigger", {})
        self.tr_kind.value = tr.get("kind", "passive")
        self.tr_event.value = tr.get("event")
        when = tr.get("when", "")
        self.tr_when.value = when if isinstance(when, str) else ""
        self.tr_owner.value = tr.get("owner_has", "")
        self.op_forms = [OpForm(self, o, title=f"ops[{i}]")
                         for i, o in enumerate(ef.get("ops", []))]
        self.rebuild_ops()
        self._set_status(f"Загружен шаблон «{tid}»", ft.Colors.GREEN_400)

    def _set_status(self, msg, color=ft.Colors.LIGHT_BLUE_400):
        self.status.value = msg
        self.status.color = color
        self.page.update()

    # -- form -> state --------------------------------------------------------
    def collect_form(self) -> dict:
        effect_form = {
            "id": (self.ef_id.value or "").strip() or "unnamed",
            "tags": [t.strip() for t in (self.ef_tags.value or "").split(",")
                     if t.strip()],
            "trigger": {"kind": self.tr_kind.value or "passive",
                        "event": self.tr_event.value or "",
                        "when": self.tr_when.value or "",
                        "owner_has": self.tr_owner.value or ""},
            "ops": [f.to_form() for f in self.op_forms],
        }
        return {"name": self.item_name.value,
                "description": self.item_desc.value,
                "effects": [effect_form]}

    # -- actions ---------------------------------------------------------------
    def validate(self, e=None):
        form = self.collect_form()
        item = ui_logic.build_item_json(form)
        errs = ui_logic.validate(item)
        self._last_item = item
        self.json_out.value = "```json\n" + \
            json.dumps(item, ensure_ascii=False, indent=2) + "\n```"
        if errs:
            self._set_status(f"❌ ошибок: {len(errs)}", ft.Colors.RED_400)
            self.room_out.value = "**Ошибки валидации:**\n" + \
                "\n".join(f"- `{x}`" for x in errs)
        else:
            self._set_status("✅ схема валидна", ft.Colors.GREEN_400)
        self.page.update()

    def build_lua(self, e=None):
        if not self._last_item:
            self.validate()
        item = self._last_item
        if ui_logic.validate(item):
            self._set_status("сначала исправь ошибки валидации",
                             ft.Colors.RED_400)
            return
        lua = ui_logic.to_lua(item)
        try:
            ui_logic.lua_load(lua)
            self._set_status("Lua собран и загружен lupa ✅",
                             ft.Colors.GREEN_400)
        except ImportError:
            self._set_status("Lua собран (lupa не установлена)",
                             ft.Colors.AMBER_400)
        except Exception as ex:
            self._set_status(f"lupa load failed: {ex}", ft.Colors.RED_400)
        self.lua_out.value = "```lua\n" + lua + "\n```"
        self.page.update()

    def test_room(self, e=None):
        if not self._last_item:
            self.validate()
        item = self._last_item
        if ui_logic.validate(item):
            self._set_status("валидация не пройдена", ft.Colors.RED_400)
            return
        report = ui_logic.run_training_room(
            item, scenario={"hero_hp": 100.0,
                            "events": ["use", "attack", "attack"]})
        lines = ["### 🏋️ Тренировочная комната (hero hp=100/1000)", ""]
        for st in report["steps"]:
            lines.append(f"- event **{st['event']}** → hero hp={st['hero_hp']}, "
                         f"манекен hp={st['dummy_hp']}")
        s = report["summary"]
        lines += ["", f"**Итог:** HP {s['hp']}/{s['max_hp']} ({s['hp_pct']}%), "
                      f"kills={s['kills']}",
                  f"- моды: `{json.dumps(s['mods'], ensure_ascii=False)}`",
                  f"- баффы: `{json.dumps(s['buffs'], ensure_ascii=False)}`",
                  "", "**Лог эффектов:**", "```"]
        lines += report["log"][:40]
        lines.append("```")
        self.room_out.value = "\n".join(lines)
        self._set_status("тренировочная комната прогнана ✅",
                         ft.Colors.GREEN_400)
        self.page.update()


# ---------------------------------------------------------------- entry point

def main(page: ft.Page):
    BuilderApp(page)


if __name__ == "__main__":
    web = "--web" in sys.argv
    if web:
        ft.run(main, view=ft.AppView.WEB_BROWSER, port=8550)
    else:
        ft.run(main)
