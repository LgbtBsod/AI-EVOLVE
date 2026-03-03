from __future__ import annotations

from enum import Enum


class RelationshipType(Enum):
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    HOSTILE = "hostile"


class InteractionType(Enum):
    TALK = "talk"
    TRADE = "trade"
    HELP = "help"
