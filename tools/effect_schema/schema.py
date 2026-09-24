"""Алиас: модуль переехал в src/effects/schema.py (игровой код). Здесь - для инструментов и тестов."""
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.effects import schema as _real  # noqa: E402

sys.modules[__name__] = _real
