"""Тесты для модульной системы Dev Probe."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

# Добавить путь к модулям
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dev_probe.core.snapshot_manager import SnapshotManager
from dev_probe.core.event_tracker import EventTracker, EventType
from dev_probe.core.state_analyzer import StateAnalyzer, Anomaly
from dev_probe.plugins import ToughnessPlugin, EffectsPlugin, CombatPlugin


def test_snapshot_manager():
    """Тест SnapshotManager."""
    print("Testing SnapshotManager...")
    
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        manager = SnapshotManager(output_dir)
        
        # Сделать снимок
        state = {
            "entities": [
                {
                    "id": "player_1",
                    "health": 80,
                    "max_health": 100,
                    "position": {"x": 10, "y": 20},
                    "is_alive": True,
                    "effects": [
                        {
                            "id": "strength_buff",
                            "target": "STRENGTH",
                            "value": 15.0,
                            "duration": 300.0,
                            "remaining": 250.0,
                            "tags": ["BUFF"],
                            "stacks": 1,
                        }
                    ],
                    "toughness": {
                        "current": 50,
                        "max": 100,
                        "state": "NORMAL",
                        "recovery_timer": 0,
                        "break_count": 0,
                    }
                }
            ]
        }
        
        filepath = manager.take_snapshot(state, timestamp=1.5, frame=90)
        assert filepath.exists(), "Snapshot file should exist"
        
        # Проверка данных
        with open(filepath) as f:
            data = json.load(f)
            assert data["timestamp"] == 1.5
            assert data["frame"] == 90
            assert len(data["state"]["entities"]) == 1
        
        # Получить сводку
        summary = manager.get_summary()
        assert summary["total_snapshots"] == 1
        
        print("✓ SnapshotManager tests passed")


def test_event_tracker():
    """Тест EventTracker."""
    print("Testing EventTracker...")
    
    tracker = EventTracker()
    tracker.start_tracking()
    
    # Отследить события
    tracker.track_event(
        EventType.DAMAGE_DEALT,
        {"damage": 50, "is_critical": True},
        source_id="player_1",
        target_id="enemy_1"
    )
    
    tracker.track_event(
        EventType.TOUGHNESS_DAMAGE,
        {"toughness_damage": 30},
        source_id="player_1",
        target_id="enemy_1"
    )
    
    tracker.track_event(
        EventType.TOUGHNESS_BREAK,
        {"remaining_toughness": 0},
        source_id="player_1",
        target_id="enemy_1"
    )
    
    # Проверка статистики
    damage_stats = tracker.get_damage_stats()
    assert damage_stats["total_damage"] == 50
    assert damage_stats["hit_count"] == 1
    assert damage_stats["crit_count"] == 1
    
    toughness_stats = tracker.get_toughness_stats()
    assert toughness_stats["total_breaks"] == 1
    assert toughness_stats["total_toughness_damage"] == 30
    
    # Сводка
    summary = tracker.get_summary()
    assert summary["total_events"] == 3
    
    print("✓ EventTracker tests passed")


def test_state_analyzer():
    """Тест StateAnalyzer."""
    print("Testing StateAnalyzer...")
    
    analyzer = StateAnalyzer(config={"low_hp_threshold": 0.2})
    
    # Снапшот с низким HP
    snapshot = {
        "timestamp": 5.0,
        "frame": 300,
        "state": {
            "entities": [
                {
                    "id": "player_1",
                    "health": 15,
                    "max_health": 100,
                    "position": {"x": 10, "y": 10},
                    "is_alive": True,
                    "effects": [],
                },
                {
                    "id": "enemy_1",
                    "health": 0,
                    "max_health": 50,
                    "position": {"x": 20, "y": 20},
                    "is_alive": False,
                    "toughness": {
                        "current": -5,
                        "max": 100,
                        "state": "BROKEN",
                    }
                }
            ]
        }
    }
    
    anomalies = analyzer.analyze_snapshot(snapshot)
    
    # Должны быть аномалии
    assert len(anomalies) > 0
    
    anomaly_types = [a.anomaly_type for a in anomalies]
    assert "low_health" in anomaly_types or "negative_toughness" in anomaly_types
    
    print("✓ StateAnalyzer tests passed")


def test_toughness_plugin():
    """Тест плагина стойкости."""
    print("Testing ToughnessPlugin...")
    
    plugin = ToughnessPlugin()
    
    # Симуляция снапшота с пробитием
    snapshot_broken = {
        "timestamp": 10.0,
        "frame": 600,
        "state": {
            "entities": [
                {
                    "id": "boss_1",
                    "health": 5000,
                    "max_health": 10000,
                    "is_alive": True,
                    "toughness": {
                        "current": 0,
                        "max": 2500,  # Выросло после пробития
                        "state": "BROKEN",
                    }
                }
            ]
        }
    }
    
    # Перед пробитием
    snapshot_normal = {
        "timestamp": 9.0,
        "frame": 540,
        "state": {
            "entities": [
                {
                    "id": "boss_1",
                    "health": 5000,
                    "max_health": 10000,
                    "is_alive": True,
                    "toughness": {
                        "current": 0,
                        "max": 2300,  # Было меньше
                        "state": "BROKEN",
                    }
                }
            ]
        }
    }
    
    # Обработать оба снапшота
    plugin.on_snapshot(snapshot_normal)
    plugin.on_snapshot(snapshot_broken)
    
    # Проверка
    assert len(plugin.break_events) >= 1
    
    # Финиш
    report = plugin.on_finish()
    assert report.summary["total_breaks"] >= 1
    
    print("✓ ToughnessPlugin tests passed")


def test_effects_plugin():
    """Тест плагина эффектов."""
    print("Testing EffectsPlugin...")
    
    plugin = EffectsPlugin()
    
    # Симуляция снапшота с эффектами
    snapshot = {
        "timestamp": 2.0,
        "frame": 120,
        "state": {
            "entities": [
                {
                    "id": "enemy_1",
                    "health": 80,
                    "max_health": 100,
                    "is_alive": True,
                    "effects": [
                        {
                            "id": "poison_dot",
                            "tags": ["negative", "dot"],
                            "duration": 10.0,
                            "remaining": 8.0,
                        },
                        {
                            "id": "slow_debuff",
                            "tags": ["negative", "slow"],
                            "duration": 3.0,
                            "remaining": 2.5,
                        }
                    ]
                }
            ]
        }
    }
    
    result = plugin.on_snapshot(snapshot)
    
    assert result is not None
    assert result["total_active_effects"] == 2
    assert result["total_negative_effects"] == 2
    
    # Финиш
    report = plugin.on_finish()
    assert report.summary["total_effect_applications"] >= 1
    
    print("✓ EffectsPlugin tests passed")


def test_combat_plugin():
    """Тест плагина боя."""
    print("Testing CombatPlugin...")
    
    plugin = CombatPlugin()
    tracker = EventTracker()
    tracker.start_tracking()
    
    # Зарегистрировать обработчик
    def on_damage(event):
        plugin.on_event(event)
    
    tracker.register_handler(EventType.DAMAGE_DEALT, on_damage)
    
    # Симуляция урона
    tracker.track_event(
        EventType.DAMAGE_DEALT,
        {"damage": 75, "is_critical": False},
        source_id="player_1",
        target_id="enemy_1"
    )
    
    tracker.track_event(
        EventType.DAMAGE_DEALT,
        {"damage": 150, "is_critical": True},
        source_id="player_1",
        target_id="enemy_1"
    )
    
    # Проверка
    assert len(plugin.damage_events) == 2
    
    # Финиш
    report = plugin.on_finish()
    assert report.summary["total_damage"] == 225
    assert report.summary["total_hits"] == 2
    assert report.summary["total_crits"] == 1
    
    print("✓ CombatPlugin tests passed")


def run_all_tests():
    """Запустить все тесты."""
    print("=" * 60)
    print("DEV PROBE MODULE TESTS")
    print("=" * 60)
    
    tests = [
        test_snapshot_manager,
        test_event_tracker,
        test_state_analyzer,
        test_toughness_plugin,
        test_effects_plugin,
        test_combat_plugin,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
