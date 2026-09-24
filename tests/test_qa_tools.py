"""Tests for the QA layer: tools/qa_graph.py (import graph), qa_pool.py (async
subprocess pool), probe_invariants.py, qa.py helpers (ddmin shrink, sharding,
outline, fuzz signatures), QA kernels (Rust/Python parity) and the
virtual_time marker from tests/conftest.py."""
import importlib.util
import json
import math
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import probe_kernels as kernels  # noqa: E402
import qa  # noqa: E402
import qa_graph  # noqa: E402
from probe_invariants import InvariantChecker  # noqa: E402
from qa_pool import python_job, run_many  # noqa: E402


# ---------------------------------------------------------------- import graph

@pytest.fixture(scope="module")
def graph():
    return qa_graph.build()


class TestGraph:
    def test_liveness_categories(self, graph):
        status = qa_graph.liveness(graph)
        assert status["main.py"] == "game"
        assert status["src/entities/character.py"] == "game"
        assert status["tools/qa.py"] == "tool"
        assert status["tests/test_qa_tools.py"] == "test"
        assert status["src/__init__.py"] == "game"  # пакетные __init__ исполняются при import src.x
        # путь собран из частей: строковый литерал-путь в тесте граф считает запуском файла
        assert status["src/core/" + "async_game_core.py"] == "dead"
        assert status["AI-EVOLVE/tools/dev_probe/core.py"] == "test"  # жив только в собственном тесте

    def test_impact_of_game_file(self, graph):
        tests, scripts, touched = qa_graph.impacted(graph, ["src/entities/character.py"])
        assert "tests/test_agent_tools.py" in tests  # через main.py <- probe_runtime (динамический импорт)
        assert "tools/combat_smoke_test.py" in scripts  # скрипт без __main__, с sys.exit на верхнем уровне
        assert touched == ["src/entities/character.py"]

    def test_impact_of_lua_file_by_mention(self, graph):
        tests, _, touched = qa_graph.impacted(graph, ["lua_content/qa.lua"])
        assert "tools/probe_settings.py" in touched
        assert "tests/test_qa_tools.py" in tests

    def test_hint_strings_are_not_imports(self, graph):
        # probe_analysis упоминает "src/core/rng_manager.py" в подсказке - это не импорт
        assert "src/core/rng_manager.py" not in graph["tools/probe_analysis.py"]["imports"]


# ---------------------------------------------------------------- QA kernels

class TestQaKernels:
    def test_python_twins(self):
        assert kernels.py_reach([0, 1, 2, 2, 2], [1, 2], [0]) == [1, 1, 1, 0]
        assert kernels.SplitMix64(0).next_u64() == 0xE220A8397B1DCDAF
        d = kernels.py_describe([1.0, 2.0, 3.0, 4.0, math.nan], 200, 1)
        assert d["n"] == 4 and d["mean"] == 2.5 and d["p50"] == 2.5 and d["ci_lo"] <= 2.5 <= d["ci_hi"]
        assert kernels.py_fnv1a64_lines(b"ab", [0, 0, 1, 2]) == [0xCBF29CE484222325, 0xAF63DC4C8601EC8C,
                                                              0xAF63DF4C8601F1A5]

    @pytest.mark.skipif(kernels._rust_qa is None, reason="rust_core with QaKernels not built")
    def test_rust_bit_exact(self):
        rng = random.Random(3)
        for _ in range(60):
            n = rng.randint(0, 25)
            vals = [rng.uniform(-9, 9) for _ in range(n)]
            a, b = kernels.describe(vals, 150, 9), kernels.py_describe(vals, 150, 9)
            assert all((math.isnan(a[k]) and math.isnan(b[k])) if isinstance(a[k], float) and math.isnan(a[k])
                       else a[k] == b[k] for k in a)
            offs, tg = [0], []
            for _ in range(n):
                tg += [rng.randrange(n) for _ in range(rng.randint(0, 3))]
                offs.append(len(tg))
            roots = [rng.randrange(n)] if n else []
            assert list(kernels.reach(offs, tg, roots)) == kernels.py_reach(offs, tg, roots)
        lines = ["x", "", '{"t": 1.0}']
        assert kernels.lines_fingerprint(lines) == kernels.py_fnv1a64_lines(b"x" + b'{"t": 1.0}', [0, 1, 1, 11])


# ---------------------------------------------------------------- async pool

def test_pool_keeps_order_and_runs_in_parallel():
    jobs = [python_job(f"j{i}", "-c", f"import time; time.sleep(1.0); print({i})") for i in range(4)]
    start = time.perf_counter()
    results = run_many(jobs, jobs=4)
    assert [r.stdout.strip() for r in results] == ["0", "1", "2", "3"]
    assert time.perf_counter() - start < 3.0  # 4 x 1 с параллельно, а не >= 4 с подряд


def test_pool_stop_when_skips_the_tail():
    jobs = [python_job(f"j{i}", "-c", f"import sys; sys.exit({1 if i == 0 else 0})") for i in range(6)]
    results = run_many(jobs, jobs=1, stop_when=lambda r: r.rc == 1)
    assert results[0].rc == 1 and all(r.skipped for r in results[1:])


# ---------------------------------------------------------------- invariants

def _unit(hp, max_hp, x=0.0, y=0.0, alive=None, **kw):
    alive = hp > 0 if alive is None else alive
    return SimpleNamespace(health=hp, max_health=max_hp, x=x, y=y, is_alive=lambda: alive, **kw)


class TestInvariants:
    CFG = {"hp_epsilon": 0.01, "world_slack": 5.0, "max_enemies_slack": 1, "dead_enemy_frames": 2,
           "max_violations_kept": 20}

    def check(self, scene, frames=1):
        inv = InvariantChecker(self.CFG)
        game = SimpleNamespace(scene=scene)
        for i in range(frames):
            inv.check(game, i * 0.1)
        return {v["id"]: v for v in inv.report()}

    def test_clean_world(self):
        scene = SimpleNamespace(player=_unit(100, 120), enemies=[_unit(10, 10, entity_id="enemy_1")],
                                world_size=100, max_enemies=5, player_created_objects=[])
        assert self.check(scene) == {}

    def test_catches_bugs(self):
        dead = _unit(0, 10, entity_id="enemy_dead", alive=False)
        scene = SimpleNamespace(player=_unit(149, 120), enemies=[dead, _unit(5, 10, x=999, entity_id="enemy_far"),
                                                                 _unit(math.nan, 10, entity_id="enemy_nan")],
                                world_size=100, max_enemies=1, player_created_objects=[])
        found = self.check(scene, frames=4)
        assert {"HERO_HP_OVER_MAX", "OUT_OF_WORLD", "NON_FINITE", "DEAD_ENEMY_LINGERS", "ENEMY_OVERFLOW"} <= set(found)
        assert found["HERO_HP_OVER_MAX"]["count"] == 4 and found["HERO_HP_OVER_MAX"]["t"] == 0.0

    def test_player_spawned_enemies_do_not_overflow(self):
        mine = [_unit(10, 10, entity_id=f"enemy_{i}") for i in range(5)]
        scene = SimpleNamespace(player=_unit(100, 120), enemies=mine, world_size=100, max_enemies=1,
                                player_created_objects=mine)
        assert "ENEMY_OVERFLOW" not in self.check(scene)

    def test_hero_alive_at_zero(self):
        scene = SimpleNamespace(player=_unit(0, 120, alive=True), enemies=[], world_size=100, max_enemies=5)
        assert "HERO_ALIVE_AT_ZERO" in self.check(scene)


# ---------------------------------------------------------------- qa.py helpers

def test_ddmin_shrinks_to_minimal_script(monkeypatch):
    def fake_run(scripts, seed, base, jobs, tag):
        out = []
        for cmds in scripts:
            bug = "b" in cmds and "d" in cmds
            r = SimpleNamespace(rc=1 if bug else 0)
            out.append((cmds, r, {"invariants": [{"id": "X"}]} if bug else {"invariants": []}))
        return out
    monkeypatch.setattr(qa, "_run_scripts", fake_run)
    assert qa.shrink(list("abcdefgh"), 1, "X", Path("."), 2) == ["b", "d"]


def test_signatures_split_per_bug():
    sess = {"invariants": [{"id": "A"}, {"id": "B"}], "errors": ["12:00:00 ERROR x: boom 42"], "fatal": None}
    assert qa._signatures(sess, SimpleNamespace(rc=1)) == {"A", "B", "ERROR:boom #"}
    assert qa._signatures(None, SimpleNamespace(rc=3)) == {"CRASH rc=3"}


def test_shards_balance_by_duration(tmp_path, monkeypatch):
    durations = tmp_path / "d.json"
    durations.write_text(json.dumps({"a": 10, "b": 9, "c": 1, "d": 1}), encoding="utf-8")
    monkeypatch.setattr(qa, "DURATIONS", durations)
    shards = qa._shards(["a", "b", "c", "d"], 2)
    assert sorted(map(sorted, shards)) == [["a", "c"], ["b", "d"]] or sorted(map(sorted, shards)) == [["a", "d"], ["b", "c"]]


def test_outline_is_compact(tmp_path):
    src = tmp_path / "m.py"
    src.write_text('"""Doc."""\nLIMIT = 3\n\nclass A:\n    """Cls doc."""\n    def run(self, x, *a, k=1, **kw):\n'
                   '        """Runs."""\n\ndef f(y):\n    pass\n', encoding="utf-8")
    assert qa.outline(src) == ["L2 LIMIT = ...", "L4 class A  # Cls doc.", "  L6 .run(x, *a, k, **kw)  # Runs.",
                               "L9 def f(y)"]


# ---------------------------------------------------------------- virtual_time marker

@pytest.mark.virtual_time
def test_virtual_time_marker_makes_sleep_instant():
    from src.systems.combat.components import toughness_component
    real_start = time.__getattr__("perf_counter")()  # настоящие часы под ручными
    before = time.perf_counter()
    time.sleep(1000)  # ручные часы: мгновенно
    assert time.perf_counter() - before == pytest.approx(1000)
    assert toughness_component.time is time  # код игры видит те же часы
    assert time.__getattr__("perf_counter")() - real_start < 5  # настоящее время почти не шло


def test_virtual_time_is_restored_after_marked_test():
    from src.systems.combat.components import toughness_component
    assert toughness_component.time is __import__("time")


# ---------------------------------------------------------------- real game

@pytest.mark.skipif(importlib.util.find_spec("panda3d") is None, reason="Panda3D not installed")
def test_story_and_golden_smoke(tmp_path):
    import subprocess
    out = tmp_path / "s"
    proc = subprocess.run([sys.executable, "tools/agent_play.py", "--seed", "3", "--no-invariants", "--out", str(out),
                           "wait 12; story"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert "start -> " in proc.stdout
    session = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert session["story"] and session["story"][0][1] is None
