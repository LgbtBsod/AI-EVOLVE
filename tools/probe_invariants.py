#!/usr/bin/env python3
"""Инварианты мира AI-EVOLVE, проверяемые на КАЖДОМ кадре agent_play.

Гипотезы (probe_analysis) смотрят на сэмплы раз в секунду и говорят "похоже
на"; инварианты - жёсткие правила, нарушение которых - баг всегда:
  HERO_HP_OVER_MAX     живой герой с HP > max_health
  HERO_ALIVE_AT_ZERO   is_alive() == True при HP <= 0 (сломанная защёлка смерти)
  NON_FINITE           NaN/inf в HP или координатах героя/врага
  OUT_OF_WORLD         юнит за краем карты (world_size/2 + world_slack)
  ENEMY_HP_OVER_MAX    враг с HP > max_health
  ENEMY_OVERFLOW       естественных врагов больше max_enemies + max_enemies_slack
  DEAD_ENEMY_LINGERS   мёртвый враг остаётся в scene.enemies дольше N кадров

Пороги - lua_content/qa.lua (секция invariants). Нарушения дедуплицируются по
(id, сущность): первое появление + счётчик - агенту хватает одной строки.
"""
import math

from probe_runtime import entity_id_of, entity_type_of, get_scene


class InvariantChecker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.violations = {}   # (id, who) -> {"id", "who", "t", "detail", "count"}
        self._dead_frames = {}

    def _flag(self, vid, who, t, detail):
        key = (vid, who)
        v = self.violations.get(key)
        if v is None:
            if len(self.violations) >= self.cfg["max_violations_kept"]:
                return
            self.violations[key] = {"id": vid, "who": who, "t": round(t, 2), "detail": detail, "count": 1}
        else:
            v["count"] += 1

    def check(self, game, t):
        scene = get_scene(game)
        if scene is None:
            return
        eps = self.cfg["hp_epsilon"]
        half = getattr(scene, "world_size", 0) / 2 + self.cfg["world_slack"]
        units = []
        player = getattr(scene, "player", None)
        if player is not None:
            units.append((player, True))
        enemies = list(getattr(scene, "enemies", []))
        units.extend((e, False) for e in enemies)

        for unit, is_player in units:
            who = "hero" if is_player else f"{entity_type_of(unit, False)}#{entity_id_of(unit)[-6:]}"
            hp, mhp, x, y = unit.health, unit.max_health, unit.x, unit.y
            if not all(math.isfinite(v) for v in (hp, x, y)):
                self._flag("NON_FINITE", who, t, f"hp={hp} pos=({x}, {y})")
                continue
            if half > 0 and (abs(x) > half or abs(y) > half):
                self._flag("OUT_OF_WORLD", who, t, f"pos=({x:.1f}, {y:.1f}) limit={half:.0f}")
            alive = unit.is_alive()
            if is_player:
                if alive and hp > mhp + eps:
                    self._flag("HERO_HP_OVER_MAX", who, t, f"hp={hp:.2f} max={mhp}")
                if alive and hp <= 0:
                    self._flag("HERO_ALIVE_AT_ZERO", who, t, f"hp={hp:.2f}")
            else:
                if hp > mhp + eps:
                    self._flag("ENEMY_HP_OVER_MAX", who, t, f"hp={hp:.2f} max={mhp}")
                eid = entity_id_of(unit)
                if not alive:
                    n = self._dead_frames.get(eid, 0) + 1
                    self._dead_frames[eid] = n
                    if n > self.cfg["dead_enemy_frames"]:
                        self._flag("DEAD_ENEMY_LINGERS", who, t, f"dead for {n} frames, still in scene.enemies")

        live_ids = {entity_id_of(e) for e in enemies}
        for eid in list(self._dead_frames):
            if eid not in live_ids:
                del self._dead_frames[eid]

        # Лимит касается только естественного спавна: врагов игрока (клавиша 1)
        # игра сознательно не ограничивает
        cap = getattr(scene, "max_enemies", None)
        created = {id(o) for o in getattr(scene, "player_created_objects", [])}
        natural = sum(1 for e in enemies if id(e) not in created)
        if cap is not None and natural > cap + self.cfg["max_enemies_slack"]:
            self._flag("ENEMY_OVERFLOW", "scene", t, f"{natural} naturally spawned enemies, max_enemies={cap}")

    def report(self):
        return sorted(self.violations.values(), key=lambda v: v["t"])

    def lines(self):
        return [f"INVARIANT {v['id']} {v['who']} first at t={v['t']}: {v['detail']}"
                + (f" (x{v['count']} frames)" if v["count"] > 1 else "") for v in self.report()]
