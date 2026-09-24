"""Билдер предметов без окна: тот же BuilderApp на подставной странице.

Агент (или тест) работает с формой так же, как человек: находит поле по
подписи, вводит значение, жмёт кнопку по тексту - вызываются настоящие
обработчики UI (валидация, сборка Lua, тренировочная комната, itemcheck).

    from tools.web_builder.headless import UI
    ui = UI()
    ui.pick("Шаблон из каталога", "lost_my_self")
    ui.click("+ эффект"); ui.fill("effect.id *", "my_aura") ...
    ui.click("Проверить предмет (itemcheck)"); print(ui.status)

CLI: python tools/web_builder/headless.py --template lost_my_self --check [--save PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft  # noqa: E402

from tools.web_builder.app import BuilderApp  # noqa: E402


class HeadlessPage:
    """Минимум ft.Page, который трогает BuilderApp."""

    def __init__(self):
        self.controls: list = []
        self.title = self.theme_mode = self.padding = None
        self.updates = 0

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self, *controls):
        self.updates += 1


def walk(control) -> Iterator[Any]:
    """Все контролы дерева (controls / content / fail-списки)."""
    yield control
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                yield from walk(c)
        elif child is not None and not isinstance(child, str):
            yield from walk(child)


def _label(c) -> str | None:
    lbl = getattr(c, "label", None)
    return lbl if isinstance(lbl, str) else None


def _text(c) -> str | None:
    for attr in ("content", "text"):
        v = getattr(c, attr, None)
        if isinstance(v, str):
            return v
    return None


class UI:
    def __init__(self):
        self.page = HeadlessPage()
        self.app = BuilderApp(self.page)

    # -- поиск --------------------------------------------------------------
    def controls(self) -> list:
        return [c for root in self.page.controls for c in walk(root)]

    def field(self, label: str, nth: int = 0):
        """Поле/выпадающий список/чекбокс по подписи (nth - если таких несколько, напр. в разных ops)."""
        found = [c for c in self.controls() if _label(c) == label and getattr(c, "visible", True) is not False]
        if len(found) <= nth:
            raise LookupError(f"no field {label!r} (#{nth}); have: {sorted({_label(c) for c in self.controls() if _label(c)})}")
        return found[nth]

    def button(self, text: str):
        for c in self.controls():
            if _text(c) == text and getattr(c, "on_click", None) is not None:
                return c
        raise LookupError(f"no button {text!r}")

    # -- действия пользователя --------------------------------------------------
    def fill(self, label: str, value, nth: int = 0) -> "UI":
        f = self.field(label, nth)
        f.value = value if isinstance(value, (bool, type(None))) else str(value)
        handler = getattr(f, "on_change", None) or getattr(f, "on_select", None)
        if handler:
            handler(None)
        return self

    pick = fill  # выбор в Dropdown - то же присваивание value + on_select

    def check(self, label: str, value: bool = True, nth: int = 0) -> "UI":
        return self.fill(label, value, nth)

    def click(self, text: str) -> "UI":
        self.button(text).on_click(None)
        return self

    # -- что видит пользователь --------------------------------------------------
    @property
    def status(self) -> str:
        return self.app.status.value or ""

    def panel(self, which: str) -> str:
        return {"json": self.app.json_out, "lua": self.app.lua_out, "room": self.app.room_out}[which].value or ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Item builder without a window")
    ap.add_argument("--template", action="append", default=[], help="catalog template(s) to add")
    ap.add_argument("--open", help="open an item .lua first")
    ap.add_argument("--room", metavar="SCENARIO", help="run the training room with this scenario")
    ap.add_argument("--check", action="store_true", help="run itemcheck")
    ap.add_argument("--save", metavar="PATH", help="save the item as Lua")
    args = ap.parse_args(argv)
    ui = UI()
    if args.open:
        ui.fill("файл .lua (lua_content/items/…)", args.open).click("Открыть .lua")
    for t in args.template:
        ui.pick("Шаблон из каталога", t)
    ui.click("Валидировать")
    print(ui.status)
    if args.room:
        ui.fill("сценарий комнаты (шаги через ;)", args.room).click("Тест в тренировочной комнате")
        print(ui.panel("room"))
    if args.check:
        ui.click("Проверить предмет (itemcheck)")
        print(ui.panel("room").removeprefix("```text\n").rstrip("`\n"))
    if args.save:
        ui.fill("файл .lua (lua_content/items/…)", args.save).click("Сохранить .lua")
        print(ui.status)
    return 0 if "❌" not in ui.status and "FAIL" not in ui.status else 1


if __name__ == "__main__":
    sys.exit(main())
