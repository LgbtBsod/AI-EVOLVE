"""Влечения героя: эмоция игрока и подсказки как сдвиг интереса, а не приказ.

HeroDrive выбирает цель ИИ героя по полезности:

    полезность(цель) = база(ситуация) x вес эмоции + бонус подсказки (+ липкость текущей)

База считается из ситуации (как близко враг, лут, известен ли выход), вес
даёт эмоция (lua_content/hero_mind.lua), подсказка добавляет интерес к целям
в указанной стороне или к указанной цели и затухает со временем. Текущая цель
получает небольшую липкость - герой не мечется между выходом и подсказкой.
Эмоция двигает и порог отступления, и порог зелий, и склонность «давить»
(HeroMind), но решение принимает герой.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

GOALS = ("fight", "loot", "exit", "hint", "explore")
DEFAULT = {
    "goals": {"fight": 1.4, "loot": 0.8, "exit": 0.7, "hint": 0.5, "explore": 0.25},
    "stickiness": 0.15,
    "emotions": {"calm": {"name": "Спокойствие", "weights": {}, "retreat_hp": 0.30, "heal_at": 0.35,
                          "thought": "Спокойно, по порядку."}},
    "directives": {"strength": 0.6, "duration": 30},
}
THOUGHTS = {"fight": "дерусь", "loot": "к добыче", "exit": "к выходу", "hint": "к подсказке",
            "explore": "осматриваюсь", "retreat": "отступаю"}


@lru_cache(maxsize=1)
def config() -> dict:
    try:
        from ..content import lua_bridge
        data = lua_bridge.load(lua_bridge.CONTENT / "hero_mind.lua", cache=True)
    except Exception as exc:  # без Lua - только спокойствие
        logger.warning("hero_mind.lua not loaded: %s", exc)
        return DEFAULT
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT.items()}
    for k, v in data.items():
        out[k] = v
    return out


def player_keys() -> dict[str, tuple[str, str]]:
    """Клавиша -> ("emotion" | "directive", имя) из hero_mind.lua."""
    cfg = config()
    out = {}
    for name, e in (cfg.get("emotions") or {}).items():
        if isinstance(e, dict) and e.get("key"):
            out[e["key"]] = ("emotion", name)
    for name, d in (cfg.get("directives") or {}).items():
        if isinstance(d, dict) and d.get("key"):
            out[d["key"]] = ("directive", name)
    return out


@dataclass
class Option:
    goal: str
    target: Optional[tuple[float, float]]
    base: float                     # 0..1: насколько цель уместна прямо сейчас


class HeroDrive:
    def __init__(self, emotion: str = "calm"):
        cfg = config()
        self.cfg = cfg
        self.emotion = emotion if emotion in cfg["emotions"] else "calm"
        self.directive: Optional[str] = None
        self.directive_at = 0.0
        self.goal: Optional[str] = None
        self.last_scores: dict[str, float] = {}

    # ---------------------------------------------------------------- player input
    def set_emotion(self, name: str) -> bool:
        if name not in self.cfg["emotions"]:
            return False
        self.emotion = name
        return True

    def set_directive(self, name: Optional[str], now: float) -> bool:
        dirs = self.cfg["directives"]
        if name in (None, "none"):
            self.directive = None
            return True
        if not isinstance(dirs.get(name), dict):
            return False
        self.directive, self.directive_at = name, now
        return True

    # ---------------------------------------------------------------- knobs for other minds
    @property
    def mood(self) -> dict:
        return self.cfg["emotions"][self.emotion]

    @property
    def retreat_hp(self) -> float:
        return float(self.mood.get("retreat_hp", 0.30))

    @property
    def heal_at(self) -> float:
        return float(self.mood.get("heal_at", 0.35))

    @property
    def press_bias(self) -> float:
        return float(self.mood.get("press_bias", 0.0))

    def weight(self, goal: str) -> float:
        return float((self.mood.get("weights") or {}).get(goal, 1.0))

    # ---------------------------------------------------------------- directive
    def interest(self, now: float) -> float:
        """Сила подсказки сейчас: линейно гаснет за duration секунд."""
        if self.directive is None:
            return 0.0
        dirs = self.cfg["directives"]
        left = 1.0 - (now - self.directive_at) / max(1.0, float(dirs.get("duration", 30)))
        if left <= 0:
            self.directive = None
            return 0.0
        return float(dirs.get("strength", 0.9)) * left

    def direction(self) -> Optional[tuple[float, float]]:
        d = (self.cfg["directives"].get(self.directive) or {}).get("dir") if self.directive else None
        return (float(d[0]), float(d[1])) if d else None

    def _bonus(self, opt: Option, hero_xy: tuple[float, float], now: float) -> float:
        k = self.interest(now)
        if k <= 0:
            return 0.0
        spec = self.cfg["directives"].get(self.directive) or {}
        if spec.get("goal"):
            if opt.goal == spec["goal"]:
                return k
            return k * 0.6 if opt.goal == "explore" else 0.0     # цели не видно - ищет её
        d = self.direction()
        if d is None:
            return 0.0
        if opt.goal == "explore":
            return k * 0.8                                       # пойти в ту сторону
        if opt.target is None:
            return 0.0
        vx, vy = opt.target[0] - hero_xy[0], opt.target[1] - hero_xy[1]
        n = math.hypot(vx, vy)
        return k * max(0.0, (vx * d[0] + vy * d[1]) / n) if n > 1e-6 else 0.0

    # ---------------------------------------------------------------- choice
    def choose(self, options: list[Option], hero_xy: tuple[float, float], now: float) -> Optional[Option]:
        goals = self.cfg["goals"]
        best, best_v, scores = None, -math.inf, {}
        for opt in options:
            if opt.base <= 0:
                continue
            v = float(goals.get(opt.goal, 0.5)) * opt.base * self.weight(opt.goal) + self._bonus(opt, hero_xy, now)
            if opt.goal == self.goal:
                v += float(self.cfg.get("stickiness", 0.15))
            scores[opt.goal] = round(v, 3)
            if v > best_v:
                best, best_v = opt, v
        self.last_scores = scores
        self.goal = best.goal if best else None
        return best

    def explore_target(self, hero_xy: tuple[float, float], rng) -> Optional[tuple[float, float]]:
        """Куда исследовать, если подсказана сторона: 10 шагов туда и немного в стороны."""
        d = self.direction()
        if d is None or self.directive is None:
            return None
        return (hero_xy[0] + d[0] * 10.0 + rng.uniform(-4.0, 4.0),
                hero_xy[1] + d[1] * 10.0 + rng.uniform(-4.0, 4.0))

    def thought(self, state: Optional[str] = None) -> str:
        """Строка «мыслей» для HUD: эмоция, подсказка, что делает."""
        parts = [self.mood.get("name", self.emotion)]
        if self.directive:
            parts.append((self.cfg["directives"].get(self.directive) or {}).get("name", self.directive))
        doing = THOUGHTS.get(state or self.goal or "", "")
        line = " · ".join(parts)
        return f"{line} — {doing}" if doing else line
