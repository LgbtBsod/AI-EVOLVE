"""Lightweight performance manager."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PerformanceManager:
    frame_times: list[float] = field(default_factory=list)
    max_samples: int = 120

    def record_frame(self, delta_time: float) -> None:
        self.frame_times.append(delta_time)
        if len(self.frame_times) > self.max_samples:
            self.frame_times.pop(0)

    def average_fps(self) -> float:
        if not self.frame_times:
            return 0.0
        avg = sum(self.frame_times) / len(self.frame_times)
        return 0.0 if avg <= 0 else 1.0 / avg

    def stats(self) -> Dict[str, float]:
        return {"samples": float(len(self.frame_times)), "average_fps": self.average_fps(), "timestamp": time.time()}
