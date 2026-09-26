"""Adaptation Runtime — спецификация Махораги для движка (Махорага, Части 1-6).

Модуль реализует runtime-фичи из справочника:
    * SignatureHasher / PhenomenonRegistry — уникальные подписи феноменов
      ("physical:cleave", "mana:blue", "soul:split_soul");
    * AdaptationState — колесо (wheel 0..8), прогресс по феноменам, порог,
      выученные техники, метаданные (first_seen/last_seen/sources);
    * FactionManager — фракции и отношения (feral hostile ко всем остальным);
    * AggroManager — режимы агрессии / правила выбора цели (TargetingSpec);
    * EscalationManager — per-wheel модификаторы + пороги (thresholds) + true form.

Всё сериализуемо в чистые словари (JSON-safe) — память переживает сейвы
(MemoryConfig.persist_across_combat). Состояние юнита живёт в unit.external
("mahoraga"), чтобы не ломать совместимость Unit/EntityState.

Форма Op расширена полями: phenomenon/threshold/faction/aggro_mode/targeting/
wheel_delta/escalation_delta/permanent/memory_key/exclude_self/exclude_owner/max_stacks
(см. src/effects/schema.py OP_FIELDS и lua_content/schema.lua).
"""

from __future__ import annotations

import json
from typing import Any, Callable, ClassVar, Dict, List, Optional

WHEEL_MAX_DEFAULT = 8

# ------------------------------------------------------------------ signatures


class SignatureHasher:
    """Генерация уникальной подписи феномена из ctx.damage.

    granularity:
        exact   -> damage_type:technique_id        (Cleave != Dismantle)
        type    -> damage_type                     (вся физика — один феномен)
        family  -> registry family of technique    (slash-техники — один феномен)
    combine="distinct" — составные флаги (true_damage+imaginary_mass) дают
    отдельную подпись только если они меняют technique_id/damage_type;
    ложные адаптации исключаются тем, что источник НЕ входит в id (иначе
    Махорага адаптировался бы к каждому противнику заново).
    """

    def __init__(self, families: Optional[Dict[str, str]] = None):
        self.families = dict(families or {})

    def register_family(self, technique_id: str, family: str) -> None:
        self.families[technique_id] = family

    def signature(self, damage_ctx: Dict[str, Any],
                  granularity: str = "exact") -> str:
        dt = str(damage_ctx.get("damage_type") or "physical")
        tech = damage_ctx.get("technique_id") or damage_ctx.get("skill_id")
        if granularity == "type":
            return dt
        if granularity == "family":
            fam = self.families.get(str(tech)) if tech else None
            return f"{dt}:{fam}" if fam else dt
        return f"{dt}:{tech or 'basic'}"


class PhenomenonRegistry:
    """Реестр известных феноменов (namespace "signatures" из справочника)."""

    def __init__(self, entries: Optional[Dict[str, Dict[str, Any]]] = None):
        self._entries: Dict[str, Dict[str, Any]] = dict(entries or {})

    def register(self, phenomenon_id: str, **spec: Any) -> None:
        self._entries[phenomenon_id] = spec

    def get(self, phenomenon_id: str) -> Optional[Dict[str, Any]]:
        return self._entries.get(phenomenon_id)

    def counterable_by(self, phenomenon_id: str) -> List[str]:
        return list((self._entries.get(phenomenon_id) or {}).get("counterable_by", []))

    @property
    def names(self) -> List[str]:
        return sorted(self._entries)


# ------------------------------------------------------------------ adaptation state


class AdaptationState:
    """Колесо + память адаптаций одного носителя (метрики mahoraga.*)."""

    def __init__(self, wheel_max: int = WHEEL_MAX_DEFAULT,
                 threshold_hits: int = 1, exclude_self: bool = True,
                 exclude_owner: bool = True):
        self.wheel_max = int(wheel_max)
        self.threshold_hits = max(1, int(threshold_hits))
        self.exclude_self = exclude_self
        self.exclude_owner = exclude_owner
        self.wheel = 0                                   # число адаптаций 0..wheel_max
        self.progress: Dict[str, int] = {}               # signature -> hits
        self.known_phenomena: List[str] = []             # адаптированные подписи
        self.adaptation_power: Dict[str, float] = {}     # signature -> pct immunity
        self.learned_techniques: List[str] = []          # украденные техники
        self.sources: Dict[str, str] = {}                # signature -> source_id
        self.first_seen_tick: Dict[str, int] = {}
        self.last_seen_tick: Dict[str, int] = {}
        self.total_damage: Dict[str, float] = {}         # signature -> суммарный урон
        self.kill_count = 0
        self.escape_count = 0
        self.true_form = False
        self.last_damage_signature: str = ""

    # ---- производные метрики (ЧАСТЬ 1.3)

    @property
    def total_immunities(self) -> int:
        return len(self.known_phenomena)

    @property
    def remaining_slots(self) -> int:
        return max(0, self.wheel_max - self.wheel)

    @property
    def at_max(self) -> bool:
        return self.wheel >= self.wheel_max

    @property
    def damage_multiplier(self) -> float:
        return 1.0 + self.wheel * 0.15

    @property
    def resist_multiplier(self) -> float:
        return 1.0 + self.wheel * 0.05

    @property
    def regen_multiplier(self) -> float:
        return 1.0 + self.wheel * 0.10

    @property
    def threat_level(self) -> float:
        return sum(self.adaptation_power.values()) / max(1, self.wheel_max) / 100.0

    # ---- ядро: observe/adapt

    def _record(self, signature: str, tick: int, amount: float) -> None:
        """Учёт удара по подписи: последняя подпись, тик и суммарный урон."""
        self.last_damage_signature = signature
        self.last_seen_tick[signature] = tick
        self.total_damage[signature] = self.total_damage.get(signature, 0.0) + amount

    def excluded(self, source_id: Optional[str], owner_id: Optional[str], self_id: Optional[str]) -> bool:
        """Удар не считается феноменом: «не адаптируется к себе» (exclude_self) и не к хозяину (exclude_owner)."""
        if not source_id:
            return False
        return bool((self.exclude_self and source_id == self_id) or (self.exclude_owner and source_id == owner_id))

    def observe(self, signature: str, *, tick: int = 0, amount: float = 0.0,
                source_id: Optional[str] = None, excluded: bool = False) -> bool:
        """Зарегистрировать попадание феномена. Возвращает True, если произошла
        АДАПТАЦИЯ (порог hits достигнут, слот колеса свободен). excluded - вызывающий уже проверил `excluded(...)`:
        по такому источнику новая адаптация не копится (известный феномен всё равно учитывается)."""
        if signature in self.known_phenomena:
            self._record(signature, tick, amount)
            return False
        if excluded:
            return False
        self._record(signature, tick, amount)
        self.first_seen_tick.setdefault(signature, tick)
        if source_id:
            self.sources[signature] = source_id
        hits = self.progress.get(signature, 0) + 1
        self.progress[signature] = hits
        if hits < self.threshold_hits or self.at_max:
            return False
        self.known_phenomena.append(signature)
        self.adaptation_power[signature] = 100.0            # max_immunity pct=100 (канон)
        self.wheel += 1
        return True

    def learn(self, technique_id: Optional[str]) -> None:
        if technique_id and technique_id not in self.learned_techniques:
            self.learned_techniques.append(str(technique_id))

    def unadapt(self, signature: str) -> bool:
        """kind=unadapt: сброс одной адаптации (освобождает слот колеса)."""
        if signature in self.known_phenomena:
            self.known_phenomena.remove(signature)
            self.adaptation_power.pop(signature, None)
            self.progress.pop(signature, None)
            self.wheel = max(0, self.wheel - 1)
            return True
        return False

    def reset(self) -> None:
        """kind=reset_adaptation: полный сброс колеса."""
        keep_true_form = self.true_form                     # истинная форма необратима без deescalate
        self.__init__(wheel_max=self.wheel_max, threshold_hits=self.threshold_hits,
                      exclude_self=self.exclude_self, exclude_owner=self.exclude_owner)
        self.true_form = keep_true_form

    # ---- сериализация памяти (MemoryRuntime)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wheel_max": self.wheel_max, "threshold_hits": self.threshold_hits,
            "exclude_self": self.exclude_self, "exclude_owner": self.exclude_owner,
            "wheel": self.wheel, "progress": self.progress,
            "known_phenomena": self.known_phenomena,
            "adaptation_power": self.adaptation_power,
            "learned_techniques": self.learned_techniques,
            "sources": self.sources, "first_seen_tick": self.first_seen_tick,
            "last_seen_tick": self.last_seen_tick, "total_damage": self.total_damage,
            "kill_count": self.kill_count, "escape_count": self.escape_count,
            "true_form": self.true_form,
            "last_damage_signature": self.last_damage_signature,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AdaptationState":
        st = cls(wheel_max=d.get("wheel_max", WHEEL_MAX_DEFAULT),
                 threshold_hits=d.get("threshold_hits", 1),
                 exclude_self=d.get("exclude_self", True),
                 exclude_owner=d.get("exclude_owner", True))
        for k, v in d.items():
            if k in ("wheel_max", "threshold_hits", "exclude_self", "exclude_owner"):
                continue
            setattr(st, k, v)
        return st

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def state_of(unit: Any) -> AdaptationState:
    """Адаптер: состояние Махораги живёт в unit.external["mahoraga"]."""
    ext = getattr(unit, "external", None)
    if ext is None:
        ext = {}
        unit.external = ext
    st = ext.get("mahoraga")
    if isinstance(st, dict):
        st = AdaptationState.from_dict(st)
    elif st is None:
        st = AdaptationState()
    ext["mahoraga"] = st
    return st


# ------------------------------------------------------------------ factions


class FactionManager:
    """Отношения сторон (hostile/neutral/ally), мульти-фракции, динамика."""

    DEFAULT_RELATIONS: ClassVar[Dict[str, Dict[str, str]]] = {
        "feral": {"feral": "ally", "player": "hostile", "enemy": "hostile",
                  "neutral": "hostile", "ally": "hostile", "boss": "hostile"},
        "player": {"player": "ally", "enemy": "hostile", "feral": "hostile",
                   "neutral": "neutral", "boss": "hostile", "ally": "ally"},
        "enemy": {"enemy": "ally", "player": "hostile", "feral": "hostile",
                  "neutral": "neutral", "boss": "ally", "ally": "hostile"},
        "boss": {"boss": "ally", "player": "hostile", "enemy": "ally",
                 "feral": "hostile", "neutral": "hostile", "ally": "hostile"},
        "neutral": {"neutral": "ally", "feral": "hostile"},
        "ally": {"ally": "ally", "player": "ally", "enemy": "hostile",
                 "feral": "hostile", "boss": "hostile", "neutral": "neutral"},
    }

    def __init__(self, relations: Optional[Dict[str, Dict[str, str]]] = None):
        self.relations = {f: dict(r) for f, r in
                          (relations or self.DEFAULT_RELATIONS).items()}
        self.unit_factions: Dict[str, List[str]] = {}
        self.dynamic: Dict[tuple, str] = {}                # (a,b) -> relation override

    def declare(self, faction: str, relations: Dict[str, str]) -> None:
        self.relations.setdefault(faction, {}).update(relations)

    def set_faction(self, unit_id: str, *factions: str) -> None:
        self.unit_factions[unit_id] = list(dict.fromkeys(factions))

    def factions_of(self, unit_id: str) -> List[str]:
        return self.unit_factions.get(unit_id, [])

    def relation(self, a_id: str, b_id: str) -> str:
        ov = self.dynamic.get((a_id, b_id)) or self.dynamic.get((b_id, a_id))
        if ov:
            return ov
        fa, fb = self.factions_of(a_id), self.factions_of(b_id)
        if not fa or not fb:
            return "neutral"
        if set(fa) & set(fb):
            return "ally"
        rels = {self.relations.get(x, {}).get(y, "neutral") for x in fa for y in fb}
        if "hostile" in rels:
            return "hostile"
        if "ally" in rels:
            return "ally"
        return "neutral"

    def is_hostile(self, a_id: str, b_id: str) -> bool:
        return self.relation(a_id, b_id) == "hostile"

    def override(self, a_id: str, b_id: str, relation: str) -> None:
        self.dynamic[(a_id, b_id)] = relation              # Dynamic Relations


# ------------------------------------------------------------------ aggro / targeting


class AggroManager:
    """Aggro-таблица + выбор цели по TargetingSpec (nearest/lower_hp/...)."""

    MODES: ClassVar[frozenset] = frozenset({"nearest", "farthest", "lowest_hp", "highest_threat", "random"})

    def __init__(self, rng: Optional[Callable[[int], int]] = None):
        self.modes: Dict[str, Dict[str, Any]] = {}         # aggro_mode id -> spec
        self.current_target: Dict[str, Optional[str]] = {} # unit_id -> target_id
        self.threat: Dict[tuple, float] = {}               # (attacker,victim) -> dmg
        self._rng = rng or (lambda n: 0)

    def register_mode(self, mode_id: str, **spec: Any) -> None:
        self.modes[mode_id] = spec

    def add_threat(self, attacker_id: str, victim_id: str, amount: float) -> None:
        key = (attacker_id, victim_id)
        self.threat[key] = self.threat.get(key, 0.0) + amount

    def candidates(self, unit_id: str, units: Dict[str, Any],
                   factions: FactionManager, filter_: str = "hostile") -> List[str]:
        out = []
        for uid, u in units.items():
            if uid == unit_id or not getattr(u, "alive", True):
                continue
            rel = factions.relation(unit_id, uid)
            if filter_ == "any" or (filter_ == "hostile" and rel == "hostile") \
               or (filter_ == "allies" and rel == "ally"):
                out.append(uid)
        return out

    def select(self, unit_id: str, units: Dict[str, Any], factions: FactionManager,
               mode: str = "nearest_any", positions: Optional[Dict[str, Any]] = None
               ) -> Optional[str]:
        spec = self.modes.get(mode, {})
        strategy = spec.get("select", "nearest")
        cands = self.candidates(unit_id, units, factions, spec.get("filter", "hostile"))
        if not cands:
            return None
        if strategy == "random":
            return cands[self._rng(len(cands)) % len(cands)]
        if strategy == "lowest_hp":
            return min(cands, key=lambda i: getattr(units[i], "current_hp", 0.0))
        if strategy == "highest_threat":
            return max(cands, key=lambda i: self.threat.get((unit_id, i), 0.0))
        by_distance = self._by_distance(strategy, unit_id, cands, positions or {})
        return cands[0] if by_distance is None else by_distance

    @staticmethod
    def _by_distance(strategy: str, unit_id: str, cands: List[str], pos: Dict[str, Any]) -> Optional[str]:
        """nearest / farthest по позициям; None - позиций нет (или стратегия другая): выбор остаётся первому кандидату."""
        me = pos.get(unit_id)
        if strategy not in ("nearest", "farthest") or me is None or not all(p in pos for p in cands):
            return None
        dist = lambda i: ((pos[i][0] - me[0]) ** 2 + (pos[i][1] - me[1]) ** 2) ** 0.5  # noqa: E731
        return (min if strategy == "nearest" else max)(cands, key=dist)

    def retarget(self, unit_id: str, target_id: Optional[str]) -> None:
        self.current_target[unit_id] = target_id

    def clear(self, unit_id: str) -> None:
        self.current_target[unit_id] = None
        for k in [k for k in self.threat if k[0] == unit_id]:
            del self.threat[k]


# ------------------------------------------------------------------ escalation / wheel


class EscalationManager:
    """Колесо: per-wheel модификаторы + пороговые события + true form."""

    DEFAULT_PER_WHEEL: ClassVar[Dict[str, float]] = {
        "strength": 0.15, "aspd": 0.10, "move_speed": 0.05,
        "resist_all": 0.03, "regen": 0.10,
    }

    def __init__(self, per_wheel: Optional[Dict[str, float]] = None,
                 thresholds: Optional[List[Dict[str, Any]]] = None):
        self.per_wheel = dict(per_wheel or self.DEFAULT_PER_WHEEL)
        # thresholds: [{at: N, ops: [...]}] — из EscalationConfig
        self.thresholds = sorted(thresholds or [], key=lambda t: t.get("at", 0))
        self._fired: set = set()

    def modifiers(self, wheel: int) -> Dict[str, float]:
        """Пересчёт множителей статов от текущего колеса (Per-wheel Modifier)."""
        return {stat: 1.0 + rate * wheel for stat, rate in self.per_wheel.items()}

    def crossed(self, state: AdaptationState, prev_wheel: int) -> List[Dict[str, Any]]:
        """Какие пороги пересечены при переходе prev_wheel -> state.wheel."""
        fired_now = []
        for th in self.thresholds:
            at = int(th.get("at", 0))
            if prev_wheel < at <= state.wheel:
                fired_now.append(th)
        return fired_now

    def trigger_true_form(self, state: AdaptationState) -> bool:
        if state.at_max and not state.true_form:
            state.true_form = True
            return True
        return False

    def deescalate(self, state: AdaptationState, delta: int = 1) -> None:
        """Откат эскалации (для rewind/Balefire: мир откатился — колесо тоже)."""
        for _ in range(max(0, delta)):
            if state.known_phenomena:
                state.unadapt(state.known_phenomena[-1])
        if not state.at_max:
            state.true_form = False


# ------------------------------------------------------------------ hub


class AdaptationManager:
    """Единая точка входа runtime-адаптации (подключается к бою/дуэли)."""

    def __init__(self, hasher: Optional[SignatureHasher] = None,
                 phenomena: Optional[PhenomenonRegistry] = None,
                 factions: Optional[FactionManager] = None,
                 aggro: Optional[AggroManager] = None,
                 escalation: Optional[EscalationManager] = None):
        self.hasher = hasher or SignatureHasher()
        self.phenomena = phenomena or PhenomenonRegistry(DEFAULT_SIGNATURES)
        self.factions = factions or FactionManager()
        self.aggro = aggro or AggroManager()
        self.escalation = escalation or EscalationManager()

    def on_damage(self, victim_unit: Any, damage_ctx: Dict[str, Any], *,
                  tick: int = 0, self_id: Optional[str] = None,
                  owner_id: Optional[str] = None) -> Dict[str, Any]:
        """Ядро: попадание -> подпись -> observe -> результат адаптации.

        Возвращает {"signature", "adapted", "wheel", "events": [ops...]} —
        вызывающий слой применяет ops (rotate_wheel/immune/learn/escalate)
        и пишет событие в Timeline.
        """
        st = state_of(victim_unit)
        sig = self.hasher.signature(damage_ctx,
                                    granularity=damage_ctx.get("granularity", "exact"))
        prev = st.wheel
        source_id = damage_ctx.get("source_id")
        adapted = st.observe(sig, tick=tick, amount=float(damage_ctx.get("amount", 0.0)), source_id=source_id,
                             excluded=st.excluded(source_id, owner_id, self_id))
        events: List[Dict[str, Any]] = []
        if adapted:
            tech = damage_ctx.get("technique_id")
            if tech:
                st.learn(str(tech))
                events.append({"kind": "learn_technique", "from": str(tech)})
            events.append({"kind": "rotate_wheel", "value": {"flat": 1}})
            events.append({"kind": "escalate", "value": {"flat": 1}})
            events.append({"kind": "immune", "damage_type": sig,
                           "value": {"pct": 100}, "permanent": True})
            for th in self.escalation.crossed(st, prev):
                events.extend(th.get("ops", []))
            if self.escalation.trigger_true_form(st):
                events.append({"kind": "trigger_true_form"})
        return {"signature": sig, "adapted": adapted, "wheel": st.wheel,
                "state": st, "events": events}


# предзаполненные подписи феноменов (ЧАСТЬ 6 справочника)
DEFAULT_SIGNATURES: Dict[str, Dict[str, Any]] = {
    "physical:cleave": {"damage_type": "physical", "technique_id": "cleave",
                        "family": "slash",
                        "counterable_by": ["unknown_phenomenon", "adapt"]},
    "physical:dismantle": {"damage_type": "physical", "technique_id": "dismantle",
                           "family": "slash",
                           "counterable_by": ["unknown_phenomenon", "adapt"]},
    "mana:blue": {"damage_type": "mana", "technique_id": "blue", "family": "space",
                  "counterable_by": ["unknown_phenomenon", "adapt"]},
    "mana:red": {"damage_type": "mana", "technique_id": "red", "family": "space",
                 "counterable_by": ["unknown_phenomenon", "adapt"]},
    "soul:split_soul": {"damage_type": "soul", "technique_id": "split_soul",
                        "family": "soul",
                        "counterable_by": ["unknown_phenomenon", "adapt"]},
    "none:infinity": {"damage_type": "none", "technique_id": "infinity",
                      "family": "space_defense",
                      "counterable_by": ["unknown_phenomenon", "adapt",
                                         "bypass_infinity"]},
    "true:world_cut": {"damage_type": "true", "technique_id": "world_cut",
                       "family": "concept",
                       "counterable_by": ["unknown_phenomenon", "adapt"]},
}
