"""Timeline / Event Log — фундамент движка эффектов (Фаза 1, п. 5.1.1).

Без него не работают: Balefire / Time Leap / Made in Heaven (откат),
Contessa / Yhwach / Tserriednich (предикция через симуляцию на ветках),
God Hand / GER (граф причинности), любой дебаг и replay.

Модель:
    Timeline  — append-only журнал событий с указателем head (может стоять в прошлом),
                снапшотами состояний мира, undo-цепочкой и форком веток.
    Event     — сериализуемая запись: tick, source, target, kind, data,
                causals/effects (граф причинности), reversible.
                undo-функция НЕ сериализуется — она выдаётся UndoProvider'ом
                по событию при откате (сериализуемость журнала обязательна,
                см. правило №7 архитектуры и docs/EFFECT_SCHEMA.md).

Ключевые инварианты:
    * events — плоский список, id == индекс; head двигается назад/вперёд,
      журнал при этом не переписывается (append-only), кроме случая commit
      из прошлого (ветка «стирает» нереализованное будущее — time remnant).
    * rewind приоритетно использует ближайший снапшот (дёшево),
      иначе идёт undo-цепочкой по событиям назад (Balefire/Time Leap),
      иначе — чистый move-head (мир пересчитывается из applied()).
    * fork даёт изолированную ветку со СВОИМ продолжением времени — база для
      параллельных вселенных, симуляций предикции и rollback-неткода.

Интеграция: Timeline.attach_event_system(es) подписывается на
src.core.event_system.EventSystem и пишет игровые события в журнал
(kind = "es." + имя события, данные EventData переносятся в data).

Пример:
    tl = Timeline()
    e = tl.commit(Event(source="p1", target="e1", kind="damage", data={"amount": 30}))
    snap = tl.capture_snapshot(world_serialize)   # снимок «до»
    ...
    tl.rewind(e.tick - 1, restore_fn=world_restore)
    sim = tl.fork("contessa_branch_1")            # симуляция поверх log
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional


# --------------------------------------------------------------------------
# Event
# --------------------------------------------------------------------------

@dataclass
class Event:
    """Одна запись журнала. Полностью сериализуема (JSON-safe).

    tick заполняется Timeline при commit (если передано 0/None);
    id назначается журналом (индекс в списке событий).
    """

    tick: int = 0
    source: str = ""                      # EntityRef: id источника
    target: str = ""                      # EntityRef: id цели ("" — глобальное)
    kind: str = ""                        # "damage" | "heal" | "cast" | "move" | "death" | "kill" | ...
    data: Dict[str, Any] = field(default_factory=dict)
    causals: List[int] = field(default_factory=list)   # event ids, вызвавшие это
    effects: List[int] = field(default_factory=list)   # event ids, порождённые этим
    reversible: bool = True
    id: int = -1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Event":
        keys = {"tick", "source", "target", "kind", "data",
                "causals", "effects", "reversible", "id"}
        return Event(**{k: v for k, v in d.items() if k in keys})


# --------------------------------------------------------------------------
# Snapshot
# --------------------------------------------------------------------------

@dataclass
class StateSnapshot:
    """Снимок состояния мира на момент ПОСЛЕ события end_id (-1 = начало времён).

    state — произвольный сериализуемый dict (обычно {entity_id → serialized entity}).
    """
    tick: int
    end_id: int
    state: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# UndoProvider: по событию возвращает функцию отмены либо None.
UndoProvider = Callable[[Event], Optional[Callable[[], None]]]


class TimelineError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------

class Timeline:
    """Append-only event log + снапшоты + ветвление + граф причинности."""

    def __init__(self, name: str = "main", parent: Optional["Timeline"] = None,
                 start_events: Optional[List[Event]] = None,
                 start_head: int = -1, start_tick: int = 0):
        self.name = name
        self.parent = parent
        self.events: List[Event] = list(start_events or [])   # индекс == id
        self.head: int = start_head       # id последнего «произошедшего» события (-1 = ничего)
        self.tick: int = start_tick       # логическое время за head
        self.snapshots: Dict[int, StateSnapshot] = {}         # tick → snapshot
        self.branches: Dict[str, "Timeline"] = {}
        self._undo_provider: Optional[UndoProvider] = None
        self._subs: List[Callable[[Event], None]] = []

    # ---------------- undo ----------------

    def set_undo_provider(self, provider: Optional[UndoProvider]) -> None:
        """provider(event) -> callable|None. Вызывается при rewind по undo-цепочке."""
        self._undo_provider = provider

    # ---------------- запись ----------------

    def commit(self, event: Event) -> Event:
        """Зафиксировать событие за head.

        Если head стоит в прошлом, нереализованное «будущее» этой ветки
        стирается (time remnant / Steins;Gate). Возвращает то же событие
        с проставленными id/tick.
        """
        if self.head < len(self.events) - 1:
            del self.events[self.head + 1:]
        self.tick += 1
        event.tick = self.tick
        event.id = len(self.events)
        self.events.append(event)
        self.head = event.id
        for cb in self._subs:
            cb(event)
        return event

    # ---------------- причинность ----------------

    def link_causal(self, cause: Event, effect: Event) -> None:
        """cause → effect (God Hand / GER / дебаг). Идемпотентно."""
        if cause.id < 0 or effect.id < 0:
            raise TimelineError("link_causal: events must be committed")
        if cause.id not in effect.causals:
            effect.causals.append(cause.id)
        if effect.id not in cause.effects:
            cause.effects.append(effect.id)

    def causes_of(self, event: Event) -> List[Event]:
        return [self.events[i] for i in event.causals if 0 <= i < len(self.events)]

    def effects_of(self, event: Event) -> List[Event]:
        return [self.events[i] for i in event.effects if 0 <= i < len(self.events)]

    def ancestors(self, event: Event) -> List[Event]:
        """Транзитивное замыкание причин (без самого события; циклы безопасны)."""
        seen: set = set()
        out: List[Event] = []
        stack = list(event.causals)
        while stack:
            i = stack.pop()
            if i in seen or i == event.id or not (0 <= i < len(self.events)):
                continue
            seen.add(i)
            ev = self.events[i]
            out.append(ev)
            stack.extend(ev.causals)
        return out

    # ---------------- чтение ----------------

    def applied(self) -> List[Event]:
        """События, «произошедшие» с точки зрения текущей позиции head."""
        return self.events[:self.head + 1]

    def pending(self) -> List[Event]:
        """События будущего относительно head (видны предикции/отладке)."""
        return self.events[self.head + 1:]

    def query(self, kind: Optional[str] = None, source: Optional[str] = None,
              target: Optional[str] = None, up_to_head: bool = True) -> List[Event]:
        seq = self.applied() if up_to_head else self.events
        out = []
        for e in seq:
            if kind is not None and e.kind != kind:
                continue
            if source is not None and e.source != source:
                continue
            if target is not None and e.target != target:
                continue
            out.append(e)
        return out

    # ---------------- снапшоты ----------------

    def capture_snapshot(self,
                         state_fn: Optional[Callable[[], Dict[str, Any]]] = None
                         ) -> StateSnapshot:
        """Снять состояние мира на текущий head.

        state_fn() -> сериализуемый dict (сериализация Entity/World — Фаза 1, п.2).
        """
        snap = StateSnapshot(tick=self.tick, end_id=self.head,
                             state=dict(state_fn()) if state_fn else {})
        self.snapshots[self.tick] = snap
        return snap

    def snapshot(self, tick: int) -> Optional[StateSnapshot]:
        """Ближайший снапшот с snap.tick <= min(tick, время текущего head)."""
        limit = self.events[self.head].tick if self.head >= 0 else 0
        best: Optional[StateSnapshot] = None
        for t, s in self.snapshots.items():
            if s.tick <= min(tick, limit) and (best is None or s.tick > best.tick):
                best = s
        return best

    def restore(self, snap: StateSnapshot,
                restore_fn: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        """Применить состояние снапшота и переставить head на его конец."""
        if restore_fn is not None:
            restore_fn(snap.state)
        self.head = snap.end_id
        self.tick = snap.tick

    # ---------------- откат / прокрутка ----------------

    def _head_for_tick(self, to_tick: int) -> int:
        h = -1
        for e in self.events:
            if e.tick <= to_tick:
                h = e.id
            else:
                break
        return h

    def rewind(self, to_tick: int,
               restore_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
               use_undo: bool = True) -> int:
        """Откатить мир на to_tick. Возвращает число «перестающих быть» событий.

        Стратегия:
          1) ближайший снапшот (дёшево, точечно) — если передан restore_fn и снапшот есть;
          2) undo-цепочка по событиям назад (Balefire/Time Leap) — если есть
             provider и все откатываемые события reversible;
          3) чистый move-head — мир обязан сам пересчитать состояние из applied().
        Журнал append-only: события НЕ удаляются, двигается только head.
        """
        if to_tick > self.tick:
            raise TimelineError(
                f"rewind forward not supported ({self.tick} -> {to_tick}); use fast_forward")
        target_head = self._head_for_tick(to_tick)
        n_cancel = self.head - target_head
        if n_cancel <= 0:
            self.tick = to_tick
            return 0

        snap = None if restore_fn is None else self.snapshot(to_tick)
        if snap is not None and snap.end_id <= target_head:
            # снапшот не новее цели: восстановить до него, остальное — move head
            self.restore(snap, restore_fn)
            self.head = target_head
            self.tick = (self.events[target_head].tick
                         if target_head >= 0 else to_tick)
            return n_cancel

        if use_undo and self._undo_provider is not None:
            undone = 0
            while self.head > target_head:
                ev = self.events[self.head]
                if not ev.reversible:
                    raise TimelineError(f"event {ev.id} ({ev.kind}) is not reversible")
                fn = self._undo_provider(ev)
                if fn is None:
                    raise TimelineError(f"no undo for event {ev.id} ({ev.kind})")
                fn()
                self.head -= 1
                undone += 1
            self.tick = (self.events[self.head].tick if self.head >= 0
                         else max(0, to_tick))
            return undone

        # move-head без изменения мира
        self.head = target_head
        self.tick = (self.events[target_head].tick if target_head >= 0
                     else max(0, to_tick))
        return n_cancel

    def fast_forward(self, to_tick: Optional[int] = None) -> int:
        """Прокрутить head вперёд по уже записанным событиям (replay позиции)."""
        if not self.events:
            return 0
        target = self.events[-1].tick if to_tick is None else to_tick
        h = self._head_for_tick(target)
        n = max(0, h - self.head)
        self.head = h
        self.tick = self.events[h].tick if h >= 0 else 0
        return n

    # ---------------- replay / симуляция ----------------

    def replay(self, frm: int = 0, to: Optional[int] = None,
               on_event: Optional[Callable[[Event], None]] = None) -> List[Event]:
        """События диапазона тиков [frm, to] (для симуляции/предпросмотра)."""
        out = [e for e in self.events if e.tick >= frm and (to is None or e.tick <= to)]
        if on_event is not None:
            for e in out:
                on_event(e)
        return out

    def simulate(self, branch_name: str) -> "Timeline":
        """Ветка для «взгляда в будущее»: коммить в неё можно, реальный мир — нет.

        Это база предикции (Contessa/Yhwach/Tserriednich) и планирования:
        форк → прогоны гипотетических событий → сравнение исходов → discard/merge_back.
        """
        return self.fork(branch_name)

    # ---------------- ветвление ----------------

    def fork(self, branch_name: str) -> "Timeline":
        """Изолированная ветка, наследующая историю до текущего head.

        Ветка продолжает время от собственного head (tick-часы независимы),
        поэтому будущие события родителя — «параллельная вселенная», а не прошлое.
        """
        if branch_name in self.branches:
            raise TimelineError(f"branch '{branch_name}' already exists")
        base = self.applied()
        br = Timeline(name=f"{self.name}/{branch_name}", parent=self,
                      start_events=[Event.from_dict(e.to_dict()) for e in base],
                      start_head=len(base) - 1, start_tick=self.tick)
        br.set_undo_provider(self._undo_provider)
        self.branches[branch_name] = br
        return br

    def merge_back(self, branch: "Timeline") -> List[Event]:
        """Перенести события ветки, выходящие за текущее время, в этот журнал."""
        moved = []
        for e in branch.events:
            if e.tick > self.tick:
                moved.append(self.commit(Event.from_dict({
                    k: v for k, v in e.to_dict().items() if k != "id"})))
        return moved

    # ---------------- сериализация ----------------

    def to_json(self) -> str:
        payload = {
            "name": self.name,
            "head": self.head,
            "tick": self.tick,
            "events": [e.to_dict() for e in self.events],
            "snapshots": {str(t): {"tick": s.tick, "end_id": s.end_id, "state": s.state}
                          for t, s in self.snapshots.items()},
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def from_json(text: str) -> "Timeline":
        payload = json.loads(text)
        tl = Timeline(name=payload.get("name", "main"),
                      start_events=[Event.from_dict(d) for d in payload["events"]])
        tl.head = payload.get("head", len(tl.events) - 1)
        tl.tick = payload.get("tick", tl.events[-1].tick if tl.events else 0)
        for t, sd in payload.get("snapshots", {}).items():
            tl.snapshots[int(t)] = StateSnapshot(tick=sd["tick"], end_id=sd["end_id"],
                                                 state=sd.get("state", {}))
        return tl

    # ---------------- интеграция с EventSystem ----------------

    def attach_event_system(self, event_system, kinds: Optional[List[str]] = None,
                            kind_prefix: str = "es.") -> int:
        """Автозапись событий src.core.event_system.EventSystem в журнал.

        kind = kind_prefix + event_type; source/target/данные берутся из EventData.

        ВНИМАНИЕ: EventSystem (blinker-обёртка) не поддерживает глобальный
        wildcard-подход "*": сигнал создаётся по конкретному имени. Поэтому
        подписка оформляется на переданный список имён `kinds` (по умолчанию —
        стандартный боевой набор). Возвращает число подписок.

        Стандартные имена событий совпадают с OP_KINDS/событиями src/effects
        (см. docs/EFFECT_SCHEMA.md): damage, heal, cast, death, kill, move.
        """
        if kinds is None:
            kinds = ["damage", "heal", "cast", "death", "kill", "move"]

        def make_hook(event_type):
            def hook(sender, ed):
                data = dict(getattr(ed, "event_data", {}) or {})
                self.commit(Event(
                    source=str(data.get("source", getattr(ed, "source", ""))),
                    target=str(data.get("target", "")),
                    kind=kind_prefix + str(event_type),
                    data=data,
                ))
            return hook

        for et in kinds:
            event_system.on(et, make_hook(et), subscriber_id=f"timeline:{self.name}")
        return len(kinds)

    def subscribe_local(self, callback: Callable[[Event], None]) -> None:
        """Подписка на новые события этого журнала (реактивный слой/триггеры)."""
        self._subs.append(callback)
