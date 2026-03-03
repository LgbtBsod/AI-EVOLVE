from __future__ import annotations

from dataclasses import dataclass

from .trading_types import CurrencyType, TradeCategory, TradeStatus, TradeType


@dataclass
class TradeRecord:
    trade_type: TradeType
    status: TradeStatus
    category: TradeCategory = TradeCategory.GENERAL
    currency: CurrencyType = CurrencyType.GOLD
    amount: int = 0
