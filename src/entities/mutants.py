"""Mutant entity model."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MutationType(Enum):
    PHYSICAL = "physical"
    MENTAL = "mental"


@dataclass
class Mutant:
    mutant_id: str
    level: int = 1
    mutation_type: MutationType = MutationType.PHYSICAL
