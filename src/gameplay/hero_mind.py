"""Разум героя: он сам понимает, что делают его вещи, и учится на своих боях.

Первое, чему он учится, - как вести себя на низком HP. Никто не говорит ему
«у тебя Печаль берсерка»: он замечает, что на грани смерти бьёт сильнее
(сила удара x скорость x крит против его обычной), и пробует две стойки:

    retreat - отступить, пить зелья рано (осторожный путь)
    press   - давить: драться дальше, зелье только на самом краю (путь Гатса)

Контекст - «усилен ли я сейчас» (plain / empowered). Итог эпизода (от падения
ниже порога до восстановления, конца боя или смерти) - награда бандиту
rust_core (тот же, что у врагов): выжил +0.4, доля урона, убийства; смерть - 0.
Память сохраняется между жизнями (saves/hero_mind.json), поэтому герой со
временем становится берсерком там, где это работает, и осторожным - где нет.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .tactics import memory_path, new_bandit

logger = logging.getLogger(__name__)

STANCES = ("retreat", "press")
SITUATIONS = ("plain", "empowered")
STANCE_NAMES = {"retreat": "отступить", "press": "давить"}
MIND_ENV = "AI_EVOLVE_HERO_MIND"

LOW_HP = 0.30            # ниже - решение о стойке
RECOVERED_HP = 0.60      # выше - эпизод окончен
EPISODE_MAX = 15.0       # эпизод не длиннее, с
EMPOWERED_RATIO = 1.15   # на 15% сильнее обычного - «усилен»
HEAL_AT = {"retreat": 0.35, "press": 0.12}


def mind_path() -> Optional[Path]:
    return memory_path(MIND_ENV, "hero_mind.json")


def combat_power(hero) -> float:
    """Сила героя в бою: урон x скорость x ожидаемый крит x (1 + лайфстил)."""
    dmg = float(getattr(hero, "physical_damage", 0.0) or 0.0)
    aspd = float(getattr(hero, "attack_speed", 1.0) or 1.0)
    crit = float(getattr(hero, "critical_chance", 0.0) or 0.0)
    crit_mult = float(getattr(hero, "critical_damage", 1.5) or 1.5)
    steal = float(getattr(hero, "lifesteal", 0.0) or 0.0) / 100.0
    return dmg * aspd * (1.0 + min(1.0, crit) * (crit_mult - 1.0)) * (1.0 + steal)


class HeroMind:
    def __init__(self, hero, path: Optional[Path] = None, backend: Optional[str] = None,
                 inventory_brain=None):
        self.hero = hero
        self.path = path
        self.inventory_brain = inventory_brain
        self.bandit = new_bandit(backend, c=0.5, decay=0.98, contexts=len(SITUATIONS), arms=len(STANCES))
        self.episodes = 0
        self.baseline: Optional[float] = None
        self.episode: Optional[dict] = None
        self.stance: Optional[str] = None
        self.log: list[str] = []
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.bandit.load_state(data["counts"], data["sums"])
                self.episodes = int(data.get("episodes", 0))
            except Exception as exc:
                logger.warning("hero mind not loaded: %s", exc)

    # ---------------------------------------------------------------- perception
    def hp_frac(self) -> float:
        return float(self.hero.health) / max(1.0, float(self.hero.max_health))

    def empowered(self) -> bool:
        return self.baseline is not None and combat_power(self.hero) >= self.baseline * EMPOWERED_RATIO

    # ---------------------------------------------------------------- decisions
    def _drive(self):
        return getattr(self.hero, "drive", None)      # эмоция игрока (src/gameplay/hero_drive.py)

    def low_hp(self) -> float:
        drive = self._drive()
        return drive.retreat_hp if drive is not None else LOW_HP

    def should_retreat(self) -> bool:
        """Спрашивает ИИ боя героя вместо жёсткого «ниже 30% - беги» (страх - раньше, ярость - позже)."""
        return self.hp_frac() <= self.low_hp() and self.stance != "press"

    def update(self, dt: float, in_combat: bool, now: float) -> None:
        frac = self.hp_frac()
        if frac >= RECOVERED_HP and self.episode is None:      # обычная сила - на здоровом HP
            p = combat_power(self.hero)
            self.baseline = p if self.baseline is None else 0.9 * self.baseline + 0.1 * p
        ep = self.episode
        if ep is None:
            if in_combat and frac <= self.low_hp() and self.hero.is_alive():
                ctx = 1 if self.empowered() else 0
                arm = self.bandit.select(ctx, None)
                drive = self._drive()
                # ярость подталкивает давить, но не решает за героя: учится он на том, что выбрал
                if drive is not None and STANCES[arm] == "retreat" and drive.press_bias > 0 \
                        and ((self.episodes * 7919 + int(now * 10)) % 100) / 100.0 < drive.press_bias:
                    arm = STANCES.index("press")
                self.episode = {"ctx": ctx, "arm": arm, "t0": now, "dealt": 0.0, "taken": 0.0, "kills": 0,
                                "calm": 0.0}
                self._set_stance(STANCES[arm])
            return
        ep["calm"] = 0.0 if in_combat else ep["calm"] + dt
        if not self.hero.is_alive():
            self._close(died=True)
        elif frac >= RECOVERED_HP or ep["calm"] > 1.0 or now - ep["t0"] > EPISODE_MAX:
            self._close(died=False)

    def note_hit(self, info, hero_id: str) -> None:
        ep = self.episode
        if ep is None:
            return
        if info.source == hero_id:
            ep["dealt"] += info.damage
            ep["kills"] += int(info.killed)
        elif info.target == hero_id:
            ep["taken"] += info.damage
            if info.killed:
                self._close(died=True)

    def _set_stance(self, stance: Optional[str]) -> None:
        self.stance = stance
        if self.inventory_brain is not None:
            drive = self._drive()
            calm = drive.heal_at if drive is not None else HEAL_AT["retreat"]
            self.inventory_brain.heal_at = HEAL_AT["press"] if stance == "press" else calm

    def _close(self, died: bool) -> float:
        ep, self.episode = self.episode, None
        if died:
            reward = 0.0
        else:
            reward = 0.4 + ep["dealt"] / (ep["dealt"] + ep["taken"] + 1.0) * 0.6 + 0.2 * min(2, ep["kills"])
        self.bandit.update(ep["ctx"], ep["arm"], reward)
        self.episodes += 1
        self.log.append(f"{SITUATIONS[ep['ctx']]}:{STANCES[ep['arm']]}={reward:.2f}")
        self._set_stance(None)
        return reward

    # ---------------------------------------------------------------- memory
    def lessons(self) -> dict[str, dict[str, float]]:
        out = {}
        for i, sit in enumerate(SITUATIONS):
            means = self.bandit.means(i)
            if any(means):
                out[sit] = {s: round(m, 2) for s, m in zip(STANCES, means)}
        return out

    def preferred(self, situation: str) -> Optional[str]:
        means = self.bandit.means(SITUATIONS.index(situation))
        return STANCES[max(range(len(STANCES)), key=lambda i: means[i])] if any(means) else None

    def save(self) -> None:
        if self.path is None:
            return
        counts, sums = self.bandit.state()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"counts": list(counts), "sums": list(sums), "episodes": self.episodes,
                                         "stances": STANCES, "situations": SITUATIONS}), encoding="utf-8")
