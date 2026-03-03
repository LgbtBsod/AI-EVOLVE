"""Utilities for simple numeric stats aggregation."""
from __future__ import annotations

from typing import Dict, Iterable


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def average(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def merge_stats(base: Dict[str, float], updates: Dict[str, float]) -> Dict[str, float]:
    merged = dict(base)
    merged.update(updates)
    return merged
