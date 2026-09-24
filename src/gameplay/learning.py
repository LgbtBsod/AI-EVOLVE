"""Обучение агентов игры: один бандит на всех и его память на диске.

Враги (src/gameplay/tactics.py - тактики против героя) и герой
(src/gameplay/hero_mind.py - стойка на низком HP) учатся одним и тем же:
UCB1 с затуханием - rust_core.TacticsBandit, если собран, иначе Python-двойник
PyBandit (тот же выбор бит в бит, это проверяет тест). BanditMemory добавляет
к бандиту имена контекстов и рук, счётчик опыта и JSON-файл в saves/.
Инструменты выключают файл переменной окружения (AI_EVOLVE_*=off), чтобы
прогон с тем же seed не зависел от прошлых прогонов.
"""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

try:
    from rust_core import TacticsBandit as _RustBandit
except ImportError:
    _RustBandit = None


def memory_path(env: str, name: str) -> Optional[Path]:
    """saves/<name>, путь из переменной env или None ("off" - только в памяти процесса)."""
    raw = os.environ.get(env)
    if raw is None:
        from ..content.lua_bridge import ROOT
        return ROOT / "saves" / name
    return None if raw.strip().lower() in ("", "off", "none") else Path(raw)


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


def new_bandit(backend: Optional[str], contexts: int, arms: int, c: float = 0.6, decay: float = 0.97):
    """Бандит rust_core (если собран) или его Python-двойник - одинаковый выбор."""
    if backend != "python" and _RustBandit is not None:
        return _RustBandit(contexts, arms, c, decay)
    return PyBandit(contexts, arms, c, decay)


class BanditMemory:
    """Бандит с именами контекстов и рук, счётчиком опыта и файлом памяти."""

    def __init__(self, contexts: Sequence[str], arms: Sequence[str], path: Optional[Path] = None,
                 backend: Optional[str] = None, c: float = 0.6, decay: float = 0.97, count_key: str = "outcomes"):
        self.contexts, self.arms = tuple(contexts), tuple(arms)
        self.bandit = new_bandit(backend, len(self.contexts), len(self.arms), c, decay)
        self.backend = "rust" if _RustBandit is not None and backend != "python" else "python"
        self.path = path
        self.count_key = count_key
        self.count = 0
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.bandit.load_state(data["counts"], data["sums"])
                self.count = int(data.get(count_key, 0))
            except Exception as exc:  # старая/битая память - начать заново
                logger.warning("memory %s not loaded: %s", path, exc)

    def select(self, ctx: int, allowed=None) -> int:
        return self.bandit.select(ctx, allowed)

    def update(self, ctx: int, arm: int, reward: float) -> None:
        self.bandit.update(ctx, arm, reward)
        self.count += 1

    def means(self, ctx: int) -> list[float]:
        return self.bandit.means(ctx)

    def summary(self, digits: int = 2, skip_zero: bool = True) -> dict[str, dict[str, float]]:
        """{контекст: {рука: средняя награда}} - только то, что уже пробовали."""
        out = {}
        for i, ctx in enumerate(self.contexts):
            means = self.means(i)
            if any(means):
                out[ctx] = {a: round(m, digits) for a, m in zip(self.arms, means) if m or not skip_zero}
        return out

    def best(self, ctx_name: str) -> Optional[str]:
        if ctx_name not in self.contexts:
            return None
        means = self.means(self.contexts.index(ctx_name))
        return self.arms[max(range(len(self.arms)), key=lambda i: means[i])] if any(means) else None

    def save(self) -> None:
        if self.path is None:
            return
        counts, sums = self.bandit.state()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"counts": list(counts), "sums": list(sums), self.count_key: self.count,
                                         "arms": self.arms, "contexts": self.contexts}), encoding="utf-8")
