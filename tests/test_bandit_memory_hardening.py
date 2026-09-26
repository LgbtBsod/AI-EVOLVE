"""Row 4: BanditMemory format version, name-based remap, baseline persistence."""
import json

from src.gameplay.hero_mind import HeroMind
from src.gameplay.learning import MEMORY_VERSION, BanditMemory

CTX, ARMS = ("a", "b"), ("x", "y")


def _trained(path, arms=ARMS):
    m = BanditMemory(CTX, arms, path, backend="python")
    m.update(1, arms.index("y"), 1.0)
    m.save()
    return m


def test_old_format_file_loads(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"counts": [0, 0, 0, 2.0], "sums": [0, 0, 0, 1.5], "outcomes": 5}))
    m = BanditMemory(CTX, ARMS, p, backend="python")
    assert m.count == 5 and m.means(1)[1] == 0.75


def test_added_tactic_keeps_learned_arms(tmp_path):
    p = tmp_path / "m.json"
    _trained(p)
    m = BanditMemory(CTX, ("x", "z", "y"), p, backend="python")
    assert json.loads(p.read_text())["version"] == MEMORY_VERSION
    assert m.means(1) == [0.0, 0.0, 1.0]


def test_removed_arm_drops_only_that(tmp_path):
    p = tmp_path / "m.json"
    _trained(p)
    m = BanditMemory(CTX, ("y",), p, backend="python")
    assert m.means(1) == [1.0]


def test_corrupt_file_falls_back(tmp_path):
    p = tmp_path / "m.json"
    p.write_text("{not json")
    m = BanditMemory(CTX, ARMS, p, backend="python")
    assert m.count == 0 and m.means(0) == [0.0, 0.0]


def test_baseline_persisted(tmp_path):
    p = tmp_path / "h.json"
    hm = HeroMind(object(), p, "python")
    hm.baseline = 12.5
    hm.save()
    assert HeroMind(object(), p, "python").baseline == 12.5
