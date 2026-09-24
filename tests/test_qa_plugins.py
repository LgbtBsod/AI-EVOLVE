"""Плагины tools/qa.py (tools/qa_plugins/*): автообнаружение, item и lua команды."""
import argparse
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import lua_bridge  # noqa: E402
import qa  # noqa: E402
import qa_graph  # noqa: E402

needs_lua = pytest.mark.skipif(not lua_bridge.available_backends(), reason="no Lua backend")


def run(capsys, *argv):
    code = qa.main(list(argv))
    return code, capsys.readouterr().out


def test_plugins_are_discovered_and_live_in_the_import_graph():
    sub = argparse.ArgumentParser().add_subparsers()
    qa.load_plugins(sub)
    assert {"item", "lua"} <= set(sub.choices)
    status = qa_graph.liveness(qa_graph.build())
    assert status["tools/qa_plugins/item.py"] == "tool"  # найден через DYNAMIC_EDGES, не «мёртвый»


def test_broken_plugin_does_not_break_qa(monkeypatch):
    import qa_plugins
    broken = types.ModuleType("qa_plugins.broken")
    broken.register = lambda sub: (_ for _ in ()).throw(RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "qa_plugins.broken", broken)
    import pkgutil
    real = pkgutil.iter_modules
    monkeypatch.setattr(pkgutil, "iter_modules",
                        lambda path: [*real(path), pkgutil.ModuleInfo(None, "broken", False)]
                        if path == qa_plugins.__path__ else real(path))
    qa.PLUGIN_ERRORS.clear()
    qa.load_plugins(argparse.ArgumentParser().add_subparsers())
    assert qa.PLUGIN_ERRORS == {"broken": "RuntimeError: boom"}
    qa.PLUGIN_ERRORS.clear()


@needs_lua
def test_lua_check_and_show(capsys):
    code, out = run(capsys, "lua", "check")
    assert code == 0 and out.strip().endswith(f"with {', '.join(lua_bridge.available_backends())}")
    code, out = run(capsys, "lua", "show", "lua_content/qa.lua", "--key", "sweep.metrics")
    assert code == 0 and out.strip().startswith('["kills"')
    code, out = run(capsys, "lua", "show", "lua_content/dev_tools.lua", "--keys")
    assert "analysis: table" in out


@needs_lua
def test_item_commands(capsys):
    code, out = run(capsys, "item", "digest", "catalog:lost_my_self.attack")
    assert code == 0 and out.splitlines()[0] == "lost_my_self.attack: 2 effect(s)"
    code, out = run(capsys, "item", "check", "--forge", "20", "--seed", "4", "--samples", "20")
    assert code == 0 and out.startswith("PASS Forged Item")
    code, out = run(capsys, "item", "diff", "lua_content/items/sorrow_of_berserk.lua")
    assert code == 0 and (out.strip() == "no differences" or out[:2] in ("+ ", "- ", "~ "))


@needs_lua
def test_item_all_passes(capsys):
    code, out = run(capsys, "item", "all", "--samples", "20")
    assert code == 0, out
    assert out.strip().splitlines()[-1].startswith("items: ")
