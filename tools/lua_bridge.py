"""Алиас: модуль переехал в src/content/lua_bridge.py (игровой код). Здесь - для инструментов и тестов."""
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.content import lua_bridge as _real  # noqa: E402

sys.modules[__name__] = _real
