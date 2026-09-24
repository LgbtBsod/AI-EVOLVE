"""Tests for the agent dev tools: tools/probe_kernels.py (Rust/Python parity),
probe_settings.py (Lua), probe_analysis.py (hypotheses/forecast), probe_db.py
(SQLite analytics), agent_play.py (script DSL) and - when Panda3D is present -
windowless fast-forward runs of agent_play.py/dev_probe.py (determinism)."""
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import probe_analysis as analysis  # noqa: E402
import probe_db  # noqa: E402
import probe_kernels as kernels  # noqa: E402
import probe_settings  # noqa: E402
from agent_play import ScriptError, eval_condition, parse_condition, parse_script  # noqa: E402


def _close(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    return a == b


def _samples(hp_series, pos=None, enemies=None, dt=1.0):
    out = []
    for i, hp in enumerate(hp_series):
        out.append({
            "t": round(i * dt, 2),
            "player": {"id": "hero_1", "hp": hp, "max_hp": 100, "pos": list(pos[i] if pos else (i * 1.0, 0.0)),
                       "alive": hp > 0, "xp": i * 10.0, "xp_next": 1000},
            "enemies": enemies[i] if enemies else [],
        })
    return out


# ---------------------------------------------------------------- kernels

class TestKernels:
    def test_backend_is_reported(self):
        assert kernels.BACKEND in ("rust", "python")

    def test_python_twins_basic(self):
        assert kernels.py_linear_fit([0, 1, 2], [1, 3, 5]) == (2.0, 1.0)
        assert kernels.py_linear_fit([1, 1], [0, 5]) is None
        assert kernels.py_sparkline([0.0, 7.0]) == "▁█"
        assert kernels.py_log_template("12:00:01 hp 5 of enemy_1a2b3c4d at 0x1f") == "hp # of enemy_# at #"
        digest, distinct = kernels.py_log_digest(["12:00:00 a 5", "12:00:01 a 7", "b"], 5)
        assert digest == [(2, "a 5"), (1, "b")] and distinct == 2

    @pytest.mark.skipif(kernels.BACKEND != "rust", reason="rust_core not built (pip install ./rust_core)")
    def test_rust_matches_python_twins(self):
        rng = random.Random(7)
        for _ in range(200):
            n = rng.randint(0, 60)
            vals = [rng.uniform(-5, 100) for _ in range(n)]
            xs = [rng.uniform(0, 10) for _ in range(n)]
            w = rng.randint(1, 30)
            assert kernels.sparkline(vals, w) == kernels.py_sparkline(vals, w)
            assert _close(kernels.linear_fit(xs, vals), kernels.py_linear_fit(xs, vals))
            samples = _samples([rng.choice([100, 15, 10, 0, 50]) for _ in range(n)],
                               pos=[(rng.choice([1.0, 1.1, 5.0]), 0.0) for _ in range(n)],
                               enemies=[[{"hp": rng.choice([0, 10]), "pos": [rng.uniform(-9, 9), rng.uniform(-9, 9)]}
                                         for _ in range(rng.randint(0, 4))] for _ in range(n)])
            table = kernels.HeroTable.from_samples(samples)
            params = {"low_hp_fraction": 0.2, "pinned_seconds": 3.0, "stuck_seconds": 4.0,
                      "stuck_distance": 0.5, "spark_width": 24}
            busy = sorted(rng.uniform(0, n or 1) for _ in range(rng.randint(0, 3)))
            assert _close(kernels.scan_hero(table, params, busy), kernels.py_scan_hero(table, params, kernels.f64(busy)))
        lines = [f"12:00:0{i % 10} WARNING x: hp {i} of enemy_{i:08x}" for i in range(30)] + ["ERROR boom"]
        assert kernels.log_digest(lines, 5) == kernels.py_log_digest(lines, 5)

    @pytest.mark.skipif(kernels.BACKEND != "rust", reason="rust_core not built")
    def test_rust_rejects_mismatched_columns(self):
        with pytest.raises(ValueError):
            kernels.pinned_interval([1.0, 2.0], [1.0], [1.0], [1], 0.2, 1.0)

    def test_hero_table_is_columnar(self):
        table = kernels.HeroTable.from_samples(_samples([100, 50], enemies=[[{"hp": 1, "pos": [3, 4]}], []]))
        assert table.ts.typecode == "d" and table.alive.typecode == "B" and table.offsets.typecode == "Q"
        assert list(table.offsets) == [0, 1, 1]


# ---------------------------------------------------------------- settings (Lua)

class TestSettings:
    def test_lua_file_is_loaded(self):
        pytest.importorskip("lupa")
        cfg = probe_settings.settings()
        assert cfg["_source"].endswith("dev_tools.lua")
        assert cfg["agent"]["player_keys"]["enemy"] == "1"

    def test_broken_lua_falls_back_to_defaults(self, tmp_path):
        bad = tmp_path / "bad.lua"
        bad.write_text("return {", encoding="utf-8")
        cfg = probe_settings.settings(bad)
        assert cfg["analysis"] == probe_settings.DEFAULTS["analysis"]
        assert "defaults" in cfg["_source"]


# ---------------------------------------------------------------- analysis

class TestAnalysis:
    def ids(self, hyps):
        return {h["id"] for h in hyps}

    def test_no_combat_far_enemies(self):
        s = _samples([100] * 10, enemies=[[{"id": "e1", "hp": 10, "pos": [150, 0]}]] * 10)
        assert "NO_COMBAT" in self.ids(analysis.hypotheses(s, [], {"duration": 10}))

    def test_close_enemies_without_attacks(self):
        s = _samples([100] * 10, pos=[(0, 0)] * 10, enemies=[[{"id": "e1", "hp": 10, "pos": [1, 0]}]] * 10)
        hyps = analysis.hypotheses(s, [], {"duration": 10})
        assert hyps[0]["id"] == "CLOSE_BUT_NO_ATTACKS" and hyps[0]["severity"] == "high"

    def test_hp_pinned_and_stuck(self):
        s = _samples([100] + [10] * 12, pos=[(1.0, 1.0)] * 13)
        ids = self.ids(analysis.hypotheses(s, [], {"duration": 12}))
        assert {"HP_PINNED", "HERO_STUCK"} <= ids

    def test_hero_never_attacks_back(self):
        s = _samples([100, 90, 80, 70, 60, 50])
        ev = [{"t": i, "source": "e1", "target": "hero_1", "damage": 10.0, "critical": False, "dodged": False}
              for i in range(5)]
        assert "HERO_NEVER_ATTACKS" in self.ids(analysis.hypotheses(s, ev, {}))

    def test_errors_point_to_code(self):
        tb = 'Traceback:\n  File "/x/AI-EVOLVE/src/entities/enemy.py", line 12, in attack\nValueError: boom'
        hyps = analysis.hypotheses(_samples([100] * 3), [], {"errors": ["ERROR x: boom"], "error_text": tb})
        assert hyps[0]["id"] == "ERRORS" and hyps[0]["look_at"] == ["src/entities/enemy.py:12 in attack"]

    def test_forecast_death_eta_and_ttk(self):
        s = _samples([100 - 5 * i for i in range(12)], enemies=[[{"id": "e1", "hp": 5, "pos": [1, 0]}]] * 12)
        fc = analysis.forecast(s, [], {"kills": [(6.0, "e1", "basic")], "duration": 11})
        assert fc["hp_slope_per_s"] == -5.0
        assert fc["death_eta_s"] == pytest.approx(9.0)
        assert fc["ttk_by_type_s"] == {"basic": 6.0}
        assert "die" in fc["outlook"]

    def test_digest_log_collapses_repeats(self):
        lines = [f"10:00:0{i} WARNING src.x: HP {i} below 20" for i in range(5)]
        assert analysis.digest_log(lines) == ["[x5] WARNING src.x: HP 0 below 20"]


# ---------------------------------------------------------------- probe DB

class TestProbeDB:
    def test_ingest_and_query(self, tmp_path):
        con = probe_db.connect(tmp_path / "p.sqlite")
        s = _samples([100, 90, 80, 70], enemies=[[{"id": "e1", "type": "basic", "hp": 10, "max_hp": 10, "pos": [1, 0]}]] * 3 + [[]])
        ev = [{"t": 1.0, "source": "hero_1", "target": "e1", "source_type": "hero", "target_type": "basic",
               "damage": 10.0, "critical": True, "dodged": False},
              {"t": 1.5, "source": "e1", "target": "hero_1", "source_type": "basic", "target_type": "hero",
               "damage": 10.0, "critical": False, "dodged": False}]
        probe_db.ingest(con, "run_a", {"kind": "agent_play", "status": "OK", "duration": 3, "created": 1}, s, ev,
                        [(3.0, "e1", "basic")])
        probe_db.ingest(con, "run_b", {"kind": "agent_play", "status": "FAIL", "duration": 3, "created": 2}, s, ev[1:])

        class A:
            run = "run_a"
            last = 10
            limit = None
        stats = probe_db.cmd_stats(con, A)
        assert "basic" in stats and "hero->enemies" in stats
        assert "HP" in stats
        assert probe_db.resolve_run(con, "last") == "run_b"
        A.a, A.b = "run_a", "run_b"
        cmp = probe_db.cmd_compare(con, A)
        assert "status: OK -> FAIL" in cmp and "kills: 1 -> 0" in cmp
        A.metric, A.kind = "kills", None
        assert "kills over 2 run(s)" in probe_db.cmd_trend(con, A)
        A.query, A.max_rows = "SELECT COUNT(*) n FROM combat", 5
        assert probe_db.cmd_sql(con, A).splitlines()[1].strip() == "3"
        assert "forecast" in probe_db.cmd_predict(con, A)


# ---------------------------------------------------------------- agent_play DSL

class TestScript:
    def test_parses_player_actions(self):
        cmds = parse_script("spawn enemy x3; attack; interact 1; wait 5\nuntil kills>=2 or dead max 30 # c\nexpect alive")
        assert [c[0] for c in cmds] == ["press", "press", "hold", "wait", "until", "expect"]
        assert cmds[0][1] == {"key": "1", "times": 3, "what": "enemy"}
        assert cmds[4][1]["max"] == 30.0

    @pytest.mark.parametrize("bad", ["fly 3", "spawn dragon", "wait -1", "wait 99999", "expect hp", "expect foo>1",
                                     "spawn enemy x999", "screenshot ../../x"])
    def test_rejects_bad_commands(self, bad):
        with pytest.raises(ScriptError):
            parse_script(bad)

    def test_conditions(self):
        m = {"kills": 3, "alive": True, "dead": False, "hp": 10.0, "nearest": None}
        assert eval_condition(parse_condition("kills>=3 and alive"), m)
        assert eval_condition(parse_condition("dead or hp<20"), m)
        assert not eval_condition(parse_condition("nearest<5"), m)  # нет врагов -> ложь
        assert eval_condition(parse_condition("not dead"), m)


# ---------------------------------------------------------------- real game (windowless, fast)

def _run(args, tmp_path):
    env = {**os.environ, "AI_EVOLVE_PROBE_DB": str(tmp_path / "probe.sqlite")}
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)


@pytest.mark.skipif(importlib.util.find_spec("panda3d") is None, reason="Panda3D not installed")
class TestRealGame:
    SCRIPT = "spawn enemy x2; until kills>=1 max 40; observe; expect kills>=1; expect alive; wait 5"

    # Основная причина найдена (`qa.py determinism`, 2026-09-24): база виртуальных часов бралась из
    # реального времени процесса, и сравнения "прошла ли ровно 1.0 с" решал случайный младший бит
    # (расхождения пар: Windows 12%, Linux 57%). База теперь фиксированная (tools/probe_runtime.py):
    # остаётся ~1-2% пар, где глобальный random расходится уже на кадре 0 и только при случайном
    # хеше строк (hashseed0 чист) - вероятно, обход множества строк при загрузке. Пока это не
    # найдено, тест на POSIX нестрогий (XFAIL/XPASS виден в отчёте, CI не красит).
    @pytest.mark.xfail(sys.platform != "win32", strict=False, reason="same-seed runs occasionally diverge on POSIX (open bug)")
    def test_agent_play_is_deterministic(self, tmp_path):
        finals = []
        for i in range(2):
            out = tmp_path / f"run{i}"
            proc = _run(["tools/agent_play.py", "--seed", "5", "--out", str(out), self.SCRIPT], tmp_path)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            assert "RESULT status=OK" in proc.stdout
            assert len(proc.stdout.splitlines()) < 25  # компактный вывод
            session = json.loads((out / "session.json").read_text(encoding="utf-8"))
            finals.append((session["final"], session["kills_list"]))
        assert finals[0] == finals[1]  # побитово одинаковые прогоны при одном seed

    def test_no_invariant_violations_in_a_fight(self, tmp_path):
        """Регрессия HP > max_health: HealthComponent героя создавался до того,
        как класс выставлял max_health, и перезаписывал HP (149/120)."""
        proc = _run(["tools/agent_play.py", "--seed", "7", "--out", str(tmp_path / "inv"), "spawn enemy x10; wait 20"],
                    tmp_path)
        session = json.loads((tmp_path / "inv" / "session.json").read_text(encoding="utf-8"))
        assert session["invariants"] == [], session["invariants"]
        assert "INVARIANT" not in proc.stdout

    def test_agent_play_failure_prints_repro(self, tmp_path):
        proc = _run(["tools/agent_play.py", "--out", str(tmp_path / "f"), "wait 1; expect kills>=99"], tmp_path)
        assert proc.returncode == 1
        assert "FAIL expect kills>=99" in proc.stdout and "repro: python tools/agent_play.py" in proc.stdout

    def test_dev_probe_windowless_fast(self, tmp_path):
        out = tmp_path / "dp"
        proc = _run(["tools/dev_probe.py", "--render", "none", "--fast", "--seed", "2", "--duration", "15",
                     "--action-at", "1:1", "--out", str(out)], tmp_path)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert len(proc.stdout.splitlines()) <= 6, proc.stdout  # без ALSA/Panda3D-мусора
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "OK" and summary["repro_exact"] is True
        assert "## Hypotheses" in (out / "summary.md").read_text(encoding="utf-8")
        con = probe_db.connect(tmp_path / "probe.sqlite")
        assert con.execute("SELECT COUNT(*) FROM runs WHERE kind='dev_probe'").fetchone()[0] == 1
