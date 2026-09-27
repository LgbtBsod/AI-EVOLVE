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

import logging
from pathlib import Path
from typing import Optional

from .learning import BanditMemory, memory_path

logger = logging.getLogger(__name__)

STANCES = ("retreat", "press")
SITUATIONS = ("plain", "empowered")
STANCE_NAMES = {"retreat": "отступить", "press": "давить"}
MIND_ENV = "AI_EVOLVE_HERO_MIND"

# Физические (не магия) способы двигаться в бою - второе измерение той же памяти, что решает
# стойку (retreat/press): контекст - выбранная стойка (герой, который решил давить, учится, что
# в этой ситуации лучше сработало - прыжок на цель или рывок в сторону), рука - какое движение
# взять. Ставки те же (выжил/урон/убийства, _close), только читаются отдельно от lessons_moves.
MOVES = ("roll", "jump", "sprint", "dash")
MOVE_NAMES = {"roll": "перекат", "jump": "прыжок", "sprint": "рывок бегом", "dash": "рывок в сторону"}

# Третье измерение: решение ДО боя - ввязываться в конкретного врага или обойти его. Контекст -
# насколько он опасен (elite/boss -> "dangerous", иначе "normal"). "avoid" не имеет исхода боя,
# который можно измерить (герой в бой не вступил), поэтому у него нет контрфактической награды -
# он получает фиксированное нейтральное значение AVOID_REWARD, а не результат гипотетической схватки.
THREAT = ("normal", "dangerous")
ENGAGE = ("engage", "avoid")
AVOID_REWARD = 0.5

LOW_HP = 0.30            # ниже - решение о стойке
RECOVERED_HP = 0.60      # выше - эпизод окончен
EPISODE_MAX = 15.0       # эпизод не длиннее, с
EMPOWERED_RATIO = 1.15   # на 15% сильнее обычного - «усилен»
HEAL_AT = {"retreat": 0.35, "press": 0.12}


def mind_path() -> Optional[Path]:
    return memory_path(MIND_ENV, "hero_mind.json")


def move_path() -> Optional[Path]:
    return memory_path(MIND_ENV, "hero_movement.json")


def engage_path() -> Optional[Path]:
    return memory_path(MIND_ENV, "hero_engage.json")


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
        self.inventory_brain = inventory_brain
        self.memory = BanditMemory(SITUATIONS, STANCES, path, backend, c=0.5, decay=0.98, count_key="episodes")
        self.move_memory = BanditMemory(STANCES, MOVES, move_path(), backend, c=0.5, decay=0.98, count_key="episodes")
        self.engage_memory = BanditMemory(THREAT, ENGAGE, engage_path(), backend, c=0.5, decay=0.98, count_key="episodes")
        stored = self.memory.extra.get("baseline")
        self.baseline: Optional[float] = float(stored) if isinstance(stored, (int, float)) else None
        self.episode: Optional[dict] = None
        self.fight: Optional[dict] = None   # решение engage/avoid для текущего врага - отдельный трекер, не эпизод low-HP
        self.stance: Optional[str] = None
        self.move: Optional[str] = None
        self.log: list[str] = []

    @property
    def path(self) -> Optional[Path]:
        return self.memory.path

    @path.setter
    def path(self, value: Optional[Path]) -> None:
        self.memory.path = value

    @property
    def episodes(self) -> int:
        return self.memory.count

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

    def decide_engage(self, enemy) -> bool:
        """Решение ДО боя: ввязаться в этого врага или обойти его (в отличие от should_retreat/stance,
        которые работают уже во время боя). Держит арм стабильным, пока враг тот же, чтобы не
        перевыбирать бандита каждый кадр."""
        fight = self.fight
        if fight is not None and fight["enemy"] is enemy:
            return ENGAGE[fight["arm"]] == "engage"
        if fight is not None:
            self._close_fight(died=False)      # цель сменилась раньше конца схватки
        ctx = 1 if self._dangerous(enemy) else 0
        arm = self.engage_memory.select(ctx)
        self.fight = {"enemy": enemy, "enemy_id": str(getattr(enemy, "entity_id", "")),
                     "ctx": ctx, "arm": arm, "dealt": 0.0, "taken": 0.0, "kills": 0}
        if ENGAGE[arm] != "engage":
            # avoid: нет боя -> нет исхода, который можно измерить, поэтому награда фиксированная,
            # а не по формуле _close_fight (которая читает dealt/taken/kills несуществующего боя)
            self.engage_memory.update(ctx, arm, AVOID_REWARD)
        return ENGAGE[arm] == "engage"

    @staticmethod
    def _dangerous(enemy) -> bool:
        return getattr(enemy, "enemy_type", None) in ("elite", "boss") or bool(getattr(enemy, "is_boss", False))

    def _close_dead_fight(self) -> None:
        """Смерть героя может закрыть схватку с engage-решением, даже если эпизод low-HP не открыт."""
        if not self.hero.is_alive() and self.fight is not None:
            self._close_fight(died=True)

    def update(self, dt: float, in_combat: bool, now: float) -> None:
        self._close_dead_fight()
        frac = self.hp_frac()
        if frac >= RECOVERED_HP and self.episode is None:      # обычная сила - на здоровом HP
            p = combat_power(self.hero)
            self.baseline = p if self.baseline is None else 0.9 * self.baseline + 0.1 * p
        ep = self.episode
        if ep is None:
            if in_combat and frac <= self.low_hp() and self.hero.is_alive():
                ctx = 1 if self.empowered() else 0
                arm = self.memory.select(ctx)
                drive = self._drive()
                # ярость подталкивает давить, но не решает за героя: учится он на том, что выбрал
                if drive is not None and STANCES[arm] == "retreat" and drive.press_bias > 0 \
                        and ((self.episodes * 7919 + int(now * 10)) % 100) / 100.0 < drive.press_bias:
                    arm = STANCES.index("press")
                move_arm = self.move_memory.select(arm)     # контекст движения = выбранная стойка
                self.episode = {"ctx": ctx, "arm": arm, "move_arm": move_arm, "t0": now, "dealt": 0.0,
                                "taken": 0.0, "kills": 0, "calm": 0.0}
                self._set_stance(STANCES[arm])
                self.move = MOVES[move_arm]
            return
        ep["calm"] = 0.0 if in_combat else ep["calm"] + dt
        if not self.hero.is_alive():
            self._close(died=True)
        elif frac >= RECOVERED_HP or ep["calm"] > 1.0 or now - ep["t0"] > EPISODE_MAX:
            self._close(died=False)

    def note_hit(self, info, hero_id: str) -> None:
        self._note_episode_hit(info, hero_id)
        self._note_fight_hit(info, hero_id)

    def _note_episode_hit(self, info, hero_id: str) -> None:
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

    def _note_fight_hit(self, info, hero_id: str) -> None:
        f = self.fight
        if f is None or ENGAGE[f["arm"]] != "engage":
            return
        if info.source == hero_id and info.target == f["enemy_id"]:
            f["dealt"] += info.damage
            if info.killed:
                f["kills"] += 1
                self._close_fight(died=False)
        elif info.target == hero_id and info.source == f["enemy_id"]:
            f["taken"] += info.damage
            if info.killed:
                self._close_fight(died=True)

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
        self.memory.update(ep["ctx"], ep["arm"], reward)
        self.move_memory.update(ep["arm"], ep["move_arm"], reward)
        self.log.append(f"{SITUATIONS[ep['ctx']]}:{STANCES[ep['arm']]}:{MOVES[ep['move_arm']]}={reward:.2f}")
        self._set_stance(None)
        self.move = None
        return reward

    def _close_fight(self, died: bool) -> Optional[float]:
        f, self.fight = self.fight, None
        if f is None or ENGAGE[f["arm"]] != "engage":
            return None       # avoid уже вознаграждён на месте, закрывать нечего
        if died:
            reward = 0.0
        else:
            reward = 0.4 + f["dealt"] / (f["dealt"] + f["taken"] + 1.0) * 0.6 + 0.2 * min(2, f["kills"])
        self.engage_memory.update(f["ctx"], f["arm"], reward)
        self.log.append(f"{THREAT[f['ctx']]}:engage={reward:.2f}")
        return reward

    # ---------------------------------------------------------------- memory
    def lessons(self, skip_zero: bool = False) -> dict[str, dict[str, float]]:
        return self.memory.summary(skip_zero=skip_zero)

    def preferred(self, situation: str) -> Optional[str]:
        return self.memory.best(situation)

    def lessons_moves(self, skip_zero: bool = False) -> dict[str, dict[str, float]]:
        return self.move_memory.summary(skip_zero=skip_zero)

    def preferred_move(self, stance: str) -> Optional[str]:
        return self.move_memory.best(stance)

    def lessons_engage(self, skip_zero: bool = False) -> dict[str, dict[str, float]]:
        return self.engage_memory.summary(skip_zero=skip_zero)

    def preferred_engage(self, threat: str) -> Optional[str]:
        return self.engage_memory.best(threat)

    def save(self) -> None:
        if self.baseline is not None:
            self.memory.extra["baseline"] = self.baseline
        self.memory.save()
        self.move_memory.save()
        self.engage_memory.save()
