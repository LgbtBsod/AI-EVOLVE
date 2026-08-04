"""
Core module initialization.
Exports main architecture components and utilities.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from .rng_manager import (
    RNGManager,
    RNGConfig,
    get_default_rng,
    set_default_rng,
    reset_default_rng,
)

__all__ = [
    'RNGManager',
    'RNGConfig',
    'get_default_rng',
    'set_default_rng',
    'reset_default_rng',
]

# Тесты для проекта "Эволюционная Адаптация: Генетический Резонанс"
