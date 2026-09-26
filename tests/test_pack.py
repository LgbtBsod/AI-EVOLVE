"""qa.py pack: ranking, answer map, token cap, state lines, and `prompt --pack` end to end."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import pack_builder as PB  # noqa: E402
from probe_settings import qa_settings  # noqa: E402

CFG = qa_settings()["pack"]


def test_answer_map_routes_questions_to_tools():
    assert any("qa.py determinism" in a for a in PB.answers("why is the test flaky", CFG))
    assert any("qa.py ci" in a for a in PB.answers("why did CI fail", CFG))
    assert PB.answers("rename a variable", CFG) == []


def test_declarations_and_words():
    text = "def make_repo(x):\n    pass\nclass Foo:\n    pass\nhygiene = {\n}\n"
    assert [n for _, n in PB.declarations(text)] == ["make_repo", "Foo", "hygiene"]
    assert PB.words_of("Fix the repo hygiene", {"fix", "the"}) == {"repo", "hygiene"}


def test_fit_tokens_caps_and_keeps_verify():
    lines = [f"file: {'x' * 80}"] * 40 + ["verify: qa.py check"]
    shown = PB.fit_tokens(lines, 100, 4)
    assert shown[-1] == "verify: qa.py check" and any("cut" in s for s in shown)
    assert sum(len(s) for s in shown) // 4 < 140


def test_state_lines_report_non_ok_rows(tmp_path):
    hist = tmp_path / "h.jsonl"
    hist.write_text(json.dumps({"name": "play:x", "status": "ok"}) + "\n" + json.dumps({"name": "golden", "status": "fail"}) + "\n", encoding="utf-8")
    assert "fail golden" in PB.state_lines(tmp_path, CFG, hist)[0]


GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "pack_golden.json").read_text(encoding="utf-8"))


def _top3(task: str) -> list:
    return [rel for _, rel, _ in PB.rank_files(task, [], CFG, PB.qa_graph.build(True))][:3]


def test_golden_top3_hit_rate():
    """Real past tasks -> expected files. Hit = one expected file in the top 3 (before the IDF ranking: 0.77; now >= 0.7 is the floor)."""
    tops = {g["task"]: _top3(g["task"]) for g in GOLDEN}
    hits = sum(any(f in tops[g["task"]] for f in g["expect"]) for g in GOLDEN)
    misses = [g["task"] for g in GOLDEN if not any(f in tops[g["task"]] for f in g["expect"])]
    assert hits / len(GOLDEN) >= 0.7, f"hit rate {hits}/{len(GOLDEN)}; missed: {misses}"


def test_tests_are_ranked_only_when_the_task_asks_for_them():
    assert not any(rel.startswith("tests/") for rel in _top3("repo hygiene"))
    assert any(rel.startswith("tests/") for _, rel, _ in PB.rank_files("pytest for repo hygiene", [], CFG, PB.qa_graph.build(True)))
    assert not any(rel.startswith("dev_probe_output/") for rel in _top3("repo hygiene"))


def test_words_are_stemmed_before_the_stop_list():
    assert PB.words_of("tools names", {"tool", "name"}) == set()


def test_build_pack_shape():
    pack = PB.build_pack("determinism", [], CFG, qa_settings())
    assert {"files", "top", "importers", "tests", "tools", "state", "verify", "answers", "skip"} <= set(pack)
    assert len(pack["top"]) <= CFG["top"]
