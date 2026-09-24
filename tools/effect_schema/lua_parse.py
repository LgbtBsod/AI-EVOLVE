"""Lua -> JSON для Effect Schema v1 (обратная сторона lua_gen).

Раньше здесь был самописный токенизатор и парсер подмножества Lua, который
восстанавливал условия из текста функций. Теперь файл исполняет настоящий
Lua (tools/lua_bridge.py: rust_core/mlua или lupa), а условия приходят из
pred("исходник", function(ctx) ... end) готовой строкой.

API:
    parse_lua(text) -> object (dict/list/scalar)
    load_item_file(path) -> {"item": {...}, "effects": [...]}
"""

from __future__ import annotations

from pathlib import Path

from .. import lua_bridge
from ..lua_bridge import LuaContentError as LuaParseError  # noqa: F401  (прежнее имя исключения)


def parse_lua(text: str):
    return lua_bridge.load(text)


def load_item_file(path) -> dict:
    data = lua_bridge.load(Path(path), cache=True)
    effects = data.pop("effects", []) if isinstance(data, dict) else []
    return {"item": data, "effects": effects}
