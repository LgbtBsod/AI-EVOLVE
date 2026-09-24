"""Коллективная память врагов: какие тактики работают против этого героя.

Бандит UCB1 с затуханием (rust_core.TacticsBandit, Python-двойник PyBandit -
тот же выбор бит в бит): контекст - архетип врага (форма тела, босс), рука -
тактика. Каждый враг выбирает тактику при появлении и сообщает итог схватки
(урон герою против полученного урона, смерть героя). Старые наблюдения
затухают: если герой сменил снаряжение или стиль, враги перестраиваются.
Память сохраняется между сессиями (saves/tactics_memory.json).
"""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_ENV = "AI_EVOLVE_TACTICS_MEMORY"   # путь файла памяти; "off" - только в памяти процесса


def memory_path(env: str = MEMORY_ENV, name: str = "tactics_memory.json") -> Optional[Path]:
    """Где хранить память (врагов, героя). Инструменты (dev probe, agent_play) ставят off:
    иначе прогон с тем же seed зависел бы от прошлых прогонов."""
    raw = os.environ.get(env)
    if raw is None:
        from ..content.lua_bridge import ROOT
        return ROOT / "saves" / name
    return None if raw.strip().lower() in ("", "off", "none") else Path(raw)

TACTICS = ("rush", "flank", "kite", "ambush", "pack", "hit_and_run")
CONTEXTS = ("humanoid", "beast", "blob", "spirit", "giant", "spider", "serpent", "boss")
TACTIC_NAMES = {"rush": "натиск", "flank": "обход с фланга", "kite": "держит дистанцию",
                "ambush": "засада", "pack": "стая", "hit_and_run": "удар и отход"}

try:
    from rust_core import TacticsBandit as _RustBandit
except ImportError:
    _RustBandit = None


class PyBandit:
    """Python-двойник rust_core.TacticsBandit (tactics/mod.rs): тот же алгоритм."""

    def __init__(self, contexts: int, arms: int, c: float = 0.6, decay: float = 0.97):
        self.arms, self.c, self.decay = arms, c, decay
        self.counts = [0.0] * (contexts * arms)
        self.sums = [0.0] * (contexts * arms)

    def select(self, ctx: int, allowed=None) -> int:
        lo = ctx * self.arms
        counts, sums = self.counts[lo:lo + self.arms], self.sums[lo:lo + self.arms]
        ok = (lambda a: allowed[a] if allowed and a < len(allowed) else True)
        for a in range(self.arms):
            if ok(a) and counts[a] < 1e-9:
                return a
        total = sum(counts[a] for a in range(self.arms) if ok(a))
        ln = math.log(max(1.0, total))
        best, best_v = None, -math.inf
        for a in range(self.arms):
            if not ok(a):
                continue
            v = sums[a] / counts[a] + self.c * math.sqrt(ln / counts[a])
            if v > best_v:
                best, best_v = a, v
        return 0 if best is None else best

    def update(self, ctx: int, arm: int, reward: float) -> None:
        lo = ctx * self.arms
        for i in range(lo, lo + self.arms):
            self.counts[i] *= self.decay
            self.sums[i] *= self.decay
        self.counts[lo + arm] += 1.0
        self.sums[lo + arm] += reward

    def means(self, ctx: int) -> list[float]:
        lo = ctx * self.arms
        return [s / n if n > 1e-9 else 0.0 for n, s in zip(self.counts[lo:lo + self.arms], self.sums[lo:lo + self.arms])]

    def state(self):
        return list(self.counts), list(self.sums)

    def load_state(self, counts, sums):
        if len(counts) != len(self.counts) or len(sums) != len(self.sums):
            raise ValueError("state shape does not match")
        self.counts, self.sums = list(counts), list(sums)


def new_bandit(backend: Optional[str] = None, c: float = 0.6, decay: float = 0.97,
               contexts: int = len(CONTEXTS), arms: int = len(TACTICS)):
    """Бандит rust_core (если собран) или его Python-двойник - одинаковый выбор."""
    if backend != "python" and _RustBandit is not None:
        return _RustBandit(contexts, arms, c, decay)
    return PyBandit(contexts, arms, c, decay)


class TacticsMemory:
    """Общая память всех врагов мира."""

    def __init__(self, path: Optional[Path] = None, backend: Optional[str] = None):
        self.bandit = new_bandit(backend)
        self.backend = "rust" if _RustBandit is not None and backend != "python" else "python"
        self.path = path
        self.outcomes = 0
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.bandit.load_state(data["counts"], data["sums"])
                self.outcomes = int(data.get("outcomes", 0))
            except Exception as exc:  # старая/битая память - начать заново
                logger.warning("tactics memory not loaded: %s", exc)

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
        return TACTICS[self.bandit.select(self.context(enemy), allowed)]

    def report(self, enemy, tactic: str, dealt: float, taken: float, hero_died: bool) -> float:
        """Итог схватки -> награда в [0, 1.5]: доля урона + бонус за убийство героя."""
        reward = dealt / (dealt + taken + 1.0) + (0.5 if hero_died else 0.0)
        self.bandit.update(self.context(enemy), TACTICS.index(tactic), reward)
        self.outcomes += 1
        return reward

    def summary(self) -> dict[str, dict[str, float]]:
        out = {}
        for i, ctx in enumerate(CONTEXTS):
            means = self.bandit.means(i)
            if any(means):
                out[ctx] = {t: round(m, 2) for t, m in zip(TACTICS, means) if m}
        return out

    def best(self, ctx_name: str) -> Optional[str]:
        if ctx_name not in CONTEXTS:
            return None
        means = self.bandit.means(CONTEXTS.index(ctx_name))
        return TACTICS[max(range(len(TACTICS)), key=lambda i: means[i])] if any(means) else None

    def save(self) -> None:
        if self.path is None:
            return
        counts, sums = self.bandit.state()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"counts": list(counts), "sums": list(sums), "outcomes": self.outcomes,
                                         "tactics": TACTICS, "contexts": CONTEXTS}), encoding="utf-8")
