"""BasePlugin.update(): after too many consecutive errors, the plugin disables itself
(system_state -> ERROR) and stops calling update_logic, instead of failing silently forever."""

from src.core.architecture import LifecycleState
from src.core.base_plugin import BasePlugin


class _AlwaysFailsPlugin(BasePlugin):
    def __init__(self):
        super().__init__("always_fails")
        self.call_count = 0

    def update_logic(self, delta_time: float) -> None:
        self.call_count += 1
        raise RuntimeError("boom")


class _FlakyPlugin(BasePlugin):
    def __init__(self, fail_times: int):
        super().__init__("flaky")
        self.call_count = 0
        self.fail_times = fail_times

    def update_logic(self, delta_time: float) -> None:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise RuntimeError("transient")


def _running_plugin(plugin: BasePlugin) -> BasePlugin:
    plugin.system_state = LifecycleState.RUNNING
    return plugin


def test_plugin_disables_after_max_consecutive_errors():
    plugin = _running_plugin(_AlwaysFailsPlugin())

    for _ in range(plugin.MAX_CONSECUTIVE_ERRORS):
        plugin.update(0.1)

    assert plugin.system_state == LifecycleState.ERROR
    assert plugin.plugin_stats["errors_count"] == plugin.MAX_CONSECUTIVE_ERRORS
    assert plugin.call_count == plugin.MAX_CONSECUTIVE_ERRORS


def test_disabled_plugin_stops_calling_update_logic():
    plugin = _running_plugin(_AlwaysFailsPlugin())

    for _ in range(plugin.MAX_CONSECUTIVE_ERRORS):
        plugin.update(0.1)
    calls_at_disable = plugin.call_count

    # Further update() calls must be no-ops: no more silent failures forever.
    for _ in range(5):
        plugin.update(0.1)

    assert plugin.call_count == calls_at_disable
    assert plugin.plugin_stats["errors_count"] == calls_at_disable


def test_a_success_resets_the_consecutive_error_streak():
    plugin_threshold = BasePlugin.MAX_CONSECUTIVE_ERRORS - 1
    plugin = _running_plugin(_FlakyPlugin(fail_times=plugin_threshold))

    for _ in range(plugin_threshold):
        plugin.update(0.1)
    assert plugin.system_state == LifecycleState.RUNNING  # not yet disabled

    plugin.update(0.1)  # succeeds, resets the streak
    assert plugin.system_state == LifecycleState.RUNNING

    for _ in range(plugin_threshold):
        plugin.update(0.1)
    assert plugin.system_state == LifecycleState.RUNNING  # still not disabled: streak was reset

    plugin.update(0.1)
    plugin.update(0.1)
    assert plugin.system_state == LifecycleState.RUNNING
