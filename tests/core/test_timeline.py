"""Тесты Timeline / Event Log — фундамента движка эффектов."""

import json

import pytest

from src.core.timeline import Event, StateSnapshot, Timeline, TimelineError


def _tl(n=0):
    tl = Timeline()
    for i in range(n):
        tl.commit(Event(tick=0, source=f"s{i}", target=f"t{i}", kind="damage",
                        data={"amount": 10 + i}))
    return tl


class TestCommit:
    def test_append_only_ids_and_ticks(self):
        tl = _tl(3)
        assert [e.id for e in tl.events] == [0, 1, 2]
        assert [e.tick for e in tl.events] == [1, 2, 3]
        assert tl.head == 2 and tl.tick == 3

    def test_head_in_past_then_commit_truncates_future(self):
        tl = _tl(5)
        tl.rewind(2, use_undo=False)          # head в прошлом
        assert len(tl.pending()) == 3
        e = tl.commit(Event(kind="cast"))     # «будущее» стирается (time remnant)
        assert len(tl.events) == 3            # 2 старых + новый
        assert e.id == 2 and e.tick == 3
        assert tl.pending() == []


class TestCausality:
    def test_link_and_queries(self):
        tl = _tl(2)
        a, b = tl.events[0], tl.events[1]
        tl.link_causal(a, b)
        assert b.causals == [a.id] and a.effects == [b.id]
        assert tl.causes_of(b) == [a]
        assert tl.effects_of(a) == [b]

    def test_ancestors_transitive_no_cycles(self):
        tl = _tl(4)
        e0, e1, e2, e3 = tl.events
        tl.link_causal(e0, e1)
        tl.link_causal(e1, e2)
        tl.link_causal(e2, e3)
        tl.link_causal(e3, e0)                # цикл — не должно зациклить
        anc = tl.ancestors(e3)
        assert {e.id for e in anc} == {0, 1, 2}


class TestQuery:
    def test_filter_by_kind_target(self):
        tl = _tl(3)
        assert len(tl.query(kind="damage", target="t1")) == 1
        assert len(tl.query(source="s9")) == 0

    def test_respects_head(self):
        tl = _tl(4)
        tl.rewind(2, use_undo=False)
        assert len(tl.query()) == 2                       # только applied
        assert len(tl.query(up_to_head=False)) == 4       # весь журнал


class TestSnapshotsAndRewind:
    def test_snapshot_restore_roundtrip(self):
        world = {"hp": {"a": 100}}
        tl = Timeline()
        tl.capture_snapshot(lambda: {"hp": dict(world["hp"])})  # снимок на tick 0
        tl.commit(Event(kind="damage", data={"amount": 30}))
        world["hp"]["a"] = 70                                   # мир изменился
        snap = tl.snapshot(0)
        assert snap is not None and snap.end_id == -1
        tl.restore(snap, lambda st: world.update(st))
        assert world["hp"]["a"] == 100 and tl.head == -1 and tl.tick == 0

    def test_rewind_prefers_snapshot(self):
        world = {"hp": 100}
        tl = Timeline()
        tl.capture_snapshot(lambda: dict(world))          # tick 0
        for amt in (10, 20):
            tl.commit(Event(kind="damage", data={"amount": amt}))
            world["hp"] -= amt
        # undo-провайдер «испорченный» — если rewind пойдёт по нему, тест упадёт
        tl.set_undo_provider(lambda ev: (_ for _ in ()).throw(AssertionError("undo used")))
        n = tl.rewind(0, restore_fn=lambda st: world.update(st))
        assert n == 2 and world["hp"] == 100 and tl.head == -1 and tl.tick == 0

    def test_rewind_uses_undo_chain(self):
        hp = {"a": 100}

        def undo_provider(ev):
            if ev.kind != "damage":
                return None
            amt = ev.data["amount"]
            return lambda: hp.__setitem__("a", hp["a"] + amt)

        tl = Timeline()
        tl.set_undo_provider(undo_provider)
        for amt in (10, 20, 30):
            tl.commit(Event(kind="damage", data={"amount": amt}))
            hp["a"] -= amt
        assert hp["a"] == 40
        cancelled = tl.rewind(1)                          # откат к тику 1 (осталось 1 событие)
        assert cancelled == 2
        assert hp["a"] == 90                              # вернули 30 и 20
        assert tl.head == 0 and tl.tick == 1

    def test_rewind_irreversible_raises(self):
        tl = Timeline()
        tl.set_undo_provider(lambda ev: (lambda: None))
        tl.commit(Event(kind="wish", reversible=False))
        tl.commit(Event(kind="damage"))
        with pytest.raises(TimelineError):
            tl.rewind(0)

    def test_rewind_move_head_without_undo(self):
        tl = _tl(5)
        n = tl.rewind(2, use_undo=False)
        assert n == 3 and tl.head == 1 and tl.tick == 2
        assert len(tl.applied()) == 2

    def test_rewind_forward_rejected(self):
        tl = _tl(2)
        with pytest.raises(TimelineError):
            tl.rewind(99)

    def test_fast_forward(self):
        tl = _tl(4)
        tl.rewind(1, use_undo=False)
        moved = tl.fast_forward()
        assert moved == 3 and tl.head == 3 and tl.tick == 4


class TestForking:
    def test_fork_isolated(self):
        tl = _tl(3)
        br = tl.fork("branch")
        assert [e.id for e in br.applied()] == [0, 1, 2]
        br.commit(Event(kind="cast"))
        assert len(tl.events) == 3                        # родитель не изменился
        assert len(br.events) == 4
        assert br.tick == 4

    def test_duplicate_branch_name_raises(self):
        tl = _tl(1)
        tl.fork("x")
        with pytest.raises(TimelineError):
            tl.fork("x")

    def test_merge_back(self):
        tl = _tl(2)
        br = tl.fork("sim")
        br.commit(Event(kind="kill", target="boss"))
        moved = tl.merge_back(br)
        assert len(moved) == 1 and tl.query(kind="kill")

    def test_simulate_does_not_touch_parent(self):
        tl = _tl(2)
        sim = tl.simulate("contessa")
        sim.commit(Event(kind="damage", target="hero"))
        assert len(tl.events) == 2


class TestSerialization:
    def test_json_roundtrip(self):
        tl = _tl(3)
        tl.link_causal(tl.events[0], tl.events[1])
        tl.capture_snapshot(lambda: {"hp": 50})
        text = tl.to_json()
        tl2 = Timeline.from_json(text)
        assert [e.to_dict() for e in tl2.events] == [e.to_dict() for e in tl.events]
        assert tl2.head == tl.head and tl2.tick == tl.tick
        assert tl2.snapshots[3].state == {"hp": 50}

    def test_events_are_plain_json(self):
        tl = _tl(1)
        d = json.loads(tl.to_json())
        assert set(d["events"][0]) >= {"tick", "source", "target", "kind", "data"}


class TestEventSystemIntegration:
    def test_attach_records_bus_events(self):
        from src.core.event_system import EventSystem
        es = EventSystem()
        tl = Timeline()
        n = tl.attach_event_system(es, kinds=["damage"])
        assert n == 1
        assert es.emit("damage", {"source": "gojo", "target": "sukuna", "amount": 99})
        assert len(tl.events) == 1
        e = tl.events[0]
        assert e.kind == "es.damage" and e.source == "gojo" and e.target == "sukuna"
        assert e.data["amount"] == 99
        # журнал по-прежнему сериализуем
        assert Timeline.from_json(tl.to_json()).events[0].to_dict() == e.to_dict()

    def test_unsubscribed_kinds_not_recorded(self):
        from src.core.event_system import EventSystem
        es = EventSystem()
        tl = Timeline()
        tl.attach_event_system(es, kinds=["heal"])
        es.emit("damage", {"source": "a", "target": "b"})   # не подписаны
        assert tl.events == []
