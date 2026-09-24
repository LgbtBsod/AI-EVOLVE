"""Общие фикстуры тестов.

Маркер `virtual_time`: тесты, которые ждут таймеры игры через time.sleep(),
идут без реальных пауз. `time` в модулях игры (src.*, main) и в модуле теста
подменяется ручными часами (tools/probe_runtime.py: ManualTime), где sleep(s)
мгновенно сдвигает time()/perf_counter() на s. Проверки тестов не меняются -
меняется только то, что ожидание больше не стоит реальных секунд.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def pytest_configure(config):
    config.addinivalue_line("markers", "virtual_time: game timers + time.sleep use an instant manual clock")


@pytest.fixture(autouse=True)
def _virtual_time(request):
    if request.node.get_closest_marker("virtual_time") is None:
        yield None
        return
    import probe_runtime

    clock = probe_runtime.ManualTime()
    patcher = probe_runtime.TimePatcher(clock).install()
    module = request.module
    real = getattr(module, "time", None)
    if real is probe_runtime._real_time:
        module.time = clock
    try:
        yield clock
    finally:
        if real is probe_runtime._real_time:
            module.time = real
        patcher.uninstall()
