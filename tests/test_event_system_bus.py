"""Модульные тесты для src/core/event_system.py - шина событий на blinker."""
import pytest

from src.core.event_system import (
    EventData,
    EventPriority,
    EventState,
    EventSystem,
)


@pytest.fixture()
def bus():
    es = EventSystem(max_history_size=5)
    es.initialize()
    yield es
    es.shutdown()


class TestPubSub:
    def test_emit_delivers_event_to_handler(self, bus):
        got = []
        bus.on("game.hit", lambda sender, event: got.append(event.event_data))
        assert bus.emit("game.hit", {"dmg": 10}) is True
        assert got == [{"dmg": 10}]

    def test_handler_receives_sender_and_event_object(self, bus):
        seen = {}

        def handler(sender, event):
            seen["sender"] = sender
            seen["event"] = event

        bus.on("ui.click", handler, subscriber_id="hud")
        bus.emit("ui.click", {"x": 1}, source="player")
        assert isinstance(seen["event"], EventData)
        assert seen["event"].source == "player"
        assert seen["event"].event_type == "ui.click"

    def test_multiple_handlers_all_called(self, bus):
        calls = []
        bus.on("sys.tick", lambda s, e: calls.append("a"), subscriber_id="a")
        bus.on("sys.tick", lambda s, e: calls.append("b"), subscriber_id="b")
        bus.emit("sys.tick", {})
        assert sorted(calls) == ["a", "b"]

    def test_off_unsubscribes_by_id(self, bus):
        got = []
        bus.on("evt", lambda s, e: got.append(1), subscriber_id="h1")
        bus.off("evt", "h1")
        bus.emit("evt", {})
        assert got == []

    def test_off_only_target_subscriber(self, bus):
        got = []
        bus.on("evt", lambda s, e: got.append("keep"), subscriber_id="keep")
        bus.on("evt", lambda s, e: got.append("drop"), subscriber_id="drop")
        bus.off("evt", "drop")
        bus.emit("evt", {})
        assert got == ["keep"]

    def test_subscribe_unsubscribe_aliases(self, bus):
        got = []
        returned = bus.subscribe("alias.evt", lambda s, e: got.append(e.event_data))
        assert returned is bus  # chaining
        bus.emit("alias.evt", {"v": 2})
        assert got == [{"v": 2}]
        # unsubscribe - алиас для off(): отписка по subscriber_id (по умолчанию "unknown")
        bus.unsubscribe("alias.evt", "unknown")
        bus.emit("alias.evt", {"v": 3})
        assert got == [{"v": 2}]  # обработчик отключён
        assert bus.get_stats()["subscriptions_active"] == 0

    def test_error_in_handler_marks_failed_and_returns_false(self, bus):
        def boom(sender, event):
            raise RuntimeError("handler exploded")

        bus.on("bad.evt", boom, subscriber_id="crash")
        assert bus.emit("bad.evt", {}) is False
        stats = bus.get_stats()
        assert stats["events_failed"] == 1
        hist = bus.get_event_history("bad.evt")
        assert hist[-1].state == EventState.FAILED
        assert "handler exploded" in hist[-1].error_message


class TestStatsAndHistory:
    def test_stats_counters(self, bus):
        bus.on("s.evt", lambda s, e: None, subscriber_id="x")
        bus.emit("s.evt", {})
        bus.emit("s.evt", {})
        stats = bus.get_stats()
        assert stats["events_processed"] == 2
        assert stats["handlers_registered"] == 1
        assert stats["subscriptions_active"] == 1
        assert stats["is_running"] is True
        assert stats["history_size"] == 2

    def test_history_capped_at_max_size(self, bus):
        for i in range(10):
            bus.emit("cap.evt", {"i": i})
        hist = bus.get_event_history("cap.evt")
        assert len(hist) == 5                      # max_history_size=5
        assert [e.event_data["i"] for e in hist] == [5, 6, 7, 8, 9]  # старейшие вытеснены

    def test_history_filter_by_type_and_limit(self, bus):
        bus.on("mixed", lambda s, e: None)
        bus.emit("a.evt", {})
        bus.emit("b.evt", {})
        bus.emit("b.evt", {})
        only_b = bus.get_event_history("b.evt")
        assert len(only_b) == 2
        assert bus.get_event_history("b.evt", limit=1) == only_b[-1:]
        assert len(bus.get_event_history()) == 3   # без фильтра - всё

    def test_clear_history(self, bus):
        bus.emit("x.evt", {})
        assert bus.clear_history() is bus
        assert bus.get_event_history() == []

    def test_priority_recorded_in_event(self, bus):
        captured = {}
        bus.on("p.evt", lambda s, e: captured.update(prio=e.priority))
        bus.emit("p.evt", {}, priority=EventPriority.CRITICAL)
        assert captured["prio"] == EventPriority.CRITICAL

    def test_successful_event_state_completed(self, bus):
        bus.emit("ok.evt", {})
        assert bus.get_event_history("ok.evt")[-1].state == EventState.COMPLETED


class TestLifecycle:
    def test_initialize_shutdown_flags(self):
        es = EventSystem()
        assert es.initialize() is True
        assert es.get_stats()["is_running"] is True
        assert es.shutdown() is True
        assert es.get_stats()["is_running"] is False

    def test_start_stop_destroy_aliases(self, bus):
        assert bus.start() is True
        assert bus.stop() is True
        bus.start()
        assert bus.destroy() is True

    def test_update_is_noop(self, bus):
        assert bus.update(0.1) is None

    def test_process_events_compat_returns_zero(self, bus):
        bus.emit("q.evt", {})
        assert bus.process_events() == 0

    def test_shutdown_disconnects_handlers(self, bus):
        got = []
        bus.on("life.evt", lambda s, e: got.append(1))
        bus.shutdown()
        bus.emit("life.evt", {})
        assert got == []
