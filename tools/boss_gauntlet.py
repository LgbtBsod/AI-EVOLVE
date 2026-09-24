"""Стенд боссов: настоящий герой против боссов мира, без окна.

    python tools/boss_gauntlet.py                    # все боссы; герой уровня босса, «Печаль берсерка»
    python tools/boss_gauntlet.py --boss lucifer --level 80
    python tools/boss_gauntlet.py --gear iron_sword,chainmail --no-sorrow --seeds 5
    python tools/boss_gauntlet.py --campaign --lives 5
        реальная сессия: герой с 1-го уровня проходит уровни мира (стая врагов акта, сундук,
        выход), опыт только за убийства и активности, между боями отдых; смерть - конец жизни.
        Разум героя (src/gameplay/hero_mind.py) помнит уроки между жизнями - видно, как он
        учится вести себя на низком HP (с «Печалью берсерка» - давить, как Гатс).
    --trace    урон по способностям и состояния ИИ героя в каждом бою
    (qa.py gauntlet ... - то же самое)

Всё настоящее: Character (ИИ боя, навыки класса), инвентарь и InventoryBrain
(зелья, переодевание), очки характеристик (HeroGrowth), перки; враги и
боссы - make_enemy() + EnemyBrain (навыки, телеграфы, призыв), единый
EffectManager. Время виртуальное: минуты боя - доли секунды. Каждый бой
пишется в probe_db (kind=gauntlet): `probe_db.py runs`, `compare`, `trend`.
"""
from __future__ import annotations

import argparse
import collections
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("AI_EVOLVE_TACTICS_MEMORY", "off")
os.environ.setdefault("AI_EVOLVE_HERO_MIND", "off")

DEFAULT_GEAR = ("iron_sword", "chainmail", "ring_of_precision")
DT = 0.05
SAMPLE_EVERY = 0.5


class _Game:
    """Минимальная «игра»: без рендера, с менеджером эффектов."""
    render = None
    effect_manager = None


class Arena:
    """Мир для менеджера: сущности, призыв, стены."""

    def __init__(self, game, plan, rng):
        self.game, self.plan, self.rng = game, plan, rng
        self.hero = None
        self.enemies: list = []
        self.manager = None

    def entities(self):
        return [self.hero] + self.enemies

    def clamp_position(self, x, y):
        return max(-40.0, min(40.0, x)), max(-40.0, min(40.0, y))

    def spawn_summon(self, kind, x, y, faction, level, owner):
        mob = self.spawn(kind, max(1, int(level)), x, y, faction)
        mob.summoned_by = owner
        return mob

    def spawn(self, kind, level, x, y, faction="monsters"):
        from src.gameplay.enemy_ai import EnemyBrain
        from src.gameplay.world import make_enemy
        mob = make_enemy(self.game, kind, level, x, y, self.plan)
        self.manager.register(mob, faction)
        mob.brain = EnemyBrain(mob, self.manager, None, self.rng, others=lambda: self.enemies)
        mob.health = mob.max_health
        self.enemies.append(mob)
        return mob


@dataclass
class Bout:
    boss: str
    level: int
    won: bool
    seconds: float
    hero_hp: float
    boss_hp_pct: float
    potions: int
    berserk: float              # секунд с HP < 40% (Lost My Self)
    adds: int
    last_will: float = 0.0      # секунд на 1 HP (Last Will)
    timeout: bool = False       # никто не умер за limit секунд
    trace: dict = field(default_factory=dict)


class Session:
    """Герой, менеджер и арена одной жизни."""

    def __init__(self, cls="warrior", gear=DEFAULT_GEAR, sorrow=True, seed=1, level=1, potions=3, mind=None):
        from src.effects.abilities import load_abilities
        from src.effects.manager import EffectManager
        from src.entities.character import Character
        from src.gameplay.hero_mind import HeroMind
        from src.gameplay.inventory import Inventory, InventoryBrain
        from src.gameplay.items import catalog
        from src.gameplay.progression import HeroGrowth, perk_effects, progression
        from src.gameplay.world import world_plan

        random.seed(seed)
        self.seed = seed
        self.rng = random.Random(seed)
        self.plan = world_plan()
        self.game = _Game()
        self.arena = Arena(self.game, self.plan, self.rng)
        self.mgr = mgr = EffectManager(world=self.arena, abilities=load_abilities(), rng=self.rng)
        self.arena.manager = self.game.effect_manager = mgr
        self.cls = cls

        hero = Character("gauntlet_hero", self.game, 0.0, 0.0, 0.5, cls, (0, 0, 1, 1), is_player=True)
        hero.ai_update_interval = 0.0
        hero.level = level
        hero.attribute_points = int(progression()["hero_points_per_level"]) * (level - 1)
        self.growth = HeroGrowth(cls)
        self.growth.spend(hero)
        mgr.register(hero, "hero")
        self.arena.hero = self.hero = hero
        self.inv = inv = Inventory(hero, capacity=20, on_change=lambda i: mgr.equip(hero, i.equipped.values()))
        cat = catalog()
        for item_id in list(gear) + (["sorrow_of_berserk"] if sorrow else []) + ["health_potion"] * potions:
            item = cat.get(item_id)
            if item is None:
                raise SystemExit(f"unknown item {item_id!r}")
            inv.add(item)
            if item.equippable:
                inv.equip(item)
        mgr.set_perks(hero, perk_effects(hero.attributes))
        self.brain = InventoryBrain(inv, role=cls)
        # разум переходит из жизни в жизнь: та же память, новое тело
        self.mind = mind or HeroMind(hero)
        self.mind.hero, self.mind.inventory_brain = hero, self.brain
        hero.mind = self.mind
        mgr.register_event_handler(lambda info: self.mind.note_hit(info, str(hero.entity_id)))
        self._events: list = []
        mgr.register_event_handler(self._record_hit)
        self.rest()

    # ---------------------------------------------------------------- between fights
    def rest(self) -> None:
        """Отдых: полное HP/мана/стамина, откат навыков, прокачка накопленных очков."""
        from src.gameplay.progression import perk_effects
        hero, mgr = self.hero, self.mgr
        if hero.attribute_points:
            self.growth.spend(hero)
            mgr.set_perks(hero, perk_effects(hero.attributes))
        st = mgr.state(hero)
        st.cooldowns.clear()
        st.external.clear()
        st.periodic.clear()
        st.refresh(mgr.now)
        hero.health, hero.mana, hero.stamina = hero.max_health, hero.max_mana, hero.max_stamina
        hero.is_defeated = False
        hero.x = hero.y = 0.0

    def _reset_arena(self) -> None:
        for e in self.arena.enemies:
            self.mgr.unregister(e)
        self.arena.enemies = []
        self.mgr.telegraphs.clear()

    # ---------------------------------------------------------------- battle loop
    def _record_hit(self, info) -> None:
        self._events.append({"t": round(self.mgr.now, 3), "source": info.source, "target": info.target,
                             "damage": info.damage, "critical": info.is_critical,
                             "dodged": info.is_dodged or getattr(info, "missed", False), "ability": info.ability})

    def _battle(self, until, limit: float) -> dict:
        """Крутит бой, пока until() не скажет «хватит» (или limit). Опыт - за каждое убийство."""
        hero, mgr, arena, brain, mind = self.hero, self.mgr, self.arena, self.brain, self.mind
        t0 = mgr.now
        self._events = []
        r = {"t": 0.0, "used": 0, "berserk": 0.0, "last_will": 0.0, "kills": [], "samples": [],
             "states": collections.Counter()}
        next_sample = 0.0
        while r["t"] < limit and hero.is_alive() and not until():
            r["t"] += DT
            mgr.update(DT)
            if brain.update(DT, lambda it: mgr.use_item(hero, it)) == "potion:hp":
                r["used"] += 1
            live = [e for e in arena.enemies if e.is_alive()]
            seen = [e for e in live if mgr.can_see(hero, e)]
            mind.update(DT, bool(seen), mgr.now)
            hero.update_ai(seen, [], DT)
            hero.use_skill_automatically(seen, DT)
            r["states"][hero.ai_state] += 1
            for e in live:
                e.update_ai(hero, DT)
            for e in [e for e in arena.enemies if not e.is_alive()]:
                mgr.unregister(e)
                arena.enemies.remove(e)
                r["kills"].append((round(mgr.now - t0, 2), str(e.entity_id), e.enemy_type))
                if getattr(e, "summoned_by", None) is None:
                    hero.add_experience(float(getattr(e, "experience_reward", 0)))
            if hero.is_alive() and hero.health <= 1.0 + 1e-9:
                r["last_will"] += DT
            if hero.is_alive() and hero.health < 0.4 * hero.max_health:
                r["berserk"] += DT
            if r["t"] >= next_sample:
                next_sample += SAMPLE_EVERY
                r["samples"].append(self._sample(r["t"]))
        mind.update(DT, False, mgr.now + 2.0)          # бой кончился - эпизод разума закрыт
        r["samples"].append(self._sample(r["t"]))
        r["events"] = [dict(e, t=round(e["t"] - t0, 3)) for e in self._events]
        return r

    def _sample(self, t: float) -> dict:
        h = self.hero
        return {"t": round(t, 2),
                "player": {"id": str(h.entity_id), "hp": h.health, "max_hp": h.max_health, "pos": [h.x, h.y],
                           "alive": h.is_alive(), "lvl": h.level, "xp": h.experience,
                           "xp_next": h.experience_to_next_level, "ai": h.ai_state},
                "enemies": [{"id": str(e.entity_id), "type": e.enemy_type, "hp": e.health, "max_hp": e.max_health,
                             "pos": [e.x, e.y]} for e in self.arena.enemies]}

    # ---------------------------------------------------------------- content
    def clear_level(self, level: int, pack: int = 3, limit: float = 120.0) -> bool:
        """Обычный уровень: стая врагов акта, сундук, выход. -> жив ли герой."""
        from src.gameplay.loot import loot_tables, roll_loot
        from src.gameplay.progression import xp_for
        self._reset_arena()
        for i in range(pack):
            ang = 2 * math.pi * i / pack
            self.arena.spawn(self.plan.pick_enemy(level, self.rng), level, 8.0 * math.cos(ang), 8.0 * math.sin(ang))
        self._battle(lambda: not self.arena.enemies, limit)
        if not self.hero.is_alive():
            return False
        gold, items = roll_loot(loot_tables().get("chest") or {}, self.rng)
        self.inv.gold += gold
        for it in items:
            self.inv.add(it)
        self.hero.add_experience(xp_for("chest") + xp_for("exit"))
        for _ in range(5):                                   # ИИ инвентаря переодевается
            self.brain.update(2.5, lambda it: self.mgr.use_item(self.hero, it))
        return True

    def fight(self, boss_id: str, level: int, limit: float = 240.0, record: bool = True) -> Bout:
        from src.gameplay.progression import xp_for
        self._reset_arena()
        boss = self.arena.spawn(boss_id, level, 9.0, 0.0)
        r = self._battle(lambda: not boss.is_alive(), limit)
        hero = self.hero
        won = boss.health <= 0 and hero.is_alive()
        if won:   # опыт за самого босса начислен в бою; плюс активность boss_kill
            hero.add_experience(xp_for("boss_kill"))
        bout = Bout(boss_id, level, won, round(r["t"], 1), round(hero.health, 1),
                    round(100.0 * max(0.0, boss.health) / max(1.0, boss.max_health), 1), r["used"],
                    round(r["berserk"], 1), sum(1 for k in r["kills"] if k[2] != boss_id) + len(self.arena.enemies),
                    round(r["last_will"], 1), hero.is_alive() and boss.is_alive(),
                    trace=self._trace(r))
        if record:
            self._ingest(bout, r)
        return bout

    def _trace(self, r: dict) -> dict:
        hid = str(self.hero.entity_id)
        dealt, taken = collections.Counter(), collections.Counter()
        for e in r["events"]:
            if e["source"] == hid:
                dealt[e["ability"]] += e["damage"]
            elif e["target"] == hid:
                taken[e["ability"]] += e["damage"]
        total = sum(r["states"].values()) or 1
        return {"states": {k: round(100.0 * v / total) for k, v in r["states"].most_common()},
                "dealt": {k: round(v) for k, v in dealt.most_common(5)},
                "taken": {k: round(v) for k, v in taken.most_common(5)}}

    def _ingest(self, bout: Bout, r: dict) -> None:
        import probe_db
        run_id = f"gauntlet_{time.strftime('%Y%m%d_%H%M%S')}_{bout.boss}_s{self.seed}_{int(time.time_ns() % 1e6)}"
        meta = {"kind": "gauntlet", "status": "WIN" if bout.won else ("TIME" if bout.timeout else "DEAD"),
                "seed": self.seed, "duration": bout.seconds, "fast": True, "render": "none",
                "label": f"{bout.boss} lvl{bout.level} hero{self.hero.level}", "boss": bout.boss,
                "lessons": self.mind.lessons()}
        err = probe_db.ingest_quietly(run_id, meta, r["samples"], r["events"], r["kills"])
        if err:
            print(err, file=sys.stderr)


def fight(boss_id: str, level: int, cls: str = "warrior", gear=DEFAULT_GEAR, sorrow: bool = True,
          seed: int = 1, limit: float = 240.0, potions: int = 3, record: bool = False) -> Bout:
    """Отдельный бой: герой того же уровня, что босс (очки раскиданы HeroGrowth)."""
    return Session(cls, gear, sorrow, seed, level, potions).fight(boss_id, level, limit, record)


def roster(plan) -> list[tuple[str, int]]:
    """Все боссы мира по порядку: мини-босс (5-й уровень акта), босс (последний), финал."""
    out = []
    for act in plan.acts:
        lo, hi = act["levels"][:2]
        if act.get("miniboss"):
            out.append((act["miniboss"], lo + 4))
        for b in plan.final_sequence(hi) or ([act["boss"]] if act.get("boss") else []):
            out.append((b, hi))
    return out


def _line(tag: str, b: Bout, name: str, head: str, trace: bool) -> str:
    s = (f"{tag} {head} {name:<28} t={b.seconds:6.1f}s hero_hp={b.hero_hp:7.1f} boss_left={b.boss_hp_pct:5.1f}% "
         f"potions={b.potions} berserk={b.berserk}s last_will={b.last_will}s adds={b.adds}")
    if trace:
        s += f"\n      ai% {b.trace['states']}  dealt {b.trace['dealt']}  taken {b.trace['taken']}"
    return s


def campaign(fights, args, gear, plan) -> int:
    """Жизни одного героя: с 1-го уровня по миру; разум (уроки) переходит в следующую жизнь."""
    from src.gameplay.hero_mind import mind_path
    mind = None
    for life in range(1, args.lives + 1):
        seed = args.seed + life - 1
        ses = Session(args.cls, gear, not args.no_sorrow, seed, 1, args.potions, mind=mind)
        mind = ses.mind
        if mind.path is None and not args.no_save:
            mind.path = mind_path() if os.environ.get("AI_EVOLVE_HERO_MIND") != "off" else None
        cleared, killed, fate = 0, 0, "прошёл мир"
        for boss_id, lvl in fights:
            for level in range(cleared + 1, lvl):             # обычные уровни до босса
                ses.rest()
                if not ses.clear_level(level):
                    fate = f"погиб на уровне {level} от стаи"
                    break
            else:
                cleared = max(cleared, lvl - 1)
                ses.rest()
                before = ses.hero.level
                b = ses.fight(boss_id, lvl)
                name = (plan.spec(boss_id) or {}).get("name", boss_id)
                tag = "WIN " if b.won else ("TIME" if b.timeout else "DEAD")
                print(_line(tag, b, name, f"life {life} hero {before:2d}->{ses.hero.level:2d} vs {lvl:2d}", args.trace))
                if b.won:
                    killed += 1
                    cleared = lvl
                    continue
                fate = f"{'не одолел' if b.timeout else 'погиб от'} {name}"
            break
        print(f"LIFE {life}: {fate}; боссов {killed}/{len(fights)}, уровень {ses.hero.level}, "
              f"уроки {mind.lessons()}, эпизодов {mind.episodes}")
    mind.save()
    print(f"RESULT lives={args.lives} lessons={mind.lessons()} low_hp_empowered="
          f"{mind.preferred('empowered')} low_hp_plain={mind.preferred('plain')}")
    return 0


def add_arguments(ap) -> None:
    ap.add_argument("--boss", help="один босс (id из bosses.lua)")
    ap.add_argument("--level", type=int, help="уровень боя (по умолчанию - уровень босса в мире)")
    ap.add_argument("--class", dest="cls", default="warrior")
    ap.add_argument("--gear", default=",".join(DEFAULT_GEAR))
    ap.add_argument("--no-sorrow", action="store_true", help="без Печали берсерка")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1, help="первый seed (кампания: жизнь N - seed+N-1)")
    ap.add_argument("--potions", type=int, default=3)
    ap.add_argument("--campaign", action="store_true", help="реальная сессия с 1-го уровня")
    ap.add_argument("--lives", type=int, default=1, help="кампания: сколько жизней (память разума общая)")
    ap.add_argument("--no-save", action="store_true", help="не писать память разума в saves/")
    ap.add_argument("--trace", action="store_true", help="урон по способностям и состояния ИИ")
    ap.add_argument("--boss-points", type=float, help="очков к КАЖДОЙ характеристике босса за уровень (world.lua: 10)")
    ap.add_argument("--enemy-points", type=int, help="очков обычному врагу за уровень (world.lua: 10)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(ap)
    return run(ap.parse_args(argv))


def run(args) -> int:
    from src.gameplay.progression import override
    if args.boss_points is not None:
        override(boss_points_per_attribute=args.boss_points)
    if args.enemy_points is not None:
        override(enemy_points_per_level={"normal": args.enemy_points})
    from src.gameplay.world import world_plan
    plan = world_plan()
    fights = roster(plan)
    if args.boss:
        fights = [(b, lvl) for b, lvl in fights if b == args.boss] or [(args.boss, args.level or 1)]
    gear = tuple(g for g in args.gear.split(",") if g)
    if args.campaign:
        return campaign(fights, args, gear, plan)
    wins = total = 0
    for boss_id, lvl in fights:
        lvl = args.level or lvl
        bouts = [fight(boss_id, lvl, args.cls, gear, not args.no_sorrow, seed, record=True)
                 for seed in range(args.seed, args.seed + args.seeds)]
        w = sum(b.won for b in bouts)
        wins, total = wins + w, total + len(bouts)
        name = (plan.spec(boss_id) or {}).get("name", boss_id)
        tag = "WIN " if w == len(bouts) else ("LOSS" if w == 0 else "MIX ")
        print(_line(tag, bouts[0], name, f"{w}/{len(bouts)} lvl {lvl:2d}", args.trace))
    print(f"RESULT wins={wins}/{total} class={args.cls} sorrow={not args.no_sorrow} gear={','.join(gear)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
