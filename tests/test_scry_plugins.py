"""
Comprehensive Unit Tests for New Dev Probe Plugins
Tests: TokenOptimizer, TestAccelerator, CombatAnalytics
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import time
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.event_system import EventSystem
from src.plugins.token_optimizer_plugin import TokenOptimizerPlugin
from src.plugins.test_accelerator_plugin import TestAcceleratorPlugin
from src.plugins.combat_analytics_plugin import CombatAnalyticsPlugin


class TestTokenOptimizerPlugin:
    """Тесты для плагина оптимизации токенов."""
    
    @pytest.fixture
    def event_system(self):
        return EventSystem()
    
    @pytest.fixture
    def plugin(self, event_system):
        return TokenOptimizerPlugin(event_system)
    
    def test_plugin_initialization(self, plugin):
        """Проверка инициализации плагина."""
        assert plugin.name == "TokenOptimizer"
        assert plugin.version == "1.0.0"
        assert plugin.state_cache == {}
        assert plugin.token_count_saved == 0
        
    def test_state_hash_generation(self, plugin):
        """Проверка генерации хэша состояния."""
        state1 = {"health": 100, "position": [0, 0, 0]}
        state2 = {"health": 100, "position": [0, 0, 0]}
        state3 = {"health": 90, "position": [0, 0, 0]}
        
        hash1 = plugin._generate_state_hash(state1)
        hash2 = plugin._generate_state_hash(state2)
        hash3 = plugin._generate_state_hash(state3)
        
        assert hash1 == hash2, "Одинаковые состояния должны иметь одинаковый хэш"
        assert hash1 != hash3, "Разные состояния должны иметь разный хэш"
        
    def test_state_hash_ignores_temporal_data(self, plugin):
        """Хэш не должен зависеть от временных данных."""
        state1 = {"health": 100, "timestamp": 1000}
        state2 = {"health": 100, "timestamp": 2000}
        
        hash1 = plugin._generate_state_hash(state1)
        hash2 = plugin._generate_state_hash(state2)
        
        assert hash1 == hash2, "Временные метки не должны влиять на хэш"
        
    def test_context_compression(self, plugin):
        """Проверка сжатия контекста."""
        long_history = [{"type": "idle", "frame": i} for i in range(20)]
        compressed = plugin._compress_context(long_history)
        
        # Сжатая версия должна быть короче
        assert len(compressed) < len(str(long_history))
        
    def test_context_compression_preserves_key_events(self, plugin):
        """Ключевые события должны сохраняться при сжатии."""
        history = [
            {"type": "start", "frame": 0},
            {"type": "idle", "frame": 1},
            {"type": "combat_start", "frame": 2},
            {"type": "idle", "frame": 3},
            {"type": "loot", "frame": 4},
            {"type": "idle", "frame": 5},
            {"type": "end", "frame": 6}
        ]
        compressed_str = plugin._compress_context(history)
        import json
        compressed = json.loads(compressed_str)
        
        types = [e['type'] for e in compressed]
        assert 'combat_start' in types
        assert 'loot' in types
        
    def test_cache_hit_detection(self, plugin, event_system):
        """Проверка обнаружения повторения состояния."""
        plugin.enable()
        
        state = {"health": 100, "action": "idle"}
        action = {"type": "wait", "duration": 1}
        
        # Сначала добавляем в кэш через экшен
        plugin.state_cache[plugin._generate_state_hash(state)] = action
        
        # Эмитим событие think_start
        result = {}
        def capture_result(sender, event):
            nonlocal result
            result = plugin._on_think_start(sender, event)
            
        event_system.subscribe("agent.think_start", capture_result)
        event_system.emit("agent.think_start", {"state": state})
        
        assert result is not None
        assert result.get("skip_thinking") == True
        assert result.get("cached_action") == action
        
        plugin.disable()
        
    def test_get_stats(self, plugin):
        """Проверка статистики плагина."""
        plugin.state_cache = {"hash1": {}, "hash2": {}}
        plugin.token_count_saved = 1000
        
        stats = plugin.get_stats()
        assert stats["cache_size"] == 2
        assert stats["tokens_saved_estimate"] == 1000


class TestTestAcceleratorPlugin:
    """Тесты для плагина ускорения тестов."""
    
    @pytest.fixture
    def event_system(self):
        return EventSystem()
    
    @pytest.fixture
    def plugin(self, event_system):
        return TestAcceleratorPlugin(event_system)
    
    def test_plugin_initialization(self, plugin):
        """Проверка инициализации."""
        assert plugin.name == "TestAccelerator"
        assert plugin.auto_fix_enabled == True
        assert plugin.idle_threshold == 5.0
        
    def test_auto_fix_critical_chance(self, plugin):
        """Автоматическое исправление шанса крита > 1."""
        bad_stats = {"critical_chance": 5.0, "health": 100}
        fixed = plugin.auto_fix_stats(bad_stats)
        
        assert fixed["critical_chance"] == 0.25
        assert fixed["health"] == 100
        
    def test_auto_fix_negative_health(self, plugin):
        """Автоматическое исправление отрицательного здоровья."""
        bad_stats = {"health": -50, "damage": 10}
        fixed = plugin.auto_fix_stats(bad_stats)
        
        assert fixed["health"] == 0
        assert fixed["damage"] == 10
        
    def test_auto_fix_disabled(self, plugin):
        """Проверка отключения авто-фикса."""
        plugin.auto_fix_enabled = False
        bad_stats = {"critical_chance": 5.0}
        fixed = plugin.auto_fix_stats(bad_stats)
        
        assert fixed["critical_chance"] == 5.0  # Не исправлено
        
    def test_idle_detection_and_force_combat(self, plugin, event_system):
        """Проверка форсирования боя при простое."""
        plugin.enable()
        plugin.last_action_time = time.time() - 10  # 10 секунд назад
        
        events_received = []
        def capture_spawn(sender, event):
            events_received.append(event.event_data if hasattr(event, 'event_data') else {})
            
        event_system.subscribe("world.spawn_enemy_nearby", capture_spawn)
        
        # Эмитим update
        event_system.emit("simulation.update", {"agent_id": "test_agent"})
        
        assert len(events_received) > 0
        assert events_received[0]["target_agent"] == "test_agent"
        assert events_received[0]["enemy_type"] == "slime"
        
        plugin.disable()
        
    def test_action_resets_timer(self, plugin):
        """Действие должно сбрасывать таймер бездействия."""
        initial_time = plugin.last_action_time
        time.sleep(0.1)
        
        # Создаем мок event объекта
        mock_event = Mock()
        mock_event.event_data = {}
        plugin._on_action(None, mock_event)
        
        assert plugin.last_action_time > initial_time
        
    def test_get_stats(self, plugin):
        """Проверка статистики."""
        plugin.events_forced = 5
        stats = plugin.get_stats()
        
        assert stats["events_forced"] == 5
        assert stats["auto_fix_enabled"] == True


class TestCombatAnalyticsPlugin:
    """Тесты для плагина аналитики боя."""
    
    @pytest.fixture
    def event_system(self):
        return EventSystem()
    
    @pytest.fixture
    def plugin(self, event_system):
        return CombatAnalyticsPlugin(event_system)
    
    def test_plugin_initialization(self, plugin):
        """Проверка инициализации."""
        assert plugin.name == "CombatAnalytics"
        assert plugin.damage_dealt_total == 0
        assert plugin.critical_hits_count == 0
        
    def test_combat_session_tracking(self, plugin, event_system):
        """Отслеживание боевых сессий."""
        plugin.enable()
        
        event_system.emit("combat.start", {"session_id": "battle_1", "timestamp": 100})
        event_system.emit("combat.end", {"timestamp": 200})
        
        assert len(plugin.combat_sessions) == 1
        assert plugin.combat_sessions[0]["id"] == "battle_1"
        assert plugin.combat_sessions[0]["ended"] == True
        
        plugin.disable()
        
    def test_damage_tracking(self, plugin, event_system):
        """Подсчет урона."""
        plugin.enable()
        
        event_system.emit("combat.start", {"session_id": "battle_1"})
        event_system.emit("combat.hit", {"damage": 10, "is_critical": False})
        event_system.emit("combat.hit", {"damage": 20, "is_critical": True})
        event_system.emit("combat.hit", {"damage": 5, "is_dodge": True})
        
        assert plugin.damage_dealt_total == 35
        assert plugin.critical_hits_count == 1
        assert plugin.dodges_count == 1
        
        plugin.disable()
        
    def test_crit_rate_anomaly_detection(self, plugin):
        """Обнаружение аномально высокого шанса крита."""
        session = {
            "id": "test",
            "damage_log": [
                {"damage": 10, "crit": True},
                {"damage": 10, "crit": True},
                {"damage": 10, "crit": True},
                {"damage": 10, "crit": False}
            ]
        }
        
        anomalies = plugin.analyze_session(session)
        
        assert any("CRIT_RATE_HIGH" in a for a in anomalies)
        
    def test_low_damage_anomaly_detection(self, plugin):
        """Обнаружение аномально низкого урона."""
        session = {
            "id": "test",
            "damage_log": [
                {"damage": 0.1, "crit": False},
                {"damage": 0.2, "crit": False},
                {"damage": 0.1, "crit": False}
            ]
        }
        
        anomalies = plugin.analyze_session(session)
        
        assert any("DAMAGE_TOO_LOW" in a for a in anomalies)
        
    def test_empty_session_analysis(self, plugin):
        """Анализ пустой сессии не должен вызывать ошибок."""
        session = {"id": "test", "damage_log": []}
        anomalies = plugin.analyze_session(session)
        
        assert anomalies == []
        
    def test_death_event_logging(self, plugin, event_system, caplog):
        """Логирование событий смерти."""
        import logging
        plugin.logger.setLevel(logging.INFO)
        plugin.enable()
        
        event_system.emit("entity.death", {"entity_id": "player", "killer_id": "enemy"})
        
        # Проверяем, что лог содержит информацию о смерти
        # (в реальном тесте можно проверить mock logger)
        
        plugin.disable()
        
    def test_get_stats(self, plugin):
        """Проверка статистики."""
        plugin.damage_dealt_total = 1000
        plugin.critical_hits_count = 50
        plugin.dodges_count = 20
        
        stats = plugin.get_stats()
        
        assert stats["total_damage"] == 1000
        assert stats["crit_count"] == 50
        assert stats["dodge_count"] == 20
        assert "tokens_saved" in stats  # Для совместимости


class TestPluginIntegration:
    """Интеграционные тесты всех плагинов вместе."""
    
    @pytest.fixture
    def event_system(self):
        return EventSystem()
    
    @pytest.fixture
    def plugins(self, event_system):
        token_opt = TokenOptimizerPlugin(event_system)
        test_acc = TestAcceleratorPlugin(event_system)
        combat_analytics = CombatAnalyticsPlugin(event_system)
        return [token_opt, test_acc, combat_analytics]
    
    def test_all_plugins_enable_disable(self, plugins):
        """Все плагины должны корректно включаться/выключаться."""
        for plugin in plugins:
            plugin.enable()
            assert plugin.enabled == True
            
        for plugin in plugins:
            plugin.disable()
            assert plugin.enabled == False
            
    def test_combined_workflow(self, event_system, plugins):
        """Сценарий: бой с оптимизацией и аналитикой."""
        # Включаем все плагины
        for p in plugins:
            p.enable()
            
        # Симуляция боя
        event_system.emit("combat.start", {"session_id": "int_test", "timestamp": 100})
        event_system.emit("combat.hit", {"damage": 15, "is_critical": True})
        event_system.emit("combat.hit", {"damage": 10, "is_critical": False})
        event_system.emit("combat.end", {"timestamp": 150})
        
        # Проверяем, что аналитика записала данные
        analytics = next(p for p in plugins if isinstance(p, CombatAnalyticsPlugin))
        assert analytics.damage_dealt_total == 25
        assert analytics.critical_hits_count == 1
        
        # Выключаем
        for p in plugins:
            p.disable()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
