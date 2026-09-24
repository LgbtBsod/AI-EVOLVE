"""Мозг врага: тактика из общей памяти врагов, навыки на дистанции, уход из
кругов, честный френдли фаер, стелс героя.

Тактику выбирает TacticsMemory (бандит в rust_core) при появлении врага и
после каждой схватки; итог схватки (урон герою против полученного, смерть
героя) возвращается в память - так враги мира учатся против ЭТОГО героя.

    rush        - прямо на героя
    flank       - заходит сбоку (сторона - по id), потом бьёт
    kite        - держит 5-7 и бьёт навыками издалека; без них - как hit_and_run
    ambush      - стоит, пока герой не подойдёт на 9 (или пока не ударят)
    pack        - сначала собирается с 2+ своими, потом нападает
    hit_and_run - ударил - отошёл на секунду

Видит героя только через EffectManager.can_see (обзор и стелс); потеряв из
виду, идёт к последнему месту, где видел, и через несколько секунд бросает.
Любой враг выходит из круга телеграфа (даже круга своего босса). Круг бьёт
всех: обычный враг не бьёт по кругу, где нет героя, но есть свои; никто не
бьёт по кругу, где стоит сам.
"""
from __future__ import annotations

import math
import zlib
from typing import Callable, Optional

from ..effects.manager import is_alive, position

SKILL_EVERY = 0.25        # как часто пробовать навыки, с
ENGAGE_SECONDS = 20.0     # затянувшаяся схватка - тоже итог для памяти
SEARCH_SECONDS = 4.0      # сколько искать героя, потеряв из виду
AMBUSH_RANGE = 9.0
KITE_MIN, KITE_MAX = 5.0, 7.0


class EnemyBrain:
    def __init__(self, enemy, manager, memory=None, rng=None,
                 others: Optional[Callable[[], list]] = None):
        import random
        self.enemy = enemy
        self.manager = manager
        self.memory = memory
        self.rng = rng or random
        self.others = others or (lambda: [])
        self.side = 1.0 if zlib.crc32(str(getattr(enemy, "entity_id", "")).encode()) & 1 else -1.0
        self.tactic = "rush"
        self.rewards: list[float] = []
        self._reset()
        self.choose()

    # ---------------------------------------------------------------- memory
    def _reset(self) -> None:
        self.dealt = self.taken = 0.0
        self.engaged_at: Optional[float] = None
        self.last_seen: Optional[tuple[float, float]] = None
        self.lost_at: Optional[float] = None
        self.triggered = False
        self.gathered = False
        self.retreat_until = -1.0
        self.skill_timer = 0.0

    def choose(self) -> str:
        self.tactic = self.memory.choose(self.enemy) if self.memory is not None else "rush"
        return self.tactic

    def note_hit(self, info, hero_id: str) -> None:
        """HitInfo из менеджера: сколько враг нанёс герою и сколько получил сам."""
        me = str(getattr(self.enemy, "entity_id", ""))
        if info.source == me and info.target == hero_id:
            self.dealt += info.damage
        elif info.target == me:
            self.taken += info.damage
            if self.engaged_at is None:
                self.engaged_at = self.manager.now

    def finish(self, hero_died: bool = False) -> Optional[float]:
        """Схватка окончена (смерть врага или героя, долгий бой, потерял героя) -> память."""
        reward = None
        if self.memory is not None and self.engaged_at is not None and (self.dealt + self.taken) > 0:
            reward = self.memory.report(self.enemy, self.tactic, self.dealt, self.taken, hero_died)
            self.rewards.append(reward)
        self._reset()
        if is_alive(self.enemy):
            self.choose()
        return reward

    # ---------------------------------------------------------------- update
    def update(self, hero, dt: float) -> None:
        e, m = self.enemy, self.manager
        now = m.now
        if hero is None or not is_alive(hero):
            self._idle(dt)
            return
        if not getattr(e, "rooted", False) and self._dodge_telegraphs(dt):
            return
        d = math.dist(position(e), position(hero))
        sees = m.can_see(e, hero)
        if sees:
            self.last_seen, self.lost_at = position(hero), None
            if self.engaged_at is None:
                self.engaged_at = now
        elif self.engaged_at is None:
            self._idle(dt)
            return
        if self.engaged_at is not None and now - self.engaged_at > ENGAGE_SECONDS:
            self.finish()
            return
        if not sees:                               # потерял (стелс, ушёл) - ищет
            self.lost_at = now if self.lost_at is None else self.lost_at
            if now - self.lost_at > SEARCH_SECONDS or self.last_seen is None:
                self.finish()
                self._idle(dt)
                return
            e.state = "searching"
            if not getattr(e, "rooted", False) and math.dist(position(e), self.last_seen) > 1.0:
                e.move_towards(*self.last_seen, dt)
            return
        self.skill_timer -= dt
        if self.skill_timer <= 0:
            self.skill_timer = SKILL_EVERY
            if self._use_skill(hero):
                return
        if self._in_reach(hero, d):
            e.state = "attacking"
            res = m.cast(e, "weapon_attack", hero)
            if res.ok and self.tactic in ("hit_and_run", "kite"):
                self.retreat_until = now + 1.0
        if getattr(e, "rooted", False):
            return
        goal = self._goal(hero, d)
        if goal is not None:
            if e.state != "attacking":
                e.state = "chasing"
            e.move_towards(goal[0], goal[1], dt)

    # ---------------------------------------------------------------- pieces
    def _idle(self, dt: float) -> None:
        e = self.enemy
        e.state = "idle"
        if self.tactic != "ambush" and not getattr(e, "rooted", False) and hasattr(e, "_wander"):
            e._wander(dt)

    def _in_reach(self, hero, d: float) -> bool:
        reach = self.manager.range_of(self.enemy, "weapon_attack") + float(getattr(hero, "size", 0.0) or 0.0) * 0.3
        return d <= reach

    def _dodge_telegraphs(self, dt: float) -> bool:
        """Стоит в круге, который вот-вот сработает (чей угодно) - выйти из него."""
        e = self.enemy
        ex, ey = position(e)
        for tg in self.manager.telegraphs:
            if tg.radius <= 0 or math.dist((ex, ey), (tg.x, tg.y)) > tg.radius + 0.5:
                continue
            dx, dy = ex - tg.x, ey - tg.y
            n = math.hypot(dx, dy)
            if n < 1e-6:                            # в самом центре - в сторону по id
                dx, dy, n = self.side, 0.0, 1.0
            e.state = "evading"
            e.move_towards(tg.x + dx / n * (tg.radius + 1.5), tg.y + dy / n * (tg.radius + 1.5), dt)
            return True
        return False

    def _skills(self) -> list[str]:
        e = self.enemy
        by_type = getattr(type(e), "TYPE_SKILLS", {})          # EnhancedEnemy: навыки по старому типу
        own = list(getattr(e, "skills", None) or by_type.get(getattr(e, "enemy_type", ""), ()))
        return [s for s in own if self.manager.ability(s) is not None]

    def _safe(self, skill: str, hero) -> bool:
        """Френдли фаер: не бить по себе; обычный враг не бьёт по своим без героя в круге."""
        caught = self.manager.area_preview(self.enemy, skill, hero)
        if not caught:
            return True
        if self.enemy in caught:
            return False
        return bool(getattr(self.enemy, "role", None)) or hero in caught

    def _use_skill(self, hero) -> bool:
        """Случайный готовый навык (боссы - из 10-20). Лечение/щит сами ждут своего when."""
        m = self.manager
        ready = [s for s in self._skills() if m.can_cast(self.enemy, s, hero)[0] and self._safe(s, hero)]
        if not ready:
            return False
        skill = ready[int(self.rng.random() * len(ready)) % len(ready)]
        res = m.cast(self.enemy, skill, hero)
        if res.ok:
            self.enemy.state = "casting"
        return res.ok

    def _reach(self) -> float:
        """Самая дальняя атака: оружие (лук) или навык (плевок, стрела)."""
        m = self.manager
        return max([m.range_of(self.enemy, "weapon_attack")] + [m.range_of(self.enemy, s) for s in self._skills()])

    def _ranged(self) -> bool:
        return self._reach() >= KITE_MIN

    def _goal(self, hero, d: float) -> Optional[tuple[float, float]]:
        e, now = self.enemy, self.manager.now
        ex, ey = position(e)
        hx, hy = position(hero)
        ux, uy = ((ex - hx) / d, (ey - hy) / d) if d > 1e-6 else (1.0, 0.0)   # от героя к врагу
        away = (ex + ux * 3.0, ey + uy * 3.0)
        tactic = self.tactic
        if tactic == "kite" and not self._ranged():
            tactic = "hit_and_run"
        if now < self.retreat_until:
            return away
        if tactic == "ambush" and not self.triggered:
            if d <= AMBUSH_RANGE or self.taken > 0:
                self.triggered = True
            else:
                e.state = "ambush"
                return None
        if tactic == "pack" and not self.gathered:
            friends = [o for o in self.others() if o is not e and is_alive(o)]
            close = [o for o in friends if math.dist(position(o), (ex, ey)) <= 8.0]
            if len(close) >= 2 or now - (self.engaged_at or now) > 6.0 or not friends:
                self.gathered = True
            else:
                mate = min(friends, key=lambda o: math.dist(position(o), (ex, ey)))
                return position(mate)
        if tactic == "kite":                        # окно: от KITE_MIN до дальности своих выстрелов
            hold = max(KITE_MIN, min(KITE_MAX, self._reach() * 0.9))
            if d < KITE_MIN:
                return away
            if d > hold:
                return hx + ux * KITE_MIN, hy + uy * KITE_MIN
            return None
        if self._in_reach(hero, d):
            return None
        if tactic == "flank" and d > 4.0:
            px, py = -uy * self.side, ux * self.side       # перпендикуляр к линии герой-враг
            return hx + px * 3.0 + ux * 1.5, hy + py * 3.0 + uy * 1.5
        return hx, hy
