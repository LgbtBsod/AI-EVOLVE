"""Модульные тесты обучения агентов: src/gameplay/learning.py.

UCB1-бандит с затуханием (PyBandit - Python-двойник rust_core.TacticsBandit),
память на диске (BanditMemory: JSON в saves/, битая память - начать заново)
и выбор бэкенда (new_bandit / memory_path через переменные окружения).
"""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gameplay import learning as lr  # noqa: E402


# --------------------------------------------------------------------- PyBandit
def test_pybandit_prefers_untried_arms():
    b = lr.PyBandit(contexts=2, arms=3)
    assert [b.select(ctx) for ctx in range(2)] == [0, 0]   # каждый контекст учится сам
    assert b.select(0, allowed=[False, True, True]) == 1  # запрещённые руки пропускаются
    b.update(0, 0, 1.0)
    assert b.select(0) == 1                               # следующая непробованная
    b.update(0, 1, 1.0)
    assert b.select(0) == 2
    b.update(0, 2, 1.0)                                   # все пробованы - решает UCB
    assert b.select(0) == 0


def test_pybandit_update_decays_other_arms_only():
    b = lr.PyBandit(contexts=1, arms=2, decay=0.5)
    b.update(0, 0, 1.0)
    assert b.counts[0] == 1.0 and b.sums[0] == 1.0        # обновлённая рука: +1/+reward без затухания
    assert b.counts[1] == 0.0 and b.sums[1] == 0.0
    b.update(0, 1, 0.5)
    assert b.counts == [pytest.approx(0.5), 1.0]          # старая наблюдения затухают
    assert b.sums == [pytest.approx(0.5), pytest.approx(0.5)]


def test_pybandit_exploits_best_mean():
    b = lr.PyBandit(contexts=1, arms=2, c=0.0)            # без исследования - чистая жадность
    for _ in range(5):
        b.update(0, 0, 0.1)
        b.update(0, 1, 0.9)
    assert b.select(0) == 1
    assert b.means(0) == [pytest.approx(0.1), pytest.approx(0.9)]


def test_pybandit_ucb_bonus_keeps_stale_arms_alive():
    """Рука с малым числом свежих наблюдений получает большой bonus sqrt(ln N / n)."""
    b = lr.PyBandit(contexts=1, arms=2, c=0.6)            # decay=0.97: рука 1 «стареет» без обновлений
    for _ in range(3):
        b.update(0, 1, 1.0)
    for _ in range(40):
        b.update(0, 0, 0.8)                               # рука 0 набирает много свежего опыта
    counts = b.counts
    assert counts[1] < counts[0]                          # затухание съело старые наблюдения руки 1
    means = b.means(0)
    v = [means[i] + b.c * math.sqrt(math.log(sum(counts)) / counts[i]) for i in range(2)]
    assert v[1] > v[0]                                    # bonus редкой руки перекрывает разрыв средних
    assert b.select(0) == 1
    greedy = lr.PyBandit(contexts=1, arms=2, c=0.0)       # тот же опыт, но без исследования
    greedy.load_state(counts, b.sums)
    assert greedy.select(0) != 1 or means[1] >= means[0]  # при c=0 решает только средняя


def test_pybandit_means_zero_for_unvisited_and_out_of_range():
    b = lr.PyBandit(contexts=1, arms=2)
    assert b.means(0) == [0.0, 0.0]
    b.update(0, 0, 0.4)
    assert b.means(0) == [pytest.approx(0.4), 0.0]


def test_pybandit_state_roundtrip_and_shape_validation():
    b = lr.PyBandit(contexts=2, arms=3)
    b.update(1, 2, 0.7)
    counts, sums = b.state()
    other = lr.PyBandit(contexts=2, arms=3)
    with pytest.raises(ValueError):
        other.load_state(counts[:-1], sums[:-1])          # не та форма - отказ
    other.load_state(counts, sums)
    assert other.state() == (list(counts), list(sums))
    assert other.select(1) == b.select(1)


def test_pybandit_all_disallowed_falls_back_to_zero():
    b = lr.PyBandit(contexts=1, arms=2)
    b.update(0, 1, 1.0)
    assert b.select(0, allowed=[False, False]) == 0       # выбирать не из чего - рука 0


# ------------------------------------------------------------------ new_bandit
def test_new_bandit_python_backend_is_double():
    b = lr.new_bandit("python", 3, 4)
    assert isinstance(b, lr.PyBandit)
    assert (b.arms, b.c, b.decay) == (4, 0.6, 0.97)
    b2 = lr.new_bandit(None, 1, 2, c=0.5, decay=0.98)
    if lr._RustBandit is None:
        assert isinstance(b2, lr.PyBandit)
    else:
        assert isinstance(b2, lr._RustBandit)
    assert b2.state()[0] == [0.0, 0.0]                    # параметры доходят до бандита


# ------------------------------------------------------------------ memory_path
def test_memory_path_env_variants(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_EVOLVE_TEST_MEMORY", raising=False)
    p = lr.memory_path("AI_EVOLVE_TEST_MEMORY", "x.json")
    if p is not None:                                     # без env - путь в saves/ по умолчанию
        assert p.name == "x.json" and p.parent.name == "saves"
    for off in ("off", "OFF", "", "none", "  "):
        monkeypatch.setenv("AI_EVOLVE_TEST_MEMORY", off)
        assert lr.memory_path("AI_EVOLVE_TEST_MEMORY", "x.json") is None
    monkeypatch.setenv("AI_EVOLVE_TEST_MEMORY", str(tmp_path / "m.json"))
    assert lr.memory_path("AI_EVOLVE_TEST_MEMORY", "x.json") == tmp_path / "m.json"


# --------------------------------------------------------------- BanditMemory
@pytest.fixture
def memory(tmp_path):
    return lr.BanditMemory(("goblin", "wolf"), ("hit", "run"), tmp_path / "mem.json", backend="python")


def test_bandit_memory_select_update_count(memory):
    assert memory.select(0) == 0
    memory.update(0, 0, 1.0)
    memory.update(1, 1, 0.5)
    assert memory.count == 2
    assert memory.backend == "python"
    assert memory.arms == ("hit", "run")


def test_bandit_memory_summary_skips_zeros(memory):
    memory.update(0, 0, 1.0)                              # wolf не пробован, run у goblin - 0
    assert memory.summary() == {"goblin": {"hit": 1.0}}
    full = memory.summary(skip_zero=False)
    assert set(full["goblin"]) == {"hit", "run"}


def test_bandit_memory_best(memory):
    assert memory.best("unknown") is None                 # нет такого контекста
    assert memory.best("goblin") is None                  # ещё ничему не научился
    for _ in range(3):
        memory.update(0, 1, 0.9)
        memory.update(0, 0, 0.1)
    assert memory.best("goblin") == "run"


def test_bandit_memory_save_load_roundtrip(memory):
    memory.update(0, 1, 0.8)
    memory.update(1, 0, 0.2)
    memory.save()
    raw = json.loads(memory.path.read_text(encoding="utf-8"))
    assert raw["outcomes"] == 2 and raw["arms"] == ["hit", "run"]
    again = lr.BanditMemory(("goblin", "wolf"), ("hit", "run"), memory.path, backend="python")
    assert again.count == 2
    assert again.bandit.state() == memory.bandit.state()
    assert again.best("goblin") == memory.best("goblin")


def test_bandit_memory_custom_count_key(tmp_path):
    m = lr.BanditMemory(("a",), ("b",), tmp_path / "k.json", backend="python", count_key="episodes")
    m.update(0, 0, 1.0)
    m.save()
    assert json.loads(m.path.read_text())["episodes"] == 1
    assert lr.BanditMemory(("a",), ("b",), tmp_path / "k.json", backend="python",
                           count_key="episodes").count == 1


def test_bandit_memory_broken_file_starts_fresh(tmp_path, caplog):
    path = tmp_path / "broken.json"
    path.write_text("{not json at all", encoding="utf-8")
    with caplog.at_level("WARNING"):
        m = lr.BanditMemory(("a",), ("b",), path, backend="python")
    assert m.count == 0                                   # битая память - начать заново, не упасть
    assert any("not loaded" in r.getMessage() for r in caplog.records)


def test_bandit_memory_wrong_shape_starts_fresh(tmp_path):
    path = tmp_path / "shape.json"
    path.write_text(json.dumps({"counts": [1.0], "sums": [1.0]}), encoding="utf-8")
    m = lr.BanditMemory(("a", "b"), ("x", "y"), path, backend="python")
    assert m.count == 0
    assert m.bandit.state() == ([0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0])


def test_bandit_memory_without_path_does_not_crash_on_save():
    m = lr.BanditMemory(("a",), ("b",), None, backend="python")
    m.save()                                              # path=None - сохранение молча ничего не делает


def test_bandit_memory_decay_reacts_to_style_change():
    """Средняя - скользящее среднее с затуханием: проигравшая тактика может вернуться в игру."""
    m = lr.BanditMemory(("a",), ("slow", "fast"), None, backend="python", decay=0.9)
    for _ in range(5):
        m.update(0, 0, 1.0)
        m.update(0, 1, 0.2)
    assert m.best("a") == "slow"
    for _ in range(60):
        m.update(0, 0, 0.0)                               # slow перестала окупаться: старые 1.0 перевешены новыми 0
    means = m.means(0)                                    # старое хорошее наблюдение забыто затуханием
    assert means[0] < means[1]
    assert m.best("a") == "fast"
