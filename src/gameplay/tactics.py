"""Коллективная память врагов: какие тактики работают против этого героя.

Бандит UCB1 с затуханием (rust_core.TacticsBandit, Python-двойник PyBandit -
тот же выбор бит в бит): контекст - архетип врага (форма тела, босс), рука -
тактика. Каждый враг выбирает тактику при появлении и сообщает итог схватки
(урон герою против полученного урона, смерть героя). Старые наблюдения
затухают: если герой сменил снаряжение или стиль, враги перестраиваются.
Память сохраняется между сессиями (saves/tactics_memory.json).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .learning import _RustBandit, BanditMemory, PyBandit, new_bandit as _new_bandit
from .learning import memory_path as _memory_path

# бандит и его двойник живут в learning.py; здесь - для тестов паритета и старых импортов
__all__ = ["CONTEXTS", "MEMORY_ENV", "TACTICS", "TACTIC_NAMES", "PyBandit", "TacticsMemory", "_RustBandit",
           "memory_path", "new_bandit"]

MEMORY_ENV = "AI_EVOLVE_TACTICS_MEMORY"   # путь файла памяти; "off" - только в памяти процесса

TACTICS = ("rush", "flank", "kite", "ambush", "pack", "hit_and_run")
CONTEXTS = ("humanoid", "beast", "blob", "spirit", "giant", "spider", "serpent", "boss")
TACTIC_NAMES = {"rush": "натиск", "flank": "обход с фланга", "kite": "держит дистанцию",
                "ambush": "засада", "pack": "стая", "hit_and_run": "удар и отход"}


def memory_path() -> Optional[Path]:
    return _memory_path(MEMORY_ENV, "tactics_memory.json")


def new_bandit(backend: Optional[str] = None):
    """Бандит тактик (контексты x тактики): rust_core или двойник."""
    return _new_bandit(backend, len(CONTEXTS), len(TACTICS))


class TacticsMemory(BanditMemory):
    """Общая память всех врагов мира."""

    def __init__(self, path: Optional[Path] = None, backend: Optional[str] = None):
        super().__init__(CONTEXTS, TACTICS, path, backend, count_key="outcomes")

    @property
    def outcomes(self) -> int:
        return self.count

    @staticmethod
    def context(enemy) -> int:
        key = "boss" if getattr(enemy, "role", None) else getattr(enemy, "shape", "humanoid")
        return CONTEXTS.index(key) if key in CONTEXTS else 0

    def choose(self, enemy) -> str:
        """Тактика для врага: из тех, что он умеет (бестиарий), лучшая по памяти."""
        pool = getattr(enemy, "tactics_pool", None) or []
        allowed = [not pool or t in pool or t == "rush" for t in TACTICS]
        if not getattr(enemy, "ranged", False) and not any(
                s in ("venom_spit", "magic_bolt") for s in getattr(enemy, "skills", []) or []):
            allowed[TACTICS.index("kite")] = "kite" in pool
        return TACTICS[self.select(self.context(enemy), allowed)]

    def report(self, enemy, tactic: str, dealt: float, taken: float, hero_died: bool) -> float:
        """Итог схватки -> награда в [0, 1.5]: доля урона + бонус за убийство героя."""
        reward = dealt / (dealt + taken + 1.0) + (0.5 if hero_died else 0.0)
        self.update(self.context(enemy), TACTICS.index(tactic), reward)
        return reward
