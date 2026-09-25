"""Модульные тесты тактической памяти врагов: src/gameplay/tactics.py.

Бандит UCB1 с затуханием: контекст - архетип врага, рука - тактика. Выбор
разрешённых тактик (бестиарий, дальний бой), награда за итог схватки и путь
памяти через переменную окружения AI_EVOLVE_TACTICS_MEMORY.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gameplay import tactics as tac  # noqa: E402


class Enemy:
    """Миниатюрный враг: только то, что читает TacticsMemory."""

    def __init__(self, shape="humanoid", role=None, tactics_pool=(), ranged=False, skills=()):
        self.shape, self.role = shape, role
        self.tactics_pool, self.ranged, self.skills = list(tactics_pool), ranged, list(skills)


@pytest.fixture
def memory(tmp_path):
    return tac.TacticsMemory(tmp_path / "tactics.json", backend="python")


def try_all_but(memory, enemy, good: str):
    """Каждая тактика (кроме good) опробована и не окупилась - память заполнена."""
    for t in tac.TACTICS:
        if t != good:
            memory.report(enemy, t, dealt=1.0, taken=9.0, hero_died=False)


# ------------------------------------------------------------------- константы
def test_contexts_and_tactics_are_consistent():
    assert len(tac.TACTICS) == 6 and len(tac.CONTEXTS) == 8
    assert set(tac.TACTIC_NAMES) == set(tac.TACTICS)      # имя есть у каждой тактики
    assert "boss" in tac.CONTEXTS


# ---------------------------------------------------------------------- context
def test_context_by_shape_role_and_unknown():
    assert tac.TacticsMemory.context(Enemy(shape="beast")) == tac.CONTEXTS.index("beast")
    assert tac.TacticsMemory.context(Enemy(shape="humanoid", role="boss")) == tac.CONTEXTS.index("boss")
    assert tac.TacticsMemory.context(Enemy(shape="dragon")) == 0          # неизвестная форма - humanoid
    assert tac.TacticsMemory.context(Enemy()) == 0                        # без shape - тоже 0


# ----------------------------------------------------------------------- choose
def test_choose_starts_with_rush_on_fresh_memory(memory):
    assert memory.choose(Enemy(shape="beast")) == "rush"                  # нет опыта - первая разрешённая


def test_choose_respects_tactics_pool(memory):
    enemy = Enemy(tactics_pool=["flank"])
    seen = {memory.choose(enemy) for _ in range(5)}
    assert seen == {"rush", "flank"}                     # только из бестиария + rush всегда можно
    try_all_but(memory, enemy, good="flank")             # всё остальное пробовано и провалилось
    for _ in range(3):                                   # флангование окупается - память закрепляет
        memory.report(enemy, "flank", dealt=50.0, taken=5.0, hero_died=False)
    assert memory.choose(enemy) == "flank"


def test_choose_kite_requires_range_or_spit(memory):
    melee = Enemy(tactics_pool=["kite"])                 # умеет по бестиарию, но без дистанции
    try_all_but(memory, melee, good="kite")              # kite формально лучшая в памяти
    assert memory.choose(melee) != "kite"                # но melee-врагу она вычеркнута
    ranged = Enemy(ranged=True, tactics_pool=["kite"])
    try_all_but(memory, ranged, good="kite")
    assert memory.choose(ranged) == "kite"               # дальнобойный - может держать дистанцию
    assert memory.choose(Enemy(skills=["venom_spit"], tactics_pool=["kite"])) == "rush"     # не его контекст пуст
    spitter = Enemy(skills=["magic_bolt"], tactics_pool=["kite"])
    try_all_but(memory, spitter, good="kite")
    assert memory.choose(spitter) == "kite"              # плевок/магия - тоже дистанция


def test_choose_learns_what_works_against_this_hero(memory):
    boss = Enemy(shape="blob", role="boss")
    try_all_but(memory, boss, good="hit_and_run")        # все тактики опробованы и провалились
    for _ in range(3):
        memory.report(boss, "hit_and_run", dealt=60.0, taken=5.0, hero_died=True)
    assert memory.choose(boss) == "hit_and_run"
    assert memory.best("boss") == "hit_and_run"          # общий отчёт видит ту же победу
    assert memory.outcomes == 8                          # 5 поражений + 3 победы (kite melee не сообщается)


# ----------------------------------------------------------------------- report
def test_report_reward_formula(memory):
    e = Enemy()
    assert memory.report(e, "rush", dealt=0.0, taken=0.0, hero_died=False) == pytest.approx(0.0)
    assert memory.report(e, "rush", dealt=0.0, taken=0.0, hero_died=True) == pytest.approx(0.5)
    assert memory.report(e, "rush", dealt=99.0, taken=0.0, hero_died=False) == pytest.approx(0.99)
    r = memory.report(e, "rush", dealt=30.0, taken=10.0, hero_died=True)
    assert r == pytest.approx(30.0 / 41.0 + 0.5)         # доля урона + бонус за убийство
    assert 0.0 <= r <= 1.5
    assert memory.outcomes == 4                          # каждое сообщение - наблюдение


def test_report_updates_only_chosen_context_arm(memory):
    wolf, goblin = Enemy(shape="beast"), Enemy(shape="humanoid")
    memory.report(wolf, "flank", dealt=100.0, taken=0.0, hero_died=True)
    means_beast = memory.means(tac.CONTEXTS.index("beast"))
    means_human = memory.means(tac.CONTEXTS.index("humanoid"))
    assert means_beast[tac.TACTICS.index("flank")] > 0   # контекст волка получил урок
    assert means_human == [0.0] * len(tac.TACTICS)       # остальные учатся сами за себя


# ------------------------------------------------------------- файл и окружение
def test_memory_persists_between_sessions(memory):
    e = Enemy(shape="spider")
    for _ in range(3):
        memory.report(e, "ambush", dealt=40.0, taken=2.0, hero_died=True)
    memory.save()
    again = tac.TacticsMemory(memory.path, backend="python")
    assert again.outcomes == memory.outcomes
    assert again.choose(Enemy(shape="spider")) == memory.choose(e)


def test_memory_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv(tac.MEMORY_ENV, "off")
    assert tac.memory_path() is None                     # инструменты: без файла, детерминированные прогоны
    target = tmp_path / "custom.json"
    monkeypatch.setenv(tac.MEMORY_ENV, str(target))
    assert tac.memory_path() == target


def test_new_bandit_matches_dimensions():
    b = tac.new_bandit("python")
    assert b.arms == len(tac.TACTICS)
    assert len(b.state()[0]) == len(tac.CONTEXTS) * len(tac.TACTICS)
