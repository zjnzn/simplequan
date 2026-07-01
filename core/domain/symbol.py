"""Symbol —— 币对市场信息（从交易所 load_markets() 同步）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Symbol:
    """币对市场信息。"""
    symbol: str = ""
    market: str = "spot"

    # 精度
    amount_precision: int = 8
    price_precision: int = 8

    # 限制
    min_amount: float = 0.0
    max_amount: float = 0.0
    min_cost: float = 0.0
    min_price: float = 0.0

    # 手续费
    maker_fee: float = 0.0
    taker_fee: float = 0.0

    # 合约特有（现货时为占位值）
    contract_size: float = 1.0
    settle: str = "USDT"
    is_linear: bool = True

    @classmethod
    def from_ccxt(cls, market_data: dict[str, Any], market: str = "spot") -> Symbol:
        """从 ccxt load_markets() 返回的 market dict 构建。"""
        precision = market_data.get("precision", {})
        limits = market_data.get("limits", {})
        amount_limits = limits.get("amount", {})
        cost_limits = limits.get("cost", {})
        price_limits = limits.get("price", {})
        fees = market_data.get("fees", {})
        trading_fees = fees.get("trading", {})

        return cls(
            symbol=market_data.get("symbol", ""),
            market=market,
            amount_precision=precision.get("amount", 8) or 8,
            price_precision=precision.get("price", 8) or 8,
            min_amount=amount_limits.get("min", 0.0) or 0.0,
            max_amount=amount_limits.get("max", 0.0) or 0.0,
            min_cost=cost_limits.get("min", 0.0) or 0.0,
            min_price=price_limits.get("min", 0.0) or 0.0,
            maker_fee=trading_fees.get("maker", 0.0) or 0.0,
            taker_fee=trading_fees.get("taker", 0.0) or 0.0,
            contract_size=market_data.get("contractSize", 1.0) or 1.0,
            settle=market_data.get("settle", "USDT") or "USDT",
            is_linear=market_data.get("linear", True) if market_data.get("linear") is not None else True,
        )
