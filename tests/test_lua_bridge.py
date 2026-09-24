"""tools/lua_bridge.py: один загрузчик Lua-контента, два бэкенда (rust_core/mlua и lupa).

Проверяется то, на что опираются инструменты: одинаковые данные из обоих
бэкендов на каждом Lua-файле проекта, условия pred() приходят исходной
строкой и считаются Lua так же, как Python (sim.eval_pred), песочница, кэш.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import lua_bridge  # noqa: E402
from tools.effect_schema import sim  # noqa: E402
from tools.effect_schema.digest import diff, digest  # noqa: E402
from tools.effect_schema.lua_gen import render_item  # noqa: E402

BACKENDS = lua_bridge.available_backends()
pytestmark = pytest.mark.skipif(not BACKENDS, reason="no Lua backend (lupa / rust_core)")
LUA_FILES = sorted((ROOT / "lua_content").rglob("*.lua"))

ITEM_EFFECTS = [
    {"id": "low", "trigger": {"kind": "condition", "when": "ctx.hp_pct < 40"},
     "amplify": {"when": "ctx.hp <= 1", "every": 10, "of": "hp_missing_below_40", "factor": 2},
     "ops": [{"kind": "mod", "target": "self", "stat": "strength", "op": "add", "value": {"pct": 20}}]},
    {"id": "hit", "trigger": {"kind": "event", "event": "attack", "filter": "ctx.kills != 0 and 1 < ctx.hp_pct <= 90"},
     "ops": [{"kind": "deal", "target": "enemy", "stat": "hp", "op": "sub", "value": {"flat": 5},
              "when": "max(ctx.hp, ctx.strength) >= 10 or ctx.hp_pct ** 2 > 100"}]},
]


@pytest.fixture
def item_lua():
    return render_item({"name": "Bridge Test"}, ITEM_EFFECTS)


@pytest.mark.parametrize("path", LUA_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_backends_agree_on_every_project_lua_file(path):
    if len(BACKENDS) < 2:
        pytest.skip("parity needs both rust_core and lupa")
    loaded = [lua_bridge.load(path, backend=b) for b in BACKENDS]
    assert all(x == loaded[0] for x in loaded[1:])


@pytest.mark.parametrize("backend", BACKENDS)
def test_generated_item_round_trips_with_predicate_sources(backend, item_lua):
    data = lua_bridge.load(item_lua, backend=backend)
    assert data["name"] == "Bridge Test"
    assert data["effects"] == ITEM_EFFECTS  # условия - исходные строки, числа - те же


@pytest.mark.parametrize("backend", BACKENDS)
def test_lua_predicates_match_python_on_random_contexts(backend, item_lua):
    import random
    rng = random.Random(7)
    ctxs = [{"hp": rng.choice([1, rng.uniform(0, 500)]), "hp_pct": rng.uniform(0, 100),
             "kills": rng.choice([0, 1, 3]), "strength": rng.uniform(0, 30)} for _ in range(200)]
    rows = lua_bridge.eval_preds(item_lua, ctxs, backend=backend)
    sources = ["ctx.hp_pct < 40", "ctx.hp <= 1", "ctx.kills != 0 and 1 < ctx.hp_pct <= 90",
               "max(ctx.hp, ctx.strength) >= 10 or ctx.hp_pct ** 2 > 100"]
    for ctx, row in zip(ctxs, rows):
        assert set(row) == set(sources)
        for src in sources:
            assert row[src] == bool(sim.eval_pred(src, ctx)), (src, ctx)


@pytest.mark.parametrize("backend", BACKENDS)
def test_functions_dropped_and_globals_mode(backend):
    assert lua_bridge.load("return { a = 1, f = function() end, t = { 1, 2 } }", backend=backend) == \
        {"a": 1, "t": [1, 2]}
    src = "mannequins = { dummy = { hp = 10 } }\nreturn { fallback = true }"
    assert lua_bridge.load(src, globals=("mannequins", "scenarios"), backend=backend) == \
        {"mannequins": {"dummy": {"hp": 10}}}
    assert lua_bridge.load("return { fallback = true }", globals=("mannequins",), backend=backend) == \
        {"fallback": True}


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("src", ["return io.open('x')", "return os.time()", "return dofile('x')",
                                 "return load('return 1')()", "return {", "local t = {}; t.me = t; return t"])
def test_sandbox_and_errors_raise_lua_content_error(backend, src):
    with pytest.raises(lua_bridge.LuaContentError):
        lua_bridge.load(src, backend=backend)


@pytest.mark.parametrize("backend", BACKENDS)
def test_print_is_silenced(backend, capfd):
    assert lua_bridge.load("print('noise'); return 1", backend=backend) == 1
    assert "noise" not in capfd.readouterr().out


def test_rust_instruction_budget_stops_infinite_loop():
    if "rust" not in BACKENDS:
        pytest.skip("rust_core not built")
    with pytest.raises(ValueError, match="instruction budget"):
        lua_bridge._RustLua.load_json("while true do end", max_instructions=1_000_000)


def test_export_lua_is_shared_between_backends():
    if "rust" not in BACKENDS:
        pytest.skip("rust_core not built")
    assert lua_bridge._RustLua.EXPORT_LUA == lua_bridge.EXPORT_LUA_PATH.read_text(encoding="utf-8")


def test_cache_hit_skips_lua_and_survives_corruption(tmp_path, monkeypatch, item_lua):
    monkeypatch.setattr(lua_bridge, "CACHE_DIR", tmp_path)
    first = lua_bridge.load(item_lua, cache=True)
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text(encoding="utf-8")) == first
    monkeypatch.setitem(lua_bridge.LOADERS, "rust", None)
    monkeypatch.setitem(lua_bridge.LOADERS, "lupa", None)
    assert lua_bridge.load(item_lua, cache=True) == first  # без единого бэкенда - из кэша
    files[0].write_text("{broken", encoding="utf-8")
    monkeypatch.undo()
    monkeypatch.setattr(lua_bridge, "CACHE_DIR", tmp_path)
    assert lua_bridge.load(item_lua, cache=True) == first  # битый кэш перечитывается


def test_digest_and_diff_are_compact():
    item = {"name": "Bridge Test", "effects": ITEM_EFFECTS}
    lines = digest(item)
    assert lines[0] == "Bridge Test: 2 effect(s)"
    assert lines[1] == ("low | condition when[ctx.hp_pct < 40] | amplify x2/10 hp_missing_below_40 "
                        "when[ctx.hp <= 1] | mod self strength add 20%")
    changed = json.loads(json.dumps(item))
    changed["effects"][1]["ops"][0]["value"] = {"flat": 7}
    changed["effects"].append({"id": "new", "trigger": {"kind": "passive"}, "ops": []})
    out = diff(item, changed)
    assert out[0] == "+ new" and out[1].startswith("~ hit") and "sub 7" in out[1]
    assert diff(item, item) == ["no differences"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_sparse_integer_keys_stay_a_mapping(backend):
    # { [76] = ... } - номера уровней, а не список: lupa раньше терял ключи
    assert lua_bridge.load("return { [76] = 'a', [80] = 'b' }", backend=backend) == {"76": "a", "80": "b"}
    assert lua_bridge.load("return { 'x', 'y' }", backend=backend) == ["x", "y"]
