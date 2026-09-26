"""Row 6: per-instance namespace, isolated handler errors, unique ids."""
from src.core.event_system import EventSystem


def test_two_systems_do_not_share_handlers():
    a, b = EventSystem(), EventSystem()
    got = []
    a.on("ping", lambda s, e: got.append("a"), "ha")
    b.emit("ping", {})
    assert got == []
    a.emit("ping", {})
    assert got == ["a"]


def test_raising_handler_does_not_stop_others():
    es, got = EventSystem(), []

    def boom(s, e):
        raise RuntimeError("x")

    es.on("ev", boom, "boom")
    es.on("ev", lambda s, e: got.append(1), "ok")
    assert es.emit("ev", {}) is False       # failure visible to the caller, as before
    assert got == [1]
    assert es.get_stats()["events_failed"] == 1


def test_ids_unique_in_burst():
    es = EventSystem()
    for _ in range(200):
        es.emit("burst", {})
    ids = [e.event_id for e in es.get_event_history(limit=500)]
    assert len(ids) == len(set(ids)) == 200
