from __future__ import annotations

from enum import Enum


class TradeType(Enum):
    BUY = "buy"
    SELL = "sell"


class TradeStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CurrencyType(Enum):
    GOLD = "gold"


class TradeCategory(Enum):
    GENERAL = "general"
