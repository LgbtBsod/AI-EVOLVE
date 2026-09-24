"""qa.py determinism (tools/qa_plugins/determinism.py) + its two producers: agent_play --trace-frames and the
leak recorder (tools/probe_runtime.py, AI_EVOLVE_LEAK_REPORT).

Everything except the last class runs on synthetic traces / synthetic code and never boots the game, so
nothing here depends on timing. The last class runs the real command once (skipped without Panda3D)."""
import importlib.util
import json
import math
import random
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import agent_play  # noqa: E402
import lua_bridge  # noqa: E402
import probe_runtime  # noqa: E402
import qa_pool  # noqa: E402
from qa_plugins import determinism as det  # noqa: E402

FPS = 30
RESULT_RE = re.compile(r"^RESULT determinism pairs=(\d+) diverged=(\d+) classes=(\d+) first_frame=(\S+) t=(\S+) "
                       r"channel=(rng|state|none)", re.M)


# ------------------------------------------------------------------ synthetic traces

def enemy(i, x=10.0, y=5.0, hp=40.0, ty="slime"):
    return {"id": f"e{i}", "ty": ty, "x": agent_play.hex_float(x), "y": agent_play.hex_float(y),
            "hp": agent_play.hex_float(hp)}


def world(hero_x=1.0, hero_hp=100.0, enemies=None):
    hx = agent_play.hex_float
    return {"hero": {"x": hx(hero_x), "y": hx(2.0), "hp": hx(hero_hp), "mana": hx(30.0), "stamina": hx(50.0),
                     "ai": "fighting", "lvl": 1, "xp": hx(0.0)},
            "en": enemies if enemies is not None else [enemy(1), enemy(2, ty="goblin")]}


def make_trace(n, world_at=lambda i: world(), rng_at=lambda i: "aaaaaaaa:bbbbbbbb:-", t_at=lambda i: i / FPS):
    """Records exactly as FrameTracer writes them (state omitted while unchanged)."""
    records, prev = [], None
    for i in range(n):
        w, t = world_at(i), t_at(i)
        wh = agent_play.hash_state(w)
        rec = {"f": i, "t": t, "h": agent_play.hash_state([agent_play.hex_float(t), wh]), "r": rng_at(i)}
        if wh != prev:
            rec["s"] = w
        prev = wh
        records.append(rec)
    return records


def carried(records):
    """What load_trace returns: state carried forward into every record."""
    out, state = [], None
    for rec in records:
        rec = dict(rec)
        state = rec.get("s", state)
        rec["s"] = state
        out.append(rec)
    return out


def write_trace(path, records):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records), encoding="utf-8")


def plus_ulp(x, n=1):
    for _ in range(n):
        x = math.nextafter(x, math.inf)
    return x


def compare(a, b, **cfg):
    return det.compare_traces(carried(a), carried(b), {**det.DEFAULTS, **cfg})


def hypothesis_ids(div, **kw):
    ctx = det.build_context(div, det.DEFAULTS, **kw)
    return [h["id"] for h in det.evaluate_rules(ctx, det.DEFAULTS)]


# ------------------------------------------------------------------ ULP helper

class TestUlpDistance:
    def test_neighbours_and_equal(self):
        assert det.ulp_distance(1.0, 1.0) == 0
        assert det.ulp_distance(1.0, math.nextafter(1.0, 2.0)) == 1
        assert det.ulp_distance(1.0, plus_ulp(1.0, 7)) == 7
        assert det.ulp_distance(plus_ulp(1.0, 7), 1.0) == 7          # symmetric

    def test_float_hex_strings_are_read_back_bit_exact(self):
        a = 9.8
        assert det.ulp_distance(a.hex(), plus_ulp(a, 3).hex()) == 3
        assert det.ulp_distance(agent_play.hex_float(a), agent_play.hex_float(plus_ulp(a))) == 1

    def test_across_zero_and_signed_zero(self):
        tiny = 5e-324  # smallest denormal
        assert det.ulp_distance(tiny, -tiny) == 2
        assert det.ulp_distance(0.0, -0.0) == 0
        assert det.ulp_distance(-1.0, math.nextafter(-1.0, -2.0)) == 1   # negative side is ordered correctly

    def test_nan_inf_and_non_numbers(self):
        assert det.ulp_distance(float("nan"), float("nan")) == 0
        assert det.ulp_distance(float("nan"), 1.0) is None
        assert det.ulp_distance("fighting", "idle") is None
        assert det.ulp_distance(True, 1.0) is None
        assert det.ulp_distance(1.0, float("inf")) > 10 ** 15

    def test_hex_float_strips_zeros_but_keeps_every_bit(self):
        for x in (0.0, -0.0, 1.0, 0.1, 9.8, 1e-300, 3.0 * 2 ** -1074, 123456.789, 2.0 ** 60):
            assert float.fromhex(agent_play.hex_float(x)).hex() == x.hex()
        assert agent_play.hex_float(15) == "0x1.ep+3"          # ints are hex'd as floats
        assert agent_play.hex_float(None) is None and agent_play.hex_float("idle") == "idle"


# ------------------------------------------------------------------ divergence analysis

class TestCompareTraces:
    def test_identical_traces_do_not_diverge(self):
        a, b = make_trace(90), make_trace(90)
        assert compare(a, b) is None
        assert det.fingerprint(carried(a)) == det.fingerprint(carried(b))

    def test_one_ulp_state_divergence_is_float_level_at_the_right_frame_and_field(self):
        base = 9.8
        a = make_trace(90, lambda i: world(hero_x=base + i * 0.01))
        # from frame 40 on hero.x is one ULP away; RNG untouched
        b = make_trace(90, lambda i: world(hero_x=plus_ulp(base + i * 0.01) if i >= 40 else base + i * 0.01))
        div = compare(a, b)
        assert div.frame == 40 and div.state_first == 40 and div.rng_first is None
        assert div.last_same == 39 and div.channel == "state"
        assert div.float_level and div.classification == "float-level"
        assert [f.path for f in div.fields] == ["hero.x"]
        f = div.fields[0]
        assert f.ulp == 1 and f.kind == "float" and 0 < f.abs_diff < 1e-14
        assert det.fingerprint(carried(a)) != det.fingerprint(carried(b))
        ids = hypothesis_ids(div)
        assert "float_ulp" in ids and "rng_first" not in ids and "logic" not in ids
        text = "\n".join(det.pair_lines(div, det.DEFAULTS, det.evaluate_rules(det.build_context(div, det.DEFAULTS), det.DEFAULTS)))
        assert "float-level (<= 4 ULP)" in text and "hero.x" in text and "1 ULP" in text
        assert "last identical frame: f39" in text and "first divergent f40" in text

    def test_threshold_is_data_driven(self):
        a = make_trace(20, lambda i: world(hero_x=1.0))
        b = make_trace(20, lambda i: world(hero_x=plus_ulp(1.0, 6) if i >= 5 else 1.0))
        assert compare(a, b).float_level is False                 # 6 ULP > default 4
        assert compare(a, b, float_ulp=8).float_level is True

    def test_large_state_difference_is_logic_level(self):
        a = make_trace(60, lambda i: world())
        b = make_trace(60, lambda i: world(hero_hp=94.0 if i >= 33 else 100.0))
        div = compare(a, b)
        assert div.frame == 33 and not div.float_level and div.classification == "logic-level"
        assert div.fields[0].path == "hero.hp" and div.fields[0].kind == "logic"
        ids = hypothesis_ids(div)
        assert "logic" in ids and "float_ulp" not in ids

    def test_rng_diverging_before_state_names_the_rng_channel(self):
        a = make_trace(60, rng_at=lambda i: f"{i:08x}:bbbbbbbb:-")
        b = make_trace(60, world_at=lambda i: world(hero_hp=90.0 if i >= 27 else 100.0),
                       rng_at=lambda i: (f"{i:08x}" if i < 25 else f"{i:08x}"[::-1]) + ":bbbbbbbb:-")
        div = compare(a, b)
        assert div.channel == "rng" and div.rng_first == 25 and div.state_first == 27
        assert div.frame == 25 and div.last_same == 24
        assert div.rng_parts == ["random"]
        assert not div.float_level
        ctx = det.build_context(div, det.DEFAULTS)
        hyp = {h["id"]: h for h in det.evaluate_rules(ctx, det.DEFAULTS)}
        assert "rng_first" in hyp and "f25" in hyp["rng_first"]["symptom"] and "2 frame(s) later" in hyp["rng_first"]["symptom"]
        assert "unseeded" in hyp["rng_first"]["cause"]
        assert "float_ulp" not in hyp

    def test_rng_only_divergence_state_still_identical(self):
        a = make_trace(40)
        b = make_trace(40, rng_at=lambda i: "aaaaaaaa:bbbbbbbb:-" if i < 30 else "aaaaaaaa:cccccccc:-")
        div = compare(a, b)
        assert div.channel == "rng" and div.state_first is None and div.rng_parts == ["rng_manager"]
        assert div.fields == []
        assert any("still identical" in h["symptom"] for h in det.evaluate_rules(det.build_context(div, det.DEFAULTS), det.DEFAULTS))

    def test_state_first_with_float_noise_beats_a_later_rng_change(self):
        # the usual chain of the CI flake: ULP noise first, a threshold later flips an RNG draw
        a = make_trace(60, rng_at=lambda i: "aaaaaaaa:bbbbbbbb:-")
        b = make_trace(60, world_at=lambda i: world(hero_x=plus_ulp(1.0) if i >= 10 else 1.0),
                       rng_at=lambda i: "aaaaaaaa:bbbbbbbb:-" if i < 50 else "dddddddd:bbbbbbbb:-")
        div = compare(a, b)
        assert div.channel == "state" and div.frame == 10 and div.rng_first == 50 and div.float_level

    def test_same_frame_float_noise_is_state_but_logic_change_is_rng(self):
        rng = lambda i: "aaaaaaaa:bbbbbbbb:-" if i < 10 else "cccccccc:bbbbbbbb:-"  # noqa: E731
        a = make_trace(30)
        noise = make_trace(30, lambda i: world(hero_x=plus_ulp(1.0) if i >= 10 else 1.0), rng)
        real = make_trace(30, lambda i: world(hero_hp=50.0 if i >= 10 else 100.0), rng)
        assert compare(a, noise).channel == "state"
        assert compare(a, real).channel == "rng"

    def test_entity_order_difference(self):
        e1, e2 = enemy(1, x=3.0), enemy(2, x=7.0, ty="goblin")
        a = make_trace(30, lambda i: world(enemies=[e1, e2]))
        b = make_trace(30, lambda i: world(enemies=[e2, e1] if i >= 12 else [e1, e2]))
        div = compare(a, b)
        assert div.frame == 12 and div.order and not div.entity_set
        ids = hypothesis_ids(div)
        assert "order" in ids and "logic" not in ids            # not double-reported as a generic logic diff

    def test_different_enemy_count_is_an_entity_set_difference(self):
        a = make_trace(30, lambda i: world(enemies=[enemy(1), enemy(2)]))
        b = make_trace(30, lambda i: world(enemies=[enemy(1)] if i >= 8 else [enemy(1), enemy(2)]))
        div = compare(a, b)
        assert div.frame == 8 and div.entity_set and not div.order
        assert "en.count" in [f.path for f in div.fields]
        assert "entity_set" in hypothesis_ids(div)

    def test_only_time_differs(self):
        a = make_trace(30)
        b = make_trace(30, t_at=lambda i: i / FPS if i < 12 else i / FPS + 1e-9)
        div = compare(a, b)
        assert div.frame == 12 and div.only_t and [f.path for f in div.fields] == ["t"]
        assert "only_t" in hypothesis_ids(div)

    def test_divergence_at_a_whole_second_is_a_tick_boundary(self):
        a = make_trace(90)
        on_tick = make_trace(90, lambda i: world(hero_hp=99.0 if i >= FPS else 100.0))
        off_tick = make_trace(90, lambda i: world(hero_hp=99.0 if i >= FPS + 7 else 100.0))
        assert compare(a, on_tick).tick is True and "tick" in hypothesis_ids(compare(a, on_tick))
        assert compare(a, off_tick).tick is False

    def test_crossed_tick_helper(self):
        assert det.crossed_tick(29 / FPS, 30 / FPS, 1.0)
        assert not det.crossed_tick(30 / FPS, 31 / FPS, 1.0)
        assert det.crossed_tick(0.9, 2.1, 1.0)
        assert not det.crossed_tick(None, 1.0, 1.0) and not det.crossed_tick(0.5, 1.5, 0)

    def test_length_difference_with_identical_prefix(self):
        a, b = make_trace(50), make_trace(40)
        div = compare(a, b)
        assert div.length and div.frame == 40 and div.last_same == 39 and (div.len_a, div.len_b) == (50, 40)
        assert "length" in hypothesis_ids(div)

    def test_divergence_at_frame_zero_has_no_last_identical_frame(self):
        div = compare(make_trace(5), make_trace(5, lambda i: world(hero_hp=1.0)))
        assert div.frame == 0 and div.last_same is None
        assert "last identical frame: none" in det.pair_lines(div, det.DEFAULTS, [])[0]


class TestCrossVariantRules:
    @staticmethod
    def ids(stats, classes=1, runs=12):
        div = compare(make_trace(20), make_trace(20, lambda i: world(hero_x=plus_ulp(1.0) if i >= 5 else 1.0)))
        ctx = det.build_context(div, det.DEFAULTS, stats, classes, runs)
        return {h["id"]: h for h in det.evaluate_rules(ctx, det.DEFAULTS)}

    def test_hashseed_theory_refuted(self):
        hyp = self.ids({"normal": {"pairs": 6, "diverged": 2}, "hashseed0": {"pairs": 6, "diverged": 1}})
        assert "hashseed_refuted" in hyp and "hashseed_implicated" not in hyp
        assert "1/6" in hyp["hashseed_refuted"]["symptom"] and "NOT the cause" in hyp["hashseed_refuted"]["cause"]

    def test_hashseed_theory_implicated(self):
        hyp = self.ids({"normal": {"pairs": 6, "diverged": 2}, "hashseed0": {"pairs": 6, "diverged": 0}})
        assert "hashseed_implicated" in hyp and "hashseed_refuted" not in hyp

    def test_aslr_off_diverging_more_often(self):
        hyp = self.ids({"normal": {"pairs": 6, "diverged": 0}, "aslr-off": {"pairs": 6, "diverged": 3}})
        assert "aslr_implicated" in hyp and "3/6" in hyp["aslr_implicated"]["symptom"]
        assert "aslr_implicated" not in self.ids({"normal": {"pairs": 6, "diverged": 3}, "aslr-off": {"pairs": 6, "diverged": 1}})

    def test_recurring_trajectory_classes(self):
        assert "multi_class" in self.ids({}, classes=2, runs=12)
        assert "multi_class" not in self.ids({}, classes=1, runs=12)
        assert "multi_class" not in self.ids({}, classes=2, runs=2)      # one diverged pair proves nothing about classes

    def test_severity_orders_the_hypotheses(self):
        div = compare(make_trace(20), make_trace(20, lambda i: world(hero_x=plus_ulp(1.0) if i >= 5 else 1.0)))
        ctx = det.build_context(div, det.DEFAULTS, {"normal": {"pairs": 6, "diverged": 2}, "hashseed0": {"pairs": 6, "diverged": 1}}, 2, 12)
        sev = [h["severity"] for h in det.evaluate_rules(ctx, det.DEFAULTS)]
        assert sev == sorted(sev, key=lambda s: {"high": 0, "medium": 1, "info": 2}[s])


# ------------------------------------------------------------------ data (Lua) and files

class TestSettings:
    def test_lua_rules_match_the_python_defaults(self):
        if not lua_bridge.available_backends():
            pytest.skip("no Lua backend")
        lua = det.qa_settings()["determinism"]
        assert [h["id"] for h in lua["hypotheses"]] == [h["id"] for h in det.DEFAULTS["hypotheses"]]
        assert {h["when"] for h in lua["hypotheses"]} <= set(det.PREDICATES)
        for key in ("pairs", "seed", "float_ulp", "tick_seconds", "max_fields", "hypotheses_shown", "top_leaks", "max_lines",
                    "variants", "float_sites", "owners", "leak_severity"):
            assert lua[key] == det.DEFAULTS[key], key
        assert det.settings()["hypotheses"] == lua["hypotheses"]

    def test_every_rule_template_formats(self):
        div = compare(make_trace(20), make_trace(20, lambda i: world(hero_x=plus_ulp(1.0) if i >= 5 else 1.0)))
        vars_ = det.build_context(div, det.DEFAULTS, {"aslr-off": {"pairs": 2, "diverged": 1}}, 2, 4)["vars"]
        for rule in det.DEFAULTS["hypotheses"]:
            for key in ("symptom", "cause", "look"):
                rule[key].format_map(vars_)                       # must not raise
                assert "{" not in rule[key].format_map(vars_), (rule["id"], key)

    def test_python_defaults_apply_when_lua_lacks_the_key_or_breaks(self, monkeypatch):
        monkeypatch.setattr(det, "qa_settings", lambda: {"scenarios": []})
        assert det.settings() == det.DEFAULTS
        monkeypatch.setattr(det, "qa_settings", lambda: {"determinism": {"float_ulp": 8, "unknown_key": 1}})
        cfg = det.settings()
        assert cfg["float_ulp"] == 8 and cfg["pairs"] == det.DEFAULTS["pairs"] and "unknown_key" not in cfg

        def boom():
            raise RuntimeError("no lua")
        monkeypatch.setattr(det, "qa_settings", boom)
        assert det.settings() == det.DEFAULTS

    def test_load_trace_carries_state_forward_and_survives_a_torn_last_line(self, tmp_path):
        recs = make_trace(10)
        assert sum("s" in r for r in recs) == 1                   # unchanged world is not repeated
        path = tmp_path / "t.jsonl"
        write_trace(path, recs)
        path.write_text(path.read_text(encoding="utf-8") + '{"f":10,"t":0.3', encoding="utf-8")   # killed mid-write
        loaded = det.load_trace(path)
        assert len(loaded) == 10 and all(r["s"] == recs[0]["s"] for r in loaded)

    def test_trace_size_stays_small(self, tmp_path):
        recs = make_trace(240, lambda i: world(hero_x=1.0 + i * 0.0137, enemies=[enemy(k, x=k + i * 0.011) for k in range(1, 6)]))
        path = tmp_path / "t.jsonl"
        write_trace(path, recs)
        assert path.stat().st_size < 600_000                        # 8 s at 30 fps with 5 moving enemies

    def test_fit_lines_keeps_result_and_repro_and_respects_the_limit(self):
        sections = [["RESULT"], ["variants"], ["a1", "a2", "a3"], ["b1", "b2", "b3", "b4"], ["leak1", "leak2"], ["repro"]]
        out = det.fit_lines(sections, 8)
        assert len(out) == 8 and out[0] == "RESULT" and out[1] == "variants" and out[-1] == "repro"
        assert det.fit_lines(sections, 99) == [x for s in sections for x in s]


# ------------------------------------------------------------------ leaks

class TestLeakReport:
    def test_ranking_puts_unseeded_rng_above_frequent_harmless_clock_reads(self):
        found = [
            {"kind": "time.perf_counter (real clock, bypasses the virtual one)", "where": "src/a.py:1", "detail": "", "via": "", "count": 900},
            {"kind": "random.Random() unseeded", "where": "src/rng_manager.py:42", "detail": "", "via": "src/effect.py:152", "count": 1},
            {"kind": "threading.Thread.start", "where": "src/b.py:5", "detail": "Loop", "via": "", "count": 2},
            {"kind": "time.time_ns", "where": "src/c.py:9", "detail": "", "via": "", "count": 30},
        ]
        ranked = det.rank_leaks(found, det.DEFAULTS)
        assert [f["kind"].split()[0] for f in ranked] == ["random.Random()", "threading.Thread.start", "time.time_ns", "time.perf_counter"]
        assert "via src/effect.py:152" in det.leak_text(ranked[0]) and "x1" in det.leak_text(ranked[0])
        assert "[REAL]" in det.leak_text(ranked[-1])

    def test_merge_takes_the_max_count_per_site(self, tmp_path):
        f = {"kind": "os.urandom", "where": "src/x.py:3", "detail": "", "via": ""}
        for name, n in (("a.json", 4), ("b.json", 6)):
            (tmp_path / name).write_text(json.dumps({"findings": [{**f, "count": n}]}), encoding="utf-8")
        merged = det.merge_leaks([tmp_path / "a.json", tmp_path / "b.json", tmp_path / "missing.json"])
        assert len(merged) == 1 and merged[0]["count"] == 6

    def test_leak_lines_are_compact(self):
        found = [{"kind": f"uuid.uuid{i}", "where": f"src/f{i}.py:{i}", "detail": "", "via": "", "count": i} for i in range(1, 9)]
        lines = det.leak_lines(det.rank_leaks(found, det.DEFAULTS), det.DEFAULTS)
        assert lines[0].startswith("leaks (top 5 of 8") and len(lines) <= 4
        assert det.leak_lines([], det.DEFAULTS) == []


@pytest.mark.filterwarnings("ignore:datetime.datetime.utcnow:DeprecationWarning")
@pytest.mark.skipif(not hasattr(sys, "monitoring"), reason="needs sys.monitoring (Python 3.12+)")
class TestLeakRecorder:
    SRC = '''
import datetime, os, random, threading, time, uuid

def work(shim):
    for _ in range(3):
        datetime.datetime.now()
    datetime.datetime.utcnow()
    os.urandom(4)
    uuid.uuid4()
    random.Random()
    random.Random(7)                     # seeded: not a leak
    random.SystemRandom()
    t = threading.Thread(target=lambda: None, name="bg")
    t.start(); t.join()
    shim.time_ns()
    shim.sleep(0)
    shim.time()                          # virtual: not a leak
    shim.perf_counter()                  # virtual: not a leak
    time.perf_counter()                  # the REAL module bound in this file: bypasses the shim
'''

    @pytest.fixture
    def recorder(self, tmp_path):
        rec = probe_runtime.LeakRecorder(tmp_path / "leaks.json", roots=[tmp_path])
        if not rec.install():
            pytest.skip("no free sys.monitoring tool id")
        probe_runtime._LEAKS = rec
        yield rec
        probe_runtime._LEAKS = None
        rec.uninstall()

    def run_fake_game(self, tmp_path, recorder):
        path = tmp_path / "fake_game.py"
        path.write_text(self.SRC, encoding="utf-8")
        ns = {}
        exec(compile(self.SRC, str(path), "exec"), ns)
        clock = types.SimpleNamespace(getFrameTime=lambda: 1.0)
        ns["work"](probe_runtime.VirtualTime(clock))
        return {(f["kind"], f["detail"]): f for f in recorder.report()["findings"]}

    def test_records_uncovered_sources_with_location_and_counts(self, tmp_path, recorder):
        found = self.run_fake_game(tmp_path, recorder)
        kinds = {k for k, _ in found}
        assert {"datetime.now", "datetime.utcnow", "os.urandom", "uuid.uuid4", "random.Random() unseeded",
                "random.SystemRandom()", "threading.Thread.start", "time.time_ns", "time.sleep"} <= kinds
        assert found[("datetime.now", "")]["count"] == 3
        assert found[("datetime.now", "")]["where"].endswith("fake_game.py:6") or ":6" in found[("datetime.now", "")]["where"]
        assert found[("datetime.now", "")]["func"] == "work"
        assert any(k == "threading.Thread.start" and "<lambda>" in d for k, d in found)       # target name is reported
        assert sum(1 for k, _ in found if k == "random.Random() unseeded") == 1     # Random(7) is not counted
        assert any(k.startswith("time.perf_counter (real") for k, _ in found)
        # the shim's own covered clocks are not leaks
        assert not any(k in ("time.time", "time.monotonic") for k, _ in found)
        assert sum(1 for k, _ in found if k == "time.perf_counter") == 0

    def test_code_outside_the_game_roots_is_ignored(self, tmp_path, recorder):
        elsewhere = tmp_path.parent / "not_game_code.py"
        elsewhere.write_text(self.SRC, encoding="utf-8")
        ns = {}
        exec(compile(self.SRC, str(elsewhere), "exec"), ns)
        ns["work"](probe_runtime.VirtualTime(types.SimpleNamespace(getFrameTime=lambda: 1.0)))
        assert recorder.report()["findings"] == []

    def test_recording_does_not_change_behaviour(self, tmp_path, recorder):
        random.seed(11)
        expected = [random.random() for _ in range(3)]
        random.seed(11)
        ns = {}
        exec(compile("import random\ndef f():\n    return [random.random() for _ in range(3)]\n", str(tmp_path / "g.py"), "exec"), ns)
        assert ns["f"]() == expected

    def test_report_is_written_as_json(self, tmp_path, recorder):
        self.run_fake_game(tmp_path, recorder)
        recorder.write()
        data = json.loads((tmp_path / "leaks.json").read_text(encoding="utf-8"))
        assert data["schema"] == 1 and data["findings"] and {"kind", "where", "count", "via"} <= set(data["findings"][0])

    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("AI_EVOLVE_LEAK_REPORT", raising=False)
        monkeypatch.setattr(probe_runtime, "_LEAKS", None)
        assert probe_runtime.start_leak_recorder() is None and probe_runtime._LEAKS is None


# ------------------------------------------------------------------ agent_play --trace-frames (no game)

class TestFrameTracer:
    @staticmethod
    def fake_game():
        hero = types.SimpleNamespace(x=0, y=0.5, health=100.0, mana=20.0, stamina=30.0, ai_state="idle", level=1, experience=0)
        enemies = [types.SimpleNamespace(x=5.0, y=5.0, health=40.0, enemy_type="slime", entity_id="uuid-A"),
                   types.SimpleNamespace(x=6.0, y=6.0, health=40.0, enemy_type="goblin", entity_id="uuid-B")]
        scene = types.SimpleNamespace(player=hero, enemies=enemies)
        return types.SimpleNamespace(scene=scene), hero, enemies

    def test_off_by_default(self):
        assert agent_play.parse_args(["wait 1"]).trace_frames is None
        assert agent_play.parse_args(["--trace-frames", "x.jsonl", "wait 1"]).trace_frames == "x.jsonl"

    def test_one_line_per_frame_bit_exact_and_process_independent(self, tmp_path):
        game, hero, enemies = self.fake_game()
        tracer = agent_play.FrameTracer(tmp_path / "t.jsonl", game)
        for i in range(4):
            if i == 2:
                hero.x = 0.1 + 0.2                                # a value that needs all 17 digits
            tracer.record(i / FPS)
        tracer.close()
        lines = (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 4
        recs = [json.loads(line) for line in lines]
        assert [r["f"] for r in recs] == [0, 1, 2, 3]
        assert [("s" in r) for r in recs] == [True, False, True, False]     # state only when the world changed
        assert recs[0]["t"] == 0.0 and recs[3]["t"] == 3 / FPS
        assert float.fromhex(recs[2]["s"]["hero"]["x"]) == 0.1 + 0.2       # bit-exact
        assert [e["id"] for e in recs[0]["s"]["en"]] == ["e1", "e2"]       # ordinals, never the uuid entity_id
        assert "uuid" not in lines[0]
        assert set(recs[0]["s"]["hero"]) == {"x", "y", "hp", "mana", "stamina", "ai", "lvl", "xp"}
        assert set(recs[0]["s"]["en"][0]) == {"id", "ty", "x", "y", "hp"}
        assert len(recs[0]["h"]) == 12 and re.fullmatch(r"[0-9a-f]{8}:([0-9a-f]{8}|-):([0-9a-f]{8}|-)", recs[0]["r"])

    def test_rng_hash_moves_with_the_random_module_and_the_project_rng_manager(self):
        random.seed(3)
        before = agent_play.FrameTracer.rng_hashes()
        assert agent_play.FrameTracer.rng_hashes() == before                # reading does not consume randomness
        random.random()
        after = agent_play.FrameTracer.rng_hashes()
        assert after.split(":")[0] != before.split(":")[0]
        try:
            from src.core import rng_manager
        except ImportError:
            return
        old = rng_manager._default_rng
        try:
            rng_manager.set_default_rng(rng_manager.RNGManager(rng_manager.RNGConfig(seed=1)))
            first = agent_play.FrameTracer.rng_hashes().split(":")[1]
            rng_manager._default_rng.random()
            assert agent_play.FrameTracer.rng_hashes().split(":")[1] != first and first != "-"
        finally:
            rng_manager._default_rng = old

    def test_a_trace_from_the_tracer_round_trips_through_the_analyser(self, tmp_path):
        game, hero, _ = self.fake_game()
        paths = []
        for name, x in (("a", 1.0), ("b", plus_ulp(1.0))):
            hero.x = 0.0
            tracer = agent_play.FrameTracer(tmp_path / f"{name}.jsonl", game)
            for i in range(6):
                hero.x = x if i >= 3 else 0.0
                tracer.record(i / FPS)
            tracer.close()
            paths.append(tmp_path / f"{name}.jsonl")
        div = det.compare_traces(det.load_trace(paths[0]), det.load_trace(paths[1]), det.DEFAULTS)
        assert div.frame == 3 and div.float_level and div.fields[0].path == "hero.x" and div.fields[0].ulp == 1


# ------------------------------------------------------------------ the command, with fake runs

class FakeRuns:
    """Replaces qa_pool.run_many: writes the files agent_play would, from a per-run recipe."""

    def __init__(self, recipe, leaks=None, rc=None):
        self.recipe, self.leaks, self.rc, self.jobs = recipe, leaks, rc or (lambda job: 0), []

    def __call__(self, jobs, max_jobs=None, stop_when=None):
        results = []
        for job in jobs:
            self.jobs.append(job)
            out = job.meta["out"]
            rc = self.rc(job)
            if rc in (0, 1):
                write_trace(out / "trace.jsonl", self.recipe(job))
                (out / "session.json").write_text("{}", encoding="utf-8")
                if "AI_EVOLVE_LEAK_REPORT" in job.env and self.leaks:
                    Path(job.env["AI_EVOLVE_LEAK_REPORT"]).write_text(json.dumps({"findings": self.leaks}), encoding="utf-8")
            results.append(qa_pool.Result(job.name, rc, "", "boom" if rc not in (0, 1) else "", 0.1, job.meta))
        return results


def run_command(monkeypatch, capsys, fake, *argv):
    monkeypatch.setattr(det, "run_many", fake)
    import argparse
    parser = argparse.ArgumentParser()
    det.register(parser.add_subparsers())
    args = parser.parse_args(["determinism", *argv])
    code = args.func(args)
    return code, capsys.readouterr().out


class TestCommandWithFakeRuns:
    SCRIPT = "spawn enemy x2; wait 3"

    def test_identical_pairs_exit_zero(self, monkeypatch, capsys, tmp_path):
        code, out = run_command(monkeypatch, capsys, FakeRuns(lambda job: make_trace(60)),
                                self.SCRIPT, "--pairs", "3", "--variants", "normal,hashseed0", "--out", str(tmp_path))
        m = RESULT_RE.search(out)
        assert code == 0 and m and m.groups() == ("6", "0", "1", "-", "-", "none")
        assert "normal 3/3 identical" in out and "hashseed0 3/3 identical" in out
        assert len(out.splitlines()) <= 25
        assert (tmp_path / "report.json").is_file() and (tmp_path / "repro_determinism.sh").is_file()

    def test_diverged_pair_reports_frame_channel_fields_hypotheses_and_repro(self, monkeypatch, capsys, tmp_path):
        base = 9.8

        def recipe(job):
            # only run b of pair 2 in `normal` drifts by 1 ULP from frame 63 (t = 2.1 s)
            drift = job.meta["variant"] == "normal" and job.meta["pair"] == 1 and job.meta["side"] == "b"
            return make_trace(120, lambda i: world(hero_x=plus_ulp(base) if drift and i >= 63 else base))
        leaks = [{"kind": "random.Random() unseeded", "where": "src/core/rng_manager.py:42", "detail": "", "via": "src/x.py:152", "count": 1}]
        code, out = run_command(monkeypatch, capsys, FakeRuns(recipe, leaks), self.SCRIPT, "--pairs", "3",
                                "--variants", "normal,hashseed0", "--wrap", "taskset -c 0", "--out", str(tmp_path))
        lines = out.splitlines()
        m = RESULT_RE.search(out)
        assert code == 1 and m and m.groups() == ("6", "1", "2", "63", "2.10", "state")
        assert len(lines) <= 25, out
        assert "normal 2/3 identical" in out and "hashseed0 3/3 identical" in out
        assert "first divergent: normal/pair2" in out
        assert "last identical frame: f62" in out and "float-level (<= 4 ULP)" in out
        assert "hero.x" in out and "1 ULP" in out
        assert "[high]" in out and "float non-determinism" in out and "hashseed_refuted" not in out
        assert "PYTHONHASHSEED=0 pairs are clean" in out          # hashseed0 clean, normal diverged -> implicated
        assert "leaks (top 1 of 1" in out and "random.Random() unseeded" in out and "via src/x.py:152" in out
        repro = [ln for ln in lines if ln.startswith("repro:")]
        assert len(repro) == 1 and "repro_determinism.sh" in repro[0]
        sh = (tmp_path / "repro_determinism.sh").read_text(encoding="utf-8")
        assert sh.count("tools/agent_play.py --seed 5") == 2 and "taskset -c 0" in sh and "PYTHONHASHSEED=random" in sh
        assert "--trace-frames" in sh and "determinism --diff" in sh and self.SCRIPT in sh and "TRIES" in sh
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert report["diverged"] == 1 and report["classes"] == 2
        div = report["variants"]["normal"]["pairs"][1]["divergence"]
        assert div["frame"] == 63 and div["channel"] == "state" and div["fields"][0]["ulp"] == 1
        assert report["leaks"] and report["env"]["python"]

    def test_wrap_and_variant_prefixes_reach_the_run_command(self, monkeypatch, capsys, tmp_path):
        fake = FakeRuns(lambda job: make_trace(10))
        monkeypatch.setattr(det, "variant_spec", lambda name: (["setarch", "x86_64", "-R"], {"PYTHONHASHSEED": "random"}, None)
                            if name == "aslr-off" else ([], {"PYTHONHASHSEED": "0"}, None))
        run_command(monkeypatch, capsys, fake, self.SCRIPT, "--pairs", "1", "--variants", "aslr-off,hashseed0",
                    "--wrap", "taskset -c 0", "--no-leaks", "--out", str(tmp_path))
        by_variant = {j.meta["variant"]: j for j in fake.jobs}
        assert by_variant["aslr-off"].argv[:5] == ["taskset", "-c", "0", "setarch", "x86_64"]
        assert by_variant["aslr-off"].argv[6:8] == [sys.executable, "tools/agent_play.py"]
        assert by_variant["hashseed0"].env["PYTHONHASHSEED"] == "0" and "AI_EVOLVE_LEAK_REPORT" not in by_variant["hashseed0"].env
        assert "--trace-frames" in by_variant["hashseed0"].argv

    def test_unavailable_variant_is_skipped_with_a_note(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(det.shutil, "which", lambda name: None)
        code, out = run_command(monkeypatch, capsys, FakeRuns(lambda job: make_trace(20)), self.SCRIPT, "--pairs", "1",
                                "--variants", "normal,aslr-off", "--out", str(tmp_path))
        assert code == 0 and "aslr-off skipped (setarch not found" in out and "pairs=1 " in out

    def test_failed_run_is_a_tool_error(self, monkeypatch, capsys, tmp_path):
        fake = FakeRuns(lambda job: make_trace(20), rc=lambda job: 3 if job.meta["side"] == "b" else 0)
        code, out = run_command(monkeypatch, capsys, fake, self.SCRIPT, "--pairs", "2", "--variants", "normal", "--out", str(tmp_path))
        assert code == 2 and "errors=2" in out and "run error: normal/pair1/b: rc=3" in out

    def test_a_divergence_wins_over_a_run_error(self, monkeypatch, capsys, tmp_path):
        def recipe(job):
            return make_trace(30, lambda i: world(hero_hp=1.0 if job.meta["side"] == "b" and i > 5 else 100.0))
        fake = FakeRuns(recipe, rc=lambda job: 3 if job.meta["pair"] == 1 else 0)
        code, out = run_command(monkeypatch, capsys, fake, self.SCRIPT, "--pairs", "2", "--variants", "normal", "--out", str(tmp_path))
        assert code == 1 and "pairs=1 diverged=1" in out and "errors=1" in out       # errors = pairs that could not be compared

    def test_setarch_refusal_skips_the_variant_instead_of_failing(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(det, "variant_spec", lambda name: (["setarch", "x86_64", "-R"], {}, None) if name == "aslr-off" else ([], {}, None))
        fake = FakeRuns(lambda job: make_trace(20), rc=lambda job: 1 if job.meta["variant"] == "aslr-off" else 0)
        # setarch failing to set the personality exits before agent_play writes anything
        real = fake.__call__

        def refusing(jobs, *a, **k):
            results = real(jobs, *a, **k)
            for r in results:
                if r.meta["variant"] == "aslr-off":
                    (r.meta["out"] / "trace.jsonl").unlink()
                    r.stderr = "setarch: failed to set personality to x86_64"
            return results
        code, out = run_command(monkeypatch, capsys, refusing, self.SCRIPT, "--pairs", "1", "--variants", "normal,aslr-off", "--out", str(tmp_path))
        assert code == 0 and "aslr-off skipped (setarch refused" in out and "errors=" not in out

    def test_bad_input_is_exit_two_before_any_run(self, monkeypatch, capsys, tmp_path):
        fake = FakeRuns(lambda job: make_trace(5))
        assert run_command(monkeypatch, capsys, fake, self.SCRIPT, "--variants", "bogus")[0] == 2
        assert run_command(monkeypatch, capsys, fake, "definitely not a command")[0] == 2
        assert run_command(monkeypatch, capsys, fake)[0] == 2
        assert fake.jobs == []

    def test_diff_mode_analyses_two_trace_files(self, monkeypatch, capsys, tmp_path):
        write_trace(tmp_path / "a.jsonl", make_trace(50))
        write_trace(tmp_path / "b.jsonl", make_trace(50, lambda i: world(hero_x=plus_ulp(1.0, 2) if i >= 20 else 1.0)))
        code, out = run_command(monkeypatch, capsys, FakeRuns(None), "--diff", str(tmp_path / "a.jsonl"), str(tmp_path / "b.jsonl"))
        assert code == 1 and "first_frame=20" in out and "channel=state" in out and "2 ULP" in out
        code, out = run_command(monkeypatch, capsys, FakeRuns(None), "--diff", str(tmp_path / "a.jsonl"), str(tmp_path / "a.jsonl"))
        assert code == 0 and "channel=none" in out
        assert run_command(monkeypatch, capsys, FakeRuns(None), "--diff", str(tmp_path / "a.jsonl"), str(tmp_path / "nope.jsonl"))[0] == 2

    def test_plugin_is_discovered_by_qa(self):
        import argparse
        import qa
        sub = argparse.ArgumentParser().add_subparsers()
        qa.load_plugins(sub)
        assert "determinism" in sub.choices


# ------------------------------------------------------------------ the real game (one run)

@pytest.mark.skipif(importlib.util.find_spec("panda3d") is None, reason="Panda3D not installed")
class TestRealGame:
    def test_two_pairs_of_a_short_script(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, "tools/qa.py", "determinism", "spawn enemy x2; wait 3", "--pairs", "2", "--variants", "normal",
             "--out", str(tmp_path / "det")], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300)
        out = proc.stdout
        m = RESULT_RE.search(out)
        assert m, out + proc.stderr
        assert m.group(1) == "2" and len(out.splitlines()) <= 25
        if sys.platform == "win32":   # this machine is deterministic; POSIX CI has the open flake this tool was built for
            assert proc.returncode == 0 and m.group(2) == "0" and m.group(6) == "none", out
        else:
            assert proc.returncode in (0, 1), out
        trace = tmp_path / "det" / "normal" / "pair1" / "a" / "trace.jsonl"
        recs = det.load_trace(trace)
        assert len(recs) >= 90 and recs[0]["s"]["hero"] is not None and trace.stat().st_size < 600_000
        assert (tmp_path / "det" / "normal" / "pair1" / "a" / "leaks.json").is_file()
        report = json.loads((tmp_path / "det" / "report.json").read_text(encoding="utf-8"))
        assert report["schema"] == 1 and (tmp_path / "det" / "repro_determinism.sh").is_file()
